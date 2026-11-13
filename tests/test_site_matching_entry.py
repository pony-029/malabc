# -*- coding: utf-8 -*-
"""`site_matching.py`（仓根）：**匹配口径**的纯函数。

## 为什么这层值得单独一个文件

`入口与流水线` 有 22 个根脚本，但只有 2 个测试文件 import 过它们 —— 于是
"这一层有没有人测"长期是空白。这组判据挑的是**口径类**函数：它们不报错、
只是"数得不一样"，而数个数的差异会一路放大到覆盖率/命中率报表里。

四条性质各自独立：
* 子串计数 vs 词边界计数 —— 同一段文本必须给出**不同**的数（否则词边界是假的）；
* 命名空间拆分 —— `a::b::c` 与 `std::vector` 的"标识符部分"；
* `token_regex` 必须真的带词边界（`foobar` 不能匹配 `foo`）；
* `is_phrase` —— 含空格的 token 是"短语"，不含的是"词"。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_substring_and_wordbound_differ():
    """同一段文本：子串计数 3、词边界计数 2 —— 两者**必须不同**。

    如果它们相等，说明某个函数退化成另一个的别名，词边界静默失效：
    搜 `foo` 会把 `foobar` 也算进去，命中数虚高。
    """
    import site_matching as S

    text = "foo foobar foo"
    assert S.count_substring(text, "foo") == 3
    assert S.count_wordbound(text, "foo") == 2
    assert S.count_substring(text, "foo") != S.count_wordbound(text, "foo")


def test_namespace_split_and_ident_part():
    """`a::b::c` 拆三段；`std::vector` 的标识符部分是 `vector`。"""
    import site_matching as S

    assert S.namespace_parts("a::b::c") == ("a", "b", "c")
    assert S.ident_part("std::vector") == "vector"
    # 不含命名空间时原样返回
    assert S.ident_part("plain") == "plain"


def test_token_regex_has_word_boundary():
    """`token_regex("foo")` 必须能匹配 `foo`、**不能**匹配 `foobar`。"""
    import site_matching as S

    pat = re.compile(S.token_regex("foo"))
    assert pat.search("foo") is not None
    assert pat.search("foobar") is None, "词边界失效（foobar 被当成 foo）"
    assert pat.search("a foo b") is not None


def test_is_phrase_distinguishes_space():
    """含空格的 token 是短语，不含的是词。"""
    import site_matching as S

    assert S.is_phrase("a b") is True
    assert S.is_phrase("ab") is False
