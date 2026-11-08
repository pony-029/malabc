# -*- coding: utf-8 -*-
"""验收：HIR→MIR 映射表（委派产物）必须满足三条机器判据。

## 为什么要有这条判据

这张表由**本地模型产出**、由人验收后入库。委派产物的典型失败是"看起来很规整"：

- 键名大小写/前缀漂移（`EW.mul` / `ew_mul`）；
- MIR id 拼错或写了一个不存在的算子（`OP-MULT`）；
- 悄悄少给一两个键。

三种都不会报错，只会在真正降级时**静默漏算子**。所以判据要钉死：
**每个 id 必须真实存在于 `operators.py`**，键集合必须与规格完全一致。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from translate import hir_ops as H          # noqa: E402
from translate import operators as O        # noqa: E402

#: 规格里要求的 26 个键（顺序无关）
SPEC = {
    "ew.add", "ew.sub", "ew.mul", "ew.div",
    "lin.matmul",
    "red.sum", "red.mean", "red.max", "red.min",
    "un.abs", "un.sqrt", "un.log10", "un.sin", "un.floor",
    "shape.transpose",
    "cat.hcat", "cat.vcat",
    "idx.slice", "idx.get",
    "mem.copy", "mem.setidx", "mem.setidx2",
    "guard.mask",
    "search.find",
    "alloc.fill",
    "set.setdiff",
    # R717：补齐语料里出现过的尺寸/谓词/下标算子
    "shape.flatten", "shape.size",
    "pred.isempty", "pred.length", "pred.numel", "pred.any", "pred.nnz",
    "pred.isequal", "pred.isequalk",
    "idx.row", "idx.colrange",
}


def test_key_set_matches_spec():
    got = set(H.HIR_TO_MIR)
    assert got == SPEC, "键集合不符：多 %r 少 %r" % (sorted(got - SPEC), sorted(SPEC - got))
    assert len(H.HIR_TO_MIR) == len(SPEC), "存在重复键"


def test_every_id_exists_in_operator_table():
    """**最关键的一条**：MIR id 必须真实存在，否则降级时会静默漏算子。"""
    known = {op["id"] for op in O.OPERATORS}
    bad = {k: v for k, v in H.HIR_TO_MIR.items() if v not in known}
    assert not bad, "映射到了不存在的算子：%r" % (bad,)


def test_lookup_and_family():
    assert H.mir_of("red.mean") == "OP-MEAN"
    assert H.mir_of("EW.MUL ") == "OP-MUL", "应容错大小写与空白"
    assert H.mir_of("red.unknown") is None, "未登记必须返回 None，不得猜"
    assert H.family_of("red.mean") == "red"
    assert H.family_of("no_dot") == ""
