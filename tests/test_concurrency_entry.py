# -*- coding: utf-8 -*-
"""`concurrency.py`（仓根）：并发 token 的**普查口径**。

这层的两个坑都不报错，只是给一个"看起来合理"的数：

* `census()` 的键名漂移 —— 消费方按 `per_lang` / `by_outcome` 取值，改名即静默清零；
* `lookup()` 对未知 token 必须返回 `"unknown"` 而不是 `None`/`""` ——
  后者会被写成 "未知 = 不并发"，把一个**没数据**的结论伪装成**否定**结论。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_census_shape_is_stable():
    """`census()` 的键集合固定为 `{per_lang, by_outcome}` 且都非空。"""
    import concurrency as C

    c = C.census()
    assert set(c) == {"per_lang", "by_outcome"}, \
        "census() 的键变了（消费方会静默清零）：%r" % sorted(c)
    for k, v in c.items():
        assert v, "%s 是空的 —— 普查表没有内容，判据会空转" % k


def test_lookup_unknown_is_explicit():
    """未知 token 必须显式返回 `"unknown"`（不是 None / 空串）。"""
    import concurrency as C

    got = C.lookup("python", "__definitely_not_a_token__")
    assert got == "unknown", \
        "未知 token 返回了 %r —— 它会被误读成'不并发'" % (got,)
