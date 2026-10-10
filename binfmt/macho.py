"""Mach-O 解析（macOS .dylib / .bundle / fat binary）。

⚠️ 诚实声明（黑帽 K7）——本模块的验证等级**低于**同包的 PE / ELF：

    模块        真实语料验证   夹具验证   报告里的待遇
    ──────────  ─────────────  ──────────  ──────────────────────────
    pe.py       是（多家厂商）   是          结论可直接引用
    elf.py      是（多家厂商）   是          结论可直接引用
    macho.py    **无**          是          **结论必须带「未验证」限定**
    ──────────  ─────────────  ──────────  ──────────────────────────

  为什么没有：本机是 Windows；WSL 被安全策略禁用；网络受限无法下载 macOS 样本。
  因此本模块只有合成夹具。R36/C''6 起，这张表被编码成**两个机器可读字段**
  （`BinaryReport.verified` / `.fixture_verified`）并渲染进报告正文 ——
  任何依赖它的结论都必须在报告里带上这个限定，不允许把它与「已用真实文件验证」
  的 PE/ELF 混为一谈。措辞也必须分开：只说「未验证」会让人以为连夹具都没过。

一个真实的歧义：Mach-O fat binary 的 magic 0xCAFEBABE 与 Java class 文件相同。
本模块用「nfat_arch 合理性 + 每个 arch 的 offset/size 是否落在文件内」做消歧；
消歧失败时**返回空并说明**，而不是硬认成 Mach-O。

R68 起，本模块不再只读「容器」——它同时读**依赖形态**与**符号表**：

    指令                        含义                       落到哪
    ──────────────────────────  ─────────────────────────  ─────────────────────
    LC_ID_DYLIB                 本库的 install name（身份）  Dependency(id_dylib)
    LC_LOAD_DYLIB               强依赖                      Dependency(load_dylib)
    LC_LOAD_WEAK_DYLIB          弱依赖（缺了也能跑）          Dependency(load_dylib)
    LC_REEXPORT_DYLIB           再导出依赖                   Dependency(load_dylib)
    LC_LOAD_UPWARD_DYLIB        向上依赖（同层互依赖）        Dependency(load_dylib)
    LC_LAZY_LOAD_DYLIB          惰性依赖（已废弃）            Dependency(load_dylib)
    LC_LOAD_DYLINKER            动态链接器（/usr/lib/dyld）   Dependency(load_dylinker)
    LC_RPATH                    @rpath 搜索路径              Dependency(rpath)
    LC_SYMTAB + nlist_64        外部符号表                   Symbol(export/import)
    ──────────────────────────  ─────────────────────────  ─────────────────────

  ⚠ 命名约定（**必须记住**）：Mach-O 里 C 符号带**前导下划线**
    （源码写 `foo`，符号表里是 `_foo`）。本模块**原样保留**（`_foo`）；
    归一（去掉那一个前导下划线再去和源码侧的名字对账）发生在 attribute.py，
    且**只对 macho 容器**做 —— 别的容器上的 `_foo` 是合法的 C 名字，不能动它。

  仍**不做**（诚实边界）：反汇编、重定位、运行期符号绑定（two-level namespace /
  dyld shared cache 的解析）、以及 fat 切片内部的逐片解析（fat 目前只列切片清单）。
"""
import io
import struct

from .model import (
    CONTAINER_MACHO, DEP_ID_DYLIB, DEP_LOAD_DYLIB, DEP_LOAD_DYLINKER, DEP_RPATH,
    MAX_CHUNK, Section, Symbol, BinaryReport, SYM_EXPORT, SYM_IMPORT,
    Dependency,
)

MH_MAGIC = 0xFEEDFACE
MH_MAGIC_64 = 0xFEEDFACF
MH_CIGAM = 0xCEFAEDFE
MH_CIGAM_64 = 0xCFFAEDFE
FAT_MAGIC = 0xCAFEBABE
FAT_CIGAM = 0xBEBAFECA

CPU_TYPE = {
    7: "x86", 0x01000007: "x86_64", 12: "arm", 0x0100000C: "aarch64",
    18: "ppc", 0x01000012: "ppc64",
}
FILETYPE = {
    1: "object", 2: "exec", 3: "fvmlib", 4: "core", 5: "preload",
    6: "dylib", 7: "dylinker", 8: "bundle", 9: "dylib_stub", 10: "dsym", 11: "kext",
}

LC_SEGMENT = 0x1
LC_SEGMENT_64 = 0x19
LC_SYMTAB = 0x2
LC_LOAD_DYLIB = 0xC
LC_ID_DYLIB = 0xD
LC_LOAD_DYLINKER = 0xE
LC_LAZY_LOAD_DYLIB = 0x20
LC_REQ_DYLD = 0x80000000
LC_LOAD_WEAK_DYLIB = 0x18 | LC_REQ_DYLD
LC_REEXPORT_DYLIB = 0x1F | LC_REQ_DYLD
LC_LOAD_UPWARD_DYLIB = 0x23 | LC_REQ_DYLD
LC_RPATH = 0x1C | LC_REQ_DYLD

# 「我依赖谁」的全部 dylib 命令（LC_ID_DYLIB 是**身份**，单独处理）
DYLIB_LOAD_CMDS = {
    LC_LOAD_DYLIB: "LC_LOAD_DYLIB",
    LC_LOAD_WEAK_DYLIB: "LC_LOAD_WEAK_DYLIB",
    LC_REEXPORT_DYLIB: "LC_REEXPORT_DYLIB",
    LC_LOAD_UPWARD_DYLIB: "LC_LOAD_UPWARD_DYLIB",
    LC_LAZY_LOAD_DYLIB: "LC_LAZY_LOAD_DYLIB",
}

MAX_CMD_BODY = 64 * 1024
MAX_SYMTAB_SYMS = 200000
MAX_STRTAB = 16 << 20

# nlist n_type 位域
N_STAB = 0xE0
N_TYPE = 0x0E
N_EXT = 0x01
N_UNDF = 0x0
N_SECT = 0x0E

MAX_CMDS = 4096
MAX_SECTS = 4096
MAX_FAT_ARCH = 64
MAX_NAME = 512

GPU_SEG_HINTS = (b"__nv_fatbin", b"__NV_FATBIN", b"__hip_fatbin", b"__HIP_FATBIN",
                 b".nv_fatbin", b".hip_fatbin")


THIN_MAGICS = (b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe",
               b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf")
FAT_MAGICS = (b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca")


def thin_magic(head):
    return len(head) >= 4 and head[:4] in THIN_MAGICS


def fat_magic(head):
    return len(head) >= 4 and head[:4] in FAT_MAGICS


def looks_like_fat(head, fsize):
    """对外暴露的消歧判定（container.sniff 需要）。"""
    return _looks_like_fat(head, fsize)


def sniff(head):
    if len(head) < 4:
        return False
    m = head[:4]
    return m in THIN_MAGICS + FAT_MAGICS


def _looks_like_fat(head, fsize):
    """消歧 0xCAFEBABE：Mach-O fat vs Java class。

    字节序列相同，用结构合理性判定：nfat_arch 必须 1..64，
    且每个 fat_arch 的 offset+size 必须落在文件内。
    """
    if len(head) < 8 or head[:4] != b"\xca\xfe\xba\xbe":
        return False
    n = struct.unpack_from(">I", head, 4)[0]
    if not (1 <= n <= MAX_FAT_ARCH):
        return False
    per = 20
    need = 8 + n * per
    if len(head) < need:
        return False
    for i in range(n):
        off, size = struct.unpack_from(">II", head, 8 + i * per + 8)
        if off < need or (fsize and off + size > fsize):
            return False
    return True


def parse(path, scan_cap=None):
    import os
    # R33/C'5 + R36/C''6：**两条验证轴分开写**。
    #   verified=False         —— 没有真实语料（本机 Windows，无 macOS 样本）
    #   fixture_verified=True  —— 有合成夹具（tools/check_binfmt_fixtures.py::_make_macho
    #                             会造出带 LC_SEGMENT_64 的真结构 thin Mach-O 64 并断言）
    # 只写 verified=False 会让人误以为「连夹具都没过」；只写 True 又会把合成夹具
    # 冒充成真实语料验证 —— 两种都是谎言，所以分成两个字段。
    rep = BinaryReport(path=path, container=CONTAINER_MACHO, verified=False,
                       fixture_verified=True)
    try:
        fsize = os.path.getsize(path)
    except OSError:
        fsize = 0
    f = io.open(path, "rb")
    try:
        head = f.read(4096)
        if not sniff(head):
            rep.notes.append("Mach-O: 魔数不匹配")
            return rep
        rep.notes.append("Mach-O: ⚠ 未经**真实语料**验证（本机无 Mach-O 样本）；"
                         "已通过合成夹具（LC_SEGMENT_64 段/节 + fat 切片）")
        magic = head[:4]
        if magic == b"\xca\xfe\xba\xbe":
            if not _looks_like_fat(head, fsize):
                rep.notes.append("Mach-O: 0xCAFEBABE 结构不合理，疑似 Java class 而非 fat binary")
                return rep
            return _parse_fat(f, head, rep, fsize)
        endian = "<" if magic in (b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe") else ">"
        # R36/K9：**必须把已经读到的 head 传下去**。旧实现在这里让 _parse_thin
        # 自己 `f.read(32)` —— 而文件指针此刻已在 4096，于是 32 字节头部是从
        # 文件偏移 4096 读的：magic 恒为 0 ⇒ is64=False ⇒ cputype/filetype/ncmds
        # 全零 ⇒ 整条命令表不被遍历。**不报错，只是安静地给出错误答案**
        # （实测：arch=unknown(0x0)、bits=32、sections=0）。这比崩溃更危险。
        return _parse_thin(f, rep, endian, head)
    except (OSError, struct.error) as e:
        rep.notes.append("Mach-O: 解析中断 %s: %s" % (type(e).__name__, e))
        return rep
    finally:
        f.close()


def _parse_fat(f, head, rep, fsize):
    n = struct.unpack_from(">I", head, 4)[0]
    rep.flavour = "fat"
    rep.endian = "big"
    rep.arch = "fat(%d)" % n
    rep.notes.append("Mach-O: fat binary 含 %d 个架构切片" % n)
    for i in range(min(n, MAX_FAT_ARCH)):
        cputype, cpusub, off, size, align = struct.unpack_from(">IIIII", head, 8 + i * 20)
        rep.notes.append("Mach-O:   slice[%d] cputype=0x%x arch=%s off=%d size=%d"
                         % (i, cputype, CPU_TYPE.get(cputype, "?"), off, size))
    return rep


def _parse_thin(f, rep, endian, head):
    # R36/K9：head 由调用方从**文件开头**读入并传入；这里绝不再 f.read()。
    head = head[:32]
    if len(head) < 28:
        rep.notes.append("Mach-O: 文件不足 28 字节，无法解析 thin 头")
        return rep
    mv = int.from_bytes(head[:4], "little" if endian == "<" else "big")
    is64 = mv in (MH_MAGIC_64, MH_CIGAM_64)
    cputype, cpusub, filetype, ncmds, sizeofcmds, flags = \
        struct.unpack_from(endian + "IIIIII", head, 4)
    rep.arch = CPU_TYPE.get(cputype, "unknown(0x%x)" % cputype)
    rep.bits = 64 if is64 else 32
    rep.endian = "little" if endian == "<" else "big"
    rep.flavour = FILETYPE.get(filetype, "ft=%d" % filetype)
    if ncmds > MAX_CMDS:
        rep.notes.append("Mach-O: ncmds=%d 超上限，截断" % ncmds)
        ncmds = MAX_CMDS
    off = 32 if is64 else 28
    symtab = None
    for _ in range(ncmds):
        f.seek(off)
        b = f.read(8)
        if len(b) < 8:
            break
        cmd, cmdsize = struct.unpack_from(endian + "II", b, 0)
        if cmdsize < 8:
            rep.notes.append("Mach-O: cmd=0x%x cmdsize=%d 非法，停止" % (cmd, cmdsize))
            break
        if cmd in (LC_SEGMENT, LC_SEGMENT_64):
            f.seek(off)
            body = f.read(min(cmdsize, 4096))
            _read_segment(f, rep, body, cmd, cmdsize, endian, is64)
        elif cmd in DYLIB_LOAD_CMDS or cmd == LC_ID_DYLIB:
            f.seek(off)
            body = f.read(min(cmdsize, MAX_CMD_BODY))
            _read_dylib_cmd(rep, body, cmd, endian)
        elif cmd == LC_RPATH:
            f.seek(off)
            body = f.read(min(cmdsize, MAX_CMD_BODY))
            _read_rpath_cmd(rep, body, endian)
        elif cmd == LC_LOAD_DYLINKER:
            f.seek(off)
            body = f.read(min(cmdsize, MAX_CMD_BODY))
            _read_dylinker_cmd(rep, body, endian)
        elif cmd == LC_SYMTAB and symtab is None:
            f.seek(off)
            body = f.read(24)
            if len(body) >= 24:
                symtab = struct.unpack_from(endian + "IIII", body, 8)
        off += cmdsize
    # 符号表在命令表**之后**读：strtab/symtab 的偏移是文件绝对偏移，与命令表无关
    if symtab is not None:
        _read_symtab(f, rep, symtab, endian, is64)
    return rep


def _read_segment(f, rep, body, cmd, cmdsize, endian, is64):
    if len(body) < 72:
        return
    segname = body[8:24].split(b"\x00")[0].decode("latin1", "replace")
    if is64:
        vmaddr, vmsize, fileoff, filesize = struct.unpack_from(endian + "QQQQ", body, 24)
        nsects = struct.unpack_from(endian + "I", body, 64)[0]
        shdr = 72
        shsize = 80
    else:
        vmaddr, vmsize, fileoff, filesize = struct.unpack_from(endian + "IIII", body, 24)
        nsects = struct.unpack_from(endian + "I", body, 48)[0]
        shdr = 56
        shsize = 68
    hint = ""
    sb = segname.encode("latin1")
    if any(h in sb for h in GPU_SEG_HINTS):
        hint = segname
    rep.sections.append(Section(name=segname or "<unnamed-seg>", vaddr=vmaddr,
                                vsize=vmsize, file_off=fileoff, file_size=filesize,
                                kind="segment", gpu_hint=hint))
    if nsects > MAX_SECTS:
        rep.notes.append("Mach-O: 段 %s 的节数 %d 超上限" % (segname, nsects))
        nsects = MAX_SECTS
    for i in range(nsects):
        o = shdr + i * shsize
        if o + 32 > len(body):
            break
        sectname = body[o:o + 16].split(b"\x00")[0].decode("latin1", "replace")
        sname = body[o + 16:o + 32].split(b"\x00")[0].decode("latin1", "replace")
        if is64:
            addr, size = struct.unpack_from(endian + "QQ", body, o + 32)
            soff = struct.unpack_from(endian + "I", body, o + 48)[0]
        else:
            addr, size = struct.unpack_from(endian + "II", body, o + 32)
            soff = struct.unpack_from(endian + "I", body, o + 40)[0]
        rep.sections.append(Section(name="%s,%s" % (sname, sectname), vaddr=addr,
                                    vsize=size, file_off=soff, file_size=size,
                                    kind="section"))


def _cstr_in(buf, off, limit=MAX_NAME):
    """在**已读入内存**的字节串里取 NUL 结尾字符串（不碰文件指针）。"""
    if off is None or off < 0 or off >= len(buf):
        return ""
    end = buf.find(b"\x00", off)
    if end < 0:
        end = len(buf)
    return buf[off:end][:limit].decode("latin1", "replace")


def _read_dylib_cmd(rep, body, cmd, endian):
    """dylib_command: cmd(4) cmdsize(4) name.offset(4) ts(4) cur(4) compat(4) + name。

    `name.offset` 是**相对本命令起始处**的偏移，按 ABI 必须 >= 24。
    偏移非法时写 note 跳过，**不猜** —— 一个假的依赖名比没有依赖名更糟。
    """
    if len(body) < 24:
        rep.notes.append("Mach-O: cmd=0x%x 命令体只有 %d 字节（<24），跳过"
                         % (cmd, len(body)))
        return
    name_off = struct.unpack_from(endian + "I", body, 8)[0]
    if name_off < 24 or name_off >= len(body):
        rep.notes.append("Mach-O: cmd=0x%x 的 name.offset=%d 非法（命令体 %d 字节）"
                         % (cmd, name_off, len(body)))
        return
    nm = _cstr_in(body, name_off)
    if not nm:
        return
    if cmd == LC_ID_DYLIB:
        rep.dependencies.append(Dependency(name=nm, kind=DEP_ID_DYLIB,
                                          origin=rep.path, detail="install name"))
        rep.notes.append("Mach-O: LC_ID_DYLIB=%s" % nm)
    else:
        rep.dependencies.append(Dependency(
            name=nm, kind=DEP_LOAD_DYLIB, origin=rep.path,
            detail=DYLIB_LOAD_CMDS.get(cmd, "cmd=0x%x" % cmd)))


def _read_rpath_cmd(rep, body, endian):
    """rpath_command: cmd(4) cmdsize(4) path.offset(4) + path。"""
    if len(body) < 12:
        rep.notes.append("Mach-O: LC_RPATH 命令体只有 %d 字节（<12），跳过"
                         % len(body))
        return
    off = struct.unpack_from(endian + "I", body, 8)[0]
    if off < 12 or off >= len(body):
        rep.notes.append("Mach-O: LC_RPATH 的 path.offset=%d 非法" % off)
        return
    p = _cstr_in(body, off)
    if p:
        rep.dependencies.append(Dependency(name=p, kind=DEP_RPATH,
                                           origin=rep.path, detail="LC_RPATH"))


def _read_dylinker_cmd(rep, body, endian):
    """dylinker_command: cmd(4) cmdsize(4) name.offset(4) + name —— 头只有 **12** 字节
    （与 dylib_command 的 24 不同；混用会把链接器路径当成库名）。"""
    if len(body) < 12:
        rep.notes.append("Mach-O: LC_LOAD_DYLINKER 命令体 %d 字节（<12），跳过"
                         % len(body))
        return
    off = struct.unpack_from(endian + "I", body, 8)[0]
    if off < 12 or off >= len(body):
        rep.notes.append("Mach-O: LC_LOAD_DYLINKER 的 name.offset=%d 非法" % off)
        return
    p = _cstr_in(body, off)
    if p:
        rep.dependencies.append(Dependency(name=p, kind=DEP_LOAD_DYLINKER,
                                           origin=rep.path,
                                           detail="LC_LOAD_DYLINKER"))


def _read_symtab(f, rep, sym, endian, is64):
    """LC_SYMTAB + nlist/nlist_64 -> 导出（N_EXT|N_SECT）与未定义（N_EXT|N_UNDF）。

    只收**外部**符号（N_EXT）：内部/调试符号对「跨库归因」没有意义，收进来
    只会把导出表灌满噪声。名字里的前导下划线**原样保留**（归一在 attribute.py）。
    """
    symoff, nsyms, stroff, strsize = sym
    ent = 16 if is64 else 12
    if nsyms <= 0:
        return
    if nsyms > MAX_SYMTAB_SYMS:
        rep.notes.append("Mach-O: LC_SYMTAB 符号数 %d 超上限，截断到 %d"
                         % (nsyms, MAX_SYMTAB_SYMS))
        nsyms = MAX_SYMTAB_SYMS
    if strsize > MAX_STRTAB:
        rep.notes.append("Mach-O: 字符串表 %d 字节超上限，截断到 %d"
                         % (strsize, MAX_STRTAB))
        strsize = MAX_STRTAB
    if strsize <= 0:
        rep.notes.append("Mach-O: LC_SYMTAB 的 strsize=%d，符号名不可读，跳过"
                         % strsize)
        return
    try:
        f.seek(stroff)
        strs = f.read(strsize)
    except OSError as e:
        rep.notes.append("Mach-O: 字符串表读取失败 %s" % e)
        return
    n_exp = n_imp = n_skip = 0
    for i in range(nsyms):
        try:
            f.seek(symoff + i * ent)
            b = f.read(ent)
        except OSError:
            break
        if len(b) < ent:
            rep.notes.append("Mach-O: 符号表在 idx=%d 处被截断" % i)
            break
        strx = struct.unpack_from(endian + "I", b, 0)[0]
        n_type = b[4]
        n_sect = b[5]
        if is64:
            value = struct.unpack_from(endian + "Q", b, 8)[0]
        else:
            value = struct.unpack_from(endian + "I", b, 8)[0]
        if (n_type & N_STAB) or not (n_type & N_EXT):
            n_skip += 1
            continue
        nm = _cstr_in(strs, strx)
        if not nm:
            continue
        t = n_type & N_TYPE
        if t == N_UNDF:
            kind = SYM_IMPORT
            n_imp += 1
        elif t == N_SECT and n_sect != 0:
            kind = SYM_EXPORT
            n_exp += 1
        else:
            n_skip += 1
            continue
        rep.symbols.append(Symbol(name=nm, kind=kind, origin=rep.path,
                                  address=value, section=".symtab"))
    if n_skip:
        rep.notes.append("Mach-O: LC_SYMTAB 跳过 %d 个非外部/调试符号" % n_skip)
    rep.scanned_bytes += nsyms * ent + len(strs)
