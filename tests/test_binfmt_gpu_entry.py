# -*- coding: utf-8 -*-
"""`binfmt/gpu.py`（638 行）：**段名前缀剥离**与 **Itanium 反解名**。

这两个纯函数都在"把二进制里的名字变成人能读的名字"这条路上，错法各不相同：

* `section_base_name` 削多了 → 段名残缺，后面按段名找 kernel 会全部落空；
  削少了 → 带 `slice[0]:` 前缀的段名进了报表，用户看到的是内部标记；
* `demangle_itanium` 解不开时**必须给空串**，不能原样回吐 ——
  回吐会让 `_Z3addii` 直接当成函数名出现在图里，看起来像"解析成功了"。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for sub in ("", "binfmt"):
    p = os.path.join(ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)


def test_fat_slice_prefix_is_stripped():
    """`slice[0]:__TEXT,__text` → `__TEXT,__text`（前缀只由 fat 合并产生）。"""
    from binfmt import gpu as G

    assert G.section_base_name("slice[0]:__TEXT,__text") == "__TEXT,__text"
    assert G.section_base_name("slice[3]:__DATA,__const") == "__DATA,__const"


def test_no_prefix_is_left_untouched():
    """**反向**：没有 `slice[i]:` 前缀时一个字节都不动（ELF 段名叫 `.nv_fatb`）。"""
    from binfmt import gpu as G

    for name in (".nv_fatb", ".text", ".rodata.str1.1", ""):
        assert G.section_base_name(name) == name, \
            "%r 被误改成了 %r" % (name, G.section_base_name(name))


def test_itanium_demangle_basic_forms():
    """能解开最常见的两种：自由函数 `_Z3addii`、成员 `_ZN3Foo3barEv`。"""
    from binfmt import gpu as G

    assert G.demangle_itanium("_Z3addii") == "add"
    assert G.demangle_itanium("_ZN3Foo3barEv") == "Foo::bar"


def test_undemangleable_returns_empty_not_echo():
    """**关键语义**：解不开时给空串，**不能原样回吐**。

    回吐会让调用方以为"解开了"，于是 `_Zxyz` 这种内部符号直接进报表；
    而空串是可判定的——调用方据此保留原名或跳过。
    """
    from binfmt import gpu as G

    for name in ("plain_name", "_Z", ""):
        got = G.demangle_itanium(name)
        assert got == "", "%r 解不开却返回了 %r（应给空串）" % (name, got)
