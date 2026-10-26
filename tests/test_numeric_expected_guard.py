# -*- coding: utf-8 -*-
"""`numeric_expected` 的护栏：桩不能当真值。

背景：`trigfns` 曾以 `unimplemented` 被写进 `numeric.expected`，
语料因此"32/32 通过"了两轮 —— 实际是拿桩和桩比。
真值只能来自外部参照（Octave），参照自己没算出数时**必须拒绝**。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import numeric_expected as NE  # noqa: E402


def test_stub_rows_flags_every_stub_form():
    rows = {
        "ok": "1 2 3",
        "a": "unimplemented",
        "b": "error",
        "c": "skipped (no shape)",
        "d": "3",
    }
    bad = NE.stub_rows(rows)
    names = sorted(b.split(":")[0] for b in bad)
    assert names == ["a", "b", "c"], bad


def test_stub_rows_accepts_real_numbers():
    rows = {"x": "8 9 1", "y": "1.4142135623730951", "z": "-0.5"}
    assert NE.stub_rows(rows) == []


def test_expected_file_has_no_stub_value():
    """现存的每个期望值都必须是**数值**，不是桩。"""
    path = os.path.join(ROOT, "translate", "examples", "numeric.expected")
    text = open(path, encoding="utf-8").read()
    rows = {}
    for ln in text.splitlines():
        if ":" not in ln:
            continue
        k, v = ln.split(":", 1)
        rows[k.strip()] = v.strip()
    assert rows, "numeric.expected 是空的"
    assert NE.stub_rows(rows) == []
