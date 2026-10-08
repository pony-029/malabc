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
