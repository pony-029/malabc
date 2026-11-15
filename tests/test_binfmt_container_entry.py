# -*- coding: utf-8 -*-
"""`binfmt/container.sniff`：**解析器分派**。

整个分析链路的第一跳就是它 —— 判错方向，后面所有字段都是垃圾：

* 把 PE 当 ELF 解析 → 读出一堆错位字段，在很深的地方报一个无关错误；
* 把截断的 fat 当 Mach-O → 去读不存在的架构表；
* 认不出却返回 `'elf'` → 比返回 `''` 更糟（`''` 至少能让调用方跳过）。

所以判据盯两件事：**认得对的**、以及**认不出时老实说认不出**。
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


def _dir():
    tmp = os.environ.get("M2C_TMP")
    return tempfile.mkdtemp(prefix="cont_",
                            dir=tmp if tmp and os.path.isdir(tmp) else None)


def _put(d, name, data):
    p = os.path.join(d, name)
    with open(p, "wb") as f:
        f.write(data)
    return p


def _elf():
    return b"\x7fELF" + bytes([2, 1, 1]) + b"\x00" * 57


def _pe():
    b = bytearray(0x80)
    b[0:2] = b"MZ"
    struct.pack_into("<I", b, 0x3C, 0x40)
    b[0x40:0x44] = b"PE\x00\x00"
    return bytes(b)


def _fat(pad=True):
    head = (struct.pack(">I", 0xCAFEBABE) + struct.pack(">I", 1) +
            struct.pack(">iiIII", 0, 0, 0x100, 0x100, 0))
    return head + (b"\x00" * 0x300 if pad else b"")


def _thin():
    return struct.pack("<I", 0xFEEDFACF) + b"\x00" * 60


def test_dispatch_elf_and_pe():
    """ELF 与 PE 必须各自认对（这两类占绝大多数样本）。"""
    from binfmt import container as C

    d = _dir()
    try:
        assert C.sniff(_put(d, "a.elf", _elf())) == "elf"
        assert C.sniff(_put(d, "b.dll", _pe())) == "pe"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_dispatch_macho_thin_and_fat():
    """Mach-O 的 thin 与（结构完整的）fat 都要认成 `macho`。"""
    from binfmt import container as C

    d = _dir()
    try:
        assert C.sniff(_put(d, "t.macho", _thin())) == "macho"
        assert C.sniff(_put(d, "f.fat", _fat())) == "macho"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_truncated_fat_is_not_macho():
    """**截断的 fat 不能认成 macho** —— 否则解析器会去读不存在的架构表。"""
    from binfmt import container as C

    d = _dir()
    try:
        got = C.sniff(_put(d, "t.fat", _fat(pad=False)))
        assert got != "macho", "截断的 fat 被认成 macho（会越界读架构表）"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_unknown_and_missing_return_empty():
    """认不出时给空串；文件不存在也不抛（"还没构建"是正常状态）。"""
    from binfmt import container as C

    d = _dir()
    try:
        assert C.sniff(_put(d, "x.bin", b"\x00" * 64)) == ""
        assert C.sniff(_put(d, "y.txt", b"hello")) == ""
        assert C.sniff(os.path.join(d, "nope")) == ""
    finally:
        shutil.rmtree(d, ignore_errors=True)
