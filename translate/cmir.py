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
    for _c in (str(_op.get("c") or ""),) + tuple(_op.get("c_aliases") or ()):
        if _c.startswith("mlc_op_"):
            _C2OP[_c] = _op["id"]

#: 同一个算子在不同形态下会有**后缀变体**：`mlc_op_size` / `mlc_op_size_all`、
#: `mlc_op_fill` / `mlc_op_fill_alloc`。精确匹配会漏掉这些 → 三段对拍里表现为
#: "算子消失了"（实测 `sizeall` 就是这样，被误判成发射器丢算子）。
_C2OP_SUFFIXES = ("_all", "_alloc", "_n", "_mask", "_masked", "_2")


def _lookup(cname):
    """按 **最长前缀** 反查算子 id（先精确，再去掉已知后缀）。"""
    if cname in _C2OP:
        return _C2OP[cname]
    for suf in _C2OP_SUFFIXES:
        if cname.endswith(suf):
            base = cname[:-len(suf)]
            if base in _C2OP:
                return _C2OP[base]
    return None

#: 函数签名。**必须带 `re.M`**：`^` 否则只匹配文件首字符，而 `.c` 文件开头是
#: 注释块 —— 于是签名永远匹配不到，arg/ret 全空，反推产物在 VM 里一句都跑不了
#: （R793 实测：报「未定义的量」）。
_FUNC_RE = re.compile(r"^mlc_status\s+m2c_(\w+)\s*\((.*?)\)\s*\{", re.S | re.M)
#: `mlc_array s2 = {0};` —— 局部量声明
_LOCAL_RE = re.compile(r"^\s*mlc_array\s+(\w+)\s*(?:=\s*\{0\})?\s*;\s*$", re.M)
#: `mlc_array_init(&s2, MLC_F64, 1, (int64_t[]){4})` —— 紧跟声明的形状
_INIT_RE = re.compile(
    r"mlc_array_init\(\s*&(\w+)\s*,\s*MLC_\w+\s*,\s*(\d+)\s*,\s*"
    r"\(int64_t\[\]\)\s*\{([\d,\s]*)\}\s*\)")
#: `/* @m2c arg-shape A 3,2 */` —— 生成器写的**形状元数据**。
#: C 的签名表达不了它，但对拍需要：没有形状，VM 会用默认值填形参，
#: 数值静默变形（R793 实测 `colmean` 从 `1 3 5` 变 `1 2 3`）。
_SHAPE_RE = re.compile(r"@m2c\s+(arg|ret)-shape\s+(\w+)\s+([\d,]+)")
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
    st = {"ops": 0, "consts": 0, "loops": 0, "unknown": 0, "shape_unknown": 0}

    sig = _FUNC_RE.search(text)
    args, rets = [], []
    if sig:
        # 函数名以 **C 签名**为准（文件名只是兜底）：
        # 之前用 `fname`（文件 stem），反推出的 MIR 全叫 `func:gen`，与源码函数名无关。
        fname = sig.group(1)
        for a in _split_args(sig.group(2)):
            if "*" in a:                       # `mlc_array *y` -> 返回值
                rets.append(_strip_ref(a.split("*")[-1]))
            elif a.startswith("mlc_array "):
                args.append(_strip_ref(a.split(None, 1)[1]))

    # 形状元数据（生成器写在函数头前的注释里）
    shapes = {}
    for m in _SHAPE_RE.finditer(text):
        shapes[m.group(2)] = m.group(3)

    out = ["version 3"]
    out.append("func:%s" % fname)
    for a in args:
        sh = shapes.get(a)
        out.append("arg:%s:f64:%s" % (a, sh) if sh else "arg:%s:f64" % a)
    for r in rets:
        sh = shapes.get(r)
        out.append("ret:%s:f64:%s" % (r, sh) if sh else "ret:%s:f64" % r)
    missing = [n for n in list(args) + list(rets) if n not in shapes]
    if missing:
        # **参数形状在 C 里没有记录**：生成物只写 `mlc_array A`，而原 MIR 是
        # `arg:A:f64:3,2`。反推时补不出来，于是 VM 会用默认值填充 —— 反推产物
        # **可执行、但数值只在"实参恰好是 1 元"时才与原路径一致**（R793 实测：
        # `colmean` 原路径 `1 3 5`，反推 `1 2 3`）。
        # 这里如实标注，而不是假装形状已知。
        out.append("# arg-shape:unknown（C 未记录形参形状，VM 将用默认值填充）")
        st["shape_unknown"] = len(args)
    # **局部量必须声明**，否则 VM 会报「未定义的量」（实测 `sig`）。
    # 形状从紧跟着的 `mlc_array_init(&x, MLC_F64, n, (int64_t[]){...})` 取；
    # 取不到形状时按 1 元声明（**不猜多维**，只保证可执行）。
    inits = dict((m.group(1), [d for d in m.group(3).replace(" ", "").split(",") if d])
                 for m in _INIT_RE.finditer(text))
    declared = set(args) | set(rets)
    for m in _LOCAL_RE.finditer(text):
        nm = m.group(1)
        if nm in declared:
            continue
        declared.add(nm)
        dims = inits.get(nm) or ["1"]
        out.append("var:%s:f64:%s" % (nm, ",".join(dims)))

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
        oid = _lookup("mlc_op_" + m.group(1)) if m else None
        if oid is not None:
            parts = [_strip_ref(p) for p in _split_args(m.group(2))]
            # **实参顺序归一化**：C 侧一律 `mlc_op_x(&a, &b, &dst)`，dst 在**末尾**；
            # 而 MIR 的 `op:` 是 `op:<id>:<dst>:<a>:<b>`，dst 在**第二位**。
            # 不归一化的话，下游（HIR 抬升按名字消费实参）会把 dst 当成操作数 ——
            # 实测 `fir_lp` 的 ③ HIR 往返因此少了一个 `OP-ADD`。
            if len(parts) >= 2:
                parts = [parts[-1]] + parts[:-1]
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
