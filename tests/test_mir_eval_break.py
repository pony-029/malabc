# -*- coding: utf-8 -*-
"""参考解释器必须支持 `break`（`while` 条件降级依赖它）。

为什么要这条用例：R469 我给解释器补了 break，没写测试就去跑对拍，
结果 while2d 从"未对拍"变成"不一致"（解释器 12，真值 6）——
break 被静默忽略，循环多跑一轮。**先锁期望，再改实现。**
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from translate import mir_eval  # noqa: E402

#: 最小 MIR：y 从 0 起，每轮 += 1，`i >= 4` 时 break —— 期望 y == 3。
#:
#: 两个坑都记在这里：
#:   * 必须有**入参**：`run_all` 不驱动零参函数（main 无法为它构造输入）
#:   * 用 `op:OP-ADD`（数组运算）累加：`setb` 会把 y 变成标量，
#:     那不是返回值的真实形态，run_all 会判失败
MIR = """version 3
func:brk
arg:x:f64:1
ret:y:f64:1
const:y:0
const:k:1
var:i:i64
set:i:1
while:1:eq:1
if:i:ge:4
break
end
op:OP-ADD:y:y:k
setb:i:add:i:1
end
end
"""


def test_break_exits_loop():
    funcs = mir_eval.parse(MIR)
    res = mir_eval.run_all(funcs)
    y = res.get("brk")
    assert y is not None, "解释器没能执行含 break 的函数"
    got = float(y[0].data[0])
    assert got == 3.0, "break 未生效：期望 3，实得 %r" % got
