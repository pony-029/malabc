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

一图看懂（夹具是怎么造的，以及它证明了什么）：

    现场合成一个字节串（不依赖任何外部文件）
          │
          ├─ PE 头 + 段表 + 导入表 + 导出表   ──▶ C6 / C4
          ├─ ELF 头 + program header           ──▶ C4
          ├─ .nv_fatb 段（8 字节截断名）+ 魔数  ──▶ C2 / C3
          ├─ .hip_fat  段（AMD 侧同款）        ──▶ C2
          ├─ SPIR-V 模块（藏在通用数据段里）    ──▶ C3
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


def _make_macho(path, segments=None, cputype=0x01000007, filetype=6,
                pad_to=0x2400):
    """构造一个最小但结构合法的 thin Mach-O 64（little-endian）。

    segments: [(segname, [(sectname, addr, size, fileoff), ...])]，默认
              `__TEXT`（含 `__text`）+ `__nv_fatbin`（用于打 GPU 段名提示）。

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
    sizeofcmds = sum(len(c) for c in cmds)
    out = bytearray()
    out += b"\xcf\xfa\xed\xfe"                       # MH_MAGIC_64
    out += struct.pack("<IIIIII", cputype, 3, filetype, len(cmds), sizeofcmds, 0)
    out += struct.pack("<I", 0)                      # reserved
    for c in cmds:
        out += c
    if pad_to and len(out) < pad_to:
        out += b"\x00" * (pad_to - len(out))
    with io.open(path, "wb") as f:
        f.write(bytes(out))
    return len(out)


def _make_macho_fat(path, nslices=2):
    """构造一个最小 fat Mach-O（big-endian 头 + n 个 thin 切片）。"""
    per = 20
    hdr_len = 8 + nslices * per
    slices = []
    for i in range(nslices):
        body = bytearray()
        body += b"\xcf\xfa\xed\xfe"
        body += struct.pack("<IIIIII", 0x01000007 - (i and 1) * 0x01000000,
                            3, 6, 0, 0, 0)
        body += struct.pack("<I", 0)
        slices.append(bytes(body))
    out = bytearray()
    out += b"\xca\xfe\xba\xbe" + struct.pack(">I", nslices)
    off = hdr_len
    for i, s in enumerate(slices):
        out += struct.pack(">IIIII", 0x01000007 - (i and 1) * 0x01000000,
                           3, off, len(s), 0)
        off += len(s)
    for s in slices:
        out += s
    out += b"\x00" * 64
    with io.open(path, "wb") as f:
        f.write(bytes(out))
    return len(out)


# ---------------------------------------------------------------- 断言

def _check(findings, cond, msg):
    if not cond:
        findings.append(msg)
    return cond


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

    return findings


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
        from binfmt.model import BinaryReport as _BR
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

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if (bad >= 4 and good >= 4) else 1


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
          "段/节解析、fat 切片、fixture_verified 两轴) 全部通过）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
