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

# ---- 归因结果（接入 renderers/unresolved.py 用） ----
ATTR_SOURCE = "source"
ATTR_LIBRARY = "library"
ATTR_GPU_KERNEL = "gpu_kernel"
ATTR_MISSING = "missing"


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
                 gpu_blobs=None, notes=None, scanned_bytes=0, truncated=False):
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
        # 诚实记账：扫描被截断、字段存疑等
        self.notes = [] if notes is None else notes
        self.scanned_bytes = scanned_bytes
        self.truncated = truncated

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
            "notes": list(self.notes),
            "scanned_bytes": self.scanned_bytes,
            "truncated": self.truncated,
        }


# ---- 定长读取上限（黑帽 K1/K8）：单次 I/O 不得超过这个值 ----
MAX_CHUNK = 8 << 20
