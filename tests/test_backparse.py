# -*- coding: utf-8 -*-
"""**回译产物必须能被自己的前端重新解析** —— 往返闭环的最后一环。

## 为什么需要这条判据

往返（`.m → MIR → .m'`）此前是 58/58 通过的，但那是因为 `roundtrip` 在 VM
失败时会**回退到 Octave**，把"回译产物解析不了"盖住了。

把 oracle 换成 VM 后暴露：13 个函数的回译产物 **前端解析不了** ——
`A((i+0))`、`find(x~=0,2)`、`ones(2,(k+0))` 这些写法前端不认。
闭环断在最后一步，而**报表依然是绿的**。

## 判据的两类

- **正例**：回译**实际会产出**的写法，必须能解析；
- **反例**：本来就正确的写法（`A(i)`、`A(2,:)`、`y = floor(a*10)`），
  改造后**不能被误伤** —— 三个反例分别对应 R701/R703/R704 的三次回归。
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
WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"

CASES = [
    # (名称, 源码, 是否应能解析)
    # ---- 反例：本来就对，不能被误伤 ----
    ("rej_1d_index", "function y = f(A, i)\n% @m2c shape A 4\n% @m2c shape y 1\n"
                     "y = A(i);\nend\n", True),
    ("rej_2d_row", "function y = f(A)\n% @m2c shape A 2,3\n% @m2c shape y 1,3\n"
                   "y = A(2, :);\nend\n", True),
    ("rej_call_arith", "function y = f(a)\n% @m2c shape a 3\n% @m2c shape y 3\n"
                       "y = floor(a * 10);\nend\n", True),
    # ---- 正例：回译会产出的形态 ----
    ("idx_paren", "function y = f(A, i)\n% @m2c shape A 4\n% @m2c shape y 1\n"
                  "y = A((i + 0));\nend\n", True),
    ("idx_arith", "function y = f(A, i, j)\n% @m2c shape A 3,3\n% @m2c shape y 1\n"
                  "y = A((i + ((j - 1) * 3)));\nend\n", True),
    ("slice_arith", "function y = f(x, i)\n% @m2c shape x 6\n% @m2c shape y 3\n"
                    "seg = x((i + 0):(i + 2));\nend\n", True),
    ("setidx2_arith", "function y = f(A, i, j)\n% @m2c shape A 3,3\n% @m2c shape y 3,3\n"
                      "A((i + 0), (j + 0)) = 99;\ny = A;\nend\n", True),
    ("find_n_cond", "function y = f(x)\n% @m2c shape x 4\n% @m2c shape y 2\n"
                    "y = find(x ~= 0, 2);\nend\n", True),
    ("ctor_paren", "function y = f(k)\n% @m2c shape k 1\n% @m2c shape y 2\n"
                   "y = ones(2, (k + 0));\nend\n", True),
    # ---- 正例：本轮新增的三类（回译剩余缺口） ----
    ("assign_paren", "function y = f(i)\n% @m2c shape i 1\n% @m2c shape y 1\n"
                     "i = (i + 1);\ny = i;\nend\n", True),
    ("const_left_mul", "function y = f(a)\n% @m2c shape a 3\n% @m2c shape y 3\n"
                       "y = 10 .* a;\nend\n", True),
    ("const_right_mul", "function y = f(a)\n% @m2c shape a 3\n% @m2c shape y 3\n"
                        "y = a .* 10;\nend\n", True),
    ("while_literal", "function y = f()\n% @m2c shape y 1\n"
                      "y = 0;\nwhile 1 == 1\ny = y + 1;\nbreak;\nend\nend\n", True),
]


def _unmapped(src):
    d = tempfile.mkdtemp(prefix="bp_", dir=WORK if os.path.isdir(WORK) else None)
    p = os.path.join(d, "t.m")
    io.open(p, "w", encoding="utf-8", newline="\n").write(src)
    mir = os.path.join(d, "t.mir")
    subprocess.run([sys.executable, MIR_PY, p, "-o", mir],
                   stdin=subprocess.DEVNULL, timeout=120,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not os.path.isfile(mir):
        return ["<无 MIR>"]
    return [l[9:] for l in io.open(mir, encoding="utf-8").read().splitlines()
            if l.startswith("unmapped:")]


#: 回译会产出、但前端**尚不认**的写法（R705 实测：能修好，但会牵动别处，暂缓）。
#: 标 xfail 而不是删掉 —— 它们是"闭环欠账"，要一直可见。
PENDING = set()


@pytest.mark.parametrize("name,src,want", CASES)
def test_backparse(name, src, want):
    if name in PENDING:
        pytest.xfail("已知未支持（回译会产出、前端尚不认）：见 PLAN_TRACKER R705")
    bad = _unmapped(src)
    got = not bad
    assert got == want, "%s：期望可解析=%s，实际未映射 %r" % (name, want, bad[:2])
