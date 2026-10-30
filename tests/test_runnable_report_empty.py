# -*- coding: utf-8 -*-
"""`empty`（算完但结果为空）必须被**单独分类**，且 `runnable_report` 默认拒绝它。

## 为什么

R579 我把清理段写错，让「半实现」的函数走提前 return：
状态 OK、输出空。而 YALMIP 的 `numeric` 从 4 涨到 8 —— 我只看后者，
于是 4 个**假绿**混进了读数（R581 才更正）。

`empty` 这一类就是为它准备的。这里锁两件事：
1. `classify()` 把 `<名字>:`（冒号后为空）认成 `empty`，而不是数值或错误；
2. `runnable_report` 在没有 `--allow-empty` 时**以非零退出**。
"""
import io
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import runnable_report as R  # noqa: E402


def test_classify_marks_empty():
    text = "a: 1 2 3\nb:\nc: unimplemented\nd: error\ne: skipped (reject:struct)\n"
    cnt, rows = R.classify(text)
    assert cnt["numeric"] == 1, cnt
    assert cnt["empty"] == 1, cnt
    assert cnt["unimplemented"] == 1, cnt
    assert cnt["error"] == 1, cnt
    assert cnt["skipped_reject"] == 1, cnt
    assert ("empty", "b", "") in rows, rows


def test_empty_names_are_reported_and_gate_exists():
    """源码里必须存在「empty 非零则非零退出」这条路径与放行开关。"""
    p = os.path.join(ROOT, "tools", "runnable_report.py")
    src = io.open(p, encoding="utf-8").read()
    assert "--allow-empty" in src, "缺少显式放行开关"
    assert 'if cnt["empty"]' in src, "缺少 empty 的硬判据分支"
    assert "return 1" in src, "硬判据没有落到非零退出"
