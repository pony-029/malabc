# -*- coding: utf-8 -*-
"""`binfmt/attribute.py`：**符号索引**与**跨库冲突**判定。

这一层回答"这个符号是谁提供的"，而它的两个失效方向都是"报表看起来正常"：

* 冲突漏报 → 用户以为某符号只有一个来源，实际有两个库在抢；
* 冲突误报 → 每个库都报一堆，很快没人看（判据被当成噪音关掉）。

所以判据必须**双向**：跨库同名要报、同库重复导出**不能**报。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for sub in ("", "binfmt"):
    p = os.path.join(ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)


def _rep(path, symbols=()):
    from binfmt.model import BinaryReport, SYM_EXPORT, Symbol

    r = BinaryReport(path=path)
    r.symbols = [Symbol(name=n, kind=SYM_EXPORT, origin=path) for n in symbols]
    r.dependencies = []
    return r


def test_index_collects_exports():
    """索引收下全部导出符号，并记下报告数。"""
    from binfmt import attribute as A

    idx = A.build_index([_rep("a.so", ["foo", "bar"])])
    assert len(idx.reports) == 1, "报告数不对：%r" % (len(idx.reports),)
    assert set(idx.exports) == {"foo", "bar"}, \
        "导出符号集合不对：%r" % (sorted(idx.exports),)


def test_cross_library_duplicate_is_a_conflict():
    """两个库导出同名符号 → 必须报，且带出**两个来源**。"""
    from binfmt import attribute as A

    got = A.conflicts([_rep("lib/liba.so", ["foo"]),
                       _rep("lib/libb.so", ["foo"])])
    assert got, "跨库同名导出没被报成冲突"
    blob = str(got)
    assert "foo" in blob, "冲突里没有符号名：%r" % (blob[:160],)
    assert "liba.so" in blob and "libb.so" in blob, \
        "冲突里没有两个来源（用户不知道去查哪两个）：%r" % (blob[:200],)


def test_same_library_duplicate_is_not_a_conflict():
    """**反向**：同一个库里重复出现同名符号，不该算跨库冲突。

    否则每个库都会报自己，判据立刻变成噪音。
    """
    from binfmt import attribute as A

    assert A.conflicts([_rep("c.so", ["dup", "dup"])]) == [], \
        "同库重复导出被当成了冲突"

    # 互不相同也不该报
    assert A.conflicts([_rep("x.so", ["p"]), _rep("y.so", ["q"])]) == [], \
        "无同名却报了冲突"
