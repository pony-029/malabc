# -*- coding: utf-8 -*-
"""块语句降级失败时，**块必须仍然平衡**。

## 这条判据防的是什么

`if a >= 0 && b <= 1` 的条件降不了级时，第一版只发一条 `unmapped:` —— **连 `if:` 都没开**。
结果后面的 `else` 成了孤儿，被记成 `blockmarker`（YALMIP 实测 1159 条），
而且整份 MIR 不可解析。

正确做法：降级失败也要发一个**恒假占位块**。语义上等于"这一块没执行"（走到这里的函数
本来就是桩），但块平衡保住了，**后面的代码可以继续翻译**。

## 判据

对每种"条件降不了级"的形态，断言：
1. `else` **不得**出现在 `unmapped:` 里；
2. MIR 里的 `if:` 数与 `end` 数配对（这里用 `blocks` 平衡的间接证据：`mir.py` 退出码 0 且无 `blockmarker`）。
"""
import io
import os
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MIR_PY = os.path.join(ROOT, "translate", "mir.py")
TMPROOT = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"

#: 条件都**降不了级**（`&&` / struct 字段 / `isa`）——正是这条判据要覆盖的形态
CASES = {
    "and_cond": "if a >= 0 && b <= 1",
    "dot_field": "if s.v > 0",
    "isa_str": "if isa(x, 'function_handle')",
    "or_cond": "if a > 0 || b > 0",
}


def _run(src_text, name, d):
    p = os.path.join(d, name + ".m")
    io.open(p, "w", encoding="utf-8", newline="\n").write(src_text)
    mir = os.path.join(d, name + ".mir")
    r = subprocess.run([sys.executable, MIR_PY, p, "-o", mir],
                       stdin=subprocess.DEVNULL, timeout=300,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0 or not os.path.isfile(mir):
        return None
    return io.open(mir, encoding="utf-8").read()


@pytest.mark.parametrize("name,cond", sorted(CASES.items()))
def test_else_survives_unlowerable_condition(name, cond):
    base = TMPROOT if os.path.isdir(TMPROOT) else None
    d = tempfile.mkdtemp(prefix="m2c_block_", dir=base)
    src = ("function y = f(a, b)\n"
           "%% @m2c shape a 1\n%% @m2c shape b 1\n%% @m2c shape y 1\n"
           "%s\n  y = 1;\nelse\n  y = 2;\nend\nend\n" % cond)
    text = _run(src, name, d)
    assert text is not None, "MIR 生成失败（源解析阶段就断了）"
    lines = [l.strip() for l in text.splitlines()]
    bad = [l for l in lines if l.startswith("unmapped:") and l.split(":", 1)[1].strip() == "else"]
    assert not bad, "`else` 成了孤儿（块没打开）：%s" % bad
    assert "else" in lines, "`else` 没有作为块语句被接受"
    assert "why:blockmarker" not in text, "仍有 blockmarker 归因"
