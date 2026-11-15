# -*- coding: utf-8 -*-
"""`binfmt/report.py`：**人读的尺寸**与**摘要行的计数**。

这层是最终给人看的那一面，错法都很"温和"：

* `_human(1024)` 若显示 `1024 B`，读者要自己换算；若显示 `1.0 KiB` 才对。
  边界 1023/1024 是最容易写错的一位。
* `to_summary_line` 里的 `sym=` / `dep=` 必须跟着真实计数走 ——
  写死或算错不会报错，只会让报表长期显示一个错的规模。
* 取不到的字段要给 `?`，不能崩 —— 它在"只解析了一半"的库上也会被调用。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for sub in ("", "binfmt"):
    p = os.path.join(ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)


def _report(n_sym=0, n_dep=0):
    from binfmt.model import (BinaryReport, SYM_EXPORT, DEP_LINK_FLAG,
                              Dependency, Symbol)

    rep = BinaryReport(path="lib/libfoo.so")
    rep.symbols = [Symbol(name="s%d" % i, kind=SYM_EXPORT, origin="a")
                   for i in range(n_sym)]
    rep.dependencies = [Dependency(name="d%d.so" % i, kind=DEP_LINK_FLAG,
                                   origin="a") for i in range(n_dep)]
    return rep


def test_human_size_boundaries():
    """`_human` 的进制边界：1024 必须进位，1023 不必。"""
    from binfmt import report as R

    assert R._human(0) == "0 B"
    assert R._human(1023) == "1023 B", "1023 不该进位：%r" % (R._human(1023),)
    assert R._human(1024) == "1.0 KiB", "1024 没进位到 KiB：%r" % (R._human(1024),)
    assert R._human(1536) == "1.5 KiB", "1.5 KiB 显示不对：%r" % (R._human(1536),)
    assert R._human(1024 * 1024) == "1.0 MiB"


def test_summary_line_counts_follow_reality():
    """`sym=` / `dep=` 必须等于真实条数（写死或算错都不会报错）。"""
    from binfmt import report as R

    empty = R.to_summary_line(_report())
    assert "sym=0" in empty and "dep=0" in empty, \
        "空报告的计数不对：%r" % (empty,)

    line = R.to_summary_line(_report(n_sym=2, n_dep=1))
    assert "sym=2" in line, "2 个符号却没显示 sym=2：%r" % (line,)
    assert "dep=1" in line, "1 个依赖却没显示 dep=1：%r" % (line,)


def test_summary_line_tolerates_missing_fields():
    """取不到的字段用 `?` 占位、**不崩** —— 半解析的报告也会被打印。"""
    from binfmt import report as R

    line = R.to_summary_line(_report())
    assert isinstance(line, str) and line.strip(), "摘要行为空"
    assert "?" in line, "缺失字段没有占位符（读者会以为值是空的）：%r" % (line,)
