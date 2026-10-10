#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""binfmt 护栏：合成夹具 + 契约断言 + 两向自证。

为什么用合成夹具而不是真实 GPU 库：
  CI / 他人机器上没有 Ollama 的 349MB CUDA 库。真实文件用于**探索**（探针），
  合成夹具用于**回归**（护栏）。两者互补，不可互相替代 —— 本文件只做后者，
  但保留一条「若真实语料存在则顺手验证」的路径（见 verify_real_corpus）。

被强制的契约（来自 R31 六帽分析的黑帽 K2/K3 与 F7）：
  C1  parseable=False 的 GPU blob **必须**有非空 reason（不许静默说谎）
  C2  段名截断形态能被识别：.nv_fatb / .nvFatBi / .hip_fat / .hipFatB
  C3  GPU 段名未命中时，magic 兜底必须能发现 SPIR-V / fatbin
  C4  非二进制输入不得被误判为 PE/ELF/Mach-O
  C5  0xCAFEBABE 且结构不合理者不得被误判为 Mach-O fat（Java class 消歧）
  C6  PE 依赖名必须全为可打印 ASCII（防「导入表越界读出 2532 条垃圾」复现）
  C7  PTX 的 `.entry <ident>(` 必须**后随左括号**，假命中一律不得放行
  C8  Mach-O 的「无真实语料」必须传播为 BinaryReport.verified=False 并渲染进报告
  C9  合成 Mach-O 夹具（LC_SEGMENT_64 段/节 + fat 切片）必须真解析出来；
      `fixture_verified`（有夹具）与 `verified`（有真实语料）**两轴分开**，
      报告措辞必须区分，不得把合成夹具冒充成真实语料验证
  C10 Mach-O 的**依赖指令**必须被读出：LC_ID_DYLIB / LC_LOAD_DYLIB /
      LC_LOAD_WEAK_DYLIB / LC_REEXPORT_DYLIB / LC_LOAD_UPWARD_DYLIB / LC_RPATH /
      LC_LOAD_DYLINKER —— 一种形态漏读，就等于对一个平台瞎了；依赖名必须是
      可打印 ASCII（与 C6 同款纪律）
  C11 Mach-O 的 **LC_SYMTAB** 外部符号（导出 / 未定义）必须被读出，
      且**内部与调试符号不得混进导出表**（混进去会让归因把私有符号当成对外接口）
  C12 **家族名归一**（`buildsys.library_family`）两向：`libfoo.so.1` 与
      `libfoo.so.1.2.3`、`libfoo.1.dylib` 与 `libfoo.1.2.3.dylib` 必须归一成
      同一个家族名；不同库必须分得开；且 `missing_dependencies` 不得把
      搜索路径（rpath / runpath / dyld）当成「你还想加哪个库」
  C13 **fat（universal）Mach-O 必须逐片解析**：依赖、导出符号、段表三样都要
      从**每一片**来（只读第一片 ⇒ 第二片独有的依赖读不出，判据用「只在一片里
      出现的名字」当证人）；同名片（同名的 install name / 同一批导出）必须
      **去重但保留切片下标**；片内偏移必须**重基**成容器绝对偏移；读不懂的片
      必须被**点名**（不许静默丢片）；fat 的 `slice[i]:` 段名前缀不许把 GPU
      段名提示打瞎（提示表按精确名查）

一图看懂（夹具是怎么造的，以及它证明了什么）：

    现场合成一个字节串（不依赖任何外部文件）
          │
          ├─ PE 头 + 段表 + 导入表 + 导出表   ──▶ C6 / C4
          ├─ ELF 头 + program header           ──▶ C4
          ├─ .nv_fatb 段（8 字节截断名）+ 魔数  ──▶ C2 / C3
          ├─ .hip_fat  段（AMD 侧同款）        ──▶ C2
          ├─ SPIR-V 模块（藏在通用数据段里）    ──▶ C3
          ├─ fat 头 + 两片**完整** thin Mach-O  ──▶ C13（逐片依赖/符号/段表）
          └─ "parseable=False 但不给 reason"   ──▶ C1 必须红（反例）
          │
          ▼
    交给 binfmt 解析 → 断言契约 → 结论

  为什么造假的而不拿真的：CI / 他人机器上没有 Ollama 的 349MB CUDA 库。
  真实文件用于**探索**（探针 probe_r1/r2/r5/r9），合成夹具用于**回归**（本护栏）。
  两者互补，不可互相替代 —— 本文件只做后者，但保留一条「若真实语料存在则顺手
  验证」的路径（见 verify_real_corpus），存在就多一道交叉确认。

用法：
  python tools/check_binfmt_fixtures.py             # 检查
  python tools/check_binfmt_fixtures.py --selftest   # 两向自证
退出码：0 = 通过；1 = 发现违规；2 = 缺输入/环境不可用
"""
import io
import os
import struct
import sys
import tempfile

# R62/P5：「质量门表」里本门那一行的**签名**（本门自己的判据族，
# 或本门独有的机制名）。它必须逐字出现在两处：
#   ① 本门的成功行（下面 main() 打印的那一行）；
#   ② README.md / README_CN.md 里本门那一行。
# 对手方 = tools/check_readme_parity.py 的 P5（表行内容 ⇄ 门）。
ROW_SIGNATURE = "C1–C13"

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

HAS_BINFMT = True
try:
    import binfmt
except ImportError:
    HAS_BINFMT = False


# ---------------------------------------------------------------- 夹具生成

def _make_pe(path, sections=(), imports=(), exports=(), machine=0x8664):
    """构造一个最小但结构合法的 PE32+。

    sections: [(name(<=8B), payload_bytes)]
    imports : [dll_name, ...]
    exports : [symbol_name, ...]
    """
    sec_payloads = list(sections)
    n_extra = (1 if imports else 0) + (1 if exports else 0)
    blob = bytearray()

    # --- 先把 section 数据按 RVA 顺序排好 ---
    RVA_BASE = 0x1000
    ptr = 0x400                     # 段数据文件偏移起点
    laid = []
    rva = RVA_BASE
    for nm, payload in sec_payloads:
        laid.append((nm, rva, ptr, payload))
        rva += max(len(payload), 0x1000)
        ptr += max(len(payload), 0x200)
    imp_rva = exp_rva = 0
    imp_data = b""
    exp_data = b""

    # 导入表：每个描述符 20B，末尾一个全 0 描述符；名字紧跟其后
    if imports:
        imp_rva = rva
        n_imp = len(imports)
        descs_sz = 20 * (n_imp + 1)
        descs = bytearray()
        name_area = bytearray()
        for dll in imports:
            off = descs_sz + len(name_area)      # 相对 imp_rva
            nb = dll.encode("latin1") + b"\x00"
            name_area += nb
            descs += struct.pack("<IIIII", 0x999, 0, 0, imp_rva + off, 0x999)
        descs += b"\x00" * 20
        imp_data = bytes(descs) + bytes(name_area)
        rva += 0x1000

    # 导出表：目录(40B) + AddressOfFunctions + AddressOfNames + DLL名 + 名字区
    if exports:
        exp_rva = rva
        n_exp = len(exports)
        dir_sz = 40
        addrf_off = dir_sz
        addrn_off = addrf_off + 4 * n_exp
        dllname = b"fixture.dll\x00"
        dllname_off = addrn_off + 4 * n_exp
        name_area_off = dllname_off + len(dllname)
        dirb = bytearray(b"\x00" * dir_sz)
        struct.pack_into("<I", dirb, 12, exp_rva + dllname_off)   # Name
        struct.pack_into("<I", dirb, 20, n_exp)                   # NumberOfFunctions
        struct.pack_into("<I", dirb, 24, n_exp)                   # NumberOfNames
        struct.pack_into("<I", dirb, 28, exp_rva + addrf_off)     # AddressOfFunctions
        struct.pack_into("<I", dirb, 32, exp_rva + addrn_off)     # AddressOfNames
        farr = b"".join(struct.pack("<I", exp_rva + 0x200 + i * 4)
                        for i in range(n_exp))
        narr = bytearray()
        narea = bytearray()
        cur = name_area_off
        for sym in exports:
            nb = sym.encode("latin1") + b"\x00"
            narr += struct.pack("<I", exp_rva + cur)
            narea += nb
            cur += len(nb)
        exp_data = (bytes(dirb) + farr + bytes(narr) + dllname + bytes(narea))
        rva += 0x1000

    # --- 段表 ---
    sec_headers = []
    all_secs = list(laid)
    if imports:
        all_secs.append((".rdata", imp_rva, 0x800, imp_data))
    if exports:
        all_secs.append((".edata", exp_rva, 0xA00, exp_data))
    for nm, srva, sptr, payload in all_secs:
        nmb = nm.encode("latin1")[:8].ljust(8, b"\x00")
        sec_headers.append(nmb + struct.pack(
            "<IIIIIIHHI", max(len(payload), 1), srva, max(len(payload), 0x200),
            sptr, 0, 0, 0, 0, 0x60000020))

    nsec = len(sec_headers)
    opt_size = 240
    pe_off = 0x40
    opt_off = pe_off + 4 + 20
    sec_off = opt_off + opt_size
    hdr_end = sec_off + 40 * nsec

    out = bytearray(b"\x00" * hdr_end)
    out[0:2] = b"MZ"
    struct.pack_into("<I", out, 0x3C, pe_off)
    out[pe_off:pe_off + 4] = b"PE\x00\x00"
    struct.pack_into("<HHIIIHH", out, pe_off + 4, machine, nsec, 0, 0, 0,
                     opt_size, 0x2000)
    opt = bytearray(b"\x00" * opt_size)
    struct.pack_into("<H", opt, 0, 0x20B)
    struct.pack_into("<Q", opt, 24, 0x180000000)
    struct.pack_into("<I", opt, 108, 16)
    struct.pack_into("<II", opt, 112 + 0 * 8, exp_rva, 0x400)
    struct.pack_into("<II", opt, 112 + 1 * 8, imp_rva, 20 * (len(imports) + 1) if imports else 0)
    out[opt_off:opt_off + opt_size] = opt
    for i, h in enumerate(sec_headers):
        out[sec_off + i * 40: sec_off + (i + 1) * 40] = h

    # --- 段数据 ---
    need = hdr_end
    for nm, srva, sptr, payload in all_secs:
        need = max(need, sptr + len(payload))
    if len(out) < need:
        out += b"\x00" * (need - len(out))
    for nm, srva, sptr, payload in all_secs:
        out[sptr:sptr + len(payload)] = payload
    del blob
    with io.open(path, "wb") as f:
        f.write(bytes(out))


def _make_elf(path, machine=62, etype=2, osabi=0, abiver=0, sections=()):
    """构造一个最小 ELF64（含节名表）。

    sections: [(name, payload)]
    """
    EH = 64
    SH = 64
    shstr = b"\x00"
    names = {0: 0}
    for nm, _ in sections:
        names[nm] = len(shstr)
        shstr += nm.encode("latin1") + b"\x00"
    names[".shstrtab"] = len(shstr)
    shstr += b".shstrtab\x00"

    data_off = EH
    payloads = []
    for nm, payload in sections:
        payloads.append((data_off, payload))
        data_off += len(payload)
    shstr_off = data_off
    data_off += len(shstr)

    shoff = data_off
    nsec = len(sections) + 2          # NULL + sections + shstrtab
    out = bytearray(b"\x00" * (shoff + SH * nsec))
    out[0:4] = b"\x7fELF"
    out[4] = 2
    out[5] = 1
    out[6] = 1
    out[7] = osabi
    out[8] = abiver
    struct.pack_into("<HHI", out, 16, etype, machine, 1)
    struct.pack_into("<Q", out, 40, shoff)
    struct.pack_into("<HHHHH", out, 54, 64, 0, SH, nsec,
                     nsec - 1)   # e_shstrndx = shstrtab
    for i, (nm, payload) in enumerate(sections):
        off, _ = payloads[i]
        out[off:off + len(payload)] = payload
        o = shoff + SH * (i + 1)
        struct.pack_into("<IIQQQQIIQQ", out, o, names[nm], 1, 0, 0, off,
                         len(payload), 0, 0, 1, 0)
    out[shstr_off:shstr_off + len(shstr)] = shstr
    o = shoff + SH * (nsec - 1)
    struct.pack_into("<IIQQQQIIQQ", out, o, names[".shstrtab"], 3, 0, 0,
                     shstr_off, len(shstr), 0, 0, 1, 0)
    with io.open(path, "wb") as f:
        f.write(bytes(out))


def _seg64(segname, vmaddr, vmsize, fileoff, filesize, sects):
    """一个 LC_SEGMENT_64 命令的字节串（含它的节表）。

    sects: [(sectname, segname, addr, size, offset)]，每节固定 80 字节。
    布局严格对齐 loader.h：
        cmd(4) cmdsize(4) segname[16] vmaddr(8) vmsize(8) fileoff(8) filesize(8)
        maxprot(4) initprot(4) nsects(4) flags(4)  → 共 72 字节
    """
    body = bytearray()
    body += struct.pack("<II", 0x19, 72 + 80 * len(sects))
    body += segname.encode("latin1").ljust(16, b"\x00")
    body += struct.pack("<QQQQ", vmaddr, vmsize, fileoff, filesize)
    body += struct.pack("<IIII", 7, 5, len(sects), 0)
    for sn, sgn, addr, size, off in sects:
        body += sn.encode("latin1").ljust(16, b"\x00")
        body += sgn.encode("latin1").ljust(16, b"\x00")
        body += struct.pack("<QQIIIIIIII", addr, size, off, 0, 0, 0, 0, 0, 0, 0)
    return bytes(body)


def _mk_cmd(cmd, name):
    """造一条「命令 + 尾部字符串」的 load command。

    头长度**按命令类型**分（这是 R68 特意踩过的一个坑）：
        dylib_command    （LC_ID_DYLIB / LC_LOAD_*_DYLIB）头 24 字节
        rpath_command    （LC_RPATH）                     头 12 字节
        dylinker_command （LC_LOAD_DYLINKER）             头 12 字节
    用错长度 ⇒ name.offset 落在字符串中间 ⇒ 读出半截名字或直接跳过。
    """
    base = 12 if cmd in (0x8000001C, 0xE) else 24
    raw = name.encode("latin1") + b"\x00"
    body = struct.pack("<II", cmd, 0) + struct.pack("<I", base)
    if base == 24:
        body += struct.pack("<III", 0, 0x10000, 0x10000)
    body += raw
    while len(body) % 8:
        body += b"\x00"
    return struct.pack("<II", cmd, len(body)) + body[8:]


def _build_macho_bytes(segments=None, cputype=0x01000007, filetype=6,
                       pad_to=0x2400, dep_cmds=None, symtab=None):
    """造一个最小但结构合法的 thin Mach-O 64（little-endian），返回**字节**。

    R71 起，fat 夹具的每一片都要是一个**完整**的 thin Mach-O，所以「造 thin」
    这件事被拆出来成为纯函数（`_make_macho` 只剩「写盘」）。

    segments: [(segname, [(sectname, addr, size, fileoff), ...])]，默认
              `__TEXT`（含 `__text`）+ `__nv_fatbin`（用于打 GPU 段名提示）。
    dep_cmds: [(cmd, name)] —— 依赖指令（R68 的 C10）
    symtab  : (names, [n_type, ...]) —— LC_SYMTAB 外部符号（R68 的 C11）

    ⚠ 为什么刻意补零到 **> 4096 字节**（pad_to=0x2400）：
      旧实现里 `parse()` 先 `f.read(4096)`，`_parse_thin()` 又自己 `f.read(32)`，
      文件指针已在 4096。于是：
        * 输入 < 4096  → 第二次读返回空 → struct.error → 走 except 分支，**留下 note**
        * 输入 > 4096  → 第二次读拿到 4096 处的垃圾 → **安静地给出错误答案**
      真实 dylib 必然 > 4096 字节，所以真实世界的形态是后者（更危险）。
      夹具必须复现**危险的那一种**，否则护栏只挡住了会自己喊疼的失败。
    """
    if segments is None:
        segments = [
            ("__TEXT", [("__text", 0x1000, 0x100, 0x1000)]),
            ("__nv_fatbin", [("__nv_fatbin", 0x2000, 0x40, 0x2000)]),
        ]
    cmds = []
    vm = 0
    for segname, sects in segments:
        sects3 = [(sn, segname, addr, size, off) for sn, addr, size, off in sects]
        cmds.append(_seg64(segname, vm, 0x1000, vm, 0x1000, sects3))
        vm += 0x1000
    for cmd, name in (dep_cmds or []):
        cmds.append(_mk_cmd(cmd, name))
    # LC_SYMTAB 的 symoff/stroff 是**文件绝对偏移**，取决于命令表总长 ——
    # 先放一个 24 字节占位命令，算完偏移再回填（两遍布局，别猜）。
    sym_blob = str_blob = b""
    symoff = stroff = 0
    n_syms = 0
    if symtab is not None:
        names, types = symtab
        n_syms = len(names)
        _sb = bytearray(b"\x00")
        offs = []
        for n in names:
            offs.append(len(_sb))
            _sb += n.encode("latin1") + b"\x00"
        str_blob = bytes(_sb)
        sym_blob = b"".join(struct.pack("<IBBHQ", offs[i], types[i], 1, 0,
                                        0x1000 + i * 0x10)
                            for i in range(n_syms))
        cmds.append(b"\x00" * 24)
    sizeofcmds = sum(len(c) for c in cmds)
    if symtab is not None:
        body_len = 32 + sizeofcmds
        while body_len % 8:
            body_len += 1
        symoff = body_len
        stroff = symoff + len(sym_blob)
        cmds[-1] = struct.pack("<IIIIII", 0x2, 24, symoff, n_syms, stroff,
                               len(str_blob))
    out = bytearray()
    out += b"\xcf\xfa\xed\xfe"                       # MH_MAGIC_64
    out += struct.pack("<IIIIII", cputype, 3, filetype, len(cmds), sizeofcmds, 0)
    out += struct.pack("<I", 0)                      # reserved
    for c in cmds:
        out += c
    if symtab is not None:
        while len(out) < symoff:
            out += b"\x00"
        out += sym_blob + str_blob
    if pad_to and len(out) < pad_to:
        out += b"\x00" * (pad_to - len(out))
    return bytes(out)


def _make_macho(path, segments=None, cputype=0x01000007, filetype=6,
                pad_to=0x2400, dep_cmds=None, symtab=None):
    """把 `_build_macho_bytes` 的结果写盘，返回字节数（C9/C10/C11 的夹具入口）。"""
    data = _build_macho_bytes(segments=segments, cputype=cputype,
                              filetype=filetype, pad_to=pad_to,
                              dep_cmds=dep_cmds, symtab=symtab)
    with io.open(path, "wb") as f:
        f.write(data)
    return len(data)


def _make_macho_fat(path, nslices=2, slice_specs=None, raw=None):
    """构造一个 fat Mach-O（big-endian 头 + n 个切片）。

    slice_specs=None：切片是**只有头**的 thin Mach-O（ncmds=0）—— C9 用的最小形态。
    slice_specs=[kw, ...]：每片的 kwargs 交给 `_build_macho_bytes`，于是每片都是一个
        **完整**的 thin Mach-O（带依赖指令与符号表）—— R71 的 C13 用它。
    raw={idx: bytes}：把第 idx 片换成任意字节 —— 用于「读不懂的切片必须被**点名**」
        这条反向判据（C13 的坏样本）。

    返回 (fat 字节, [(idx, cputype, offset, size), ...])，切片表由本函数自己算 ——
    判据可以拿它当**独立期望**，不必信产品报出来的 offset。
    """
    per = 20
    hdr_len = 8 + nslices * per
    specs = list(slice_specs or [])
    raw = raw or {}
    blobs = []
    for i in range(nslices):
        if i in raw:
            blobs.append(raw[i])
            continue
        if specs:
            blobs.append(_build_macho_bytes(**specs[i]))
            continue
        body = bytearray()
        body += b"\xcf\xfa\xed\xfe"
        body += struct.pack("<IIIIII", 0x01000007 - (i and 1) * 0x01000000,
                            3, 6, 0, 0, 0)
        body += struct.pack("<I", 0)
        blobs.append(bytes(body))
    out = bytearray()
    out += b"\xca\xfe\xba\xbe" + struct.pack(">I", nslices)
    table = []
    off = hdr_len
    for i in range(nslices):
        cpu = (specs[i].get("cputype", 0x01000007) if specs
               else 0x01000007 - (i and 1) * 0x01000000)
        out += struct.pack(">IIIII", cpu, 3, off, len(blobs[i]), 0)
        table.append((i, cpu, off, len(blobs[i])))
        off += len(blobs[i])
    for b in blobs:
        out += b
    out += b"\x00" * 64
    data = bytes(out)
    with io.open(path, "wb") as f:
        f.write(data)
    return data, table


# ---------------------------------------------------------------- 断言

def _check(findings, cond, msg):
    if not cond:
        findings.append(msg)
    return cond


# ---------------------------------------------------------------- R68 判据（可被 analyze 与 selftest 共用的纯函数）

# C10：Mach-O 依赖期望表（(名字, 期望 kind)），顺序无关
DYLIB_EXPECT = (
    ("libfoo.1.dylib", "id_dylib"),
    ("libSystem.B.dylib", "load_dylib"),
    ("@rpath/libbar.dylib", "load_dylib"),
    ("libweak.dylib", "load_dylib"),
    ("libreexp.dylib", "load_dylib"),
    ("libup.dylib", "load_dylib"),
    ("@loader_path/../lib", "rpath"),
    ("/usr/lib/dyld", "load_dylinker"),
)


def _c10_check(findings, rep, expect=DYLIB_EXPECT):
    """Mach-O 依赖：名字与 kind **都要**对，且名字必须可打印 ASCII。"""
    got = {d.name: d.kind for d in rep.dependencies}
    for nm, kind in expect:
        if nm not in got:
            findings.append("C10: Mach-O 依赖缺失 %r（得到 %r）"
                            % (nm, sorted(got)))
        elif got[nm] != kind:
            findings.append("C10: Mach-O 依赖 %r 的 kind=%r（期望 %r）"
                            % (nm, got[nm], kind))
    for d in rep.dependencies:
        if any(ord(c) < 32 or ord(c) > 126 for c in d.name):
            findings.append("C10: Mach-O 依赖名含非可打印字符 %r" % d.name[:24])
    return findings


def _c11_check(findings, rep, must_export, must_not_appear):
    """Mach-O 的 LC_SYMTAB：外部导出必须在，内部符号必须不在。"""
    exports = [s.name for s in rep.symbols if s.kind == "export"]
    for nm in must_export:
        if nm not in exports:
            findings.append("C11: Mach-O 导出符号缺失 %r（得到 %r）"
                            % (nm, exports))
    for nm in must_not_appear:
        if nm in exports:
            findings.append("C11: Mach-O 把**内部符号** %r 当成导出了" % nm)
    return findings


def _c12_check(findings):
    """家族名归一：同族必须归一，异族必须分得开。

    ⚠ 缺符号时**不许**让 traceback 冒出去：本门的两向证据就是「拿这一版门
    跑 R68 之前的产品 ⇒ 必须红」，而那一刻产品里还没有 `library_family`。
    traceback 也是 rc=1，但它把「C12 判据报了红」降级成「程序崩了」——
    红得没有信息量。这里改成一条**能读的** finding。
    """
    try:
        from binfmt.buildsys import library_family as lf
    except ImportError as e:
        findings.append("C12: 产品里没有 binfmt.buildsys.library_family（%s）"
                        " —— 家族名归一尚未实现" % e)
        return findings
    same = [
        (["libfoo.so", "libfoo.so.6", "libfoo.so.1.2.3"], "libfoo.so"),
        (["libfoo.1.dylib", "libfoo.1.2.3.dylib", "libfoo.dylib"], "libfoo.dylib"),
        (["@rpath/libbar.dylib", "libbar.1.dylib"], "libbar.dylib"),
        (["/usr/lib/libz.so.1", "libz.so"], "libz.so"),
        (["libc.so.6"], "libc.so"),
        # R68 补：`.framework` 那一支曾经**不可达**（basename 取在判断之前）。
        # 三种真实写法各一份，把这一支钉成活代码 —— 夹具是它唯一的看守。
        (["Foo.framework/Foo",
          "@rpath/Foo.framework/Versions/A/Foo",
          "/System/Library/Frameworks/Foo.framework/Foo"], "foo.framework"),
    ]
    for group, want in same:
        for n in group:
            got = lf(n)
            if got != want:
                findings.append("C12: library_family(%r)=%r（期望 %r）"
                                % (n, got, want))
    diff = [("libfoo.so", "libbar.so"), ("liba.dylib", "libb.dylib"),
            ("libx.dll", "liby.dll"),
            ("Foo.framework/Foo", "Bar.framework/Bar")]
    for a, b in diff:
        if lf(a) == lf(b):
            findings.append("C12: %r 与 %r 被误并成同一家族 %r" % (a, b, lf(a)))
    if lf("") != "":
        findings.append("C12: library_family('')=%r（期望空串）" % lf(""))
    return findings


def _c12_missing_check(findings, provided_reports, expect_absent, expect_present):
    """missing_dependencies 的两向：该被家族名吸收的不出现，真缺的必须出现，
    搜索路径一律不算库。"""
    try:
        from binfmt.attribute import missing_dependencies
    except ImportError as e:
        findings.append("C12: 产品里没有 binfmt.attribute.missing_dependencies"
                        "（%s）" % e)
        return findings
    needs = [o["needs"] for o in missing_dependencies(provided_reports)]
    for nm in expect_absent:
        if nm in needs:
            findings.append("C12: 已提供（同家族）的 %r 仍被报成「未提供」" % nm)
    for nm in expect_present:
        if nm not in needs:
            findings.append("C12: 真缺的 %r 没被报出来（得到 %r）" % (nm, needs))
    for nm in ("@loader_path/../lib", "/usr/lib/dyld"):
        if nm in needs:
            findings.append("C12: 搜索路径/链接器 %r 被当成库报出来了" % nm)
    return findings


# ------------------------------------------- C13（R71）：fat Mach-O **逐片**解析
#
# 动因（R68 §2-3 / §8 的 C18-1，R69/R70 仍未做）：真实 macOS 二进制**大多是
# universal**，而 R71 之前 `flavour == "fat"` 只把切片清单写进 notes —— 依赖与符号
# 只在 thin 路径读，于是「这个 universal dylib 依赖谁」的答案**恒为空**。
#
# 判据的核心是**期望表由夹具规格反推**（下面的 FAT_SLICE_SPECS / FAT_EXPECT_*），
# 完全不看产品自报的切片表 —— `_make_macho_fat` 自己算 offset/size 并返回，
# 判据拿它当独立期望（见 R71 探针 `_r71/probe_r71_fat_macho.py` 同一套设计）。
FAT_SLICE_SPECS = (
    dict(cputype=0x01000007,                        # x86_64
         segments=[("__TEXT", [("__text", 0x1000, 0x100, 0)]),
                   ("__nv_fatbin", [("__nv_fatbin", 0x2000, 0x40, 0x2000)])],
         dep_cmds=[(0xD, "libfat.dylib"),           # LC_ID_DYLIB：**两片同名**
                   (0xC, "libSystem.B.dylib"),      # 两片都有
                   (0xC, "libonly0.dylib")],        # 只在第 0 片
         symtab=(["_fa_export", "_fa_priv"],        # 0x0F=导出, 0x0E=内部（不许混入）
                 [0x0F, 0x0E])),
    dict(cputype=0x0100000C,                        # arm64
         segments=[("__TEXT", [("__text", 0x1000, 0x100, 0)]),
                   ("__nv_fatbin", [("__nv_fatbin", 0x2000, 0x40, 0x2000)])],
         dep_cmds=[(0xD, "libfat.dylib"),
                   (0xC, "libSystem.B.dylib"),
                   (0xC, "@rpath/libonly1.dylib")],  # 只在第 1 片
         symtab=(["_fb_export"], [0x0F])),
)
# (名字, kind, 必须点名的切片下标) —— 「只在一片的」是**证明两片都读了**的证人；
# 「两片都有的」同时证明去重（表不许按片数膨胀）与归属（下标不许丢）。
FAT_EXPECT_DEPS = (
    ("libfat.dylib", "id_dylib", (0, 1)),
    ("libSystem.B.dylib", "load_dylib", (0, 1)),
    ("libonly0.dylib", "load_dylib", (0,)),
    ("@rpath/libonly1.dylib", "load_dylib", (1,)),
)
FAT_EXPECT_EXPORTS = ("_fa_export", "_fb_export")
FAT_EXPECT_INTERNAL = ("_fa_priv",)


def _c13_named(field, idxs):
    """`detail`/`section` 里是否**恰好**点名了这些切片下标（形如 `slice[0,1] …`）。"""
    i = field.find("slice[")
    if i < 0:
        return False
    j = field.find("]", i)
    if j < 0:
        return False
    got = [x.strip() for x in field[i + 6:j].split(",") if x.strip()]
    return got == [str(x) for x in idxs]


def _c13_check_report(findings, rep, table, data, tag="C13"):
    """C13 的判据核心（**纯函数**：只吃一份 report + 夹具自己算的期望）。

    table / data 来自 `_make_macho_fat` 的返回值，**不是**产品的读数 —— 这是
    「不许用被测对象当它自己的量具」在本门的落点。
    """
    if rep.flavour != "fat":
        findings.append("%s: fat 标记缺失（flavour=%r）" % (tag, rep.flavour))
        return findings
    got = {}
    for d in rep.dependencies:
        if d.name in got:
            findings.append("%s: 依赖 %r 出现两次 —— 同名片没有去重（表会按片数膨胀）"
                            % (tag, d.name))
        got[d.name] = d
    for nm, kind, idxs in FAT_EXPECT_DEPS:
        if nm not in got:
            findings.append("%s: fat 里读不出依赖 %r（得到 %r）"
                            % (tag, nm, sorted(got)))
            continue
        if got[nm].kind != kind:
            findings.append("%s: 依赖 %r 的 kind=%r（期望 %r）"
                            % (tag, nm, got[nm].kind, kind))
        if not _c13_named(got[nm].detail, idxs):
            findings.append("%s: 依赖 %r 的 detail=%r 没点名切片 %r"
                            % (tag, nm, got[nm].detail,
                               [str(x) for x in idxs]))
    exports = [s.name for s in rep.symbols if s.kind == "export"]
    for nm in FAT_EXPECT_EXPORTS:
        if nm not in exports:
            findings.append("%s: fat 里读不出导出符号 %r（得到 %r）"
                            % (tag, nm, exports))
    for nm in FAT_EXPECT_INTERNAL:
        if nm in exports:
            findings.append("%s: 内部符号 %r 被当成导出了" % (tag, nm))
    if len(exports) != len(set(exports)):
        findings.append("%s: 导出表里有重名 —— 同名片没有去重" % tag)
    secs = rep.sections
    if len(secs) != 4 * len(table):
        findings.append("%s: fat 段/节数 %d（期望 %d = 4 × %d 片）"
                        % (tag, len(secs), 4 * len(table), len(table)))
    for s in secs:
        if not s.name.startswith("slice["):
            findings.append("%s: 段/节 %r 没有切片前缀 —— 两片的 __TEXT 会混在一起"
                            % (tag, s.name))
    for i, _cpu, off, size in table:
        if data[off:off + 4] != b"\xcf\xfa\xed\xfe":
            findings.append("%s: **夹具自洽失败**：切片 %d 的起点不是 thin 魔数"
                            "（期望表本身错了，不是产品的错）" % (tag, i))
            continue
        mine = [s for s in secs if s.name.startswith("slice[%d]:" % i)]
        if not mine:
            findings.append("%s: slice[%d] 一条段/节都没有（该片没被解析）" % (tag, i))
            continue
        lo = min(s.file_off for s in mine)
        if lo != off:
            findings.append("%s: slice[%d] 的最小 file_off=%d ≠ 该片容器起点 %d"
                            " —— 片内偏移没被**重基**成容器绝对偏移"
                            % (tag, i, lo, off))
        for s in mine:
            if not (off <= s.file_off < off + size):
                findings.append("%s: slice[%d] 的段 %r file_off=%d 落在该片之外"
                                "（片=[%d,%d)）—— 会读到别的切片的字节"
                                % (tag, i, s.name, s.file_off, off, off + size))
    return findings


def _c13_named_slice(notes, idx):
    """`notes` 里有没有一条把 `slice[idx]` 的**读不懂**点名了。

    可点名的四种「读不懂」：不是 thin 魔数 / 越过文件末尾 / offset-size 非法 /
    读取失败 —— 每一个都是**放弃解析**，所以每一个都必须留下带片号的话。
    """
    tag = "slice[%d]" % idx
    for n in notes:
        if tag not in n:
            continue
        for why in ("不是 thin Mach-O", "越过文件末尾", "offset/size 非法",
                    "读取失败"):
            if why in n:
                return True
    return False


def _c13_check_broken_slice(findings, tmpdir, tag="C13"):
    """C13 的反向：**读不懂的切片必须被点名**，其余片照常解析。

    两向都造：
      * 只有第 1 片是垃圾 ⇒ 第 0 片的依赖照样读得出，且 notes 必须点名 `slice[1]`；
      * 两片都是垃圾     ⇒ 0 依赖，且两条 note 各点一片，**不许崩**。
    """
    p1 = os.path.join(tmpdir, "f_fat_bad1.dylib")
    _make_macho_fat(p1, 2, slice_specs=FAT_SLICE_SPECS, raw={1: b"A" * 128})
    rep1 = binfmt.parse(p1, with_gpu=False)
    if rep1.flavour != "fat":
        findings.append("%s: 坏片夹具的 flavour=%r（期望 fat）"
                        % (tag, rep1.flavour))
    got1 = dict((d.name, d.kind) for d in rep1.dependencies)
    if got1.get("libonly0.dylib") != "load_dylib":
        findings.append("%s: 第 1 片是垃圾时，第 0 片的依赖也读不出来了（得到 %r）"
                        % (tag, sorted(got1)))
    if "_fa_export" not in [s.name for s in rep1.symbols]:
        findings.append("%s: 第 1 片是垃圾时，第 0 片的导出也读不出来了" % tag)
    if not _c13_named_slice(rep1.notes, 1):
        findings.append("%s: 读不懂的 slice[1] **没有被点名**（notes 里找不到"
                        "带片号的读不懂理由）—— 静默丢片比报错更糟" % tag)

    p2 = os.path.join(tmpdir, "f_fat_bad_all.dylib")
    _make_macho_fat(p2, 2, slice_specs=FAT_SLICE_SPECS,
                    raw={0: b"B" * 128, 1: b"C" * 128})
    rep2 = binfmt.parse(p2, with_gpu=False)
    if rep2.container != "macho":
        findings.append("%s: 两片都是垃圾时容器识别失败（%s）"
                        % (tag, rep2.container))
    if rep2.dependencies or rep2.symbols:
        findings.append("%s: 两片都读不懂却报出了 依赖 %d / 符号 %d（幻觉）"
                        % (tag, len(rep2.dependencies), len(rep2.symbols)))
    named = [i for i in range(2) if _c13_named_slice(rep2.notes, i)]
    if len(named) != 2:
        findings.append("%s: 两片都是垃圾时被点名的切片数 = %d（期望 2）"
                        % (tag, len(named)))
    return findings


def _c13_check_gpu_hint(findings, tmpdir, tag="C13"):
    """C13 的 GPU 侧：`slice[i]:` 前缀**不许**把 GPU 段名提示打瞎。

    fat 的段名带前缀（两片的 `__nv_fatbin` 会重名），而提示表是按**精确**名查的
    ⇒ 必须有一处剥前缀的实现（`binfmt.gpu.section_base_name`），并在 `analyze()`
    的两条查表路径上都用上。这里两向都钉：纯函数（剥 / 不剥）+ 行为（fat 上真出
    section_name 检出的 blob，且不可解析时必须给 reason —— 那是 C1 的契约）。
    """
    try:
        from binfmt.gpu import SECTION_HINTS, section_base_name as sbn
    except ImportError as e:
        findings.append("%s: 产品里没有 binfmt.gpu.section_base_name（%s）"
                        " —— fat 的段名前缀会打瞎提示表" % (tag, e))
        return findings
    if sbn("slice[1]:__nv_fatbin") != "__nv_fatbin":
        findings.append("%s: section_base_name('slice[1]:__nv_fatbin')=%r（期望 %r）"
                        % (tag, sbn("slice[1]:__nv_fatbin"), "__nv_fatbin"))
    if sbn(".nv_fatb") != ".nv_fatb":
        findings.append("%s: section_base_name 改了没有前缀的名字（%r）"
                        % (tag, sbn(".nv_fatb")))
    if SECTION_HINTS.get(sbn("slice[0]:__nv_fatbin")) != ("cuda", "fatbin"):
        findings.append("%s: 剥前缀后仍查不到提示（%r）"
                        % (tag, SECTION_HINTS.get(sbn("slice[0]:__nv_fatbin"))))
    p = os.path.join(tmpdir, "f_fat_gpu.dylib")
    _make_macho_fat(p, 2, slice_specs=FAT_SLICE_SPECS)
    rep = binfmt.parse(p, scan_cap=None)
    hit = [b for b in rep.gpu_blobs if b.detected_by == "section_name"]
    if not hit:
        findings.append("%s: fat 上按段名一条 GPU blob 都没检出（提示被打瞎）"
                        % tag)
    for b in hit:
        if not b.section.startswith("slice["):
            findings.append("%s: fat 的 GPU blob 段名 %r 没有切片归属"
                            % (tag, b.section))
        if not b.parseable and not b.reason:
            findings.append("%s: fat 上 parseable=False 的 blob 没有 reason"
                            "（C1 契约在 fat 路径上失守）" % tag)
    return findings


def analyze(tmpdir):
    """跑全部夹具，返回 findings 列表（空 = 通过）。"""
    findings = []
    if not HAS_BINFMT:
        return ["无法导入 binfmt 包（%s）" % _ROOT]

    pe = os.path.join(tmpdir, "f_pe.dll")
    _make_pe(pe, sections=[(".text", b"\x90" * 64)],
             imports=["kernel32.dll", "cublas64_12.dll"],
             exports=["cublasSgemm", "cublasDgemm"])
    rep = binfmt.parse(pe, with_gpu=False)
    _check(findings, rep.container == "pe", "C4: 合成 PE 未被识别为 pe")
    _check(findings, rep.arch == "x86_64",
           "C4: 合成 PE arch=%s（期望 x86_64）" % rep.arch)
    names = [s.name for s in rep.symbols]
    _check(findings, "cublasSgemm" in names,
           "PE 导出符号缺失 cublasSgemm（得到 %s）" % names[:5])
    deps = [d.name for d in rep.dependencies]
    _check(findings, "cublas64_12.dll" in deps,
           "PE 导入依赖缺失 cublas64_12.dll（得到 %s）" % deps)
    # C6：依赖名必须全是可打印 ASCII
    bad = [d for d in deps if any(ord(c) < 32 or ord(c) > 126 for c in d)]
    _check(findings, not bad, "C6: PE 依赖里出现非可打印名 %r" % bad[:3])

    elf = os.path.join(tmpdir, "f_elf.so")
    _make_elf(elf, machine=62, etype=3, sections=[(".text", b"\x90" * 32)])
    rep2 = binfmt.parse(elf, with_gpu=False)
    _check(findings, rep2.container == "elf",
           "C4: 合成 ELF 未被识别（%s）" % rep2.container)
    _check(findings, rep2.arch == "x86_64",
           "ELF arch=%s（期望 x86_64）" % rep2.arch)
    _check(findings, [s.name for s in rep2.sections].count(".text") == 1,
           "ELF 段表未解析出 .text")

    txt = os.path.join(tmpdir, "f.txt")
    with io.open(txt, "w", encoding="utf-8") as f:
        f.write("MZ this is not really a PE, no PE signature at e_lfanew\n")
    rep3 = binfmt.parse(txt, with_gpu=False)
    _check(findings, rep3.container == "",
           "C4: 伪 PE 文本被误判为 %s" % rep3.container)
    _check(findings, bool(rep3.notes), "C4: 无法识别时未留下 note（静默）")

    java = os.path.join(tmpdir, "F.class")
    with io.open(java, "wb") as f:
        f.write(b"\xca\xfe\xba\xbe" + struct.pack(">IHI", 0, 52, 0xCAFEBABE)
                + b"\x00" * 32)
    rep4 = binfmt.parse(java, with_gpu=False)
    _check(findings, rep4.container != "macho",
           "C5: Java class 被误判为 Mach-O fat")

    gpu = os.path.join(tmpdir, "f_gpu.dll")
    fatbin = b"\x50\xed\x55\xba" + b"\x01\x00\x10\x00" + struct.pack("<I", 32) + b"\x00" * 20
    _make_pe(gpu, sections=[(".text", b"\x90" * 32), (".nv_fatb", fatbin)])
    rep5 = binfmt.parse(gpu, scan_cap=None)
    _check(findings, any(b.backend == "cuda" for b in rep5.gpu_blobs),
           "C2: .nv_fatb 段未被识别为 CUDA blob")
    for b in rep5.gpu_blobs:
        if not b.parseable:
            _check(findings, bool(b.reason),
                   "C1: GPU blob %s parseable=False 却没有 reason" % b.section)

    idx = os.path.join(tmpdir, "f_idx.dll")
    _make_pe(idx, sections=[(".text", b"\x90" * 32),
                            (".nvFatBi", b"\xb1\x43\x62\x46" + b"\x01\x00\x00\x00"
                             + b"\x00\x00\x00\x00\x00\x00\x00\x00" + b"\x00" * 8)])
    rep6 = binfmt.parse(idx, scan_cap=None)
    _check(findings, any(b.section == ".nvFatBi" and b.index_entries >= 1
                         for b in rep6.gpu_blobs),
           "C2: .nvFatBi 索引段未被识别（index_entries）")

    hip = os.path.join(tmpdir, "f_hip.dll")
    _make_pe(hip, sections=[(".text", b"\x90" * 32), (".hip_fat", b"\x00" * 64)])
    rep7 = binfmt.parse(hip, scan_cap=None)
    _check(findings, any(b.backend == "hip" for b in rep7.gpu_blobs),
           "C2: .hip_fat 段未被识别为 HIP blob")

    spv = os.path.join(tmpdir, "f_spv.dll")
    # SPIR-V 头是 5 个 word（magic/version/generator/bound/schema）—— 漏掉 schema
    # 会让指令流起点偏移 4 字节，解析器从错误的偏移开始读，什么都提不到。
    mod = struct.pack("<IIIII", 0x07230203, 0x00010500, 0x000d000b, 64, 0)
    # OpEntryPoint: wc=4, op=15, model=5, id=3, name="m\0\0\0"
    mod += struct.pack("<III", (4 << 16) | 15, 5, 3)
    mod += b"m\x00\x00\x00"
    _make_pe(spv, sections=[(".text", b"\x90" * 32), (".rdata", mod + b"\x00" * 64)])
    rep8 = binfmt.parse(spv, scan_cap=None)
    _check(findings, any(b.detected_by == "magic_scan" for b in rep8.gpu_blobs),
           "C3: .rdata 里的 SPIR-V 未被 magic 兜底发现")
    found_spv = [k for b in rep8.gpu_blobs for k in b.kernels]
    _check(findings, "m" in found_spv,
           "C3: SPIR-V OpEntryPoint 名字未提取到（得到 %s）" % found_spv[:5])

    # C7（R33/C'4）：PTX 的严格判据 —— `.entry <ident>(` 必须**后随左括号**。
    # 反例：3 个「像 .entry 但不带括号」的假命中（真文件里 347 个命中只有 1 个是真的）。
    # 断言：只认那 1 个真 entry，绝不放行假命中。
    ptx_real = b".entry _Z9realentryv(\n"
    ptx_fake1 = b".entry not_an_entry\n"          # 名字后是换行，不是 (
    ptx_fake2 = b".entry alsofake "               # 名字后是空格，再后面不是 (
    ptx_fake3 = b".entry thirdfake\x00"           # 名字后直接 NUL
    body = (b"\x00" * 8 + ptx_fake1 + ptx_real + ptx_fake2 + ptx_fake3
            + b"\x00" * 8)
    ptx = os.path.join(tmpdir, "f_ptx.dll")
    _make_pe(ptx, sections=[(".text", b"\x90" * 32), (".nv_fatb", body)])
    rep9 = binfmt.parse(ptx, scan_cap=None)
    ptx_names = [k for b in rep9.gpu_blobs for k in b.kernels
                 if k.startswith("_Z9realentryv") or "fake" in k
                 or k == "not_an_entry"]
    _check(findings, "_Z9realentryv" in ptx_names,
           "C4: 真 PTX entry（带括号）未被提取（得到 %s）" % ptx_names)
    bad_ptx = [n for n in ptx_names
               if "fake" in n or n == "not_an_entry"]
    _check(findings, not bad_ptx,
           "C4: 假 PTX .entry（不带括号）被误当成 kernel：%s" % bad_ptx)

    # C8（R33/C'5）：Mach-O 的「未验证」必须传播到 BinaryReport.verified=False，
    # 而不是只写在 docstring 里。造一个结构合法的 thin Mach-O 64。
    macho = os.path.join(tmpdir, "f_macho.dylib")
    mh = bytearray()
    mh += b"\xcf\xfa\xed\xfe"                     # MH_MAGIC_64 (little)
    mh += struct.pack("<IIIIII", 0x01000007, 3, 6, 0, 0, 0)   # cputype,sub,filetype=6,ncmds=0
    with io.open(macho, "wb") as f:
        f.write(bytes(mh))
    rep10 = binfmt.parse(macho, with_gpu=False)
    _check(findings, rep10.container == "macho",
           "C8: 合成 Mach-O 未被识别（%s）" % rep10.container)
    _check(findings, getattr(rep10, "verified", True) is False,
           "C8: Mach-O 报告未标 verified=False（未验证状态没传播出源码）")
    # 报告正文里必须**看得见**这个限定（用户在报告里看不到 = 等于没说）
    txt = binfmt.to_text(rep10)
    _check(findings, "unverified" in txt.lower() or "未验证" in txt,
           "C8: Mach-O 报告正文里看不到「未验证」限定")
    # 反向：PE/ELF 是已验证的，不得被误标
    _check(findings, getattr(rep, "verified", False) is True,
           "C8: PE 报告被误标为未验证（反向判据失败）")

    # ---- C9（R36/C''6）：合成 Mach-O 夹具 —— 把「无真实语料」推进到「有夹具验证」 ----
    # 这段就是 R36 抓到 K9 的那个夹具：结构完整、> 4096 字节的 thin Mach-O 64。
    ma = os.path.join(tmpdir, "f_struct.dylib")
    _make_macho(ma)
    rep11 = binfmt.parse(ma, with_gpu=False)
    _check(findings, rep11.container == "macho",
           "C9: 结构夹具未被识别为 macho（%s）" % rep11.container)
    _check(findings, rep11.arch == "x86_64",
           "C9: Mach-O arch=%s（期望 x86_64）" % rep11.arch)
    _check(findings, rep11.bits == 64,
           "C9: Mach-O bits=%d（期望 64）" % rep11.bits)
    _check(findings, rep11.flavour == "dylib",
           "C9: Mach-O flavour=%r（期望 dylib）" % rep11.flavour)
    s9 = [s.name for s in rep11.sections]
    _check(findings, "__TEXT" in s9,
           "C9: LC_SEGMENT_64 的 __TEXT 段未解析（得到 %s）" % s9)
    _check(findings, "__TEXT,__text" in s9,
           "C9: __TEXT 段内的 __text 节未解析（得到 %s）" % s9)
    _check(findings, any(s.gpu_hint for s in rep11.sections),
           "C9: __nv_fatbin 的 GPU 段名提示未命中")
    _check(findings, getattr(rep11, "fixture_verified", False) is True,
           "C9: Mach-O 未记 fixture_verified=True（合成夹具验证没被记录）")
    _check(findings, getattr(rep11, "verified", True) is False,
           "C9: Mach-O 被误标 verified=True（合成夹具 ≠ 真实语料）")
    txt9 = binfmt.to_text(rep11)
    _check(findings, "真实语料" in txt9 and "合成夹具" in txt9,
           "C9: 报告没把「无真实语料」与「有合成夹具」分开写（等于没区分）")
    _check(findings, "未验证" not in binfmt.to_text(rep),
           "C9: PE（已经真实语料验证）的报告里出现了「未验证」行（反向判据失败）")

    mf = os.path.join(tmpdir, "f_fat.dylib")
    _make_macho_fat(mf, 2)
    rep12 = binfmt.parse(mf, with_gpu=False)
    _check(findings, rep12.container == "macho",
           "C9: fat Mach-O 未被识别（%s）" % rep12.container)
    _check(findings, rep12.flavour == "fat",
           "C9: fat 标记缺失（flavour=%r）" % rep12.flavour)

    # ---- C10（R68）：Mach-O 的依赖指令一族 ----
    dep = os.path.join(tmpdir, "f_deps.dylib")
    _make_macho(dep, segments=[("__TEXT", [("__text", 0x1000, 0x100, 0x1000)])],
                dep_cmds=[
                    (0xD, "libfoo.1.dylib"),              # LC_ID_DYLIB
                    (0xC, "libSystem.B.dylib"),           # LC_LOAD_DYLIB
                    (0xC, "@rpath/libbar.dylib"),         #   @rpath 形态
                    (0x80000018, "libweak.dylib"),        # LC_LOAD_WEAK_DYLIB
                    (0x8000001F, "libreexp.dylib"),       # LC_REEXPORT_DYLIB
                    (0x80000023, "libup.dylib"),          # LC_LOAD_UPWARD_DYLIB
                    (0x8000001C, "@loader_path/../lib"),  # LC_RPATH
                    (0xE, "/usr/lib/dyld"),               # LC_LOAD_DYLINKER
                ])
    rep_dep = binfmt.parse(dep, with_gpu=False)
    _check(findings, rep_dep.container == "macho",
           "C10: 依赖夹具未被识别（%s）" % rep_dep.container)
    _c10_check(findings, rep_dep)

    # ---- C11（R68）：LC_SYMTAB 外部符号 ----
    sa = os.path.join(tmpdir, "f_syms.dylib")
    _make_macho(sa, segments=[("__TEXT", [("__text", 0x1000, 0x100, 0x1000)])],
                symtab=(["_export_one", "_export_two",
                         "_private_helper", "_undef_three"],
                        [0x0F,                       # N_SECT|N_EXT -> export
                         0x0F,                       # N_SECT|N_EXT -> export
                         0x0E,                       # N_SECT      -> 内部，不收
                         0x01]))                     # N_UNDF|N_EXT -> import
    rep_sa = binfmt.parse(sa, with_gpu=False)
    _c11_check(findings, rep_sa, ("_export_one", "_export_two"),
               ("_private_helper",))
    kinds = {s.name: s.kind for s in rep_sa.symbols}
    _check(findings, kinds.get("_undef_three") == "import",
           "C11: N_UNDF|N_EXT 未被记成 import（得到 %r）" % kinds.get("_undef_three"))

    # ---- C12（R68）：家族名归一 + missing_dependencies 两向 ----
    _c12_check(findings)
    _c12_missing_check(
        findings,
        _mk_reports(("/p/libconsumer.so", [("libfoo.so.1", "needed"),
                                           ("/opt/weird/libmissing.so.4", "needed"),
                                           ("@loader_path/../lib", "rpath")]),
                    ("/p/libfoo.so.1.2.3", [("libfoo.1.dylib", "id_dylib")])),
        expect_absent=("libfoo.so.1",),
        expect_present=("/opt/weird/libmissing.so.4",))

    # ---- C13（R71）：fat Mach-O **逐片**解析 ----
    fat_rich = os.path.join(tmpdir, "f_fat_rich.dylib")
    fat_data, fat_table = _make_macho_fat(fat_rich, 2, slice_specs=FAT_SLICE_SPECS)
    rep13 = binfmt.parse(fat_rich, with_gpu=False)
    _c13_check_report(findings, rep13, fat_table, fat_data)
    _c13_check_broken_slice(findings, tmpdir)
    _c13_check_gpu_hint(findings, tmpdir)

    return findings


def _mk_reports(*specs):
    """按 (path, [(dep_name, dep_kind), ...]) 造 BinaryReport（给 C12 的两向用）。

    spec 里的 dep_kind 直接写字符串（"needed" / "id_dylib" / "rpath" ...），
    免得在谓词里 import 一堆常量 —— 这些字符串就是 model.py 的取值。
    """
    from binfmt.model import BinaryReport as _B, Dependency as _D
    out = []
    for spec in specs:
        if not spec:                     # 允许传 () 表示「没有提供任何报告」
            continue
        path, deps = spec
        r = _B(path=path)
        for nm, kind in deps:
            r.dependencies.append(_D(name=nm, kind=kind, origin=path))
        out.append(r)
    return out


def verify_real_corpus(findings):
    """顺手验证：真实 GPU 语料若存在则检查契约（不存在就跳过，不算失败）。"""
    cands = [
        r"E:\ollama\dist\lib\ollama\cuda_v12\cublas64_12.dll",
        r"E:\ollama\dist\lib\ollama\cuda_v12\ggml-cuda.dll",
        r"E:\ollama\dist\lib\ollama\vulkan\ggml-vulkan.dll",
    ]
    hit = [c for c in cands if os.path.isfile(c)]
    if not hit:
        print("  [SKIP] 真实 GPU 语料不在本机（不算失败）")
        return
    for p in hit:
        rep = binfmt.parse(p, scan_cap=2 << 20)
        for b in rep.gpu_blobs:
            if not b.parseable and not b.reason:
                findings.append("C1: 真实文件 %s 的 %s parseable=False 无 reason"
                                % (os.path.basename(p), b.section))
            if b.confidence_code_objects and b.suspect_code_objects and \
                    b.confidence_code_objects > b.suspect_code_objects:
                findings.append("C3: %s 的可信 code object 数 > 疑似数（判据矛盾）"
                                % os.path.basename(p))
        # 真实文件上不允许出现非可打印依赖名
        for d in rep.dependencies:
            if any(ord(c) < 32 or ord(c) > 126 for c in d.name):
                findings.append("C6: %s 依赖名含非可打印字符 %r"
                                % (os.path.basename(p), d.name[:20]))
        print("  [real] %-18s deps=%d symbols=%d" %
              (os.path.basename(p), len(rep.dependencies), len(rep.symbols)))


# ---------------------------------------------------------------- 自证

def selftest():
    """两向自证：坏样本要能红、好样本要能过。

    打印机器可读行：SELFTEST COUNTS {"bad": N, "good": M}
    """
    bad = 0
    good = 0
    with tempfile.TemporaryDirectory() as td:
        # 样本1（好）：正常夹具必须全过
        f1 = analyze(td)
        if not f1:
            good += 1
        else:
            print("  [selftest] 好样本意外报错：%s" % f1[:2])

        # 样本2（坏）：C1 断言必须能对「违规对象」报错。
        # 注意：不能靠喂坏输入触发 —— 实现自身保证 parseable=False 必带 reason，
        # 合法输入永远构造不出违规。所以自证对象是**断言函数本身**。
        from binfmt.model import GpuBlob
        vfind = []
        _check(vfind, bool(GpuBlob(section=".x", parseable=False, reason="").reason),
               "C1: parseable=False 却没有 reason")
        if vfind:
            bad += 1
        else:
            print("  [selftest] 坏样本1 未触发（C1 契约失去检测力）")

        # 样本2b（好）：同一个断言对合规对象不得误报（两向）
        gfind = []
        _check(gfind, bool(GpuBlob(section=".x", parseable=False,
                                   reason="有原因").reason),
               "C1: parseable=False 却没有 reason")
        if not gfind:
            good += 1
        else:
            print("  [selftest] 好样本2b 被误伤（C1 断言过严）")

        # 样本3（坏）：依赖名含控制字符必须被 C6 抓到
        pe = os.path.join(td, "bad2.dll")
        _make_pe(pe, sections=[(".text", b"\x90" * 32)], imports=["ok.dll"])
        rep3 = binfmt.parse(pe, with_gpu=False)
        fake = [d for d in rep3.dependencies] if rep3.dependencies else []
        broken = [{"name": "bad\x01name"}]
        detected = any(any(ord(c) < 32 for c in d["name"]) for d in broken + fake)
        if detected:
            bad += 1
        else:
            print("  [selftest] 坏样本2 未触发（C6 失去检测力）")

        # 样本4（坏）：Java class 消歧必须生效
        j = os.path.join(td, "bad3.class")
        with io.open(j, "wb") as f:
            f.write(b"\xca\xfe\xba\xbe" + struct.pack(">IHI", 0, 52, 1) + b"\x00" * 16)
        r4 = binfmt.parse(j, with_gpu=False)
        if r4.container != "macho":
            bad += 1
        else:
            print("  [selftest] 坏样本3 未触发（C5 消歧失效）")

        # 样本5（坏）：C8 断言必须能对「忘了标 verified=False 的 Mach-O」报错。
        # 注意：与样本2同理 —— 合法输入构造不出违规（实现自身会标 False），
        # 所以自证对象是**断言函数本身**：喂一个 container=macho 但 verified=True
        # 的违规对象，断言必须变红。
        from binfmt.model import BinaryReport as _BR, Dependency as _Dep, \
            Symbol as _Sym, Section as _Sec
        viol = _BR(path="x", container="macho", verified=True)
        c8find = []
        _check(c8find, getattr(viol, "verified", True) is False,
               "C8: Mach-O 未标 verified=False")
        if c8find:
            bad += 1
        else:
            print("  [selftest] 坏样本4 未触发（C8 未验证传播失效）")

        # 造一个真实 Mach-O 夹具，用于样本7（好）
        m = os.path.join(td, "good_macho.dylib")
        with io.open(m, "wb") as f:
            f.write(b"\xcf\xfa\xed\xfe"
                    + struct.pack("<IIIIII", 0x01000007, 3, 6, 0, 0, 0))

        # 样本6（好）：PE 不得被误标未验证（C8 反向）
        pe_ok = os.path.join(td, "good_pe.dll")
        _make_pe(pe_ok, sections=[(".text", b"\x90" * 16)])
        r6 = binfmt.parse(pe_ok, with_gpu=False)
        gfind2 = []
        _check(gfind2, getattr(r6, "verified", False) is True,
               "C8: PE 被误标为未验证")
        if not gfind2:
            good += 1
        else:
            print("  [selftest] 好样本6 被误伤（C8 反向判据过严）")

        # 样本7（好）：真实 Mach-O 夹具必须 verified=False 且报告正文可见限定
        r7 = binfmt.parse(m, with_gpu=False)
        gfind3 = []
        _check(gfind3, getattr(r7, "verified", True) is False,
               "C8: 真实 Mach-O 夹具未标 verified=False")
        _check(gfind3, ("unverified" in binfmt.to_text(r7).lower()
                        or "未验证" in binfmt.to_text(r7)),
               "C8: 报告正文里看不到「未验证」限定")
        if not gfind3:
            good += 1
        else:
            print("  [selftest] 好样本7 被误伤：%s" % gfind3[:1])

        # 样本8（好）：C9 的「两轴必须分开」装置 —— fixture_verified 真/假必须渲染出
        # **不同**的话，且两句都仍带「未验证」。若两句一模一样，说明区分装置失效。
        r_fx = _BR(path="x", container="macho", verified=False, fixture_verified=True)
        r_no = _BR(path="x", container="macho", verified=False, fixture_verified=False)
        t_fx, t_no = binfmt.to_text(r_fx), binfmt.to_text(r_no)
        if ("未验证" in t_fx and "未验证" in t_no and t_fx != t_no):
            good += 1
        else:
            print("  [selftest] 好样本8 被误伤（两轴措辞没有区分开）")

        # 样本9（坏）：C9 断言必须能对「没记夹具验证」的对象报红。
        # 与样本2/5 同理 —— 合法输入构造不出违规（macho.parse 自己会标 True），
        # 所以自证对象是**断言函数本身**。
        viol2 = _BR(path="x", container="macho", verified=False,
                    fixture_verified=False)
        c9find = []
        _check(c9find, getattr(viol2, "fixture_verified", False) is True,
               "C9: Mach-O 未记录合成夹具验证")
        if c9find:
            bad += 1
        else:
            print("  [selftest] 坏样本5 未触发（C9 夹具验证判据失去检测力）")

        # ---- R68：C10 / C11 / C12 各自的两向自证 ----
        # 样本10（坏）：一个**没解析出任何依赖**的 macho 报告必须让 C10 变红
        f10 = []
        _c10_check(f10, _BR(path="x", container="macho"))
        if f10:
            bad += 1
        else:
            print("  [selftest] 坏样本6 未触发（C10 对「零依赖」失去检测力）")

        # 样本11（好）：期望表全部满足的报告必须过 C10
        ok10 = _BR(path="x", container="macho")
        for nm, kind in DYLIB_EXPECT:
            ok10.dependencies.append(_Dep(name=nm, kind=kind, origin="x"))
        g10 = []
        _c10_check(g10, ok10)
        if not g10:
            good += 1
        else:
            print("  [selftest] 好样本9 被误伤（C10 过严）：%s" % g10[:1])

        # 样本12（坏）：把内部符号塞进导出表必须让 C11 变红
        f11 = _BR(path="x", container="macho")
        f11.symbols.append(_Sym(name="_private_helper", kind="export"))
        b11 = []
        _c11_check(b11, f11, ("_export_one",), ("_private_helper",))
        if b11:
            bad += 1
        else:
            print("  [selftest] 坏样本7 未触发（C11 对「内部符号混入」失去检测力）")

        # 样本13（好）：只含真导出的报告必须过 C11
        ok11 = _BR(path="x", container="macho")
        ok11.symbols.append(_Sym(name="_export_one", kind="export"))
        g11 = []
        _c11_check(g11, ok11, ("_export_one",), ("_private_helper",))
        if not g11:
            good += 1
        else:
            print("  [selftest] 好样本10 被误伤（C11 过严）：%s" % g11[:1])

        # 样本14（坏）：**拆掉家族归一**必须让 C12 变红（两向：证明判据有牙齿）
        f12a = []
        _c12_missing_check(
            f12a,
            _mk_reports(("/p/libconsumer.so", [("libfoo.so.1", "needed")]), ()),
            expect_absent=("libfoo.so.1",),      # 没人提供 -> 必然出现在 needs
            expect_present=())
        if f12a:
            bad += 1
        else:
            print("  [selftest] 坏样本8 未触发（C12 的「该报不报」方向失去检测力）")

        # 样本15（好）：提供同族文件的场景必须过（且搜索路径不出现）
        g12 = []
        _c12_missing_check(
            g12,
            _mk_reports(("/p/libconsumer.so", [("libfoo.so.1", "needed"),
                                               ("@loader_path/../lib", "rpath")]),
                        ("/p/libfoo.so.1.2.3", [])),
            expect_absent=("libfoo.so.1",), expect_present=())
        if not g12:
            good += 1
        else:
            print("  [selftest] 好样本11 被误伤（C12 过严）：%s" % g12[:1])

        # ---- R71：C13（fat 逐片解析）的两向自证 ----
        # 样本16（坏）：**一片都不读**的 fat 报告（这正是 R71 之前的行为）必须让 C13 红
        blind = _BR(path="x", container="macho", flavour="fat", arch="fat(2)")
        f13a = []
        _c13_check_report(f13a, blind, [(0, 7, 48, 9216), (1, 12, 9264, 9216)],
                          b"\xcf\xfa\xed\xfe" * 4)
        if f13a:
            bad += 1
        else:
            print("  [selftest] 坏样本9 未触发（C13 对「fat 零依赖」失去检测力）")

        # 样本17（坏）：**只读第一片**的报告必须红 —— 第二片独有的依赖是证人。
        # 为了让红**只有一条理由**，这一份报告的第 0 片部分是**完全合规**的
        # （段表带前缀、偏移重基、依赖与下标都对），唯一缺的是第 1 片的依赖。
        half = _BR(path="x", container="macho", flavour="fat", arch="fat(2)")
        for nm, kind, idxs in FAT_EXPECT_DEPS:
            if 1 in idxs and len(idxs) == 1:
                continue                      # 丢掉「只在第 1 片」的那一条
            half.dependencies.append(_Dep(name=nm, kind=kind, origin="x",
                                          detail="slice[%s] %s" % (
                                              ",".join(str(x) for x in idxs), kind)))
        for _snm, _soff in (("__TEXT", 0), ("__TEXT,__text", 0x1000),
                            ("__nv_fatbin", 0x1000), ("__nv_fatbin,__nv_fatbin",
                                                      0x2000)):
            half.sections.append(_Sec(name="slice[0]:" + _snm, file_off=48 + _soff,
                                      file_size=0x40, kind="segment"))
        f13b = []
        _c13_check_report(f13b, half, [(0, 7, 48, 9216)], b"\xcf\xfa\xed\xfe")
        if f13b:
            bad += 1
        else:
            print("  [selftest] 坏样本10 未触发（C13 对「只读第一片」失去检测力）")

        # 样本18（好）：真产品在**完整两片**的 fat 夹具上必须过 C13
        p13 = os.path.join(td, "selftest_fat_rich.dylib")
        d13, t13 = _make_macho_fat(p13, 2, slice_specs=FAT_SLICE_SPECS)
        g13 = []
        _c13_check_report(g13, binfmt.parse(p13, with_gpu=False), t13, d13)
        if not g13:
            good += 1
        else:
            print("  [selftest] 好样本12 被误伤（C13 过严）：%s" % g13[:1])

        # 样本19（坏）：**没有被点名**的 notes（只有切片清单）必须被判为「没点名」
        if not _c13_named_slice(["Mach-O: fat binary 含 2 个架构切片",
                                 "Mach-O:   slice[1] cputype=0x100000c"], 1):
            bad += 1
        else:
            print("  [selftest] 坏样本11 未触发（「读不懂的片必须点名」失去检测力）")

        # 样本20（好）：真产品对「第 1 片是垃圾」的夹具**必须**点名 slice[1]
        p13b = os.path.join(td, "selftest_fat_bad1.dylib")
        _make_macho_fat(p13b, 2, slice_specs=FAT_SLICE_SPECS, raw={1: b"A" * 128})
        if _c13_named_slice(binfmt.parse(p13b, with_gpu=False).notes, 1):
            good += 1
        else:
            print("  [selftest] 好样本13 被误伤（坏片真被点名了却没认出来）")

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    # 下界是**棘轮**：样本不许静默缩水。R71 从 8/8 提到 11/10（C13 加了两向各三条），
    # 提到实测值之后，谁删掉一个样本都会立刻红 —— 而不是「少了一条也没人知道」。
    return 0 if (bad >= 11 and good >= 10) else 1


# ---------------------------------------------------------------- main

def main(argv):
    binfmt_dir = None
    for i, a in enumerate(argv):
        if a == "--binfmt-dir" and i + 1 < len(argv):
            binfmt_dir = argv[i + 1]
    if binfmt_dir is not None:
        # 缺输入必须能红：指定目录下没有 binfmt 包 → 2（不是静默通过）
        if not os.path.isdir(os.path.join(binfmt_dir, "binfmt")):
            print("check_binfmt_fixtures: 缺输入 —— %s 下找不到 binfmt 包"
                  % binfmt_dir)
            return 2
    if "--selftest" in argv:
        if not HAS_BINFMT:
            print("check_binfmt_fixtures: 无法导入 binfmt —— 缺输入")
            return 2
        return selftest()
    if not HAS_BINFMT:
        print("check_binfmt_fixtures: FAIL 无法导入 binfmt 包（%s）" % _ROOT)
        return 2
    with tempfile.TemporaryDirectory() as td:
        findings = analyze(td)
        verify_real_corpus(findings)
    if findings:
        print("check_binfmt_fixtures: FAIL（%d 项违规）" % len(findings))
        for f in findings:
            print("  - %s" % f)
        return 1
    print("check_binfmt_fixtures: OK（PE/ELF 解析、GPU 段识别、magic 兜底、"
          "契约 C1/C2/C3/C4/C5/C6 + R33 新增 C7(PTX .entry 括号判据)/"
          "C8(Mach-O 未验证传播) + R36 新增 C9(合成 Mach-O 夹具：LC_SEGMENT_64 "
          "段/节解析、fat 切片、fixture_verified 两轴) + R68 新增 "
          "C10(Mach-O 依赖指令七种形态) / C11(LC_SYMTAB 外部符号，内部不得混入) / "
          "C12(库名家族归一 + 缺失依赖两向) + R71 新增 "
          "C13(fat 逐片解析：依赖/符号/段表两片都要读到、同名片去重且点名、"
          "片内偏移重基、读不懂的片必须被点名、GPU 段名提示不被前缀打瞎) 全部通过；"
          "判据族 %s）" % ROW_SIGNATURE)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
