# -*- coding: utf-8 -*-
"""MIR 参考解释器（Python）—— 用于"两边一致"的对拍。

本机没有 MATLAB/Octave，所以"两边的另一边"只能自己造。这里用的是：
**同一份 MIR，两种执行方式**

    MIR ──解释执行（本文件）──▶ 参考结果
     └──发射成 C──▶ gcc 编译运行 ──▶ 实际结果

两者从同一 MIR 出发，但语义实现完全不同（Python 循环 vs C 代码）。
比对能抓出：索引基准（0/1）、存储顺序（行/列优先）、广播规则、形状推断、
别名与所有权 —— **这些都是语法合法的错**，编译器和 golden 都看不见。

诚实边界：只覆盖 MIR 里已有的算子；遇到 `unmapped:` 就**整函数返回 None**
（= 无法对拍），不猜。
"""

# --- 数组：扁平 + 形状（行主序，与 mlc_array 一致） ----------------------


class Arr(object):
    __slots__ = ("data", "shape")

    def __init__(self, data, shape):
        self.data = [float(x) for x in data]
        self.shape = [int(x) for x in shape]

    def __repr__(self):
        return "Arr(%r, %r)" % (self.data[:6], self.shape)


def numel(shape):
    n = 1
    for d in shape:
        n *= d
    return n


def bcast(a_shape, b_shape):
    """按尾维对齐广播；不可广播返回 None（与 C / Rust 同规则）。"""
    n = max(len(a_shape), len(b_shape))
    out = []
    for i in range(n):
        da = a_shape[i + len(a_shape) - n] if i + len(a_shape) >= n else 1
        db = b_shape[i + len(b_shape) - n] if i + len(b_shape) >= n else 1
        if da != db and da != 1 and db != 1:
            return None
        out.append(max(da, db))
    return out


def _strides(shape):
    st = [1] * len(shape)
    for i in range(len(shape) - 2, -1, -1):
        st[i] = st[i + 1] * shape[i + 1]
    return st


def _broadcast_map(shape, out_shape):
    """输出每个线性位置该取输入的哪个位置（广播展开）。"""
    nd = len(out_shape)
    ost = _strides(out_shape)
    ist = _strides(shape)
    idx = []
    for k in range(numel(out_shape)):
        off = 0
        for d in range(nd):
            coord = (k // ost[d]) % out_shape[d]
            sd = d + len(shape) - nd
            if sd >= 0:
                off += (coord if shape[sd] != 1 else 0) * ist[sd]
        idx.append(off)
    return idx


def _binop(a, b, fn):
    sh = bcast(a.shape, b.shape)
    if sh is None:
        return None
    am = _broadcast_map(a.shape, sh)
    bm = _broadcast_map(b.shape, sh)
    return Arr([fn(a.data[am[i]], b.data[bm[i]]) for i in range(len(am))], sh)


_CMP = {0: lambda v, k: v > k, 1: lambda v, k: v >= k, 2: lambda v, k: v < k,
        3: lambda v, k: v <= k, 4: lambda v, k: v == k, 5: lambda v, k: v != k}


def _linear_offset(shape, idx0):
    """MATLAB 列主序线性下标 -> 行主序扁平 offset。"""
    if idx0 < 0 or idx0 >= numel(shape):
        return None
    st = _strides(shape)
    off = 0
    for d, dim in enumerate(shape):
        off += (idx0 % dim) * st[d]
        idx0 //= dim
    return off


def _i(x):
    """取整数（标量数组或数字都接受）。"""
    return int(x.data[0]) if isinstance(x, Arr) else int(x)


def _f(x):
    """取浮点。"""
    return float(x.data[0]) if isinstance(x, Arr) else float(x)


def apply_op(oid, args):
    """执行一个算子；无法执行返回 None（放弃，不猜）。"""
    try:
        return _apply_op(oid, args)
    except Exception:        # noqa: BLE001 - 参考执行器不该因为类型意外而崩
        return None


def _apply_op(oid, args):
    if oid in ("OP-ADD", "OP-SUB", "OP-MUL", "OP-DIV"):
        fn = {"OP-ADD": lambda x, y: x + y,
              "OP-SUB": lambda x, y: x - y,
              "OP-MUL": lambda x, y: x * y,
              "OP-DIV": lambda x, y: (x / y) if y else float("inf")}[oid]
        return _binop(args[0], args[1], fn)
    if oid == "OP-SUM":
        a = args[0]
        d = a.data
        if len(a.shape) == 1:
            return Arr([sum(d)], [1])
        if len(a.shape) == 2:
            rows, cols = a.shape
            if rows > 1:
                # MATLAB 默认沿第一个非单例维：2x3 -> 1x3
                return Arr([sum(d[i * cols + j] for i in range(rows))
                            for j in range(cols)], [1, cols])
            return Arr([sum(d)], [1])
        return None
    if oid in ("OP-MEAN", "OP-MAX", "OP-MIN"):
        d = args[0].data
        if oid == "OP-MEAN":
            return Arr([sum(d) / len(d) if d else 0.0], [1])
        if oid == "OP-MAX":
            return Arr([max(d) if d else 0.0], [1])
        return Arr([min(d) if d else 0.0], [1])
    if oid == "OP-INDEX":
        a, i = args[0], _i(args[1])
        if i < 1 or i > len(a.data):
            return None
        off = _linear_offset(a.shape, i - 1)
        if off is None:
            return None
        return Arr([a.data[off]], [1])
    if oid in ("OP-SQRT", "OP-ABS", "OP-EXP", "OP-LOG"):
        import math as _m
        f = {"OP-SQRT": _m.sqrt, "OP-ABS": abs,
             "OP-EXP": _m.exp, "OP-LOG": _m.log}[oid]
        return Arr([f(v) for v in args[0].data], list(args[0].shape))
    if oid == "OP-COLRANGE":
        a = args[0]
        lo = int(args[1]); hi = int(args[2])
        sh = a.shape or [len(a.data)]
        if len(sh) < 2:
            raise ValueError("colrange 需要 2-D")
        rows, cols = sh[0], sh[1]
        if hi < 0:
            hi = cols
        if lo < 1 or hi > cols or hi < lo:
            raise ValueError("colrange 越界")
        k = hi - lo + 1
        d = [a.data[i * cols + (lo - 1 + j)]
             for j in range(k) for i in range(rows)]
        return Arr(d, [rows, k])
    if oid == "OP-COL":
        a = args[0]
        j = int(args[1]) if isinstance(args[1], int) else int(args[1].data[0])
        sh = a.shape or [len(a.data)]
        if len(sh) < 2 or j < 1 or j > sh[1]:
            raise ValueError("col 越界")
        rows = sh[0]
        return Arr([a.data[i + (j - 1) * rows] for i in range(rows)], [rows])
    if oid == "OP-SIZE":
        dim = int(args[1]) if len(args) > 1 else 1
        sh = args[0].shape or [len(args[0].data)]
        val = sh[dim - 1] if dim <= len(sh) else (1 if args[0].data else 0)
        return Arr([float(val)], [1])
    if oid == "OP-NUMEL":
        return Arr([float(len(args[0].data))], [1])
    if oid == "OP-LENGTH":
        sh = args[0].shape or [len(args[0].data)]
        return Arr([float(max(sh))], [1])
    if oid == "OP-ISEMPTY":
        return Arr([1.0 if len(args[0].data) == 0 else 0.0], [1])
    if oid == "OP-ROW":
        # A(i,:)：二维，返回第 i 行；越界放弃（不猜）
        a, row = args[0], _i(args[1])
        if len(a.shape) != 2:
            return None
        rows, cols = a.shape
        if row < 1 or row > rows:
            return None
        base = (row - 1) * cols
        return Arr(list(a.data[base:base + cols]), [cols])
    if oid == "OP-SLICE":
        a, lo, hi = args[0], _i(args[1]), _i(args[2])
        if len(a.shape) != 1 or lo < 1 or hi < lo or hi > a.shape[0]:
            return None
        return Arr(a.data[lo - 1:hi], [hi - lo + 1])
    if oid == "OP-FLATTEN":
        a = args[0]
        if len(a.shape) == 1:
            return Arr(a.data, [a.shape[0]])
        if len(a.shape) < 2:
            return None
        n = numel(a.shape)
        return Arr([a.data[_linear_offset(a.shape, k)] for k in range(n)],
                   [n])
    if oid in ("OP-MASK", "OP-FIND"):
        a, cmp_v, k = args[0], _i(args[1]), _f(args[2])
        if len(a.shape) != 1:
            return None
        test = _CMP[cmp_v]
        if oid == "OP-MASK":
            out = [v for v in a.data if test(v, k)]
        else:
            out = [float(i + 1) for i, v in enumerate(a.data) if test(v, k)]
        return Arr(out, [len(out)])
    if oid == "OP-TRANSPOSE":
        a = args[0]
        if len(a.shape) != 2:
            return None
        m, n = a.shape
        return Arr([a.data[i * n + j] for j in range(n) for i in range(m)],
                   [n, m])
    if oid == "OP-MATMUL":
        a, b = args[0], args[1]
        if len(a.shape) != 2 or len(b.shape) != 2 or a.shape[1] != b.shape[0]:
            return None
        m, k = a.shape
        _, n = b.shape
        out = [sum(a.data[i * k + t] * b.data[t * n + j] for t in range(k))
               for i in range(m) for j in range(n)]
        return Arr(out, [m, n])
    return None


# --- MIR 解析 -------------------------------------------------------------


class Func(object):
    def __init__(self, name):
        self.name = name
        self.args = []       # [(name, shape|None)]
        self.rets = []       # [(name, shape|None)]
        self.locals = []
        self.body = []
        self.unmapped = 0
        self.reject = None   # 整函数被拒的原因（cell/struct/...）


def _var(spec):
    p = spec.split(":")
    shape = None
    if len(p) >= 3 and p[2]:
        shape = [int(x) for x in p[2].split(",")]
    return (p[0], shape)


def parse(text):
    funcs, cur = [], None
    stack = []           # dict: kind / body / data

    def emit(stmt):
        if stack:
            fr = stack[-1]
            if fr["kind"] == "if":
                # then / else 必须分开收集，否则 `if` 永远走同一个分支
                (fr["else"] if fr["in_else"] else fr["then"]).append(stmt)
            else:
                fr["body"].append(stmt)
        elif cur is not None:
            cur.body.append(stmt)

    for raw in text.splitlines():
        ln = raw.strip()
        if not ln or ln.startswith("#") or ln.startswith("version"):
            continue
        if ln.startswith("func:"):
            cur = Func(ln[5:])
            funcs.append(cur)
            stack = []
            continue
        if cur is None:
            continue
        if ln.startswith("arg:"):
            cur.args.append(_var(ln[4:]))
        elif ln.startswith("ret:"):
            cur.rets.append(_var(ln[4:]))
        elif ln.startswith("var:"):
            cur.locals.append(ln[4:].split(":")[0])
        elif ln == "else":
            if stack and stack[-1]["kind"] == "if":
                stack[-1]["in_else"] = True
        elif ln == "end":
            if not stack:
                continue
            fr = stack.pop()
            if fr["kind"] == "for":
                emit(("for", fr["data"], fr["body"]))
            elif fr["kind"] == "while":
                emit(("while", fr["data"], fr["body"]))
            else:
                emit(("if", fr["data"], (fr["then"], fr["else"])))
        elif ln.startswith("op:"):
            p = ln[3:].split(":")
            emit(("op", (p[0], p[1], [x for x in p[2:] if x]), None))
        elif ln.startswith("const:"):
            p = ln[6:].split(":")
            emit(("const", (p[0], float(p[1])), None))
        elif ln.startswith("fill:"):
            p = ln[5:].split(":")
            emit(("fill", (p[0], [int(x) for x in p[1].split(",")],
                           float(p[2])), None))
        elif ln.startswith("set:"):
            p = ln[4:].split(":")
            emit(("set", (p[0], p[1]), None))
        elif ln.startswith("setb:"):
            p = ln[5:].split(":")     # "setb:" 是 5 个字符，少一位会整体错位
            emit(("setb", (p[0], p[1], p[2], p[3]), None))
        elif ln.startswith("call2:"):
            p = ln[6:].split(":")
            names = [x.strip() for x in p[0].split(",") if x.strip()]
            emit(("call2", (names, p[1], [x for x in p[2:] if x]), None))
        elif ln.startswith("call:"):
            p = ln[5:].split(":")
            emit(("call", (p[0], p[1], [x for x in p[2:] if x]), None))
        elif ln.startswith("for:"):
            p = ln[4:].split(":")
            stack.append({"kind": "for", "data": {"var": p[0], "from": p[1],
                                                 "to": p[2]}, "body": []})
        elif ln.startswith("while:"):
            p = ln[6:].split(":")
            stack.append({"kind": "while", "data": {"cond": (p[0], p[1], p[2])},
                          "body": []})
        elif ln.startswith("if:"):
            p = ln[3:].split(":")
            stack.append({"kind": "if", "data": (p[0], p[1], p[2]),
                          "then": [], "else": [], "in_else": False,
                          "body": []})
        elif ln == "break":
            emit(("break", None, None))
        elif ln.startswith("reject:"):
            cur.reject = ln[7:].strip()
        elif ln.startswith("unmapped:"):
            cur.unmapped += 1
    return funcs


# --- 执行 -----------------------------------------------------------------

def _num(s, env):
    if s in env:
        v = env[s]
        return v.data[0] if isinstance(v, Arr) else float(v)
    try:
        return float(s)
    except ValueError:
        return None


def _cond(env, cond):
    left = _num(cond[0], env)
    right = _num(cond[2], env)
    if left is None or right is None:
        return None
    return {"eq": left == right, "ne": left != right, "lt": left < right,
            "le": left <= right, "gt": left > right,
            "ge": left >= right}[cond[1]]


def exec_block(stmts, env, by_name, depth=0):
    if depth > 64:
        return False
    for kind, data, body in stmts:
        if kind == "op":
            oid, lhs, args = data
            if oid == "OP-SETIDX":
                # args = (右值, 下标)。就地写：只有这里同时有 lhs 与 env
                v = env.get(args[0]) if args[0] in env else None
                if v is None:
                    return False
                idx = _num(args[1], env)
                dst = env.get(lhs)
                if idx is None or dst is None:
                    return False
                i0 = int(idx) - 1
                if i0 < 0 or i0 >= len(dst.data):
                    return False
                dst.data[i0] = float(v.data[0])
                continue
            vals = []
            for a in args:
                if a in env:
                    vals.append(env[a])
                else:
                    try:
                        vals.append(Arr([float(a)], [1]))
                    except ValueError:
                        return False
            out = apply_op(oid, vals)
            if out is None:
                return False
            env[lhs] = out
        elif kind == "const":
            env[data[0]] = Arr([data[1]], [1])
        elif kind == "fill":
            env[data[0]] = Arr([data[2]] * numel(data[1]), data[1])
        elif kind == "set":
            v = _num(data[1], env)
            if v is None:
                return False
            env[data[0]] = v
        elif kind == "setb":
            name, op, a, b = data
            av, bv = _num(a, env), _num(b, env)
            if av is None or bv is None:
                return False
            env[name] = {"add": av + bv, "sub": av - bv, "mul": av * bv,
                         "div": (av / bv if bv else float("inf"))}[op]
        elif kind == "call2":
            names, fname, args = data
            callee = by_name.get(fname)
            if callee is None or len(callee.rets) != len(names):
                return False
            avals = [env.get(a) for a in args]
            if any(v is None for v in avals):
                return False
            res = call(callee, avals, by_name, depth + 1)
            if res is None or len(res) != len(names):
                return False
            for n, v in zip(names, res):
                env[n] = v
        elif kind == "call":
            lhs, fname, args = data
            callee = by_name.get(fname)
            if callee is None or len(callee.rets) != 1:
                return False
            avals = [env.get(a) for a in args]
            if any(v is None for v in avals):
                return False
            res = call(callee, avals, by_name, depth + 1)
            if res is None:
                return False
            env[lhs] = res[0]
        elif kind == "for":
            lo, hi = _num(data["from"], env), _num(data["to"], env)
            if lo is None or hi is None:
                return False
            for k in range(int(lo), int(hi) + 1):
                env[data["var"]] = k
                if not exec_block(body, env, by_name, depth + 1):
                    return False
        elif kind == "if":
            c = _cond(env, data)
            if c is None:
                return False
            then_b, else_b = body
            if not exec_block(then_b if c else else_b, env, by_name, depth + 1):
                return False
        elif kind == "break":
            env["__break__"] = True
        elif kind == "while":
            for _ in range(100000):
                c = _cond(env, data["cond"])
                if c is None:
                    return False
                if not c:
                    break
                env.pop("__break__", None)
                if not exec_block(body, env, by_name, depth + 1):
                    return False
                if env.pop("__break__", None):
                    break
            else:
                return False
        # break 要立刻停止本轮剩余语句，否则后面的赋值还会执行（差一轮）
        if env.get("__break__"):
            return True
    return True


def call(func, arg_vals, by_name, depth=0):
    """执行一个函数；返回 [Arr] 或 None（无法对拍）。"""
    if func.unmapped:
        return None
    if len(func.args) != len(arg_vals):
        return None
    env = {}
    for (name, _shape), val in zip(func.args, arg_vals):
        env[name] = val
    try:
        ok = exec_block(func.body, env, by_name, depth)
    except Exception:        # noqa: BLE001
        return None
    if not ok:
        return None
    out = []
    for rname, _shape in func.rets:
        if rname not in env:
            return None
        v = env[rname]
        out.append(v if isinstance(v, Arr) else Arr([v], [1]))
    return out


DYNAMIC_OPS = ("OP-MASK", "OP-FIND")


def ret_is_dynamic(func, name):
    """返回值是否由"长度数据相关"的算子产生（C 侧允许它没有声明形状）。"""
    def walk(stmts):
        for kind, data, body in stmts:
            if kind == "op" and data[1] == name and data[0] in DYNAMIC_OPS:
                return True
            if kind == "if" and body:
                if walk(body[0]) or walk(body[1]):
                    return True
            if body and kind in ("for", "while"):
                if walk(body):
                    return True
        return False
    return walk(func.body)


def drivable(func):
    """能否被外部驱动 —— **必须与 C 侧 main 的 drivable 逐条一致**。

    否则会对同一个函数一边判"可跑"、一边判"跳过"，产生**假不一致**
    （YALMIP 的 `isnan` 就是这么被误报的）。
    """
    if func.unmapped or not func.args or not func.rets:
        return False
    for _name, shape in func.args:
        if shape is not None and not shape:
            return False
    for name, shape in func.rets:
        if shape:
            continue
        if ret_is_dynamic(func, name):
            continue
        return False
    return True


def run_all(funcs):
    """对每个可驱动函数，用默认输入（a[i]=i+1、标量 2）算出输出。

    返回 {函数名: [Arr] 或 None}。
    """
    by_name = dict((f.name, f) for f in funcs)
    out = {}
    for f in funcs:
        if not drivable(f):
            out[f.name] = None
            continue
        args = []
        for _n, sh in f.args:
            if sh:
                args.append(Arr([float(i + 1) for i in range(numel(sh))], sh))
            else:
                args.append(2)      # 标量默认值，与 main.c 一致
        try:
            out[f.name] = call(f, args, by_name)
        except Exception:    # noqa: BLE001
            out[f.name] = None
    return out
