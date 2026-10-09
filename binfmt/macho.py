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
"""
import io
import struct

from .model import (
    CONTAINER_MACHO, MAX_CHUNK, Section, Symbol, BinaryReport, SYM_EXPORT,
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
        off += cmdsize
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
