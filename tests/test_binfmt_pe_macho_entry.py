# -*- coding: utf-8 -*-
"""`binfmt/pe.py` + `binfmt/macho.py`：**最小头夹具**（不需要真实二进制）。

这两个 sniff 决定"要不要把这个文件送进解析器"。判错的方向有两边：
* **假阳**：非 PE 文件被当 PE 解析 → 读到一堆垃圾字段，在很深的地方报无关错误；
* **假阴**：真 PE 被跳过 → 报表里那个 dll 的导出符号**整块消失**，而没人发现。

四条判据：

| 判据 | 断言 |
|---|---|
| PE 正常 | `MZ` + `e_lfanew → "PE\\0\\0"` → True |
| PE 错签名 | 同为 MZ 但签名是 `XX\\0\\0` → False |
| PE 非 MZ | 全零头 → False |
| Mach-O thin | `0xFEEDFACF`(LE) 与 `0xFEEDFACE`(BE) 都认；垃圾不认 |
| Mach-O fat | `0xCAFEBABE` 认；**尾巴被截断时必须判 False**（`looks_like_fat` 会比大小） |
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for sub in ("", "binfmt"):
    p = os.path.join(ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)


def _pe(magic=b"PE\x00\x00"):
    head = bytearray(0x80)
    head[0:2] = b"MZ"
    struct.pack_into("<I", head, 0x3C, 0x40)      # e_lfanew
    head[0x40:0x44] = magic
    return bytes(head)


def _fat(narch=2, off=0, size=0):
    """fat 头。`off/size` 全零**不合法**：`looks_like_fat` 要求每个架构的
    `offset >= 头长度` 且 `offset+size <= fsize`（用来与 Java class 消歧）。"""
    head = struct.pack(">I", 0xCAFEBABE) + struct.pack(">I", narch)
    for _ in range(narch):
        head += struct.pack(">iiIII", 0, 0, off, size, 0)   # cputype/cpusubtype/off/size/align
    return head


def _fat_valid():
    """一个**结构合理**的 fat 头：1 个架构，数据落在 0x100 起、长 0x100。"""
    return _fat(narch=1, off=0x100, size=0x100)


def test_pe_sniff_three_ways():
    """PE：正常 True；签名错 False；非 MZ False。"""
    from binfmt import pe as PE

    assert PE.sniff(_pe()) is True
    assert PE.sniff(_pe(b"XX\x00\x00")) is False, "签名错了竟然还通过"
    assert PE.sniff(b"\x00" * 0x80) is False, "非 MZ 竟然通过"


def test_macho_thin_magic_both_endians():
    """thin Mach-O：小端与大端的 magic 都要认，垃圾不认。"""
    from binfmt import macho as M

    assert M.thin_magic(struct.pack("<I", 0xFEEDFACF) + b"\x00" * 28) is True
    assert M.thin_magic(struct.pack(">I", 0xFEEDFACE) + b"\x00" * 28) is True
    assert M.thin_magic(b"\x00" * 32) is False


def test_macho_fat_magic_and_sniff():
    """fat Mach-O（0xCAFEBABE）要被认出。"""
    from binfmt import macho as M

    fat = _fat()
    assert M.fat_magic(fat) is True
    assert M.sniff(fat) is True


def test_truncated_fat_is_rejected():
    """**结构合理性**：架构表越界 → 不是合法 fat（这是与 Java class 消歧的关键）。"""
    from binfmt import macho as M

    good = _fat_valid()
    assert M.looks_like_fat(good, 0x400) is True, "结构合理的 fat 被判非法"
    # 文件只有 64 字节，而架构数据从 0x100 开始 → 越界
    assert M.looks_like_fat(good, 64) is False, \
        "架构表越界的 fat 被当合法（解析器会去读不存在的字节）"
    # 全零架构表（offset=0 小于头长度）同样不合法
    assert M.looks_like_fat(_fat(narch=2), 0x400) is False, \
        "offset=0 的架构表竟然判合法"
