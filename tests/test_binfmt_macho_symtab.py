# -*- coding: utf-8 -*-
"""`binfmt/macho.py` 的 **LC_SYMTAB 符号归类**（合成夹具，本机无 Mach-O 样本）。

三条性质，每条都对应一种"报表看起来正常"的错法：

* **导出 vs 导入**：`N_EXT|N_SECT` 是导出、`N_EXT|N_UNDF` 是导入 —— 判反了，
  "这个符号是谁提供的"整张归因表就反了；
* **前导下划线原样保留**：Mach-O 里 C 符号带 `_`（源码 `foo` → 符号 `_foo`）。
  这一层**故意不归一**（归一发生在 `attribute.py`，且只对 macho 容器做）——
  在这里去掉下划线，`_foo` 就会和别的容器的合法 C 名字 `_foo` 混淆；
* **非外部符号要跳过并说出来**：静默丢弃会让"我明明定义了它"变成查不出的怪事。
"""
import os
import shutil
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for sub in ("", "binfmt"):
    p = os.path.join(ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)

MH_MAGIC_64 = 0xFEEDFACF
LC_SYMTAB = 0x2
N_EXT = 0x01
N_UNDF = 0x00
N_SECT = 0x0E


def _macho_with_symtab(syms):
    """`syms = [(name, n_type)]` → 完整 thin Mach-O 字节。"""
    strtab = b"\x00"
    idx = {}
    for name, _ in syms:
        idx[name] = len(strtab)
        strtab += name.encode() + b"\x00"

    hdr_size, cmd_size, ent = 32, 24, 16
    symoff = hdr_size + cmd_size
    stroff = symoff + ent * len(syms)

    body = b"".join(struct.pack("<IBBHQ", idx[n], t, 1, 0, 0x1000)
                    for n, t in syms)
    hdr = struct.pack("<IIIIIIII", MH_MAGIC_64, 0x0100000C, 0, 6, 1,
                      cmd_size, 0, 0)
    cmd = struct.pack("<IIIIII", LC_SYMTAB, cmd_size, symoff, len(syms),
                      stroff, len(strtab))
    return hdr + cmd + body + strtab


def _parse(data):
    from binfmt import macho as M

    tmp = os.environ.get("M2C_TMP")
    d = tempfile.mkdtemp(prefix="sym_",
                         dir=tmp if tmp and os.path.isdir(tmp) else None)
    try:
        p = os.path.join(d, "libs.dylib")
        with open(p, "wb") as f:
            f.write(data)
        return M.parse(p)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_export_and_import_are_distinguished():
    """`N_EXT|N_SECT` → 导出；`N_EXT|N_UNDF` → 导入（判反则归因表整张反）。"""
    rep = _parse(_macho_with_symtab([("_foo", N_EXT | N_SECT),
                                     ("_bar", N_EXT | N_UNDF)]))
    got = dict((s.name, s.kind) for s in rep.symbols)
    assert got.get("_foo") == "export", "定义在段内的外部符号没被判导出：%r" % (got,)
    assert got.get("_bar") == "import", "未定义的外部符号没被判导入：%r" % (got,)


def test_leading_underscore_is_preserved():
    """**前导下划线必须原样保留**（归一不在这层做）。"""
    rep = _parse(_macho_with_symtab([("_foo", N_EXT | N_SECT)]))
    names = [s.name for s in rep.symbols]
    assert "_foo" in names, "下划线被提前剥掉了：%r" % (names,)
    assert "foo" not in names, "名字被归一了（应留给 attribute.py）：%r" % (names,)


def test_non_external_symbols_are_skipped_but_reported():
    """非外部符号要跳过，**并在 notes 里说出跳过了几个**（不能静默丢）。"""
    rep = _parse(_macho_with_symtab([("_foo", N_EXT | N_SECT),
                                     ("local_only", N_SECT)]))
    names = [s.name for s in rep.symbols]
    assert "local_only" not in names, "内部符号被收进导出表：%r" % (names,)
    assert any("非外部" in n or "跳过" in n for n in rep.notes), \
        "跳过了符号却没说：%r" % (rep.notes[:3],)


def test_no_symtab_means_no_symbols():
    """**反向**：没有 LC_SYMTAB 时不能凭空造符号（也不能崩）。"""
    hdr = struct.pack("<IIIIIIII", MH_MAGIC_64, 0x0100000C, 0, 6, 0, 0, 0, 0)
    rep = _parse(hdr)
    assert list(rep.symbols) == [], "无符号表却报出符号：%r" % (rep.symbols,)
    assert rep.bits == 64 and rep.arch == "aarch64"
