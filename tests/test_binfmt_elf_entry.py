# -*- coding: utf-8 -*-
"""`binfmt/elf.py`（506 行）：**最小 ELF 头夹具**（不依赖磁盘上的真二进制）。

这三个函数只看头字节，所以可以用 64 字节的手工夹具精准验证 —— 而它们决定
"这个文件能不能按标准 ELF 解析"，判错的后果是：把 CUDA cubin 当普通 ELF 硬解，
读出一堆垃圾字段，然后在很深的地方报一个无关的错误。

| 函数 | 判据 |
|---|---|
| `sniff` | `\\x7fELF` + 至少 16 字节；`MZ` 与短字节都要 False |
| `classify` | 普通 ELF → 不是 GPU；`osabi=CUDA`/`e_machine=EM_CUDA` → `cuda`；AMDGPU → `hip` |
| `is_standard_layout` | `e_type` 越界 / `e_shoff` 过大 → False 且说明原因 |

⚠ 实测记录：`classify` 判的是「**像不像 GPU code object**」，不是"是不是 ELF"。
普通 ELF 返回 `(False, '', '')` 是**正确**的 —— 第一版我按"判 ELF 类型"理解，
差点把正确行为写成失败。
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


def _head(osabi=0, machine=0x3E, e_type=2, shoff=0x1000, size=64):
    """造一个 64 字节的 ELF64 头（只填被用到的字段）。"""
    ident = b"\x7fELF" + bytes([2, 1, 1, osabi]) + b"\x00" * 8
    rest = struct.pack("<HHIQQQIHHHHHH", e_type, machine, 1, 0x1000, 0, shoff,
                       0, 64, 0, 0, 64, 40, 0)
    return (ident + rest)[:size]


def test_sniff_needs_magic_and_length():
    """`sniff`：magic 对且够长才算；`MZ`、短字节都 False。"""
    from binfmt import elf as E

    assert E.sniff(_head()) is True
    assert E.sniff(b"MZ" + b"\x00" * 60) is False
    assert E.sniff(b"\x7fELF") is False, "13 字节的半截文件竟然通过"


def test_classify_detects_gpu_code_objects():
    """GPU code object 必须被认出；普通 ELF 必须**不**被认成 GPU。"""
    from binfmt import elf as E

    assert E.classify(_head()) == (False, "", ""), "普通 ELF 被误判成 GPU"

    cuda = E.classify(_head(osabi=E.ELFOSABI_CUDA))
    assert cuda[0] is True and cuda[1] == "cuda", "osabi=CUDA 没被认出：%r" % (cuda,)

    cuda2 = E.classify(_head(machine=E.EM_CUDA))
    assert cuda2[0] is True and cuda2[1] == "cuda", "e_machine=EM_CUDA 没被认出：%r" % (cuda2,)

    hip = E.classify(_head(machine=E.EM_AMDGPU))
    assert hip[0] is True and hip[1] == "hip", "AMDGPU 没被认成 hip：%r" % (hip,)


def test_standard_layout_rejects_nonstandard_fields():
    """`e_type` 越界 / `e_shoff` 过大 → 不可按标准 ELF 解析，且说明原因。"""
    from binfmt import elf as E

    ok, why = E.is_standard_layout(_head(), 2, 0x1000)
    assert ok is True and why == "", "正常 ELF 被判不可解析：%r" % (why,)

    bad_type, why1 = E.is_standard_layout(_head(), 0x8000, 0x1000)
    assert bad_type is False, "cubin 的 e_type=0x8000 竟然判标准"
    assert "e_type" in why1, "理由没指明 e_type：%r" % (why1,)

    bad_off, why2 = E.is_standard_layout(_head(), 2, 1 << 48)
    assert bad_off is False, "越界的 e_shoff 竟然判标准"
    assert "e_shoff" in why2, "理由没指明 e_shoff：%r" % (why2,)
