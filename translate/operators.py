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
    {"id": "OP-INDEX", "matlab": "x(i)", "c": "mlc_op_index",
     "kind": "index", "rules": ("IDX-1", "ORDER-1"),
     "sample": "y = x(2);",
     "verified_by": "op_index_shift.json"},
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
                 "OP-MATMUL")

_ASSIGN_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*(.+?)\s*;\s*$")
_BIN_RE = re.compile(r"^([A-Za-z_]\w*)\s*(\.\*|\./|\+|-|\*)\s*([A-Za-z_]\w*)$")
_CALL_RE = re.compile(r"^(sum|mean|max|min)\s*\(\s*([A-Za-z_]\w*)\s*\)$")
_TRANS_RE = re.compile(r"^([A-Za-z_]\w*)\s*\.'\s*$")
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


def by_id(op_id):
    for op in OPERATORS:
        if op["id"] == op_id:
            return op
    raise KeyError("未知算子：%s" % op_id)


def parse_line(line):
    """把一条 MATLAB 赋值语句识别成算子；识别不了返回 None（进 unmapped）。"""
    m = _ASSIGN_RE.match(line or "")
    if not m:
        return None
    lhs, rhs = m.group(1), m.group(2).strip()

    cm = _CALL_RE.match(rhs)
    if cm:
        return {"operator": _CALL_OPS[cm.group(1)],
                "lhs": lhs, "args": [cm.group(2)], "raw": line.rstrip("\n")}

    tm = _TRANS_RE.match(rhs)
    if tm:
        return {"operator": "OP-TRANSPOSE",
                "lhs": lhs, "args": [tm.group(1)], "raw": line.rstrip("\n")}

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
