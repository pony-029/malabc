# -*- coding: utf-8 -*-
"""**逐函数对拍**：默认路径 vs `--hir-emit` 必须三项全等（常驻判据）。

## 为什么必须有这条

`--hir-emit` 让 MIR 由 HIR 产出。总量相等（96 算子 / 165 行号）**不排除**
"这个函数少一条、那个多一条" —— 而默认切换后，任何一处错位都会让某人看到的
诊断指向错误的行。

所以这条判据问的是**逐函数**：同一函数在两条路径下的
① 算子多重集 ② `# src` 取值集合 ③ 数值 是否全等。

它是"能不能把 hir-emit 设为默认"的**闸门**。
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import hir_parity as P          # noqa: E402


@pytest.mark.skipif(not os.path.isfile(P.M2C), reason="m2c 未构建")
def test_default_vs_hir_emit_are_identical_per_function(capsys):
    """逐函数三项全等；退出码 0 即全等。"""
    rc = P.main([P.CORPUS, "--values"])
    out = capsys.readouterr().out
    assert rc == 0, "对拍有差异：\n%s" % out[-800:]
    assert "差异：0 个函数" in out, out[-400:]
    assert "数值：两条路径完全一致" in out, out[-400:]
