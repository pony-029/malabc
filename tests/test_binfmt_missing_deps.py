# -*- coding: utf-8 -*-
"""`missing_dependencies()`：哪些依赖"你可能还想一起分析"。

语义容易读错，所以判据要钉清楚：它返回的是**建议**，不是"这些库不存在"。
而且比较必须按**家族名** —— `libfoo.so.1` 与磁盘上的 `libfoo.so.1.2.3`
是同一个库，不能报成缺失（那是该函数注释里点名的 R68 收敛点）。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for sub in ("", "binfmt"):
    p = os.path.join(ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)


def _report(path, needs=()):
    from binfmt.model import BinaryReport, Dependency, DEP_LINK_FLAG

    r = BinaryReport(path=path)
    r.dependencies = [Dependency(name=n, kind=DEP_LINK_FLAG, origin=path)
                      for n in needs]
    return r


def test_unprovided_dependency_is_suggested():
    """没人提供它 → 出现在建议里，且带上"谁需要它"。"""
    from binfmt import attribute as A

    got = A.missing_dependencies([_report("a.so", ["libfoo.so.1"])])
    assert got, "依赖没被报出来"
    blob = str(got)
    assert "libfoo.so.1" in blob, "建议里没有依赖名：%r" % (blob[:200],)
    assert "a.so" in blob, "建议里没有'谁需要它'：%r" % (blob[:200],)


def test_family_match_is_not_missing():
    """**家族名相同就不算缺**：`libfoo.so.1` ← `libfoo.so.1.2.3`。"""
    from binfmt import attribute as A

    got = A.missing_dependencies([
        _report("a.so", ["libfoo.so.1"]),
        _report("libfoo.so.1.2.3"),          # 有人提供了同一家族的实现
    ])
    assert not got, "家族名相同的库被误报成缺失：%r" % (got,)
