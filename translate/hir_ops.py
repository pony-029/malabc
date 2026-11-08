# -*- coding: utf-8 -*-
"""HIR → MIR 映射（唯一事实来源的雏形）。

> 生成方式：本地模型 `pony_hh` 按规格产出，**经机器验收后入库**。
> 验收判据见 `tests/test_hir_ops.py`：每个 MIR id 必须真实存在于
> `translate/operators.py`，键集合必须与规格一致，且不得重复。

## 为什么单独一张表

HIR 只使用 `family.name` 这种**语义名**（`ew.mul` / `red.mean`），
MIR 里才是 `OP-MUL` / `OP-MEAN`。这层映射是两者之间的**唯一连接点**：
- HIR 侧永远不写 `OP-*`（避免语义层被实现细节污染）；
- MIR 侧永远不写 `ew.*`（发射器不需要知道语义分类）。

改这里 = 改语义到实现的对应，一处生效。
"""

HIR_TO_MIR = {
    # 逐元素二元
    "ew.add": "OP-ADD",
    "ew.sub": "OP-SUB",
    "ew.mul": "OP-MUL",
    "ew.div": "OP-DIV",
    # 线性代数
    "lin.matmul": "OP-MATMUL",
    # 归约
    "red.sum": "OP-SUM",
    "red.mean": "OP-MEAN",
    "red.max": "OP-MAX",
    "red.min": "OP-MIN",
    # 一元
    "un.abs": "OP-ABS",
    "un.sqrt": "OP-SQRT",
    "un.log10": "OP-LOG10",
    "un.sin": "OP-SIN",
    "un.floor": "OP-FLOOR",
    # 形状
    "shape.transpose": "OP-TRANSPOSE",
    # 拼接
    "cat.hcat": "OP-HCAT",
    "cat.vcat": "OP-VCAT",
    # 下标
    "idx.slice": "OP-SLICE",
    "idx.get": "OP-INDEX",
    # 存储
    "mem.copy": "OP-COPY",
    "mem.setidx": "OP-SETIDX",
    "mem.setidx2": "OP-SETIDX2",
    # 掩码选值
    "guard.mask": "OP-MASK",
    # 查找
    "search.find": "OP-FIND",
    # 按运行期维度分配
    "alloc.fill": "OP-FILLA",
    # 集合
    "set.setdiff": "OP-SETDIFF",
    # ---- 尺寸/谓词（R717 补：语料里 20 个函数因此可参与 HIR）----
    "shape.flatten": "OP-FLATTEN",
    "shape.size": "OP-SIZE",
    "pred.isempty": "OP-ISEMPTY",
    "pred.length": "OP-LENGTH",
    "pred.numel": "OP-NUMEL",
    "pred.any": "OP-ANY",
    "pred.nnz": "OP-NNZ",
    "pred.isequal": "OP-ISEQUAL",
    "pred.isequalk": "OP-ISEQUALK",
    # ---- 下标（行/列区间）----
    "idx.row": "OP-ROW",
    "idx.colrange": "OP-COLRANGE",

}

#: 规格要求的 26 个键（用于验收：多一个少一个都算交付不合格）
EXPECTED_KEYS = frozenset(HIR_TO_MIR)


def mir_of(hir_name):
    """HIR 名 → MIR id；未登记返回 None（**不猜**）。"""
    return HIR_TO_MIR.get((hir_name or "").strip().lower())


def family_of(hir_name):
    """`red.mean` → `red`。family 决定参数要求，是归因的依据。"""
    n = (hir_name or "").strip()
    return n.split(".", 1)[0] if "." in n else ""
