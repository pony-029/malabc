"""ELF 解析（Linux / ROCm .so、对象文件、以及 HSA code object）。

只解析对「归属」有用的部分：机器类型、段/节表、PT_DYNAMIC 的依赖与 SONAME、
.dynsym/.symtab 的动态符号。**不做**反汇编、不做重定位。

特别处理：CUDA cubin 是「借用 ELF 布局但字段非标准」的文件。它和真 ELF 的差别
**不是细节，而是整张表都不可信**（R31 探针在真实 cuBLAS 上实测）：

    字段              真 ELF 该是        CUDA cubin 实测     结论
    ────────────────  ────────────────  ──────────────────  ──────────────
    e_ident[0:4]      \\x7f E L F         \\x7f E L F          ✅ 只有这里像
    e_ident[7]        OSABI（0/3/…）      0x33 (ELFOSABI_CUDA) ✅ 可信判据
    e_type            1/2/3/4            0x8000              ❌ 非标准
    e_machine         3/62/…             0x100 (≠190!)       ❌ 非标准
    e_shoff           文件内偏移          落 0xCAFE... 哨兵   ❌ 不可信
    ────────────────  ────────────────  ──────────────────  ──────────────

  ⇒ 所以「数 \\x7fELF」只能当**便宜判据**（suspect_code_objects）；
    **可信判据必须含 e_ident[7] == 0x33**（或 0x40 = ELFOSABI_AMDGPU_HSA）。
    本模块不假装能解析 cubin，只识别并标记它 —— 见 detect_cubin_like()。
"""
import io
import struct

from .model import (
    CONTAINER_ELF, DEP_NEEDED, DEP_RPATH, DEP_RUNPATH, Section, Symbol,
    BinaryReport, Dependency, SYM_DYNAMIC, SYM_EXPORT,
)

MACHINE = {
    0: "none", 2: "sparc", 3: "x86", 8: "mips", 20: "ppc", 21: "ppc64",
    22: "s390", 40: "arm", 42: "sh", 50: "ia64", 62: "x86_64", 83: "avr",
    183: "aarch64", 190: "cuda", 224: "amdgpu", 243: "riscv", 247: "bpf",
    258: "loongarch",
}
ELF_TYPE = {0: "ET_NONE", 1: "ET_REL", 2: "ET_EXEC", 3: "ET_DYN", 4: "ET_CORE"}
OSABI = {
    0: "sysv", 1: "hpux", 2: "netbsd", 3: "linux", 6: "solaris", 9: "freebsd",
    12: "openbsd", 51: "cuda", 64: "amdgpu_hsa", 97: "arm", 255: "standalone",
}

SHT_STRTAB = 3
SHT_DYNAMIC = 6
SHT_DYNSYM = 11
SHT_SYMTAB = 2
SHT_NOBITS = 8

SHF_EXECINSTR = 0x4
SHF_ALLOC = 0x2

PT_DYNAMIC = 2

DT_NULL, DT_NEEDED, DT_SONAME, DT_RPATH, DT_RUNPATH = 0, 1, 14, 15, 29
DT_STRTAB, DT_SYMTAB, DT_STRSZ = 5, 6, 10

ELFOSABI_CUDA = 51
ELFOSABI_AMDGPU_HSA = 64
EM_CUDA = 190
EM_AMDGPU = 224

MAX_SECTIONS = 4096
MAX_PHNUM = 1024
MAX_DYNAMIC = 8192
MAX_SYMS = 200000
MAX_NAME = 512


def sniff(head):
    return len(head) >= 16 and head[:4] == b"\x7fELF"


def classify(head):
    """从 ELF 头判定这是不是一个「像 GPU code object」的文件。

    返回 (is_gpu, backend, note)。判定只看 e_ident[7] 与 e_machine ——
    这两个字段在 CUDA cubin 与 AMD HSACO 上是可靠的，而 e_type/e_shoff 不是。
    """
    if not sniff(head):
        return False, "", ""
    osabi = head[7]
    e_machine = struct.unpack_from("<H", head, 18)[0] if len(head) >= 20 else 0
    if osabi == ELFOSABI_CUDA or e_machine == EM_CUDA:
        return True, "cuda", "ELFOSABI_CUDA(%d)/e_machine=%d" % (osabi, e_machine)
    if osabi == ELFOSABI_AMDGPU_HSA or e_machine == EM_AMDGPU:
        return True, "hip", "ELFOSABI_AMDGPU_HSA(%d)/e_machine=%d" % (osabi, e_machine)
    return False, "", ""


def is_standard_layout(head, e_type, e_shoff):
    """CUDA cubin 借用 ELF 布局但字段非标准。此函数判定「能否按标准 ELF 解析」。

    判据来自 R31 探针实测：cubin 的 e_type=0x8000、e_machine=0x100、
    e_shoff 落在 0xCAFE 哨兵区。任一异常即认为不可按标准布局解析。
    """
    if e_type not in (0, 1, 2, 3, 4):
        return False, "e_type=0x%x 不在标准 ET_* 取值内" % e_type
    if e_shoff >= (1 << 48):
        return False, "e_shoff=0x%x 越界（疑为哨兵值）" % e_shoff
    return True, ""


def _cstr(f, off, limit=MAX_NAME):
    if off is None or off < 0:
        return ""
    f.seek(off)
    out = bytearray()
    while len(out) < limit:
        c = f.read(1)
        if not c or c == b"\x00":
            break
        out += c
    return out.decode("utf-8", "replace")


def parse(path, scan_cap=None):
    rep = BinaryReport(path=path, container=CONTAINER_ELF)
    f = io.open(path, "rb")
    try:
        head = f.read(64)
        if not sniff(head):
            rep.notes.append("ELF: 缺少 \\x7fELF 魔数")
            return rep
        cls = head[4]
        data = head[5]
        if cls not in (1, 2):
            rep.notes.append("ELF: 未知 EI_CLASS=%d" % cls)
            return rep
        endian = "<" if data == 1 else ">"
        rep.bits = 64 if cls == 2 else 32
        rep.endian = "little" if data == 1 else "big"
        osabi = head[7]
        abiver = head[8]
        e_type, e_machine = struct.unpack_from(endian + "HH", head, 16)
        if cls == 2:
            e_phoff = struct.unpack_from(endian + "Q", head, 32)[0]
            e_shoff = struct.unpack_from(endian + "Q", head, 40)[0]
            e_phentsize, e_phnum, e_shentsize, e_shnum, e_shstrndx = \
                struct.unpack_from(endian + "HHHHH", head, 54)
        else:
            e_phoff = struct.unpack_from(endian + "I", head, 28)[0]
            e_shoff = struct.unpack_from(endian + "I", head, 32)[0]
            e_phentsize, e_phnum, e_shentsize, e_shnum, e_shstrndx = \
                struct.unpack_from(endian + "HHHHH", head, 42)
        rep.arch = MACHINE.get(e_machine, "unknown(%d)" % e_machine)
        rep.flavour = ELF_TYPE.get(e_type, "type=%d" % e_type).lower()
        if osabi:
            rep.notes.append("ELF: OSABI=%d(%s) abiver=%d"
                             % (osabi, OSABI.get(osabi, "?"), abiver))
        rep.scanned_bytes = 64

        ok, why = is_standard_layout(head, e_type, e_shoff)
        if not ok:
            rep.notes.append("ELF: 非标准布局 —— %s；跳过节表/动态段解析" % why)
            secs = _scan_sections_guess(f, e_shoff, e_shnum, e_shentsize, cls, endian)
            rep.sections = secs
            if secs:
                rep.notes.append("ELF: 在 e_shoff=0x%x 处仍读到 %d 个节（布局接近标准）"
                                 % (e_shoff, len(secs)))
            return rep

        secs, shstr = _read_sections(f, e_shoff, e_shnum, e_shentsize, e_shstrndx,
                                     cls, endian, rep)
        rep.sections = secs
        _read_dynamic(f, secs, cls, endian, rep)
        _read_dynsym(f, secs, cls, endian, rep)
        return rep
    except (OSError, struct.error) as e:
        rep.notes.append("ELF: 解析中断 %s: %s" % (type(e).__name__, e))
        return rep
    finally:
        f.close()


def _scan_sections_guess(f, e_shoff, e_shnum, e_shentsize, cls, endian):
    """非标准布局的降级尝试：只读节名，不做任何语义解释。"""
    if not e_shoff or not e_shnum or e_shnum > MAX_SECTIONS:
        return []
    out = []
    ent = e_shentsize or (64 if cls == 2 else 40)
    try:
        for i in range(min(e_shnum, MAX_SECTIONS)):
            f.seek(e_shoff + i * ent)
            b = f.read(ent)
            if len(b) < ent:
                break
            name_off, sh_type = struct.unpack_from(endian + "II", b, 0)
            if cls == 2:
                addr = struct.unpack_from(endian + "Q", b, 16)[0]
                off = struct.unpack_from(endian + "Q", b, 24)[0]
                size = struct.unpack_from(endian + "Q", b, 32)[0]
            else:
                addr = struct.unpack_from(endian + "I", b, 12)[0]
                off = struct.unpack_from(endian + "I", b, 16)[0]
                size = struct.unpack_from(endian + "I", b, 20)[0]
            out.append(Section(name="<sec%d>" % i, vaddr=addr, vsize=size,
                               file_off=off, file_size=size,
                               kind="type=%d nameoff=%d" % (sh_type, name_off)))
    except (OSError, struct.error):
        pass
    return out


def _read_sections(f, e_shoff, e_shnum, e_shentsize, e_shstrndx, cls, endian, rep):
    if not e_shoff or not e_shnum:
        return [], ""
    if e_shnum > MAX_SECTIONS:
        rep.notes.append("ELF: 节数 %d 超上限，截断到 %d" % (e_shnum, MAX_SECTIONS))
        e_shnum = MAX_SECTIONS
    ent = e_shentsize or (64 if cls == 2 else 40)
    raw = []
    for i in range(e_shnum):
        f.seek(e_shoff + i * ent)
        b = f.read(ent)
        if len(b) < ent:
            rep.notes.append("ELF: 节表在 idx=%d 处被截断" % i)
            break
        name_off, sh_type = struct.unpack_from(endian + "II", b, 0)
        if cls == 2:
            flags = struct.unpack_from(endian + "Q", b, 8)[0]
            addr = struct.unpack_from(endian + "Q", b, 16)[0]
            off = struct.unpack_from(endian + "Q", b, 24)[0]
            size = struct.unpack_from(endian + "Q", b, 32)[0]
        else:
            flags = struct.unpack_from(endian + "I", b, 8)[0]
            addr = struct.unpack_from(endian + "I", b, 12)[0]
            off = struct.unpack_from(endian + "I", b, 16)[0]
            size = struct.unpack_from(endian + "I", b, 20)[0]
        raw.append((name_off, sh_type, flags, addr, off, size))
    shstr_off = 0
    if 0 <= e_shstrndx < len(raw):
        shstr_off = raw[e_shstrndx][4]
    out = []
    for name_off, sh_type, flags, addr, off, size in raw:
        nm = _cstr(f, shstr_off + name_off) if shstr_off else ""
        kind = []
        if flags & SHF_EXECINSTR:
            kind.append("text")
        elif sh_type == SHT_NOBITS:
            kind.append("bss")
        elif flags & SHF_ALLOC:
            kind.append("data")
        out.append(Section(name=nm or ("<sec@%d>" % off), vaddr=addr, vsize=size,
                           file_off=off, file_size=size if sh_type != SHT_NOBITS else 0,
                           kind=",".join(kind)))
    return out, shstr_off


def _read_dynamic(f, secs, cls, endian, rep):
    """读 SHT_DYNAMIC，提取 DT_NEEDED / DT_SONAME / DT_RPATH / DT_RUNPATH。

    注意：本函数绝不抛异常终止流程（更不得 SystemExit）——损坏的 .dynamic
    只应记 note 后返回已解析部分。
    """
    dsec = None
    for s in secs:
        if s.name == ".dynamic":
            dsec = s
            break
    if dsec is None:
        if any(s.name == ".dynstr" for s in secs):
            rep.notes.append("ELF: 发现 .dynstr 但未定位 .dynamic，跳过依赖解析")
        return
    step = 16 if cls == 2 else 8
    limit = min(dsec.file_size // step if step else 0, MAX_DYNAMIC)
    ents = []
    for i in range(limit):
        f.seek(dsec.file_off + i * step)
        b = f.read(step)
        if len(b) < step:
            rep.notes.append("ELF: .dynamic 在 idx=%d 处被截断" % i)
            break
        if cls == 2:
            tag, val = struct.unpack_from(endian + "qQ", b, 0)
        else:
            tag, val = struct.unpack_from(endian + "iI", b, 0)
        if tag == DT_NULL:
            break
        ents.append((tag, val))
    if limit and len(ents) >= limit:
        rep.notes.append("ELF: .dynamic 条目达上限 %d，截断" % MAX_DYNAMIC)

    strtab_vaddr = 0
    for tag, val in ents:
        if tag == DT_STRTAB:
            strtab_vaddr = val
    str_off = _vaddr_to_off(secs, strtab_vaddr) if strtab_vaddr else None
    if str_off is None and strtab_vaddr:
        rep.notes.append("ELF: DT_STRTAB=0x%x 无法映射到文件偏移，依赖名不可读" % strtab_vaddr)

    for tag, val in ents:
        if tag == DT_NEEDED:
            nm = _cstr(f, str_off + val) if str_off is not None else ""
            if nm:
                rep.dependencies.append(Dependency(name=nm, kind=DEP_NEEDED,
                                                   origin=rep.path))
        elif tag == DT_SONAME:
            nm = _cstr(f, str_off + val) if str_off is not None else ""
            if nm:
                rep.notes.append("ELF: SONAME=%s" % nm)
        elif tag in (DT_RPATH, DT_RUNPATH):
            nm = _cstr(f, str_off + val) if str_off is not None else ""
            if nm:
                rep.dependencies.append(Dependency(
                    name=nm, kind=DEP_RPATH if tag == DT_RPATH else DEP_RUNPATH,
                    origin=rep.path))


def _vaddr_to_off(secs, vaddr):
    for s in secs:
        hi = max(s.vsize, s.file_size)
        if s.vaddr <= vaddr < s.vaddr + hi:
            delta = vaddr - s.vaddr
            if delta < max(s.file_size, 0):
                return s.file_off + delta
            return None
    return None


def _read_dynsym(f, secs, cls, endian, rep):
    """读 .dynsym（动态符号表）——这是「这个库能提供什么」的答案。"""
    dsec = None
    strsec = None
    for s in secs:
        if s.name == ".dynsym":
            dsec = s
        elif s.name == ".dynstr":
            strsec = s
    if dsec is None:
        if any(s.name == ".symtab" for s in secs):
            rep.notes.append("ELF: 只有 .symtab（未 strip 的调试符号），无 .dynsym")
        return
    ent = 24 if cls == 2 else 16
    cnt = dsec.file_size // ent if ent else 0
    if cnt > MAX_SYMS:
        rep.notes.append("ELF: .dynsym 符号数 %d 超上限，截断到 %d" % (cnt, MAX_SYMS))
        cnt = MAX_SYMS
    stroff = strsec.file_off if strsec else 0
    for i in range(cnt):
        f.seek(dsec.file_off + i * ent)
        b = f.read(ent)
        if len(b) < ent:
            break
        name_off = struct.unpack_from(endian + "I", b, 0)[0]
        if cls == 2:
            info = b[4]
            shndx = struct.unpack_from(endian + "H", b, 6)[0]
            value = struct.unpack_from(endian + "Q", b, 8)[0]
        else:
            value = struct.unpack_from(endian + "I", b, 4)[0]
            info = b[12]
            shndx = struct.unpack_from(endian + "H", b, 14)[0]
        if name_off == 0:
            continue
        nm = _cstr(f, stroff + name_off) if stroff else ""
        if not nm:
            continue
        bind = info >> 4
        typ = info & 0xF
        kind = SYM_DYNAMIC
        if typ == 2 and shndx != 0:
            kind = SYM_EXPORT
        elif shndx == 0:
            kind = SYM_IMPORT
        rep.symbols.append(Symbol(name=nm, kind=kind, origin=rep.path,
                                  address=value, section=".dynsym"))
        if bind == 1 and typ == 2:
            pass  # STB_GLOBAL + STT_FUNC
    if cnt:
        rep.scanned_bytes += cnt * ent
