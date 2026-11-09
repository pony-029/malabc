# -*- coding: utf-8 -*-
"""**标量属性位**的判据：哪些实参位置不该被物化成临时量。

## 为什么单独一条

这类位置错一次就要修一轮（R713 `alloc` / R738 `guard,search` / R739 `pred`），
三次都是"某个函数红了才发现漏了一族"。R740 改成从 `mlc_ops.h` 的**参数类型**推导，
这条判据就是钉住那份推导：期望值写在下面，与实际解析结果逐项比对。

它守的不是"能不能跑"，而是"**判定来源有没有退回到按族枚举**"——
一旦有人把 `_scalar_positions` 改坏、或头文件改了类型，这里立刻红。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from translate import hir as H          # noqa: E402

#: MIR 实参（不含 dst）里的**标量位**下标。依据 `c_runtime/include/mlc_ops.h`：
EXPECT = {
    "OP-MASK": {1, 2},        # mlc_op_mask(a, int cmp, double k, out)
    "OP-FIND": {1, 2},        # mlc_op_find_alloc(a, int cmp, double k, out)
    "OP-FIND2": {2},          # mlc_op_find_masked(a, b, int cmp, out)
    "OP-FIND3": {1, 2, 3},    # mlc_op_find_n(a, int cmp, double k, int64_t n, out)
    "OP-FILLA": {0, 1, 2},    # mlc_op_fill_alloc(int64 rows, int64 cols, double v, out)
    "OP-ISEQUALK": {1},       # mlc_op_isequal_k(a, double k, out)
    "OP-SLICE": {1, 2},       # mlc_op_slice(a, int64 from, int64 to, out)
    "OP-ROW": {1},            # mlc_op_row(a, int64 i, out)
    "OP-ADD": set(),          # mlc_op_add(a, b, out) —— 全数组，没有标量位
}


def test_scalar_positions_match_c_prototypes():
    bad = []
    for oid, want in EXPECT.items():
        got = set(H._scalar_positions(oid))
        if got != want:
            bad.append((oid, sorted(got), sorted(want)))
    assert not bad, "标量位推导与头文件不符：%r" % bad


def test_unknown_op_is_conservative():
    """原型缺失时必须**保守**（空集 = 全部物化），不能猜。"""
    assert H._scalar_positions("OP-NOT-A-REAL-OP") == set()
