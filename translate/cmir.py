# -*- coding: utf-8 -*-
"""C → MIR（第三段链路）。**只认我们自己生成的 C 子集**，不做通用 C 前端。

## 为什么只做子集

通用 C 前端（宏、指针运算、任意表达式）成本极高，且很容易做出“看起来能解析、
实际上语义全丢”的假实现。而我们生成物的形态是**受限且稳定**的：
算子一律是 `st = mlc_op_xxx(&a, &b, dst);`，常量一律是 `((double *)X.data)[0] = v;`。

## 用途

它让三段链路可以**闭环对拍**：

    .m --mir.py--> MIR --m2c--> C --cmir.py--> MIR'
                                   ↑
                            比较 MIR 与 MIR' 的算子序列

这对“发射器有没有悄悄丢算子”是一个很直接的检查 —— 比读代码可靠。

## 边界

* 只提取**算子调用**与**常量**；控制流（`while`/`for`/`if`）目前**不还原**，只计数；
* 认不出的一律跳过并计数，不猜。
"""
import argparse
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(HERE)
for _p in (_ROOT, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from translate import operators  # noqa: E402
except ImportError:                    # 直接以脚本运行时（cwd 不同）
    import operators                   # type: ignore  # noqa: E402

#: C 函数名 -> 算子 id（**从算子表反查**，不另写一份清单）
_C2OP = {}
for _op in operators.OPERATORS:
    _c = str(_op.get("c") or "")
    if _c.startswith("mlc_op_"):
        _C2OP[_c] = _op["id"]

_FUNC_RE = re.compile(r"^mlc_status\s+m2c_(\w+)\s*\((.*?)\)\s*\{", re.S)
_CALL_RE = re.compile(r"mlc_op_(\w+)\s*\(([^;]*)\)\s*;")
_CONST_RE = re.compile(r"\(\(double \*\)(\w+(?:->\w+)?)\.data\)\[0\]\s*=\s*([-\d.eE+]+)\s*;")
_LOOP_RE = re.compile(r"^\s*(while|for)\s*\(")


def _split_args(s):
    parts, depth, cur = [], 0, []
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def _strip_ref(tok):
    tok = tok.strip()
    while tok.startswith("&"):
        tok = tok[1:]
    tok = tok.replace("->", ".").strip()
    return tok


def c_to_mir(text, fname):
    """把一段生成 C 转成 MIR 文本；返回 (mir 文本, 统计)。"""
    st = {"ops": 0, "consts": 0, "loops": 0, "unknown": 0}

    sig = _FUNC_RE.search(text)
    args, rets = [], []
    if sig:
        for a in _split_args(sig.group(2)):
            if "*" in a:                       # `mlc_array *y` -> 返回值
                rets.append(_strip_ref(a.split("*")[-1]))
            elif a.startswith("mlc_array "):
                args.append(_strip_ref(a.split(None, 1)[1]))

    out = ["version 3"]
    out.append("func:%s" % fname)
    for a in args:
        out.append("arg:%s:f64" % a)
    for r in rets:
        out.append("ret:%s:f64" % r)

    for raw in text.splitlines():
        ln = raw.strip()
        if not ln or ln.startswith(("//", "/*", "*", "#include")):
            continue
        if _LOOP_RE.match(ln):
            st["loops"] += 1                   # 控制流暂不还原
            out.append("# loop: %s" % ln[:60])
            continue
        m = _CONST_RE.search(ln)
        if m:
            out.append("const:%s:%s" % (m.group(1), m.group(2)))
            st["consts"] += 1
            continue
        m = _CALL_RE.search(ln)
        if m and ("mlc_op_" + m.group(1)) in _C2OP:
            oid = _C2OP["mlc_op_" + m.group(1)]
            parts = [_strip_ref(p) for p in _split_args(m.group(2))]
            out.append("op:%s:%s" % (oid, ":".join(parts)))
            st["ops"] += 1
            continue
        if ln.startswith(("if (", "return", "}", "{", "mlc_array", "int64_t",
                          "double *", "const double *", "(void)")):
            continue
        st["unknown"] += 1
    out.append("end")
    return "\n".join(out) + "\n", st


def main():
    ap = argparse.ArgumentParser(description="C → MIR（只认本仓生成的 C 子集）")
    ap.add_argument("cfile")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--name", default=None)
    a = ap.parse_args()
    text = io.open(a.cfile, encoding="utf-8", errors="replace").read()
    name = a.name or os.path.splitext(os.path.basename(a.cfile))[0]
    mir, st = c_to_mir(text, name)
    out = a.out or (os.path.splitext(a.cfile)[0] + ".mir")
    io.open(out, "w", encoding="utf-8", newline="\n").write(mir)
    print("已写出 %s ｜ 算子 %d ｜ 常量 %d ｜ 控制流(未还原) %d ｜ 跳过 %d"
          % (out, st["ops"], st["consts"], st["loops"], st["unknown"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
