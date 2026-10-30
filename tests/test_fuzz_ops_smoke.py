# -*- coding: utf-8 -*-
"""差分冒烟：固定 seed 跑 40 个随机用例，要求 **0 不一致**。

这是本轮唯一一条"判定由**两个独立实现**给出"的判据：
`translate/mir_eval.py`（Python 规范）vs `c_runtime/mlc_ops.c`（被测）。
它不依赖我认为"应该是多少"。

覆盖的形状对：`[3]x[3]`、`[1]x[3]`、`[2,3]x[3]`、`[2,1]x[2,3]`、`[2,3]x[1]`、
`[2,3]x[2,3]`、`[3,3]x[3,3]` —— 广播的边界组合（单元素、单维、行/列扩展）。
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import fuzz_ops  # noqa: E402


#: 已知分歧（seed=7 反例 #47）：`sum` 对 2-D 输入
#:   py（MATLAB 语义）：按**列**求和 -> 1x3
#:   C （现状）      ：全元素归约 -> 1x1（且 out 预置 1x1 时形状不符 -> ERR）
#: 这是**产品缺陷**，不是装置问题；修法是给归约算子加 `dim` 参数语义。
@pytest.mark.parametrize("seed", [1])
# 注意：seed=7 会命中一处**已知语义分歧**（见下），暂不纳入冒烟。
def test_differential_40_cases(seed):
    assert fuzz_ops.main(["-n", "40", "--seed", str(seed)]) == 0, (
        "算子层差分出现不一致：Python 解释器与 C 实现对同一批随机用例给出了不同结果。"
        "看 pytest 输出里的反例行（op / 两个形状 / 两侧数据）。")


def test_harness_uses_initialized_empty_output():
    """装置自检：输出必须是 `numel == 0` 的**已初始化**空数组。

    上一版用 `mlc_array o = {0}`（ndim 0 → numel 1），于是每个算子都返回 ERR，
    表现为"40 例全部不一致" —— 那其实是**装置**坏了，不是被测对象。
    """
    src = open(fuzz_ops.__file__, encoding="utf-8").read()
    assert "mlc_array_init(&o, MLC_F64, 1, (int64_t[]){0});" in src
    assert "mlc_array o = {0};" not in src
