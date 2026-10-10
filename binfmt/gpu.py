"""GPU 内容定位与提取（CUDA fatbin/cubin / PTX / AMD HSACO / Vulkan SPIR-V）。

要回答的问题：**一个 .dll / .so 里到底藏着哪些 GPU 算子？**
难点在于「藏」——三家厂商把自己的 GPU 代码放进容器里的方式各不相同，而且
PE 段名还会被硬截断。所以这里不猜，全部依据来自 R31 隔离探针在真实文件上的实测
（docs/analysis/ANALYSIS_2026-10-08_BINARY_GPU_INTEGRATION.md 附录 A/B）。

双策略：先认「专用段名」，认不到再靠「魔数扫描」兜底 —— 缺一不可。

    容器文件（.dll/.so/.dylib）
        │
        ├─① 看段名 ──────────────────────────────────────────────┐
        │     .nv_fatb / .nvFatBi   → CUDA                       │  1 命中即定位
        │     .hip_fat / .hipFatB   → AMD HIP                    │
        │     （Vulkan **没有专用段**，SPIR-V 躲在 .rdata）       │
        │                                                        │
        └─② 段名不认 → 魔数扫描兜底 ─────────────────────────────┤
              0xba55ed50 (50 ed 55 ba) → CUDA fatbin wrapper     │
              0x07230203 (03 02 23 07) → SPIR-V module           │
                                                                 │
        ─────────────────────────────────────────────────────────┘
        │
        ▼ 提取 kernel 名（三条路径，按可靠性排序）
        ┌──────────────────────────────────────────────────────────┐
        │ 主力  扫 cubin 节名表里的 ".text._Z..."（见 F9）           │
        │         实测：cublas64_12 → 171 个；cublasLt64_12 → 59 个 │
        │         ggml-cuda.dll → 0 个（该段整体不可解析，见 F7）    │
        │ 备用  SPIR-V 的 OpEntryPoint（opcode 15）                 │
        │ 备用  PTX 明文 ".entry <ident>("（必须后随左括号，见 F10）  │
        └──────────────────────────────────────────────────────────┘
        │
        ▼
    GpuBlob（parseable / reason / kernels / suspect_code_objects / ...）

实测事实（**改动前请先重跑探针验证，不要凭直觉改**）：

  F1  PE 段名被 8 字节硬截断，三家厂商各不相同：
        CUDA   → .nv_fatb / .nvFatBi    （原始意图 .nv_fatbin / .nvFatBin）
        HIP    → .hip_fat / .hipFatB    （原始意图 .hip_fatbin / .hipFatBin）
        Vulkan → 无专用段，SPIR-V 躲在 .rdata
  F2  fatbin wrapper magic = 0xba55ed50（.nv_fatb 段起始 4 字节）
  F3  .nvFatBi 条目定长 24B，条目 magic = 0x466243b1
  F4  CUDA cubin **不是**标准 ELF（e_type=0x8000、e_machine=0x100、e_shoff 落哨兵）
      ⇒ 「数 \\x7fELF」只是便宜判据；可信判据必须含 e_ident[7]==0x33
  F5  PTX 明文存在，但「先定位块首再解析 .entry」是错的（块首 4096B 内 0 命中）
  F6  SPIR-V 是二进制，OpEntryPoint 是 opcode 15，**文本搜索无效**
  F7  存在「段很大但内容不可解析」的情形：
        ggml-cuda.dll 的 .nv_fatb 334.9 MB，7 类探针全 0 命中
        ⇒ parseable=False + reason 是**一等状态**，不得静默返回 0 kernel
  F9（本轮最重要的发现）
      CUDA 的 kernel 名**不在** PTX 明文里，而在 cubin 的**节名表**里，形如
      ".text._ZN6cublas19splitKreduce_kernelI..."。⇒ 主力路径是扫 ".text._Z"
      字符串，不需要反序列化 cubin 结构（与「拒绝完整解析 fatbin」的约束相容）。
  F10 PTX 真 entry 的形态是 ".entry <ident>("（**后面紧跟左括号**）。
      347 个 ".visible .entry " 命中里只有 1 个满足此形态 ⇒ 判据必须含「后随 (」。

判据命名纪律：`suspect_code_objects`（便宜：数 \\x7fELF）与 `kernels`（精确：
节名表里的 ".text._Z"）**分字段**，绝不互相冒充。
"""
import io
import struct

from .model import MAX_CHUNK, GpuBlob, SYM_GPU_KERNEL, Symbol

# ---- 实测魔数（不要改成"文档里的值"）----
CUDA_FATBIN_MAGIC = b"\x50\xed\x55\xba"      # 0xba55ed50
FATBIN_ENTRY_MAGIC = b"\xb1\x43\x62\x46"     # 0x466243b1
SPIRV_MAGIC = b"\x03\x02\x23\x07"            # 0x07230203
ELF_MAGIC = b"\x7fELF"

# 主力：cubin 节名表里的 kernel 节（F9）
KERNEL_SECTION_PREFIX = b".text."
KERNEL_MANGLED_MARKER = b".text._Z"
PTX_ENTRY_MARKER = b".entry "

ELFOSABI_CUDA = 51
ELFOSABI_AMDGPU_HSA = 64
EM_CUDA = 190
EM_AMDGPU = 224

SECTION_HINTS = {
    ".nv_fatb": ("cuda", "fatbin"),
    ".nvFatBi": ("cuda", "fatbin_index"),
    ".hip_fat": ("hip", "fatbin"),
    ".hipFatB": ("hip", "fatbin_index"),
    ".nv_fatbin": ("cuda", "fatbin"),
    ".nvFatBin": ("cuda", "fatbin_index"),
    ".hip_fatbin": ("hip", "fatbin"),
    ".hipFatBin": ("hip", "fatbin_index"),
    "__nv_fatbin": ("cuda", "fatbin"),
    "__hip_fatbin": ("hip", "fatbin"),
}

DEFAULT_SCAN_CAP = 64 << 20

# R71：fat（universal）的段名带 `slice[i]:` 前缀 —— 同一个 `__TEXT` 在两个架构
# 切片里都出现，不打前缀就分不开（见 macho.py 的 `_FatMerge`）。提示表是按**精确**
# 段名查的，所以查表前必须先把前缀剥掉；剥法是**一处实现**（下面这个函数），
# 免得 `analyze()` 与 `_magic_fallback()` 各写一份而慢慢分叉。
_FAT_SLICE_PREFIX = "slice["


def section_base_name(name):
    """剥掉 fat 的 `slice[i]:` 前缀；没有前缀时**原样返回**。

    前缀只由 macho.py 的 `_FatMerge` 生成，形如 `slice[0]:__TEXT,__text`。
    不是这个形状（例如 ELF 段名叫 `.nv_fatb`）时一个字节都不动。
    """
    if name.startswith(_FAT_SLICE_PREFIX):
        i = name.find("]:")
        if i > 0:
            return name[i + 2:]
    return name

IDENT_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$.@"
)
WHITESPACE = (b" ", b"\t")

MAX_KERNELS = 20000
MAX_CODE_OBJECTS = 100000
MAX_SPIRV_WORDS = 1 << 16
MAX_SPIRV_MODULES = 2048


def _scan_all(f, off, size, needle, cap=None, limit=None):
    """在 [off, off+size) 内找 needle 的所有绝对偏移。

    分块 + 重叠：每块读 step+n-1 字节，只接受起点落在 [base, base+step) 的匹配，
    因此既不漏跨块匹配、也不重复计数。

    返回 (offsets, truncated)。truncated 表示因 limit 提前终止 ——
    调用方**必须**把它记进报告（探针 6 的教训：限额输出不标注会误导读者）。
    """
    if size <= 0:
        return [], False
    if cap is not None and cap >= 0:
        size = min(size, cap)
    n = len(needle)
    out = []
    step = MAX_CHUNK
    base = off
    end = off + size
    while base < end:
        take = min(step + n - 1, end - base)
        if take <= 0:
            break
        f.seek(base)
        buf = f.read(take)
        if not buf:
            break
        i = 0
        while True:
            i = buf.find(needle, i)
            if i < 0:
                break
            if base + i < end:
                if limit is not None and len(out) >= limit:
                    return out, True
                out.append(base + i)
            i += 1
        if take <= n - 1:
            break
        base += step
    return out, False


def _read_cstr_at(f, off, limit=256):
    """读节名表里的一个名字。

    实测（R31 自检）：节名表的边界并不总是干净的 NUL —— 有的名字后面
    直接跟控制字节（如 "..._Lb0E\\x04"）。因此遇到「非标识符字符」即视为
    名字结束，而不是死等 NUL：宁可比真实名短一点，也不要带控制字符。
    """
    f.seek(off)
    buf = f.read(limit)
    out = []
    for b in buf:
        if b == 0:
            break
        ch = chr(b)
        if ch not in IDENT_CHARS:
            break
        out.append(ch)
    return "".join(out)


def _read_ident(f, off, maxlen=192):
    f.seek(off)
    buf = f.read(maxlen)
    out = []
    for b in buf:
        ch = chr(b)
        if ch in IDENT_CHARS:
            out.append(ch)
        else:
            break
    return "".join(out)


def demangle_itanium(name):
    """Itanium C++ ABI 的**部分**解码：只求名字可读，不追求完整。

    处理：
        _ZN<len>A<len>B E      → A::B
        _Z<len>F I ... E       → F<...>      （模板参数不求值）
    实测样例：
        _ZN15xmma__5x_cublas4gemm23cuda_reorder_awq_weightENS0_18R
            → xmma__5x_cublas::gemm::cuda_reorder_awq_weight
        _Z25batch_gemm_kernel1x1_coreI7double2S0_S0_Lb0ELb1
            → batch_gemm_kernel1x1_core<...>

    解不出来就返回 ""（调用方保留原始名，不丢信息）。
    """
    if not name.startswith("_Z"):
        return ""
    i = 2
    parts = []
    nested = False
    if i < len(name) and name[i] == "N":
        nested = True
        i += 1
    while i < len(name):
        if nested and name[i] == "E":
            i += 1
            break
        if name[i] == "I":
            break
        j = i
        while j < len(name) and name[j].isdigit():
            j += 1
        if j == i:
            break
        try:
            ln = int(name[i:j])
        except ValueError:
            break
        if ln <= 0 or j + ln > len(name):
            break
        parts.append(name[j:j + ln])
        i = j + ln
    if not parts:
        return ""
    out = "::".join(parts)
    if i < len(name) and name[i] == "I":
        out += "<...>"
    return out


def analyze(rep, path, scan_cap=DEFAULT_SCAN_CAP):
    """在已解析的容器结果上做 GPU 定位与提取，原地填充 rep.gpu_blobs。"""
    f = io.open(path, "rb")
    try:
        hinted = []
        for s in rep.sections:
            hint = SECTION_HINTS.get(section_base_name(s.name))
            if hint:
                hinted.append((s, hint[0], hint[1]))
        budget = [scan_cap]

        if hinted:
            for s, backend, role in hinted:
                if role == "fatbin_index":
                    rep.gpu_blobs.append(_analyze_index(f, s, backend, budget))
                else:
                    rep.gpu_blobs.append(_analyze_fatbin(f, s, backend, budget))
            if scan_cap is not None and scan_cap >= 0 and budget[0] <= 0:
                rep.notes.append(
                    "binfmt: GPU 扫描预算 %d 字节已耗尽，后续段未扫描"
                    "（用 --binfmt-scan-cap 0 取消限制）" % scan_cap)
        else:
            blob = _magic_fallback(f, rep, budget)
            if blob is not None:
                rep.gpu_blobs.append(blob)
            elif rep.sections:
                rep.notes.append(
                    "binfmt: 未命中任何 GPU 段名，且 magic 扫描未发现 GPU 内容")
            else:
                rep.notes.append("binfmt: 容器无可用段表，无法定位 GPU 内容")
        _harvest_kernel_symbols(rep)
        return rep
    finally:
        f.close()


def _take(budget, amount):
    cap = budget[0]
    if cap is None or cap < 0:
        return amount
    if cap <= 0:
        return 0
    got = min(cap, amount)
    budget[0] = cap - got
    return got


def _analyze_index(f, sec, backend, budget):
    """fatbin 索引表（.nvFatBi / .hipFatB）：报告条目数，不做 kernel 提取。"""
    blob = GpuBlob(backend=backend, section=sec.name, file_off=sec.file_off,
                   size=sec.file_size, detected_by="section_name")
    allow = _take(budget, sec.file_size)
    if allow <= 0 and sec.file_size > 0:
        blob.reason = "扫描预算不足，索引表未读取"
        return blob
    offs, trunc = _scan_all(f, sec.file_off, sec.file_size, FATBIN_ENTRY_MAGIC,
                            cap=allow)
    blob.index_entries = len(offs)
    blob.truncated = trunc
    blob.parseable = len(offs) > 0
    if offs:
        f.seek(offs[0] + 8)
        raw = f.read(8)
        if len(raw) == 8:
            blob.targets.append("entry_stride=24 first_va=0x%x"
                                % struct.unpack("<Q", raw)[0])
    else:
        blob.reason = "索引段内未找到 0x466243b1 条目魔数"
    return blob


def _analyze_fatbin(f, sec, backend, budget):
    """fatbin 主体段：识别 wrapper 魔数 + 提取 kernel。"""
    blob = GpuBlob(backend=backend, section=sec.name, file_off=sec.file_off,
                   size=sec.file_size, detected_by="section_name")
    allow = _take(budget, sec.file_size)
    if allow <= 0 and sec.file_size > 0:
        blob.reason = ("扫描预算不足（--binfmt-scan-cap），未读取段内容；"
                       "该段大小 %d 字节" % sec.file_size)
        return blob

    f.seek(sec.file_off)
    head = f.read(16)
    if head[:4] == CUDA_FATBIN_MAGIC and len(head) >= 16:
        blob.targets.append("fatbin_header_size=%d"
                            % struct.unpack_from("<I", head, 8)[0])

    if backend == "cuda":
        _extract_cuda(f, sec, blob, allow)
    elif backend == "hip":
        _extract_hip(f, sec, blob, allow)
    else:
        blob.reason = "未知 GPU 后端 %s" % backend
        return blob

    # parseable 的契约（修 R31 自检发现的缺陷 1）：
    #   必须真的提取到内容（kernel 名 或 可信 code object），
    #   而不是"看到了 wrapper 头" —— 后者会让 ggml-cuda 的 334MB 空段撒谎。
    blob.parseable = bool(blob.kernels) or blob.confidence_code_objects > 0
    if not blob.parseable and not blob.reason:
        blob.reason = ("段内未发现可提取内容：无 \".text._Z\" cubin 节名表、"
                       "无 PTX entry、无 ELFOSABI_CUDA 可信 code object。"
                       "该段大小 %d 字节、已扫描 %d 字节 —— "
                       "内容可能被压缩或采用异构布局" % (sec.file_size, allow))
    return blob


def _extract_cuda(f, sec, blob, allow):
    """CUDA：cubin 节名表（主力）+ PTX entry（严格判据）+ code object 计数。"""
    names = {}

    # 主力路径（F9）：cubin 节名表的 ".text.<mangled>"
    offs, trunc = _scan_all(f, sec.file_off, sec.file_size, KERNEL_MANGLED_MARKER,
                            cap=allow, limit=MAX_KERNELS)
    blob.truncated = blob.truncated or trunc
    for a in offs:
        nm = _read_cstr_at(f, a + len(KERNEL_SECTION_PREFIX), 256)
        if nm:
            names[nm] = names.get(nm, 0) + 1
    if names:
        blob.targets.append("cubin_section_kernels=%d uniq=%d"
                            % (sum(names.values()), len(names)))
        # 诚实记账：节名表里的 mangled 名实测可能带 1-2 个尾随字节
        # （如 "...IT_T0_EQ" 的尾部 Q）。名字主体足够用于归属，但不宣称逐字节精确。
        dm_ok = sum(1 for n in names if demangle_itanium(n))
        blob.targets.append("demangle_ok=%d/%d" % (dm_ok, len(names)))
        trail = sum(1 for n in names if n and n[-1] in "QRIP")
        if trail:
            blob.targets.append("names_with_suspect_tail=%d "
                                "(节名表边界未精确判定，尾部可能有额外字节)" % trail)
    if trunc:
        blob.targets.append("cubin_section_scan=TRUNCATED at %d" % MAX_KERNELS)
    for nm in sorted(names):
        blob.kernels.append(nm)

    # PTX 路径（F5/F10）：不要先定位块首；判据含「后随 (」
    ptx_offs, ptx_trunc = _scan_all(f, sec.file_off, sec.file_size, PTX_ENTRY_MARKER,
                                    cap=allow, limit=MAX_KERNELS)
    blob.truncated = blob.truncated or ptx_trunc
    ptx_hits = 0
    ptx_ok = 0
    for a in ptx_offs:
        ptx_hits += 1
        start = a + len(PTX_ENTRY_MARKER)
        nm = _read_ident(f, start)
        if not nm:
            continue
        f.seek(start + len(nm))
        nxt = f.read(1)
        g = 0
        while nxt in WHITESPACE and g < 4:
            nxt = f.read(1)
            g += 1
        if nxt != b"(":
            continue
        ptx_ok += 1
        if nm not in names:
            names[nm] = 1
            blob.kernels.append(nm)
    if ptx_hits:
        blob.targets.append("ptx_entry_candidates=%d strict_ok=%d"
                            % (ptx_hits, ptx_ok))

    blob.targets.extend(_cuda_targets(f, sec, allow))

    # code object 计数：便宜判据与严格判据分列（F4）
    elf_offs, _ = _scan_all(f, sec.file_off, sec.file_size, ELF_MAGIC, cap=allow,
                            limit=MAX_CODE_OBJECTS)
    blob.suspect_code_objects = len(elf_offs)
    conf = 0
    for o in elf_offs:
        f.seek(o)
        b = f.read(20)
        if len(b) >= 20 and b[7] == ELFOSABI_CUDA:
            conf += 1
    blob.confidence_code_objects = conf


def _cuda_targets(f, sec, allow):
    out = []
    vers, _ = _scan_all(f, sec.file_off, sec.file_size, b".version ", cap=allow,
                        limit=64)
    for a in vers:
        f.seek(a + len(b".version "))
        t = f.read(16).split(b"\n")[0].decode("ascii", "replace").strip()
        if t and ("ptx_version=" + t) not in out:
            out.append("ptx_version=" + t)
    tgts, _ = _scan_all(f, sec.file_off, sec.file_size, b".target ", cap=allow,
                        limit=128)
    for a in tgts:
        f.seek(a + len(b".target "))
        t = f.read(24).split(b"\n")[0].decode("ascii", "replace").strip()
        if t and ("target=" + t) not in out:
            out.append("target=" + t)
    return out


def _extract_hip(f, sec, blob, allow):
    """AMD：.hip_fat 内是 HSA code object（ELFOSABI_AMDGPU_HSA / EM_AMDGPU）。"""
    # HIP 的 kernel 名同样在节名表，但实测本机样本以 ".text" 之外的形式出现；
    # 先尝试同一路径，拿不到不猜。
    offs, trunc = _scan_all(f, sec.file_off, sec.file_size, KERNEL_MANGLED_MARKER,
                            cap=allow, limit=MAX_KERNELS)
    blob.truncated = blob.truncated or trunc
    names = set()
    for a in offs:
        nm = _read_cstr_at(f, a + len(KERNEL_SECTION_PREFIX), 256)
        if nm:
            names.add(nm)
    for nm in sorted(names):
        blob.kernels.append(nm)
    if names:
        blob.targets.append("section_kernels=%d" % len(names))

    elf_offs, _ = _scan_all(f, sec.file_off, sec.file_size, ELF_MAGIC, cap=allow,
                            limit=MAX_CODE_OBJECTS)
    blob.suspect_code_objects = len(elf_offs)
    conf = 0
    for o in elf_offs:
        f.seek(o)
        b = f.read(20)
        if len(b) < 20:
            continue
        osabi = b[7]
        e_machine = struct.unpack_from("<H", b, 18)[0]
        if osabi == ELFOSABI_AMDGPU_HSA or e_machine == EM_AMDGPU:
            conf += 1
            if conf == 1:
                blob.targets.append("first_hsa_osabi=%d e_machine=%d"
                                    % (osabi, e_machine))
    blob.confidence_code_objects = conf
    desc, _ = _scan_all(f, sec.file_off, sec.file_size, b".kd", cap=allow, limit=8)
    if desc:
        blob.targets.append("kernel_descriptor_marker=.kd x%d" % len(desc))


def _magic_fallback(f, rep, budget):
    """没有 GPU 段名时的兜底：扫可读数据段找 SPIR-V / fatbin 魔数。

    典型场景：ggml-vulkan.dll —— SPIR-V 全躲在 .rdata，无任何专用段名。
    """
    cand = []
    for s in rep.sections:
        if s.file_size <= 0:
            continue
        base = section_base_name(s.name)
        if (s.kind and "data" in s.kind) or base.startswith((".rdata", ".rodata",
                                                            ".data")):
            cand.append(s)
    if not cand:
        return None
    spv_offs = []
    fat_offs = []
    for s in cand:
        allow = _take(budget, s.file_size)
        if allow <= 0:
            rep.notes.append("binfmt: magic 兜底扫描预算耗尽于段 %s" % s.name)
            break
        got, _ = _scan_all(f, s.file_off, s.file_size, SPIRV_MAGIC, cap=allow,
                           limit=MAX_SPIRV_MODULES)
        spv_offs.extend(got)
        got2, _ = _scan_all(f, s.file_off, s.file_size, CUDA_FATBIN_MAGIC,
                            cap=allow, limit=16)
        fat_offs.extend(got2)
    if not spv_offs and not fat_offs:
        return None
    blob = GpuBlob(detected_by="magic_scan", section="<multiple>",
                   file_off=spv_offs[0] if spv_offs else fat_offs[0], size=0)
    if fat_offs:
        blob.backend = "cuda"
        blob.suspect_code_objects = len(fat_offs)
        blob.targets.append("fatbin_magic_x%d" % len(fat_offs))
    if spv_offs:
        if not fat_offs:
            blob.backend = "vulkan"
        kernels, models, trunc = _spirv_entry_points(f, spv_offs)
        # 去重：Vulkan 的 GLCompute shader 入口点大量重名（实测 1477 个模块
        # 全叫 "main"），不去重会让 kernels 计数变成「模块数」而非「算子数」，
        # 属于用便宜数字冒充结论。模块数单独记在 targets 里。
        uniq = []
        seen = set()
        for k in kernels:
            if k not in seen:
                seen.add(k)
                uniq.append(k)
        blob.kernels = uniq
        blob.truncated = blob.truncated or trunc
        blob.suspect_code_objects = max(blob.suspect_code_objects, len(spv_offs))
        blob.targets.append("spirv_modules=%d spirv_unique_kernel_names=%d"
                            % (len(spv_offs), len(uniq)))
        blob.targets.extend(models[:32])
        if len(spv_offs) >= MAX_SPIRV_MODULES:
            blob.targets.append("spirv_scan=TRUNCATED at %d modules"
                                % MAX_SPIRV_MODULES)
    blob.parseable = bool(blob.kernels or blob.targets)
    if not blob.parseable:
        blob.reason = "magic 命中但无可解析内容"
    return blob


EXEC_MODELS = {
    0: "Vertex", 1: "TessellationControl", 2: "TessellationEvaluation",
    3: "Geometry", 4: "Fragment", 5: "GLCompute", 6: "Kernel",
}


def _spirv_entry_points(f, offsets):
    """解析 SPIR-V 指令流提取 OpEntryPoint（op=15）。

    实测布局（probe_r6 证实）：
        word[0] = (wc<<16) | 15
        word[1] = ExecutionModel          (5 = GLCompute)
        word[2] = EntryPoint <id>         ← 是 id，不是名字！
        word[3..] = Name（null-terminated 字面串）
        ...
    R31 第一版实现从 word[2] 读名字，于是提出的是 id 的低字节（控制字符）。
    另：内层遇到 \\0 后必须跳出外层循环（否则读入垃圾，探针也抓出过）。
    """
    kernels = []
    models = []
    OP_ENTRY_POINT = 15
    truncated = False
    for off in offsets[:MAX_SPIRV_MODULES]:
        f.seek(off)
        hdr = f.read(20)
        if len(hdr) < 20:
            continue
        try:
            magic, ver, gen, bound, schema = struct.unpack("<IIIII", hdr)
        except struct.error:
            continue
        if magic != 0x07230203:
            continue
        major = (ver >> 16) & 0xFF
        if major == 0 or major > 1:
            continue
        if not (0 < bound < (1 << 24)):
            continue
        nwords = min(MAX_SPIRV_WORDS, max(bound, 64))
        f.seek(off + 20)
        raw = f.read(nwords * 4)
        n = len(raw) // 4
        if n <= 0:
            continue
        words = struct.unpack("<%dI" % n, raw[:n * 4])
        i = 0
        while i < len(words):
            w = words[i]
            wc = w >> 16
            op = w & 0xFFFF
            if wc == 0:
                break
            if op == OP_ENTRY_POINT and wc >= 4:
                model = words[i + 1]
                nm_bytes = bytearray()
                done = False
                for k in range(i + 3, min(i + wc, len(words))):
                    v = words[k]
                    for sh in (0, 8, 16, 24):
                        c = (v >> sh) & 0xFF
                        if c == 0:
                            done = True
                            break
                        nm_bytes.append(c)
                    if done:
                        break
                nm = nm_bytes.decode("utf-8", "replace").strip()
                mname = EXEC_MODELS.get(model, "model%d" % model)
                if nm:
                    kernels.append(nm)
                    models.append("entry:%s/%s" % (nm, mname))
            i += wc
    if len(offsets) >= MAX_SPIRV_MODULES:
        truncated = True
    return kernels, models, truncated


def _harvest_kernel_symbols(rep):
    """把 GPU kernel 提升为 Symbol(kind=gpu_kernel)，供归属分析使用。"""
    seen = set()
    for b in rep.gpu_blobs:
        for k in b.kernels:
            key = (b.backend, k)
            if key in seen:
                continue
            seen.add(key)
            rep.symbols.append(Symbol(name=k, kind=SYM_GPU_KERNEL, origin=rep.path,
                                      backend=b.backend, section=b.section,
                                      demangled=demangle_itanium(k)))
