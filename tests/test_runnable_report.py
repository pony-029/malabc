# -*- coding: utf-8 -*-
"""`runnable_report` 的分类必须**账平**：五类之和 == 带名字的行数。

为什么单独立这条：这个工具第一版漏了整个 `unimplemented` 类别，
那些行既不匹配 numeric 也不匹配 error，于是**从总数里悄悄消失** ——
我拿一个少了 77 的分母算过比例，而且连跑三轮都没发现。

这里的判据只有一条：**分类不能丢行**。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import runnable_report as R  # noqa: E402

SAMPLE = """\
    printf("k: assumed shape [4]\\n");
leaf_fn: 2 4 6 8
helper_one: 2 3 4 5
empty_one:
empty_two: 1 0
bad_one: error
stub_one: unimplemented
stub_two: unimplemented (TODO)
none_one: skipped (no shape)
rej_one: skipped (reject:struct)
rej_two: skipped (reject:cell,varargin)
"""


def test_categories_cover_every_named_line():
    cnt, rows = R.classify(SAMPLE)
    named = [ln for ln in SAMPLE.splitlines()
             if ":" in ln and not ln.strip().startswith("printf")
             and not ln.strip().startswith('"')]
    total = sum(cnt.values())
    assert total == len(rows), "明细行数与计数不一致"
    # 账平：五类之和必须等于**带名字的输出行数**
    assert total == len(named), "分类丢行：%d 行带名字，只统计到 %d" % (len(named), total)


def test_each_category_recognised():
    cnt, _ = R.classify(SAMPLE)
    assert cnt["numeric"] == 3, cnt          # leaf_fn / helper_one / empty_two
    assert cnt["error"] == 1, cnt
    assert cnt["unimplemented"] == 2, cnt    # 含带后缀的形态
    assert cnt["skipped_shape"] == 1, cnt
    assert cnt["skipped_reject"] == 2, cnt

def test_unimplemented_is_not_silently_dropped():
    """回归锁：这正是曾经漏掉的那一类。"""
    cnt, rows = R.classify("a: unimplemented\n")
    assert cnt["unimplemented"] == 1, cnt
    assert len(rows) == 1
