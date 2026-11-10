# -*- coding: utf-8 -*-
"""`--hir-emit` 的**行号对齐**判据（决策文档里的前置条件 2）。

## 为什么这条决定"能不能默认"

`--hir-emit` 让 MIR 由 HIR 产出，代价曾经是**丢掉全部 `# src:` 行号**（R743 量过：165 条）。
行号是 `check` 诊断的依据 —— 丢了它，报错从"第 12 行"退化成"某处"，可行动性消失。

R746/R747 通过"节点携带位置 + 降级回写"把行号补了回来。这条判据钉住它：

    hir-emit 的 `# src:` 条数 ≥ 默认路径的 95%

降到 95% 以下，就说明某类语句又开始丢位置了（最常见的是控制流与 const 行）。
"""
import io
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MIR_PY = os.path.join(ROOT, "translate", "mir.py")
CORPUS = os.path.join(ROOT, "translate", "examples", "numeric")
WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"


def _gen(extra, name):
    out = os.path.join(WORK, name)
    r = subprocess.run([sys.executable, MIR_PY, CORPUS] + extra + ["-o", out],
                       stdin=subprocess.DEVNULL, timeout=300,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-300:]
    return io.open(out, encoding="utf-8").read()


def test_hir_emit_keeps_src_lines():
    """`--hir-emit` 的 `# src:` 不得少于默认路径的 95%。"""
    # 基准必须显式关掉 HIR 产出（默认已开启），否则两边同路
    base = _gen(["--no-hir-emit"], "srcline_base.mir")
    he = _gen(["--hir-emit"], "srcline_he.mir")

    n_base = base.count("# src:")
    n_he = he.count("# src:")
    assert n_base > 0, "默认路径没有 # src 行？"
    ratio = 100.0 * n_he / n_base
    assert ratio >= 95.0, \
        "行号覆盖 %.1f%%（%d/%d）低于 95%% —— HIR 降级又开始丢位置了" % (
            ratio, n_he, n_base)


def test_hir_emit_keeps_all_ops():
    """行号补回来不能以丢算子为代价。"""
    base = _gen(["--no-hir-emit"], "srcline_base2.mir")
    he = _gen(["--hir-emit"], "srcline_he2.mir")
    n_base = sum(1 for l in base.splitlines() if l.startswith("op:"))
    n_he = sum(1 for l in he.splitlines() if l.startswith("op:"))
    assert n_he == n_base, "算子数 %d → %d" % (n_base, n_he)
