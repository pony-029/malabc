# -*- coding: utf-8 -*-
"""MATLAB 语句 → **算子** → C 代码（R432 / P0）。

为什么要有“算子”这一层：
  直接把 MATLAB 行逐字翻成 C，会把 1-based/列主序/隐式扩展/整型溢出
  四类差异散落到每个函数里。先把语句识别成**有限的算子**，再让每个算子
  带着自己的规则与夹具落到 C，才有唯一可验证的映射。

本模块只做**确定性段**（零 AI）：
  命中算子 ⇒ 必须引用算子 ID；
  没有算子能命中 ⇒ 进 `unmapped`（**不是猜一个翻译**）。

算子表是单一事实源；`c_runtime/include/mlc_ops.h` 是它的 C 落点。
"""

import os
import re

GOLDEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")

#: 算子目录。`verified_by` 非空 = 至少有一组双语夹具证明它。
OPERATORS = (
    {"id": "OP-ADD", "matlab": "a + b", "c": "mlc_op_add",
     "kind": "elementwise", "rules": ("EXPAND-1", "INT-1"),
     "sample": "y = a + b;",
     "verified_by": "op_add_broadcast.json"},
    {"id": "OP-SUB", "matlab": "a - b", "c": "mlc_op_sub",
     "kind": "elementwise", "rules": ("EXPAND-1", "INT-1"),
     "sample": "y = a - b;",
     "verified_by": "op_sub_scalar.json"},
    {"id": "OP-MUL", "matlab": "a .* b", "c": "mlc_op_mul",
     "kind": "elementwise", "rules": ("EXPAND-1", "INT-1"),
     "sample": "y = a .* b;",
     "verified_by": "op_mul_elementwise.json"},
    {"id": "OP-DIV", "matlab": "a ./ b", "c": "mlc_op_div",
     "kind": "elementwise", "rules": ("EXPAND-1", "INT-1"),
     "sample": "y = a ./ b;",
     "verified_by": "op_div_elementwise.json"},
    {"id": "OP-SUM", "matlab": "sum(x)", "c": "mlc_op_sum",
     "kind": "reduction", "rules": ("ORDER-1",),
     "sample": "y = sum(x);",
     "verified_by": "op_sum_vector.json"},
    {"id": "OP-MEAN", "matlab": "mean(x)", "c": "mlc_op_mean",
     "kind": "reduction", "rules": ("ORDER-1",),
     "sample": "y = mean(x);",
     "verified_by": "op_mean_vector.json"},
    {"id": "OP-MAX", "matlab": "max(x)", "c": "mlc_op_max",
     "kind": "reduction", "rules": ("ORDER-1",),
     "sample": "y = max(x);",
     "verified_by": "op_max_vector.json"},
    {"id": "OP-MIN", "matlab": "min(x)", "c": "mlc_op_min",
     "kind": "reduction", "rules": ("ORDER-1",),
     "sample": "y = min(x);",
     "verified_by": "op_min_vector.json"},
    # 由 mir.py 的降级产生（`y(i) = v`），不经过 parse_line —— 因此没有 sample；
    # 它由数值语料 cumsum_loop + 夹具 op_setidx_1d 共同验证。
    {"id": "OP-SIN", "matlab": "sin(x)", "c": "mlc_op_sin",
     "kind": "elementwise", "rules": ("ORDER-1",),
     "sample": "y = sin(x);"},
    {"id": "OP-COS", "matlab": "cos(x)", "c": "mlc_op_cos",
     "kind": "elementwise", "rules": ("ORDER-1",),
     "sample": "y = cos(x);"},
    {"id": "OP-TAN", "matlab": "tan(x)", "c": "mlc_op_tan",
     "kind": "elementwise", "rules": ("ORDER-1",),
     "sample": "y = tan(x);"},
    {"id": "OP-FLOOR", "matlab": "floor(x)", "c": "mlc_op_floor",
     "kind": "elementwise", "rules": ("ORDER-1",),
     "sample": "y = floor(x);"},
    {"id": "OP-CEIL", "matlab": "ceil(x)", "c": "mlc_op_ceil",
     "kind": "elementwise", "rules": ("ORDER-1",),
     "sample": "y = ceil(x);"},
    {"id": "OP-ROUND", "matlab": "round(x)", "c": "mlc_op_round",
     "kind": "elementwise", "rules": ("ORDER-1",),
     "sample": "y = round(x);"},
    {"id": "OP-LOG2", "matlab": "log2(x)", "c": "mlc_op_log2",
     "kind": "elementwise", "rules": ("ORDER-1",),
     "sample": "y = log2(x);"},
    {"id": "OP-LOG10", "matlab": "log10(x)", "c": "mlc_op_log10",
     "kind": "elementwise", "rules": ("ORDER-1",),
     "sample": "y = log10(x);"},
    {"id": "OP-FIND3", "matlab": "find(x,n)", "c": "mlc_op_find_n",
     "kind": "indexing", "rules": ("IDX-1",),
     "sample": "y = find(x, 2);"},
    {"id": "OP-FIND2", "matlab": "find(a cmp b)", "c": "mlc_op_find_masked",
     "kind": "indexing", "rules": ("IDX-1",),
     "sample": "y = find(a == b);"},
    {"id": "OP-ISEQUAL", "matlab": "isequal(a,b)", "c": "mlc_op_isequal",
     "kind": "reduction", "rules": ("ORDER-1",),
     "sample": "y = isequal(a, b);"},
    {"id": "OP-ISEQUALK", "matlab": "isequal(a,k)", "c": "mlc_op_isequal_k",
     "kind": "reduction", "rules": ("ORDER-1",),
     "sample": "y = isequal(a, 0);"},
    {"id": "OP-ANY", "matlab": "any(x)", "c": "mlc_op_any",
     "kind": "reduction", "rules": ("ORDER-1",),
     "sample": "y = any(x);"},
    {"id": "OP-ALL", "matlab": "all(x)", "c": "mlc_op_all",
     "kind": "reduction", "rules": ("ORDER-1",),
     "sample": "y = all(x);"},
    {"id": "OP-NNZ", "matlab": "nnz(x)", "c": "mlc_op_nnz",
     "kind": "reduction", "rules": ("ORDER-1",),
     "sample": "y = nnz(x);"},
    {"id": "OP-ISREAL", "matlab": "isreal(x)", "c": "mlc_op_isreal",
     "kind": "reduction", "rules": ("ORDER-1",),
     "sample": "y = isreal(x);"},
    {"id": "OP-ISNUMERIC", "matlab": "isnumeric(x)", "c": "mlc_op_isnumeric",
     "kind": "reduction", "rules": ("ORDER-1",),
     "sample": "y = isnumeric(x);"},
    {"id": "OP-SQRT", "matlab": "sqrt(x)", "c": "mlc_op_sqrt",
     "kind": "elementwise", "rules": ("ORDER-1",),
     "sample": "y = sqrt(x);"},
    {"id": "OP-ABS", "matlab": "abs(x)", "c": "mlc_op_abs",
     "kind": "elementwise", "rules": ("ORDER-1",),
     "sample": "y = abs(x);"},
    {"id": "OP-EXP", "matlab": "exp(x)", "c": "mlc_op_exp",
     "kind": "elementwise", "rules": ("ORDER-1",),
     "sample": "y = exp(x);"},
    {"id": "OP-LOG", "matlab": "log(x)", "c": "mlc_op_log",
     "kind": "elementwise", "rules": ("ORDER-1",),
     "sample": "y = log(x);"},
    {"id": "OP-COLRANGE", "matlab": "A(:,p:q)", "c": "mlc_op_colrange",
     "kind": "slice", "rules": ("IDX-1",),
     "sample": "y = A(:,2:end);"},
    {"id": "OP-COL", "matlab": "A(:,k)", "c": "mlc_op_col",
     "kind": "slice", "rules": ("IDX-1",),
     "sample": "y = A(:,2);"},
    {"id": "OP-SIZE", "matlab": "size(x,dim)", "c": "mlc_op_size_dim",
     "kind": "reduction", "rules": ("ORDER-1",),
     "sample": "y = size(x,2);"},
    {"id": "OP-NUMEL", "matlab": "numel(x)", "c": "mlc_op_numel",
     "kind": "reduction", "rules": ("ORDER-1",),
     "sample": "y = numel(x);"},
    {"id": "OP-LENGTH", "matlab": "length(x)", "c": "mlc_op_length",
     "kind": "reduction", "rules": ("ORDER-1",),
     "sample": "y = length(x);"},
    {"id": "OP-ISEMPTY", "matlab": "isempty(x)", "c": "mlc_op_isempty",
     "kind": "reduction", "rules": ("ORDER-1",),
     "sample": "y = isempty(x);"},
    {"id": "OP-ROW", "matlab": "y = A(i,:)", "c": "mlc_op_row",
     "kind": "slice", "rules": ("IDX-1",),
     "sample": "y = A(2,:);"},
    {"id": "OP-SETIDX", "matlab": "y(i) = v", "c": "mlc_op_setidx",
     "kind": "assign", "rules": ("IDX-1",),
     "sample": "y(2) = 3;"},
    {"id": "OP-INDEX", "matlab": "x(i)", "c": "mlc_op_index",
     "kind": "index", "rules": ("IDX-1", "ORDER-1"),
     "sample": "y = x(2);",
     "verified_by": "op_index_shift.json"},
    {"id": "OP-FIND", "matlab": "find(x > k)", "c": "mlc_op_find_alloc",
     "kind": "select", "rules": ("IDX-1",), "dynamic": True,
     "sample": "i = find(x > 1);",
     "verified_by": "op_find_gt.json"},
    {"id": "OP-FLATTEN", "matlab": "A(:)", "c": "mlc_op_flatten",
     "kind": "layout", "rules": ("ORDER-1",),
     "sample": "y = A(:);",
     "verified_by": "op_flatten_2x2.json"},
    {"id": "OP-MASK", "matlab": "x(x > k)", "c": "mlc_op_mask",
     "kind": "select", "rules": ("IDX-1",), "dynamic": True,
     "sample": "y = x(x > 1);",
     "verified_by": "op_mask_gt.json"},
    {"id": "OP-SLICE", "matlab": "x(a:b)", "c": "mlc_op_slice",
     "kind": "slice", "rules": ("IDX-1", "ORDER-1"),
     "sample": "y = x(1:2);",
     "verified_by": "op_slice_1d.json"},
    {"id": "OP-TRANSPOSE", "matlab": "x.'", "c": "mlc_op_transpose",
     "kind": "layout", "rules": ("ORDER-1",),
     "sample": "y = x.';",
     "verified_by": "op_transpose.json"},
    {"id": "OP-MATMUL", "matlab": "A * B", "c": "mlc_op_matmul",
     "kind": "linalg", "rules": ("ORDER-1",),
     "sample": "y = A * B;",
     "verified_by": "op_matmul_2x2.json"},
)

#: 已实现 C 落点的算子（其余返回 MLC_UNIMPLEMENTED —— 诚实边界）。
#: `OP-MATMUL` 已由 mlc_ops.c 真实现（2-D f64）；
#: 注意 `*` / `.*` 在**文本层**都映射到 OP-MUL —— 二者的区别要看形状，
#: 由 translate/mir.py 在知道 shape 之后决定是否升级成 OP-MATMUL。
C_IMPLEMENTED = ("OP-ADD", "OP-SUB", "OP-MUL", "OP-DIV",
                 "OP-SUM", "OP-MEAN", "OP-MAX", "OP-MIN", "OP-INDEX",
                 "OP-MATMUL", "OP-TRANSPOSE", "OP-SLICE",
                 "OP-FLATTEN", "OP-MASK", "OP-FIND", "OP-SETIDX", "OP-ROW", "OP-ISEMPTY", "OP-NUMEL", "OP-LENGTH", "OP-SIZE", "OP-COL", "OP-COLRANGE",
    "OP-SQRT", "OP-ABS", "OP-EXP", "OP-LOG",
    "OP-SIN", "OP-COS", "OP-TAN", "OP-FLOOR", "OP-CEIL",
    "OP-ROUND", "OP-LOG2", "OP-LOG10",
    "OP-ANY", "OP-ALL", "OP-NNZ", "OP-ISREAL", "OP-ISNUMERIC",
    "OP-FIND2", "OP-FIND3",
    "OP-ISEQUAL", "OP-ISEQUALK")

#: `y(i) = v`（元素赋值）。左边带下标，_ASSIGN_RE 抓不到，单列一条。
_SETIDX_LINE = re.compile(r"^\s*([A-Za-z_]\w*)\s*\(\s*([A-Za-z_]\w*|\d+)\s*\)"
                          r"\s*=\s*([A-Za-z_]\w*|-?\d+(?:\.\d+)?)\s*;?\s*$")
#: `find(a == b)` —— 逐元素比较两个**数组**（右侧是名字，不是阈值）
_FIND2_LINE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*find\s*\(\s*"
                         r"([A-Za-z_]\w*)\s*(>=|<=|==|~=|>|<)\s*"
                         r"([A-Za-z_]\w*)\s*\)\s*;?\s*$")
_FIND2_CMP = {"==": "4", "~=": "5", ">": "0", ">=": "1",
              "<": "2", "<=": "3"}

#: `find(x, n)` —— 非零下标的前 n 个
_FINDN_LINE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*find\s*\(\s*"
                         r"([A-Za-z_]\w*)\s*,\s*(\d+)\s*\)\s*;?\s*$")
#: `y = find(x)` —— 非零下标（等价于 `find(x ~= 0)`，复用 OP-FIND 的 cmp=5/k=0）
_FIND1_LINE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*find\s*\(\s*"
                         r"([A-Za-z_]\w*)\s*\)\s*;?\s*$")

#: `isequal(a,b)` / `isequal(a,0)` -> 1x1 布尔
_ISEQ_LINE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*isequal\s*\(\s*"
                        r"([A-Za-z_]\w*)\s*,\s*([A-Za-z_]\w*|-?\d+(?:\.\d+)?)\s*\)"
                        r"\s*;?\s*$")
#: 1x1 谓词（any/all/nnz/isreal/isnumeric）
_PRED_LINE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*"
                        r"(any|all|nnz|isreal|isnumeric)\s*\(\s*"
                        r"([A-Za-z_]\w*)\s*\)\s*;?\s*$")
_PRED_IDS = {"any": "OP-ANY", "all": "OP-ALL", "nnz": "OP-NNZ",
             "isreal": "OP-ISREAL", "isnumeric": "OP-ISNUMERIC"}
#: 逐元素标量函数（sqrt/abs/exp/log）
_UNARY_LINE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*"
                         r"(sqrt|abs|exp|log|sin|cos|tan|floor|ceil|round|log2|log10)"
                         r"\s*\(\s*"
                         r"([A-Za-z_]\w*)\s*\)\s*;?\s*$")
_UNARY_IDS = {"sqrt": "OP-SQRT", "abs": "OP-ABS",
              "exp": "OP-EXP", "log": "OP-LOG",
              "sin": "OP-SIN", "cos": "OP-COS", "tan": "OP-TAN",
              "floor": "OP-FLOOR", "ceil": "OP-CEIL",
              "round": "OP-ROUND", "log2": "OP-LOG2",
              "log10": "OP-LOG10"}
#: `y = A(:, lo:hi)` —— hi 可为 `end`
_COLRANGE_LINE = re.compile(
    r"^\s*([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\s*"
    r"\(\s*:\s*,\s*(\d+|end)\s*:\s*(\d+|end)\s*\)\s*;?\s*$")
#: `y = A(:, k)` —— 取单列（k 字面量或变量）
_COL_LINE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\s*"
                       r"\(\s*:\s*,\s*([A-Za-z_]\w*|\d+)\s*\)\s*;?\s*$")
#: `y = size(x, N)` —— 第二参数必须是**数字字面量**
_SIZE_LINE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*size\s*\(\s*"
                        r"([A-Za-z_]\w*)\s*,\s*(\d+)\s*\)\s*;?\s*$")
#: `y = numel(x)` / `y = length(x)`
_NUMEL_LINE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*numel\s*\(\s*"
                         r"([A-Za-z_]\w*)\s*\)\s*;?\s*$")
_LENGTH_LINE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*length\s*\(\s*"
                          r"([A-Za-z_]\w*)\s*\)\s*;?\s*$")
#: `y = isempty(x)`
_ISEMPTY_LINE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*isempty\s*\(\s*"
                           r"([A-Za-z_]\w*)\s*\)\s*;?\s*$")
#: `y = A(i,:)` 行切片
_ROWS_LINE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\s*"
                        r"\(\s*([A-Za-z_]\w*|\d+)\s*,\s*:\s*\)\s*;?\s*$")
_ASSIGN_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*(.+?)\s*;\s*$")
_BIN_RE = re.compile(r"^([A-Za-z_]\w*)\s*(\.\*|\./|\+|-|\*)\s*([A-Za-z_]\w*)$")
_CALL_RE = re.compile(r"^(sum|mean|max|min)\s*\(\s*([A-Za-z_]\w*)\s*\)$")
# `x'` 是共轭转置，`x.'` 是普通转置。本目录只处理实数 f64，二者等价，
# 所以两种写法都收 —— 只收 `.'` 会让真实代码里的 `x'` 全部掉进 unmapped。
_TRANS_RE = re.compile(r"^([A-Za-z_]\w*)\s*\.?'\s*$")
#: `find(x > 1)` —— 返回 1-based 下标（长度数据相关）
_FIND_RE = re.compile(r"^find\s*\(\s*([A-Za-z_]\w*)\s*"
                      r"(>=|<=|==|~=|>|<)\s*(-?\d+(?:\.\d+)?)\s*\)$")

#: `A(:)` —— 列优先展平
_FLAT_RE = re.compile(r"^([A-Za-z_]\w*)\s*\(\s*:\s*\)$")
#: `x(x > 1)` —— 逻辑索引（只认"对自身按常量比较"，这是最常见也最可判定的形态）
_MASK_RE = re.compile(r"^([A-Za-z_]\w*)\s*\(\s*([A-Za-z_]\w*)\s*"
                      r"(>=|<=|==|~=|>|<)\s*(-?\d+(?:\.\d+)?)\s*\)$")
#: 比较符 -> 整数码（C 侧 mlc_mask_test 用整数，避免生成侧拼字符串）
_MASK_CMP = {">": 0, ">=": 1, "<": 2, "<=": 3, "==": 4, "~=": 5}

#: `x(1:2)` / `x(2:end)` —— 1-based 闭区间切片（仅 1-D）
_SLICE_RE = re.compile(r"^([A-Za-z_]\w*)\s*\(\s*(\d+|end)\s*:\s*"
                       r"(\d+|end)\s*\)$")
_INDEX_RE = re.compile(r"^([A-Za-z_]\w*)\s*\(\s*(\d+|[A-Za-z_]\w*)\s*\)$")

_CALL_OPS = {"sum": "OP-SUM", "mean": "OP-MEAN",
             "max": "OP-MAX", "min": "OP-MIN"}
_BIN_OPS = {"+": "OP-ADD", "-": "OP-SUB", ".*": "OP-MUL",
            "./": "OP-DIV", "*": "OP-MATMUL"}


def operator_ids():
    out = []
    for op in OPERATORS:
        if op["id"] not in out:
            out.append(op["id"])
    return tuple(out)


def dynamic_ops():
    """算子表里标了 "dynamic" 的那些（输出长度数据相关 -> 由算子分配）。"""
    return {o["id"] for o in OPERATORS if o.get("dynamic")}


def by_id(op_id):
    for op in OPERATORS:
        if op["id"] == op_id:
            return op
    raise KeyError("未知算子：%s" % op_id)


def parse_line(line):
    """把一条 MATLAB 赋值语句识别成算子；识别不了返回 None（进 unmapped）。"""
    pd = _PRED_LINE.match(line or "")
    if pd is not None:
        return {"operator": _PRED_IDS[pd.group(2)], "lhs": pd.group(1),
                "args": [pd.group(3)], "raw": line.rstrip("\n")}

    fn_ = _FINDN_LINE.match(line or "")
    if fn_ is not None:
        return {"operator": "OP-FIND3", "lhs": fn_.group(1),
                "args": [fn_.group(2), "5", "0", fn_.group(3)],
                "raw": line.rstrip("\n")}

    iq = _ISEQ_LINE.match(line or "")
    if iq is not None:
        rhs = iq.group(3)
        is_lit = re.match(r"^-?\d+(\.\d+)?$", rhs) is not None
        return {"operator": "OP-ISEQUALK" if is_lit else "OP-ISEQUAL",
                "lhs": iq.group(1),
                "args": [iq.group(2), rhs],
                "raw": line.rstrip("\n")}

    f2 = _FIND2_LINE.match(line or "")
    if f2 is not None:
        return {"operator": "OP-FIND2", "lhs": f2.group(1),
                "args": [f2.group(2), f2.group(4),
                         _FIND2_CMP[f2.group(3)]],
                "raw": line.rstrip("\n")}

    f1 = _FIND1_LINE.match(line or "")
    if f1 is not None:
        return {"operator": "OP-FIND", "lhs": f1.group(1),
                "args": [f1.group(2), "5", "0"],
                "raw": line.rstrip("\n")}

    um = _UNARY_LINE.match(line or "")
    if um is not None:
        return {"operator": _UNARY_IDS[um.group(2)], "lhs": um.group(1),
                "args": [um.group(3)], "raw": line.rstrip("\n")}

    cr = _COLRANGE_LINE.match(line or "")
    if cr:
        hi = "-1" if cr.group(4) == "end" else cr.group(4)
        return {"operator": "OP-COLRANGE", "lhs": cr.group(1),
                "args": [cr.group(2), cr.group(3), hi],
                "raw": line.rstrip("\n")}

    cm3 = _COL_LINE.match(line or "")
    if cm3:
        return {"operator": "OP-COL", "lhs": cm3.group(1),
                "args": [cm3.group(2), cm3.group(3)],
                "raw": line.rstrip("\n")}

    sm2 = _SIZE_LINE.match(line or "")
    if sm2:
        return {"operator": "OP-SIZE", "lhs": sm2.group(1),
                "args": [sm2.group(2), sm2.group(3)],
                "raw": line.rstrip("\n")}

    nm = _NUMEL_LINE.match(line or "")
    if nm:
        return {"operator": "OP-NUMEL", "lhs": nm.group(1),
                "args": [nm.group(2)], "raw": line.rstrip("\n")}
    lm2 = _LENGTH_LINE.match(line or "")
    if lm2:
        return {"operator": "OP-LENGTH", "lhs": lm2.group(1),
                "args": [lm2.group(2)], "raw": line.rstrip("\n")}

    em = _ISEMPTY_LINE.match(line or "")
    if em:
        return {"operator": "OP-ISEMPTY", "lhs": em.group(1),
                "args": [em.group(2)], "raw": line.rstrip("\n")}

    rm = _ROWS_LINE.match(line or "")
    if rm:
        return {"operator": "OP-ROW", "lhs": rm.group(1),
                "args": [rm.group(2), rm.group(3)],
                "raw": line.rstrip("\n")}

    sid = _SETIDX_LINE.match(line or "")
    if sid:
        # args = (右值, 下标) —— 与 mir.py 降级后的 op: 行同序
        return {"operator": "OP-SETIDX", "lhs": sid.group(1),
                "args": [sid.group(3), sid.group(2)],
                "raw": line.rstrip("\n")}

    m = _ASSIGN_RE.match(line or "")
    if not m:
        return None
    lhs, rhs = m.group(1), m.group(2).strip()

    fdm = _FIND_RE.match(rhs)
    if fdm:
        return {"operator": "OP-FIND",
                "lhs": lhs,
                "args": [fdm.group(1), str(_MASK_CMP[fdm.group(2)]),
                         fdm.group(3)],
                "raw": line.rstrip("\n")}

    cm = _CALL_RE.match(rhs)
    if cm:
        return {"operator": _CALL_OPS[cm.group(1)],
                "lhs": lhs, "args": [cm.group(2)], "raw": line.rstrip("\n")}

    tm = _TRANS_RE.match(rhs)
    if tm:
        return {"operator": "OP-TRANSPOSE",
                "lhs": lhs, "args": [tm.group(1)], "raw": line.rstrip("\n")}

    flm = _FLAT_RE.match(rhs)
    if flm:
        return {"operator": "OP-FLATTEN",
                "lhs": lhs, "args": [flm.group(1)], "raw": line.rstrip("\n")}

    mkm = _MASK_RE.match(rhs)
    if mkm and mkm.group(1) == mkm.group(2):
        # 只认"对自身比较"（x(x>1)）。`x(y>1)` 是别的语义（y 是掩码），不做。
        return {"operator": "OP-MASK",
                "lhs": lhs,
                "args": [mkm.group(1), str(_MASK_CMP[mkm.group(3)]),
                         mkm.group(4)],
                "raw": line.rstrip("\n")}

    slm = _SLICE_RE.match(rhs)
    if slm:
        return {"operator": "OP-SLICE",
                "lhs": lhs, "args": [slm.group(1), slm.group(2), slm.group(3)],
                "raw": line.rstrip("\n")}

    im = _INDEX_RE.match(rhs)
    if im:
        return {"operator": "OP-INDEX",
                "lhs": lhs, "args": [im.group(1), im.group(2)],
                "raw": line.rstrip("\n")}

    bm = _BIN_RE.match(rhs)
    if bm:
        return {"operator": _BIN_OPS[bm.group(2)],
                "lhs": lhs, "args": [bm.group(1), bm.group(3)],
                "raw": line.rstrip("\n")}
    return None


def to_operators(source):
    """逐行识别；返回 {uses, unmapped}。空行/注释不算 unmapped。"""
    uses = []
    unmapped = []
    for line in (source or "").splitlines():
        s = line.strip()
        if not s or s.startswith("%"):
            continue
        u = parse_line(s)
        if u is None:
            unmapped.append(s)
        else:
            uses.append(u)
    return {"uses": uses, "unmapped": unmapped}


def emit_c(use, indent="    "):
    """把一条算子用例落成 C 片段（`st` 由调用方声明/检查）。"""
    op = by_id(use["operator"])
    out = [indent + "/* %s: %s */" % (op["id"], op["matlab"])]
    if op["id"] in C_IMPLEMENTED:
        if op["id"] == "OP-INDEX":
            out.append(indent + "st = mlc_op_index(&%s, %s, &%s);"
                       % (use["args"][0], use["args"][1], use["lhs"]))
        elif len(use["args"]) == 1:
            out.append(indent + "st = %s(&%s, &%s);"
                       % (op["c"], use["args"][0], use["lhs"]))
        else:
            out.append(indent + "st = %s(&%s, &%s, &%s);"
                       % (op["c"], use["args"][0], use["args"][1],
                          use["lhs"]))
        out.append(indent + "if (st != MLC_OK) { return st; }")
    else:
        out.append(indent + "st = MLC_UNIMPLEMENTED;"
                   " /* %s: C 落点未实现（诚实边界） */" % op["id"])
    return "\n".join(out)


def golden_for(op_id):
    """该算子的夹具文件名（来自 verified_by，逗号分隔）。"""
    op = by_id(op_id)
    raw = op.get("verified_by") or ""
    return [x.strip() for x in raw.split(",") if x.strip()]


def operator_problems(ops=None):
    """纯函数：算子目录的两向自检。空 = 干净。`ops` 可注入（自证用）。"""
    ops = OPERATORS if ops is None else ops
    probs = []
    seen = set()
    for op in ops:
        oid = op.get("id", "")
        if not oid:
            probs.append("OP0 有算子没有 id")
            continue
        if oid in seen:
            probs.append("OP0 算子 ID 重复：%s" % oid)
        seen.add(oid)
        for key in ("matlab", "c", "kind", "rules", "sample"):
            if not op.get(key):
                probs.append("OP1 %s 缺字段 %s" % (oid, key))
        # `verified_by` 为空是**一等状态**（未验证），不是缺陷；
        # 但一旦写了夹具，文件必须真的存在。
        raw = op.get("verified_by") or ""
        for fn in [x.strip() for x in raw.split(",") if x.strip()]:
            if not os.path.isfile(os.path.join(GOLDEN_DIR, fn)):
                probs.append("OP2 %s 的夹具不存在：%s" % (oid, fn))
    # 每个 sample 必须能被自己的算子识别（不许“登记了却解析不到”）
    for op in ops:
        u = parse_line(op.get("sample", ""))
        if u is None:
            probs.append("OP3 %s 的 sample 解析不到" % op.get("id"))
        elif u["operator"] != op.get("id"):
            probs.append("OP3 %s 的 sample 被识别成 %s"
                         % (op.get("id"), u["operator"]))
    return probs


def operator_census(ops=None):
    """验证状态三分普查（派生量）：total / verified / unverified。"""
    ops = OPERATORS if ops is None else ops
    v = [op for op in ops if op.get("verified_by")]
    return {"total": len(ops), "verified": len(v),
            "unverified": len(ops) - len(v)}
