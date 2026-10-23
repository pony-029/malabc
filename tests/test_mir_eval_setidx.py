# -*- coding: utf-8 -*-
"""参考解释器必须支持 `OP-SETIDX`（`y(i) = v`）。

为什么单独一条：`cumsum_loop` 至今是唯一的"未对拍"函数，卡在解释器这里。
而 `apply_op` 是**纯函数**（只有 args、没有 env/lhs），"就地写第 i 个元素"
放不进去 —— 必须在 `exec_block` 里做（那里才知道 lhs 与 env）。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from translate import mir_eval  # noqa: E402

#: y = zeros(1,3); y(2) = x(1)  —— 期望 [0, 1, 0]（x 的默认输入是 1 2 3）
MIR = """version 3
func:sidx
arg:x:f64:3
ret:y:f64:3
fill:y:1,3:0
op:OP-INDEX:__t1:x:1
op:OP-SETIDX:y:__t1:2
end
"""


def test_setidx_writes_element():
    res = mir_eval.run_all(mir_eval.parse(MIR))
    y = res.get("sidx")
    assert y is not None, "解释器没能执行含 OP-SETIDX 的函数"
    got = [float(v) for v in y[0].data]
    assert got == [0.0, 1.0, 0.0], "y(2)=x(1) 应为 [0,1,0]，实得 %r" % got
