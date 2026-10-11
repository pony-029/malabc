"""PE / PE32+ 解析（Windows DLL / EXE）。

只解析对「归属」有用的部分：机器类型、段表、导入表（→ 依赖边）、导出表
（→ 可解析符号）。**不做**反汇编、不做重定位、不做资源树。

Windows 上最重要的一个坑 —— 段名只有 8 字节，厂商的段名全被截断：

    厂商写的（人类以为的）   PE 里实际存的（8 字节硬截断）
    ─────────────────────   ────────────────────────────
    .nv_fatbin              .nv_fatb        ← CUDA fatbin
    .nvFatBin               .nvFatBi        ← CUDA fatbin 索引
    .hip_fatbin             .hip_fat        ← AMD HIP fatbin
    .hipFatBin              .hipFatB        ← AMD HIP fatbin 索引
    （Vulkan）              （无专用段）     ← SPIR-V 躲在通用数据段里

  ⇒ 按「文档里的段名」去查会 0 命中。gpu.py 的 SECTION_HINTS 两种名字都收，
    并且配了魔数扫描兜底 —— 这不是冗余，是必需。

安全性（黑帽 K1/K8）：
  * 全部 seek + 定长 read，单次读 <= MAX_CHUNK。
  * 所有数组长度都设硬上限（损坏文件不得导致巨量分配或长循环）。
  * 任何结构异常都记 note 并返回已解析部分，**不抛异常** —— 但会把 flavour
    标成 unknown（宁可说「我没看懂」，也不假装看懂了）。
"""
import io
import struct

from .model import (
    CONTAINER_PE, DEP_IMPORT_MODULE, MAX_CHUNK, Section, Symbol, BinaryReport,
    Dependency, SYM_EXPORT,
    EVIDENCE_OBSERVED, MIT_ASLR, MIT_NX, MIT_EXECSTACK, MIT_CANARY, MIT_RELRO,
    MIT_CFG, MIT_HIGH_ENTROPY_VA, MIT_SEH, MIT_FORCE_INTEGRITY,
    MIT_APPCONTAINER,
)

MACHINE = {
    0x014C: "x86",
    0x8664: "x86_64",
    0x01C0: "arm",
    0x01C4: "armv7",
    0xAA64: "aarch64",
    0x0200: "ia64",
}

# 硬上限：损坏/恶意文件不得让我们分配巨量内存或长时间循环
MAX_SECTIONS = 256
MAX_IMPORT_DESCS = 4096
MAX_EXPORTS = 200000
MAX_NAME_LEN = 512

# ---- R86-2：PE 静态缓解措施的判据位（全部来自头部字段，observed） ----
# DllCharacteristics 在 Optional Header 的偏移 0x46（PE32 与 PE32+ **同偏移**：
# 两者的差异在更早的 ImageBase/BaseOfData，到这里已经对齐）。
DLLCHAR_HIGH_ENTROPY_VA = 0x0020
DLLCHAR_DYNAMIC_BASE = 0x0040
DLLCHAR_FORCE_INTEGRITY = 0x0080
DLLCHAR_NX_COMPAT = 0x0100
DLLCHAR_NO_ISOLATION = 0x0200
DLLCHAR_NO_SEH = 0x0400
DLLCHAR_APPCONTAINER = 0x1000
DLLCHAR_GUARD_CF = 0x4000
OPT_DLLCHAR_OFF = 0x46
# COFF Characteristics：标了这一位 = 重定位信息已剥离 ⇒ DYNAMIC_BASE 可能不起作用
COFF_RELOCS_STRIPPED = 0x0001
# DataDirectory[10] = IMAGE_DIRECTORY_ENTRY_LOAD_CONFIG
DD_LOAD_CONFIG = 10


def _u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def _u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def sniff(head):
    """粗判。注意 MZ 只有 2 字节，非常弱 —— 必须再校验 e_lfanew 处的 PE 签名，
    否则任何以 'MZ' 开头的文本都会被误判成 PE。"""
    if len(head) < 0x40 or head[:2] != b"MZ":
        return False
    try:
        off = _u32(head, 0x3C)
    except struct.error:
        return False
    if not (0 < off < (1 << 31)):
        return False
    if off + 4 <= len(head):
        return head[off:off + 4] == b"PE\x00\x00"
    return True     # 头部不够长，先认为像 PE，由 parse() 最终裁决


def _read_cstr(f, off, limit=MAX_NAME_LEN):
    f.seek(off)
    out = bytearray()
    while len(out) < limit:
        c = f.read(1)
        if not c or c == b"\x00":
            break
        out += c
    return out.decode("latin1", "replace")


def parse(path, scan_cap=None):
    """解析 PE。返回 BinaryReport。scan_cap 目前只用于记账（PE 头部很小）。"""
    rep = BinaryReport(path=path, container=CONTAINER_PE)
    f = io.open(path, "rb")
    try:
        head = f.read(0x40)
        if not sniff(head):
            rep.notes.append("PE: 缺少 MZ/e_lfanew")
            return rep
        pe_off = _u32(head, 0x3C)
        f.seek(pe_off)
        sig = f.read(4)
        if sig != b"PE\x00\x00":
            rep.notes.append("PE: e_lfanew 处不是 PE\\0\\0 签名")
            return rep
        coff = f.read(20)
        if len(coff) < 20:
            rep.notes.append("PE: COFF 头被截断")
            return rep
        machine = _u16(coff, 0)
        nsec = _u16(coff, 2)
        opt_size = _u16(coff, 16)
        chars = _u16(coff, 18)
        rep.arch = MACHINE.get(machine, "unknown(0x%04x)" % machine)
        rep.bits = 64 if machine == 0x8664 or machine == 0xAA64 else 32
        rep.endian = "little"
        if chars & 0x2000:
            rep.flavour = "dll"
        else:
            rep.flavour = "exe"

        opt_off = pe_off + 24
        opt = f.read(min(opt_size, 240 + 16 * 16))
        image_base = 0
        data_dirs = []
        if len(opt) >= 2:
            magic = _u16(opt, 0)
            if magic == 0x20B:          # PE32+
                if len(opt) >= 32:
                    image_base = struct.unpack_from("<Q", opt, 24)[0]
                dd_off = 112
            elif magic == 0x10B:        # PE32
                if len(opt) >= 28:
                    image_base = _u32(opt, 28)
                dd_off = 96
            else:
                rep.notes.append("PE: 未知 optional header magic 0x%04x" % magic)
                dd_off = 0
            if dd_off:
                ndd = min(_u32(opt, dd_off - 4) if dd_off >= 4 else 16, 16)
                for i in range(max(0, min(ndd, 16))):
                    o = dd_off + i * 8
                    if o + 8 > len(opt):
                        break
                    data_dirs.append((_u32(opt, o), _u32(opt, o + 4)))
        rep.scanned_bytes = pe_off + 24 + opt_size

        if nsec > MAX_SECTIONS:
            rep.notes.append("PE: 段数 %d 超过上限 %d，只解析前 %d 个"
                             % (nsec, MAX_SECTIONS, MAX_SECTIONS))
            nsec = MAX_SECTIONS

        f.seek(pe_off + 24 + opt_size)
        secs = []
        for _ in range(nsec):
            b = f.read(40)
            if len(b) < 40:
                rep.notes.append("PE: 段表被截断")
                break
            nm = b[:8].rstrip(b"\x00").decode("latin1")
            vsz, va, rsz, ra = struct.unpack_from("<IIII", b, 8)
            secs.append(Section(name=nm, vaddr=va, vsize=vsz, file_off=ra, file_size=rsz))
        rep.sections = secs

        def rva_to_off(rva):
            for s in secs:
                hi = max(s.vsize, s.file_size)
                if s.vaddr <= rva < s.vaddr + hi:
                    delta = rva - s.vaddr
                    if delta < s.file_size:
                        return s.file_off + delta
                    return None
            return None

        if len(data_dirs) > 0 and data_dirs[0][0]:
            _parse_exports(f, rep, data_dirs[0], rva_to_off, image_base)
        if len(data_dirs) > 1 and data_dirs[1][0]:
            _parse_imports(f, rep, data_dirs[1], rva_to_off)

        # ---- R86-2：静态缓解措施（头部字段直接可读 ⇒ evidence_kind=observed） ----
        # ⚠ 可达性（R86-2 的门实测）：DllCharacteristics 在布局上排在
        #   DataDirectory **之前**，而 DataDirectory 的读取（`_u32`）会在
        #   头部不够长时先抛 struct.error 被外层收走。于是
        #   「解析能走到这里 ⇒ 该字段一定可读」通常是成立的；`None` 分支只在
        #   **magic 非法**（dd_off=0，整块 DataDirectory 被跳过）或文件被截断
        #   到这一步时才可达。保留它不是为了好看 —— 那个 `_u16` 一旦越界
        #   就是 struct.error 崩掉整个 parse，这里的判断是**安全闸**，
        #   顺带才是「unknown」语义。
        dllchar = None
        if len(opt) >= OPT_DLLCHAR_OFF + 2:
            dllchar = _u16(opt, OPT_DLLCHAR_OFF)
        else:
            rep.notes.append("PE: Optional Header 只有 %d 字节，读不到 "
                             "DllCharacteristics（缓解措施将是 unknown）" % len(opt))
        cookie, cookie_basis = None, None
        if len(data_dirs) > DD_LOAD_CONFIG and data_dirs[DD_LOAD_CONFIG][0]:
            got = _read_security_cookie(f, data_dirs[DD_LOAD_CONFIG], rva_to_off, rep)
            if got is not None:
                cookie, cookie_basis = got
        rep.mitigations = _compute_mitigations(rep, dllchar, chars, cookie,
                                              cookie_basis)
        return rep
    except (OSError, struct.error) as e:
        rep.notes.append("PE: 解析中断 %s: %s" % (type(e).__name__, e))
        return rep
    finally:
        f.close()


def _parse_exports(f, rep, dd, rva_to_off, image_base):
    rva, size = dd
    off = rva_to_off(rva)
    if off is None:
        rep.notes.append("PE: 导出表 RVA 0x%x 无法映射到文件偏移" % rva)
        return
    f.seek(off)
    d = f.read(40)
    if len(d) < 40:
        rep.notes.append("PE: 导出目录被截断")
        return
    n_funcs = _u32(d, 20)
    n_names = _u32(d, 24)
    a_funcs = _u32(d, 28)
    a_names = _u32(d, 32)
    dll_name_off = rva_to_off(_u32(d, 12))
    dll_name = _read_cstr(f, dll_name_off) if dll_name_off else ""
    if n_names > MAX_EXPORTS:
        rep.notes.append("PE: 导出名数 %d 超上限，截断到 %d" % (n_names, MAX_EXPORTS))
        n_names = MAX_EXPORTS
    noff = rva_to_off(a_names)
    foff = rva_to_off(a_funcs)
    if noff is None:
        rep.notes.append("PE: AddressOfNames 无法映射")
        return
    for i in range(n_names):
        f.seek(noff + i * 4)
        raw = f.read(4)
        if len(raw) < 4:
            break
        nrv = _u32(raw, 0)
        no = rva_to_off(nrv)
        if no is None:
            continue
        nm = _read_cstr(f, no)
        if not nm:
            continue
        addr = 0
        if foff is not None:
            f.seek(foff + i * 4)
            row = f.read(4)
            if len(row) == 4:
                addr = image_base + _u32(row, 0)
        rep.symbols.append(Symbol(name=nm, kind=SYM_EXPORT, origin=rep.path,
                                  address=addr, section=".text"))
    # 有函数但无名（按序号导出）—— 记数，不臆造名字
    if n_funcs > n_names:
        rep.notes.append("PE: 导出目录含 %d 个仅按序号导出的函数（无名，未列符号）"
                         % (n_funcs - n_names))
    if dll_name:
        rep.notes.append("PE: 导出模块名 %s" % dll_name)


MODULE_EXTS = (".dll", ".so", ".exe", ".sys", ".drv", ".ocx", ".cpl")


def _is_plausible_module_name(s):
    """PE 的导入名必然是「可打印 ASCII + 模块扩展名」。

    R31 自检抓出的真缺陷：不做这个校验时，导入表遍历越过 NULL 终止符后
    会把 .rdata 里的普通数据当成 IMAGE_IMPORT_DESCRIPTOR，
    于是 cublas64_12.dll 报出 2532 条依赖（真实应为个位数），
    其中只有第 1 条是对的，其余全是垃圾（含控制字符的名字）。
    """
    if not s or len(s) > 260:
        return False
    for c in s:
        o = ord(c)
        if o < 0x20 or o > 0x7E:
            return False
    return s.lower().endswith(MODULE_EXTS)


def _parse_imports(f, rep, dd, rva_to_off):
    rva, size = dd
    off = rva_to_off(rva)
    if off is None:
        rep.notes.append("PE: 导入表 RVA 0x%x 无法映射到文件偏移" % rva)
        return
    f.seek(off)
    n = 0
    stopped = ""
    # DataDirectory[1].Size 给出导入表的字节长度 —— 比盲目遍历到 NULL 更精确
    # （实测 cublas64_12.dll 的导入表只有 1 条，紧邻其后的 .rdata 数据会被误读）
    limit_desc = MAX_IMPORT_DESCS
    if size:
        limit_desc = max(1, min(limit_desc, size // 20))
    while n < limit_desc:
        # 显式 seek：_read_cstr 内部会 seek 到字符串位置，若依赖连续 read
        # 游标，第 2 条之后读到的就不是描述符了（R31 护栏抓出的真缺陷 ——
        # 它同时影响真实文件：依赖数会被严重低估）。
        f.seek(off + n * 20)
        b = f.read(20)
        if len(b) < 20:
            stopped = "导入表被截断"
            break
        oft, tds, fwd, name_rva, first_thunk = struct.unpack_from("<IIIII", b, 0)
        if oft == 0 and name_rva == 0 and first_thunk == 0:
            stopped = "遇到 NULL 终止描述符"
            break
        if name_rva == 0:
            stopped = "name_rva=0（非法描述符），停止遍历"
            break
        no = rva_to_off(name_rva)
        if no is None:
            stopped = "name_rva 0x%x 无法映射，停止遍历" % name_rva
            break
        dll = _read_cstr(f, no)
        if not _is_plausible_module_name(dll):
            stopped = ("候选名 %r 不像模块名（含控制字符/无扩展名），"
                       "判定表已结束" % dll[:24])
            break
        rep.dependencies.append(Dependency(name=dll, kind=DEP_IMPORT_MODULE,
                                           origin=rep.path))
        n += 1
    else:
        stopped = "导入描述符数达上限 %d，截断" % limit_desc
    # 记账：让「为什么停」可见 —— 与项目「不静默」纪律一致，
    # 但只有在发生过「提前停止」时才记，避免正常文件刷屏。
    if stopped and "NULL 终止" not in stopped:
        rep.notes.append("PE: 导入表遍历终止原因 —— %s（已收 %d 条）" % (stopped, n))


# ---- R86-2：GS canary 的 cookie 指针（LOAD_CONFIG 目录） ----

# IMAGE_LOAD_CONFIG_DIRECTORY 是**自描述**结构：头 4 字节就是 Size。
# SecurityCookie 在 64 位布局的偏移 88、32 位布局的偏移 60。
# ⚠ 这两个偏移**不是**猜的：它们必须与 Size 对照后才敢用 —— 见函数内注释。
_LC_SECURITY_COOKIE_OFF = {64: 88, 32: 60}
_LC_PTR_SIZE = {64: 8, 32: 4}


def _read_security_cookie(f, dd, rva_to_off, rep):
    """返回 `(cookie 值, basis)`；读不出时返回 None（**不猜**）。

    为什么宁可返回 None 也不读：SecurityCookie 的偏移是**写死**的，而
    LOAD_CONFIG 结构历史上一直在**增长**（新 Windows 版本追加字段）。
    对着一个 Size 很小的旧结构按新偏移去读，读到的是**紧邻的别的数据** ——
    它会静默产出一个「看起来合法」的假 cookie，把「没有 GS」洗成「有 GS」。
    所以这里让结构**自己**回答：Size 不覆盖到该偏移 ⇒ 判据构件缺失。
    """
    rva, size = dd
    off = rva_to_off(rva)
    if off is None:
        rep.notes.append("PE: LOAD_CONFIG RVA 0x%x 无法映射到文件偏移" % rva)
        return None
    ptr = _LC_PTR_SIZE.get(rep.bits)
    co = _LC_SECURITY_COOKIE_OFF.get(rep.bits)
    if ptr is None:
        return None
    f.seek(off)
    head = f.read(4)
    if len(head) < 4:
        rep.notes.append("PE: LOAD_CONFIG 目录被截断（读不到 Size）")
        return None
    decl = _u32(head, 0)                    # 结构**自己声明的**大小
    if decl < co + ptr:
        # 声明的大小够不到 SecurityCookie 字段 ⇒ 判据构件缺失，置 None。
        rep.notes.append("PE: LOAD_CONFIG 声明大小 %d < SecurityCookie 偏移 %d "
                         "⇒ 该字段不可读（不做越界读，避免把相邻数据当 cookie）"
                         % (decl, co + ptr))
        return None
    f.seek(off + co)
    raw = f.read(ptr)
    if len(raw) < ptr:
        rep.notes.append("PE: LOAD_CONFIG.SecurityCookie 被截断")
        return None
    val = struct.unpack_from("<Q" if ptr == 8 else "<I", raw, 0)[0]
    return val, ("LOAD_CONFIG(dir size=%d).SecurityCookie=%#x" % (decl, val))


def _compute_mitigations(rep, dllchar, coff_chars, cookie, cookie_basis):
    """R86-2：PE 静态缓解措施读数。evidence_kind=observed。

    与 ELF 侧（`elf._compute_mitigations`，inferred）**同形不同档**：
      * 这里每个值都来自**头部里写着的字段**，不需要「由缺席推否定」；
      * 但 dllchar 读不到（Optional Header 被截断）时仍然是 `None`，
        与 `False`（读到了、且没有这一位）严格分开 —— 与 ELF 侧同一条纪律。
    """
    basis = {}
    lim = [
        "这些是**头部声明值**（链接器开关的复读），不是运行时保护 —— "
        "没声明 NX_COMPAT **不证明**运行时栈一定可执行（系统级强制可能仍生效）。",
        "容器=%s：DllCharacteristics 是**构建期**配置，与运行时的系统策略无关。"
        % (rep.container or "?"),
    ]
    if dllchar is None:
        aslr = nx = cfg = hev = seh = fi = appc = None
        basis[MIT_ASLR] = "Optional Header 太短，读不到 DllCharacteristics"
        basis[MIT_NX] = basis[MIT_ASLR]
        basis[MIT_CFG] = basis[MIT_ASLR]
        lim.append("DllCharacteristics 不可读：ASLR / NX / CFG 一律置 null，不猜。")
    else:
        aslr = bool(dllchar & DLLCHAR_DYNAMIC_BASE)
        nx = bool(dllchar & DLLCHAR_NX_COMPAT)
        cfg = bool(dllchar & DLLCHAR_GUARD_CF)
        hev = bool(dllchar & DLLCHAR_HIGH_ENTROPY_VA)
        seh = not bool(dllchar & DLLCHAR_NO_SEH)
        fi = bool(dllchar & DLLCHAR_FORCE_INTEGRITY)
        appc = bool(dllchar & DLLCHAR_APPCONTAINER)
        _d = "DllCharacteristics=%#06x" % dllchar
        basis[MIT_ASLR] = "%s %s 0x%02x DYNAMIC_BASE" % (
            _d, "含" if aslr else "无", DLLCHAR_DYNAMIC_BASE)
        basis[MIT_NX] = "%s %s 0x%02x NX_COMPAT" % (
            _d, "含" if nx else "无", DLLCHAR_NX_COMPAT)
        basis[MIT_CFG] = "%s %s 0x%02x GUARD_CF" % (
            _d, "含" if cfg else "无", DLLCHAR_GUARD_CF)
        basis[MIT_HIGH_ENTROPY_VA] = "%s %s 0x%02x HIGH_ENTROPY_VA" % (
            _d, "含" if hev else "无", DLLCHAR_HIGH_ENTROPY_VA)
        basis[MIT_SEH] = "%s %s 0x%02x NO_SEH" % (
            _d, "无" if seh else "含", DLLCHAR_NO_SEH)
        basis[MIT_FORCE_INTEGRITY] = "%s %s 0x%02x FORCE_INTEGRITY" % (
            _d, "含" if fi else "无", DLLCHAR_FORCE_INTEGRITY)
        basis[MIT_APPCONTAINER] = "%s %s 0x%02x APPCONTAINER" % (
            _d, "含" if appc else "无", DLLCHAR_APPCONTAINER)
        if aslr and (coff_chars & COFF_RELOCS_STRIPPED):
            # 两条读数**互相拉扯**：都报出来，不取其一。
            lim.append("COFF 标了 RELOCS_STRIPPED(0x0001)：重定位信息已剥离，"
                       "DYNAMIC_BASE 在部分加载路径上**无法生效** —— "
                       "两条读数互相矛盾，本报告并列陈述，不做裁定。")

    # 栈可执行性：PE 没有对应构件（不由段表决定），置 None 而不是 False
    basis[MIT_EXECSTACK] = "PE 无对应构件（栈可执行性由 NX_COMPAT 声明，不由段表决定）"

    # RELRO：该机制不适用于 PE —— 置 None，绝不用 False 冒充
    basis[MIT_RELRO] = "PE 无 RELRO 机制（概念不适用，置 null 而不是 false）"

    # Stack canary：/GS 的 cookie 指针只在 LOAD_CONFIG 里
    if cookie is None:
        canary = None
        basis[MIT_CANARY] = (cookie_basis or
                             "无 LOAD_CONFIG 目录（判据构件缺失，不等于没有 GS）")
        lim.append("canary=unknown：LOAD_CONFIG 目录不在或太小 —— "
                   "**不能**据此说这个模块没有栈保护。")
    else:
        canary = cookie != 0
        basis[MIT_CANARY] = cookie_basis
        if not canary:
            lim.append("canary=NO 是**读到 cookie 字段且为 0**；"
                       "但 cookie 非 0 也不证明每个函数都插了检查。")

    return {
        "evidence_kind": EVIDENCE_OBSERVED,
        MIT_ASLR: aslr,
        MIT_NX: nx,
        MIT_EXECSTACK: None,
        MIT_CANARY: canary,
        MIT_RELRO: None,
        MIT_CFG: cfg,
        MIT_HIGH_ENTROPY_VA: hev,
        MIT_SEH: seh,
        MIT_FORCE_INTEGRITY: fi,
        MIT_APPCONTAINER: appc,
        "basis": basis,
        "limitations": lim,
    }
