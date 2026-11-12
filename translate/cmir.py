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


#: `mlc_ops.h` 里的原型：`{c 名: [参数类型…]}`。缓存一次。
_PROTOS = {}


def _protos():
    if _PROTOS:
        return _PROTOS
    import re as _re
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "c_runtime", "include", "mlc_ops.h")
    if not os.path.isfile(p):
        return _PROTOS
    s = io.open(p, encoding="utf-8", errors="replace").read()
    for m in _re.finditer(r"mlc_status\s+(mlc_op_\w+)\s*\(([^;]*?)\)\s*;", s, _re.S):
        _PROTOS[m.group(1)] = _split_args(m.group(2))
    return _PROTOS


def _dst_index(cname, nargs):
    """dst 在实参里的位置：**唯一一个非 `const` 的 `mlc_array *` 参数**。

    早前用"dst 在最后一位"的固定规则，`OP-SETIDX` 就此出错：
    原型是 `mlc_op_setidx(mlc_array *a, const mlc_array *v, int64_t i)` ——
    dst 在**第一位**，标量下标在最后。硬套"末位"会把下标当成 dst。
    查不到原型时退回末位（保守，与旧行为一致）。
    """
    ps = _protos().get(cname) or []
    for i, t in enumerate(ps):
        if "mlc_array" in t and "*" in t and "const" not in t:
            if i < nargs:
                return i
    return nargs - 1


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
#: 算子调用。两种写法都要认：
#:   裸调用 `st = mlc_op_add(&a, &b, &y);`
#:   守卫式 `if (mlc_op_add(&a, &b, &y) != MLC_OK) { return st; }`
#: 只认前者的后果：反推里**算子全丢**（实测 `iseqtest` 只剩 0 个算子）。
_CALL_RE = re.compile(r"mlc_op_(\w+)\s*\(([^;]*?)\)\s*(?:!=|;)")
#: 常量写回。**`.data` 与 `->data` 都要认**：返回值是 `mlc_array *`，
#: 发射器写的是 `((double *)y->data)[0] = 0;` —— 只认 `.data` 时这条被忽略，
#: 于是 `y` 从未被初始化，VM 报「未定义的量：y」（实测 `iseqtest`）。
_CONST_RE = re.compile(
    r"\(\(double \*\)(\w+(?:->\w+)?)(?:\.|->)data\)\[0\]\s*=\s*([-\d.eE+]+)\s*;")
_LOOP_RE = re.compile(r"^\s*(while|for)\s*\(")

#: 骨架守卫：`if (st != MLC_OK) { return st; }` / `if (mlc_array_init(...) != MLC_OK)`
#: —— 它们不是源码里的分支，是发射器保证错误传播的样板，**必须跳过**，
#: 否则反推出来的 MIR 会多出一堆假 `if`。
_GUARD_RE = re.compile(r"^\s*if\s*\(.*(!=\s*MLC_OK|==\s*MLC_ERR).*$")

#: 真分支：`if (((const double *)__t3.data)[0] > ((const double *)y->data)[0]) {`
_IF_RE = re.compile(r"^\s*if\s*\((.*)\)\s*\{\s*$")
_ELSE_RE = re.compile(r"^\s*\}\s*else\s*\{\s*$")

#: 操作数：`((const double *)X.data)[0]` / `((const double *)X->data)[0]` / 数字
_OPERAND_RE = re.compile(
    r"\(\s*\(\s*const\s+double\s*\*\s*\)\s*(\w+)(?:\s*\.data|\s*->data)\s*\)"
    r"\s*\[\s*0\s*\]")
_CMP_C2MIR = {"==": "eq", "!=": "ne", "<": "lt", "<=": "le", ">": "gt", ">=": "ge"}

#: `for (int64_t i = 2; i <= 3; ++i) {` —— MIR 是 `for:i:2:3`
_FOR_RE = re.compile(
    r"^\s*for\s*\(\s*int64_t\s+(\w+)\s*=\s*(-?\d+)\s*;\s*\1\s*<=\s*(\w+|-?\d+)\s*;")

#: `zeros/ones` 的**单行填充循环**：
#:   `for (int64_t i = 0; i < mlc_array_numel(y); ++i) { ((double *)y->data)[i] = 0; }`
#: MIR 是 `fill:<名字>:<维度>:<值>` —— 维度取自形状元数据（`arg-shape`/`ret-shape`
#: 或 `mlc_array_init`）。**必须排在 `_FOR_RE` 之前**，否则会被当成普通循环。
_FILL_RE = re.compile(
    r"^\s*for\s*\(\s*int64_t\s+\w+\s*=\s*0\s*;\s*\w+\s*<\s*mlc_array_numel\((\w+)\)"
    r"\s*;\s*\+\+\w+\s*\)\s*\{\s*\(\(double\s*\*\)\s*(\w+)(?:->|\.)data\)"
    r"\s*\[\s*\w+\s*\]\s*=\s*([-\d.eE+]+)\s*;\s*\}\s*$")

#: `int64_t __j1 = 0;` —— 标量局部量，MIR 是 `var:__j1:i64`
_INT_LOCAL_RE = re.compile(r"^\s*int64_t\s+(\w+)\s*=\s*-?\d+\s*;\s*$")

#: `__j1 = 2 - 1;` —— 标量二元运算，MIR 是 `setb:__j1:sub:2:1`
_SETB_RE = re.compile(r"^(\w+)\s*=\s*(\w+|-?\d+)\s*([-+*/])\s*(\w+|-?\d+)\s*;\s*$")
_SET_RE = re.compile(r"^(\w+)\s*=\s*(-?\d+)\s*;\s*$")
_OP_C2MIR = {"-": "sub", "+": "add", "*": "mul", "/": "div"}

#: `while (i <= 4) {` —— MIR 是 `while:i:le:4`
_WHILE_RE = re.compile(r"^\s*while\s*\((.*)\)\s*\{\s*$")

#: 函数间调用。生成物实测两种写法：
#:   `st = m2c_addone(x, y);`        ← 输出直接传（`y` 已是指针）
#:   `st = m2c_scale2(*y, y);`       ← 实参带解引用
#: 定义行 `mlc_status m2c_addone(mlc_array x, mlc_array *y) {` **不会**命中
#: （它以 `) {` 结尾，而这里要求 `);` 或 `) !=`）。
#: MIR 是 `call:<dst>:<函数名>:<实参…>` —— **dst 在最后一位**。
_FCALL_RE = re.compile(r"\bm2c_(\w+)\s*\(([^;]*?)\)\s*(?:!=|;)")

#: 迭代上限守卫：`if (++__m2c_iter > 1000000LL) { return MLC_ERR; }`
#: 它由发射器插入（防止死循环），**不是源码分支**。
_ITER_GUARD = "__m2c_iter"


def _is_num(t):
    try:
        float(t)
        return True
    except ValueError:
        return False


def _cond_to_mir(expr):
    """把 C 的比较式转成 `var:cmp:rhs`；转不了返回 None（不猜）。"""
    e = expr.strip()
    for c, name in (("==", "eq"), ("!=", "ne"), ("<=", "le"), (">=", "ge"),
                    ("<", "lt"), (">", "gt")):
        if c not in e:
            continue
        left, _, right = e.partition(c)

        def operand(t):
            t = t.strip()
            m = _OPERAND_RE.search(t)
            if m:
                return m.group(1)
            # **裸标识符/数字**：`while (i <= 4)` 里的 `i` 就是标量名，
            # 不是 `((double *)x.data)[0]` 那种取值形式。
            t = _CAST_RE.sub("", t).strip()
            if t.replace("_", "").isalnum() or _is_num(t):
                return t
            return None

        a, b = operand(left), operand(right)
        if a and b:
            return "%s:%s:%s" % (a, name, b)
    return None


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


#: C 的强制类型转换：`(int64_t)4` / `(double)` / `(const double *)`
_CAST_RE = re.compile(r"^\(\s*(?:const\s+)?(?:double|int64_t|int32_t|int|size_t)\s*\*?\s*\)")


def _strip_ref(tok):
    tok = tok.strip()
    # `&x`（取地址）与 `*y`（解引用，跨文件调用时实参常这么写）都要剥掉：
    # MIR 里只有名字。签名解析另有分支先按 `*` 分类，所以这里剥不会误伤。
    while tok[:1] in ("&", "*"):
        tok = tok[1:]
    tok = _CAST_RE.sub("", tok).strip()     # `(int64_t)4` -> `4`
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
    depth = 0                                  # 已识别的 if/else/for/while 块深度
    scalars = set()                            # 已声明为 i64 的标量（set/setb 只对它们还原）
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
        if _GUARD_RE.match(ln) and "mlc_op_" not in ln:
            # 骨架守卫，不是源码分支。
            # ⚠ **但含 `mlc_op_` 的行不能跳**：发射器把算子也写成守卫形式
            #   `if (mlc_op_isequal(&x,&x,&__c1) != MLC_OK) {...}`，
            #   整行跳过会把算子一起丢掉（实测 `iseqtest` 反推后算子是 0 个）。
            continue
        if _ELSE_RE.match(ln):
            if depth > 0:
                out.append("else")
            continue
        m_if = _IF_RE.match(ln)
        if m_if:
            cond = _cond_to_mir(m_if.group(1))
            if cond:
                out.append("if:%s" % cond)
                depth += 1
            else:
                # 转不了就如实留注释，不伪造分支（半真的 if 比没有更危险）
                out.append("# if?: %s" % m_if.group(1)[:60])
            continue
        if ln == "}":
            if depth > 0:
                depth -= 1
                out.append("end")
            continue
        m_fill = _FILL_RE.match(ln)
        if m_fill:
            name = m_fill.group(1)
            # 维度取**形状元数据**。已知差异：原 MIR 里 `ret:y:f64:4` 与
            # `fill:y:1,4:0` 本身就不一致（返回声明是 1 维 4，填充分配是 1×4），
            # C 只记了前者，所以反推得到 `fill:y:4:0` —— 元素数相同、数值一致，
            # 是**原 MIR 的信息差**，不是反推丢维度。
            dims = shapes.get(name) or ",".join(inits.get(name) or ["1"])
            out.append("fill:%s:%s:%s" % (name, dims, m_fill.group(3)))
            st["fills"] = st.get("fills", 0) + 1
            continue
        m_for = _FOR_RE.match(ln)
        if m_for:
            out.append("for:%s:%s:%s" % (m_for.group(1), m_for.group(2),
                                         m_for.group(3)))
            st["loops"] += 1
            depth += 1
            continue
        m_int = _INT_LOCAL_RE.match(ln)
        if m_int:
            if _ITER_GUARD in ln:
                continue                        # 发射器插入的死循环守卫，不属于源码
            out.append("var:%s:i64" % m_int.group(1))   # 标量局部量
            scalars.add(m_int.group(1))
            continue
        m_sb = _SETB_RE.match(ln)
        if m_sb and m_sb.group(1) in scalars:
            # 只对**已声明为 i64 的标量**还原（数组赋值另有其道，不猜）
            out.append("setb:%s:%s:%s:%s"
                       % (m_sb.group(1), _OP_C2MIR[m_sb.group(3)],
                          m_sb.group(2), m_sb.group(4)))
            continue
        m_set = _SET_RE.match(ln)
        if m_set and m_set.group(1) in scalars:
            out.append("set:%s:%s" % (m_set.group(1), m_set.group(2)))
            continue
        m_wh = _WHILE_RE.match(ln)
        if m_wh:
            cond = _cond_to_mir(m_wh.group(1))
            if cond:
                out.append("while:%s" % cond)
                depth += 1
            else:
                out.append("# while?: %s" % m_wh.group(1)[:60])
            continue
        if ln == "break;":
            out.append("break")
            continue
        if _LOOP_RE.match(ln):
            st["loops"] += 1                   # while 尚未还原（for/if 已还原）
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
                # dst 的位置按**原型**定（非 const 的 `mlc_array *`），
                # 不是固定末位 —— `OP-SETIDX` 的 dst 就在第一位。
                di = _dst_index("mlc_op_" + m.group(1), len(parts))
                parts = [parts[di]] + parts[:di] + parts[di + 1:]
            out.append("op:%s:%s" % (oid, ":".join(parts)))
            st["ops"] += 1
            continue
        m_fc = _FCALL_RE.search(ln)
        if m_fc:
            # 函数间调用（`m2c_` 前缀，与 `mlc_op_` 不冲突）
            parts = [_strip_ref(p) for p in _split_args(m_fc.group(2))]
            if len(parts) >= 2:
                out.append("call:%s:%s:%s"
                           % (parts[-1], m_fc.group(1), ":".join(parts[:-1])))
                st["calls"] = st.get("calls", 0) + 1
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
