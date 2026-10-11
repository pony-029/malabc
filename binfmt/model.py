"""binfmt 数据模型 —— 二进制分析的统一 IR。

三家容器（PE / ELF / Mach-O）解析出来的东西形状完全不同，这一层把它们压成
同一个形状，上层（归因、报告、CLI --json）就只认这一套：

    BinaryReport  (path, container, flavour, machine, bits, ...)
      ├─ sections:   [Section(name, vaddr, vsize, file_off, file_size,
      │                       kind, gpu_hint)]      ← PE 段与 ELF 节归一到这里
      ├─ symbols:    [Symbol(name, kind, source, from_lib, demangled)]
      │                 kind = export | import | dynamic | gpu_kernel
      ├─ dependencies: [Dependency(name, kind)]
      │                 kind = needed | import_module | rpath | runpath | link_flag
      │                        | load_dylib | id_dylib | load_dylinker  （R68：Mach-O）
      ├─ gpu:        GpuBlob(parseable, reason, kernels, backends, ...)
      └─ notes:      ["..."]      ← 所有「没看懂的东西」都写这里，不许静默

设计纪律（来自 R31 六帽分析的黑帽 K1/K2/K7/K8）：
  * 所有字段都要能序列化（JSON），因为要接入 renderers/ 与 CLI 的 --json。
  * **「不可解析」是一等状态**（GpuBlob.parseable / reason），不是异常。
  * **便宜判据与精确判据分字段命名**（suspect_code_objects vs kernels），不得混用
    —— 前者只是「数到了几个 \\x7fELF」，后者才是「真的认出了 kernel 名」。

为什么这里有手写类而不是 @dataclass（R62-R31f，一次真回归的反面教材）：
本模块初版用了 @dataclass，而 dataclasses 是 Python 3.7 标准库 —— 与本仓
「严格兼容 3.6.5、且零第三方依赖」的承诺直接冲突。实测证据：
    python matlabc.py binfmt --check-py36   ->   rc=1
    报 binfmt/model.py:11:1 dataclasses 标准库（需 Python 3.7）
现改为手写类：字段名、字段顺序、默认值、to_dict() 输出**逐字段保持一致**，
所以调用方（gpu/pe/elf/macho/attribute/report）一行都不用改；
Section 仍保留原 frozen=True 的只读语义（赋值抛 AttributeError）。

术语纪律：本模块用 kernel 指 GPU 算子，不用 operator/kind
（后者在本项目专指跨语言检测规则 _CROSS_LANG_KIND_META）。
"""

# ---- 容器类型 ----
CONTAINER_PE = "pe"
CONTAINER_ELF = "elf"
CONTAINER_MACHO = "macho"

# ---- 符号来源 ----
SOURCE_BINARY = "binary"

# ---- 符号 kind ----
SYM_EXPORT = "export"
SYM_IMPORT = "import"
SYM_DYNAMIC = "dynamic"
SYM_GPU_KERNEL = "gpu_kernel"

# ---- 依赖 kind ----
DEP_NEEDED = "needed"
DEP_IMPORT_MODULE = "import_module"
DEP_RPATH = "rpath"
DEP_RUNPATH = "runpath"
DEP_LINK_FLAG = "link_flag"
# ---- R68：Mach-O 的「依赖形态」单列 kind，不与 ELF/PE 混用一个名字 ----
# 为什么单列而不复用 DEP_NEEDED：三种容器的「我依赖谁」是**不同机制**
# （ELF 走 .dynamic 的 DT_NEEDED，PE 走导入表，Mach-O 走 LC_LOAD_DYLIB 一族），
# 报告里混成一个词会让人以为它们可互换。归因逻辑不依赖 kind，所以单列无代价。
DEP_LOAD_DYLIB = "load_dylib"          # LC_LOAD_DYLIB / _WEAK_ / _REEXPORT_ / _UPWARD_ / _LAZY_
DEP_ID_DYLIB = "id_dylib"              # LC_ID_DYLIB：库自己的 install name（身份，不是依赖）
DEP_LOAD_DYLINKER = "load_dylinker"    # LC_LOAD_DYLINKER（macOS 上通常是 /usr/lib/dyld）

# ---- 归因结果（接入 renderers/unresolved.py 用） ----
ATTR_SOURCE = "source"
ATTR_LIBRARY = "library"
ATTR_GPU_KERNEL = "gpu_kernel"
ATTR_MISSING = "missing"

# ---- R86：ELF 静态缓解措施（对标 REA `inspect_binary_layout` 的 mitigations） ----
# 三条纪律，与 verified/fixture_verified 是**同一条**：
#   * 整组读数一律标 evidence_kind="inferred" —— 它们是**静态推断**，
#     不是运行时保护，更不是「这个程序安全」的结论。
#   * **「没观测到」与「观测到且为否」必须分开**：`None` = 根本没读到判据构件
#     （例如程序头里没有 PT_GNU_STACK），与 `False` 是两句不同的话。
#     REA 原文（binary-diagnostics.md）："an absent canary symbol does not
#     prove every function unprotected."
#   * 每条读数都带 `basis`（来自哪个构件）与 `limitations`（它证明不了什么），
#     不许只给一个裸布尔。
EVIDENCE_INFERRED = "inferred"
MIT_PIE = "position_independent"
MIT_NX = "nx_indicator"
MIT_EXECSTACK = "executable_stack_indicator"
MIT_CANARY = "stack_canary_indicator"
MIT_RELRO = "relro"
RELRO_NONE = "none"
RELRO_PARTIAL = "partial"
RELRO_FULL = "full"

# ---- R86-2：PE 侧的缓解措施是**观测值**（observed），不是推断值 ----
# 与 ELF 的 inferred 是**两档不同的证据**，必须能分辨：
#   ELF：靠「有没有 PT_GNU_STACK / 有没有 __stack_chk_fail 符号」去**推** ⇒ inferred；
#   PE ：DllCharacteristics 与 LOAD_CONFIG 是**头部里直接写着**的字段 ⇒ observed。
# 两档都报，且**不许混** —— 把两者写成同一个词，等于把「读到的事实」和
# 「由读到的东西推出的话」混为一谈（R83 的定论：口径错了，所有读数一起错）。
#
# ⚠ 即便 observed，也仍是**构建期声明**而非运行时保护：
#   * 没声明 NX_COMPAT **不证明**运行时栈一定可执行（系统级强制可能仍生效）；
#   * 声明了 DYNAMIC_BASE 也可能被 COFF 的 RELOCS_STRIPPED 抵消。
#   两条都写进 limitations，不许只给一组漂亮的 yes/no。
EVIDENCE_OBSERVED = "observed"
MIT_ASLR = "dynamic_base"                    # DllCharacteristics & 0x0040
MIT_CFG = "control_flow_guard"               # DllCharacteristics & 0x4000
MIT_HIGH_ENTROPY_VA = "high_entropy_va"      # DllCharacteristics & 0x0020
MIT_SEH = "structured_exception_handling"    # NOT (DllCharacteristics & 0x0400)
MIT_FORCE_INTEGRITY = "force_integrity"      # DllCharacteristics & 0x0080
MIT_APPCONTAINER = "appcontainer"            # DllCharacteristics & 0x1000

# 程序段类型（只列本模块真的用到的；不解析 PT_LOAD 内容，只登记它的存在与权限）
PT_LOAD = 1
PT_INTERP = 3
PT_GNU_STACK = 0x6474E551
PT_GNU_RELRO = 0x6474E552
PT_TYPE_NAMES = {
    0: "PT_NULL", 1: "PT_LOAD", 2: "PT_DYNAMIC", 3: "PT_INTERP",
    4: "PT_NOTE", 6: "PT_PHDR", 7: "PT_TLS", 0x6474E550: "PT_GNU_EH_FRAME",
    PT_GNU_STACK: "PT_GNU_STACK", PT_GNU_RELRO: "PT_GNU_RELRO",
    0x6474E553: "PT_GNU_PROPERTY",
}
PF_X, PF_W, PF_R = 0x1, 0x2, 0x4


class Section(object):
    """容器的一个段/节。PE 的 section 与 ELF 的 section 都归一到这个形状。

    只读（等价于原来的 `@dataclass(frozen=True)`）：构造后任何赋值都抛
    `AttributeError`。构造一律用关键字传参，字段顺序与原 dataclass 相同。
    """

    __slots__ = ("name", "vaddr", "vsize", "file_off", "file_size",
                 "kind", "gpu_hint")

    def __init__(self, name, vaddr=0, vsize=0, file_off=0, file_size=0,
                 kind="", gpu_hint=""):
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "vaddr", vaddr)
        object.__setattr__(self, "vsize", vsize)
        object.__setattr__(self, "file_off", file_off)
        object.__setattr__(self, "file_size", file_size)
        object.__setattr__(self, "kind", kind)          # 原始语义标签
        object.__setattr__(self, "gpu_hint", gpu_hint)  # 命中的 GPU 段名（空=未命中）

    def __setattr__(self, key, value):
        raise AttributeError("Section 是只读对象（等价于 dataclass(frozen=True)）")

    def __delattr__(self, key):
        raise AttributeError("Section 是只读对象")

    def __repr__(self):
        return ("Section(name=%r, vaddr=%r, vsize=%r, file_off=%r, "
                "file_size=%r, kind=%r, gpu_hint=%r)"
                % (self.name, self.vaddr, self.vsize, self.file_off,
                   self.file_size, self.kind, self.gpu_hint))

    def to_dict(self):
        return {
            "name": self.name,
            "vaddr": self.vaddr,
            "vsize": self.vsize,
            "file_off": self.file_off,
            "file_size": self.file_size,
            "kind": self.kind,
            "gpu_hint": self.gpu_hint,
        }


class Segment(object):
    """ELF 程序段（PT_*）。R86 新增。

    为什么要有它：此前 `elf.py` 读了 `e_phoff/e_phnum` 却**从未使用** ——
    于是「这个文件怎么被加载」这件事在报告里是**空白**，而 NX / 可执行栈 /
    RELRO 三条判据的**唯一观测构件**恰好就是程序头里的 PT_GNU_STACK 与
    PT_GNU_RELRO。没有段表，缓解措施就只能靠猜 —— 而猜是禁止的。

    只读，字段与 REA `inspect_binary_layout` 的 `segments[]` 对齐（子集）。
    """

    __slots__ = ("index", "type", "flags", "offset", "vaddr", "filesz",
                 "memsz", "align")

    def __init__(self, index=0, type="", flags=0, offset=0, vaddr=0,
                 filesz=0, memsz=0, align=0):
        object.__setattr__(self, "index", index)
        object.__setattr__(self, "type", type)
        object.__setattr__(self, "flags", flags)
        object.__setattr__(self, "offset", offset)
        object.__setattr__(self, "vaddr", vaddr)
        object.__setattr__(self, "filesz", filesz)
        object.__setattr__(self, "memsz", memsz)
        object.__setattr__(self, "align", align)

    def __setattr__(self, key, value):
        raise AttributeError("Segment 是只读对象")

    def __delattr__(self, key):
        raise AttributeError("Segment 是只读对象")

    @property
    def perms(self):
        """rwx 三字符，未置位写 `-`。与 `readelf -l` 的 Flg 列同义。"""
        return ("r" if self.flags & PF_R else "-") + \
               ("w" if self.flags & PF_W else "-") + \
               ("x" if self.flags & PF_X else "-")

    def __repr__(self):
        return ("Segment(index=%r, type=%r, flags=%#x, offset=%#x, vaddr=%#x, "
                "filesz=%r, memsz=%r, align=%r)"
                % (self.index, self.type, self.flags, self.offset, self.vaddr,
                   self.filesz, self.memsz, self.align))

    def to_dict(self):
        return {
            "index": self.index,
            "type": self.type,
            "flags": self.flags,
            "perms": self.perms,
            "offset": self.offset,
            "vaddr": self.vaddr,
            "filesz": self.filesz,
            "memsz": self.memsz,
            "align": self.align,
        }


class Symbol(object):
    """归一化符号。source 固定为 binary（区别于源码侧符号，避免假匹配 K5）。"""

    def __init__(self, name, kind, origin="", address=0, section="",
                 backend="", demangled=""):
        self.name = name
        self.kind = kind
        self.origin = origin          # 容器路径
        self.address = address
        self.section = section
        self.backend = backend        # GPU kernel 才有：cuda / hip / vulkan
        self.demangled = demangled

    def __repr__(self):
        return ("Symbol(name=%r, kind=%r, origin=%r, address=%r, section=%r, "
                "backend=%r, demangled=%r)"
                % (self.name, self.kind, self.origin, self.address,
                   self.section, self.backend, self.demangled))

    def to_dict(self):
        return {
            "name": self.name,
            "kind": self.kind,
            "origin": self.origin,
            "address": self.address,
            "section": self.section,
            "backend": self.backend,
            "demangled": self.demangled,
            "source": SOURCE_BINARY,
        }


class Dependency(object):
    """动态依赖边。对应 ELF 的 DT_NEEDED 与 PE 的 Import Directory。"""

    def __init__(self, name, kind, origin="", resolved_path="", detail=""):
        self.name = name
        self.kind = kind
        self.origin = origin
        self.resolved_path = resolved_path
        self.detail = detail

    def __repr__(self):
        return ("Dependency(name=%r, kind=%r, origin=%r, resolved_path=%r, "
                "detail=%r)" % (self.name, self.kind, self.origin,
                                self.resolved_path, self.detail))

    def to_dict(self):
        return {
            "name": self.name,
            "kind": self.kind,
            "origin": self.origin,
            "resolved_path": self.resolved_path,
            "detail": self.detail,
        }


class GpuBlob(object):
    """一块 GPU 内容。

    parseable=False 时 kernels 必为空，且 reason 必须非空 —— 这是防静默的核心契约，
    由 tools/check_binfmt_fixtures.py 强制。

    构造签名与原 dataclass 一致（kernels/targets 由 `None` 触发建空列表，
    对应原来的 `field(default_factory=list)`）。
    """

    def __init__(self, backend="", section="", file_off=0, size=0,
                 parseable=False, reason="", kernels=None, targets=None,
                 ptx_version="", suspect_code_objects=0,
                 confidence_code_objects=0, index_entries=0, detected_by="",
                 truncated=False):
        self.backend = backend            # cuda / hip / vulkan / spirv
        self.section = section            # 命中所在的段名
        self.file_off = file_off          # 段在文件中的偏移
        self.size = size                  # 段大小
        self.parseable = parseable
        self.reason = reason
        self.kernels = [] if kernels is None else kernels
        self.targets = [] if targets is None else targets
        self.ptx_version = ptx_version
        # 便宜判据（\x7fELF 计数），不得混入 kernels
        self.suspect_code_objects = suspect_code_objects
        # 严格判据（e_ident[7]==ELFOSABI_CUDA / EM_AMDGPU）
        self.confidence_code_objects = confidence_code_objects
        # fatbin 索引表条目数（.nvFatBi/.hipFatB）：不是 code object 数，故分开记
        self.index_entries = index_entries
        self.detected_by = detected_by    # section_name / magic_scan
        self.truncated = truncated        # 扫描是否被 limit 截断（数字必须自带此标记）

    def __repr__(self):
        return ("GpuBlob(backend=%r, section=%r, size=%r, parseable=%r, "
                "kernels=%d, reason=%r)"
                % (self.backend, self.section, self.size, self.parseable,
                   len(self.kernels), self.reason))

    def to_dict(self):
        return {
            "backend": self.backend,
            "section": self.section,
            "file_off": self.file_off,
            "size": self.size,
            "parseable": self.parseable,
            "reason": self.reason,
            "kernels": list(self.kernels),
            "targets": list(self.targets),
            "ptx_version": self.ptx_version,
            "suspect_code_objects": self.suspect_code_objects,
            "confidence_code_objects": self.confidence_code_objects,
            "index_entries": self.index_entries,
            "detected_by": self.detected_by,
            "truncated": self.truncated,
        }


class BinaryReport(object):
    """一份二进制文件的完整分析结果。

    构造签名与原 dataclass 一致（列表字段由 `None` 触发建空列表）。
    """

    def __init__(self, path="", container="", arch="", bits=0, endian="",
                 flavour="", sections=None, symbols=None, dependencies=None,
                 gpu_blobs=None, notes=None, scanned_bytes=0, truncated=False,
                 verified=True, fixture_verified=True, segments=None,
                 mitigations=None):
        self.path = path
        self.container = container    # pe / elf / macho
        self.arch = arch              # x86_64 / aarch64 / amdgpu / cuda / unknown
        self.bits = bits
        self.endian = endian          # little / big
        self.flavour = flavour        # exe / dll / so / dylib / object / core / fat
        self.sections = [] if sections is None else sections
        self.symbols = [] if symbols is None else symbols
        self.dependencies = [] if dependencies is None else dependencies
        self.gpu_blobs = [] if gpu_blobs is None else gpu_blobs
        # R86：ELF 程序段（空 = 该容器无段表概念，或本文件里没读到）
        self.segments = [] if segments is None else segments
        # R86：静态缓解措施读数。`{}` = **未分析**（不是「全都没有」）——
        # 这两件事必须分开，否则「没看」会被读成「没有保护」。
        self.mitigations = {} if mitigations is None else mitigations
        # 诚实记账：扫描被截断、字段存疑等
        self.notes = [] if notes is None else notes
        self.scanned_bytes = scanned_bytes
        self.truncated = truncated
        # ---- 验证等级：**两条独立轴**，绝不合并成一个布尔 ----
        # verified        = 有**真实语料**（厂商真实文件）验证
        # fixture_verified= 有**合成夹具**验证
        # R33/C'5 先立了第一轴（PE/ELF=True，Mach-O=False），
        # R36/C''6 补第二轴：Mach-O 从此「有夹具验证但仍无真实语料」，报告措辞
        # 必须把两者分开写 —— 只写「未验证」会让人以为连夹具都没过。
        self.verified = verified
        self.fixture_verified = fixture_verified

    def __repr__(self):
        return ("BinaryReport(path=%r, container=%r, arch=%r, sections=%d, "
                "symbols=%d, dependencies=%d, gpu_blobs=%d)"
                % (self.path, self.container, self.arch, len(self.sections),
                   len(self.symbols), len(self.dependencies),
                   len(self.gpu_blobs)))

    @property
    def kernels(self):
        out = []
        for b in self.gpu_blobs:
            for k in b.kernels:
                out.append((b.backend, k))
        return out

    @property
    def export_names(self):
        return [s.name for s in self.symbols if s.kind == SYM_EXPORT]

    def to_dict(self):
        return {
            "path": self.path,
            "container": self.container,
            "arch": self.arch,
            "bits": self.bits,
            "endian": self.endian,
            "flavour": self.flavour,
            "sections": [s.to_dict() for s in self.sections],
            "symbols": [s.to_dict() for s in self.symbols],
            "dependencies": [d.to_dict() for d in self.dependencies],
            "gpu_blobs": [b.to_dict() for b in self.gpu_blobs],
            "segments": [s.to_dict() for s in self.segments],
            "mitigations": dict(self.mitigations),
            "notes": list(self.notes),
            "scanned_bytes": self.scanned_bytes,
            "truncated": self.truncated,
            "verified": self.verified,
            "fixture_verified": self.fixture_verified,
        }


# ---- 定长读取上限（黑帽 K1/K8）：单次 I/O 不得超过这个值 ----
MAX_CHUNK = 8 << 20
