# -*- coding: utf-8 -*-
"""HIR：语义层（表达式树 + family），位于 MIR（三地址）之上。

## 两层分工

| 层 | 负责 | 不该出现 |
|---|---|---|
| **HIR** | 语义：表达式树、算子 family（`ew/red/un/...`） | 临时量、`OP-*` id |
| **MIR** | 三地址降级结果：`op:` / `const:` / `setb:` | 语义判断 |

## 两个方向

- `hir_to_mir(text)`：**降级**（R692 起）。后序遍历表达式树，每个内部节点分配 `__h<n>`。
- `mir_to_hir(text, func)`：**抬升**（R711 起）。把只被下游消费一次的 `__h*` 临时量
  折回表达式树 —— 这是"HIR 参与三类场景"的前提：没有抬升，HIR 只能单向使用。

`MIR → HIR → MIR` 必须**恒等**（算子多重集相同、VM 数值相同）。控制流语句原样透传，
不参与折树（本版只对直线代码做语义化）。
"""

import re

from translate import hir_ops as _HO

_ExprParser = None   # 延迟定义见下


class _Parser:
    """表达式递归下降：`family.name(a, b(c))` / 变量 / 数字字面量。"""

    def __init__(self, s):
        self.s = s
        self.i = 0

    def _ws(self):
        while self.i < len(self.s) and self.s[self.i] in " \t":
            self.i += 1

    def parse(self):
        self._ws()
        node = self._expr()
        self._ws()
        if self.i != len(self.s):
            raise ValueError("表达式尾部有多余字符：%r" % self.s[self.i:])
        return node

    def _expr(self):
        self._ws()
        if self.i >= len(self.s):
            raise ValueError("表达式意外结束")
        m = re.match(r"-?\d+(?:\.\d+)?", self.s[self.i:])
        if m:
            self.i += len(m.group(0))
            return {"num": m.group(0)}
        m = re.match(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?", self.s[self.i:])
        if not m:
            raise ValueError("无法解析此处：%r" % self.s[self.i:self.i + 12])
        name = m.group(0)
        self.i += len(name)
        self._ws()
        if self.i >= len(self.s) or self.s[self.i] != "(":
            return {"var": name}
        self.i += 1
        args = []
        self._ws()
        if self.i < len(self.s) and self.s[self.i] == ")":
            self.i += 1
        else:
            while True:
                args.append(self._expr())
                self._ws()
                if self.i < len(self.s) and self.s[self.i] == ",":
                    self.i += 1
                    continue
                break
            if self.i >= len(self.s) or self.s[self.i] != ")":
                raise ValueError("缺少右括号")
            self.i += 1
        return {"op": name, "args": args}


_ExprParser = _Parser


def parse_hir(text):
    """HIR 文本 → list[dict]。未知行直接报错（不猜）。"""
    lines = (text or "").strip().split("\n")
    if not lines or lines[0].strip() != "hir 1":
        raise ValueError("首行必须是 `hir 1`")
    out = []
    for raw in lines[1:]:
        s = raw.strip()
        if not s:
            continue
        m = re.match(r"^func:\s*(\S+)$", s)
        if m:
            out.append({"kind": "func", "name": m.group(1)})
            continue
        m = re.match(r"^param\s+(\S+)\s+(\S+)$", s)
        if m:
            out.append({"kind": "param", "name": m.group(1), "type": m.group(2)})
            continue
        m = re.match(r"^ret\s+(\S+)\s+(\S+)$", s)
        if m:
            out.append({"kind": "ret", "name": m.group(1), "type": m.group(2)})
            continue
        m = re.match(r"^([A-Za-z_]\w*)\s*=\s*(.+)$", s)
        if m:
            out.append({"kind": "let", "dst": m.group(1),
                        "expr": _Parser(m.group(2).strip()).parse()})
            continue
        # 透传行（控制流等）：原样保留，不参与折树。
        # **必须剥掉 `raw ` 前缀** —— 否则它会被当成 MIR 语句原样输出，
        # 生成 `raw if:…` 这种垃圾行，m2c 直接拒绝（实测 ② 因此 44 个全部失败）。
        if s.startswith("raw "):
            s = s[4:].strip()
        out.append({"kind": "raw", "text": s})
    return out


def _emit_node(node, dst, out):
    """后序：先降子表达式，再发自己。返回该节点在 MIR 里可用的 token。"""
    if "var" in node:
        return node["var"]
    if "num" in node:
        tmp = _emit_node._counter = getattr(_emit_node, "_counter", 0) + 1
        name = "__h%d" % tmp
        out.append("const:%s:%s" % (name, node["num"]))
        return name

    op = node["op"]
    mir_id = _HO.mir_of(op)
    if mir_id is None:
        raise ValueError("HIR 算子未登记：%s" % op)
    # `alloc` 一族的实参是**标量字面量**（C 侧是 `int64_t rows/cols` 与 `double value`），
    # 物化成临时量会变成 `mlc_array` → gcc 报 "expected double but argument is
    # of type mlc_array"（实测 `filla`）。这类位置必须保持字面量内联。
    keep_literal = _HO.family_of(op) == "alloc"
    args = []
    for a in node["args"]:
        if keep_literal and "num" in a:
            args.append(a["num"])
        else:
            args.append(_emit_node(a, None, out))
    if dst is None:
        _emit_node._counter = getattr(_emit_node, "_counter", 0) + 1
        dst = "__h%d" % _emit_node._counter
    out.append("op:%s:%s:%s" % (mir_id, dst, ":".join(args)))
    return dst


def hir_to_mir(text):
    """HIR 文本 → MIR 语句行（不含 func:/arg:/ret:）。

    临时量从 `__h1` 起全局递增；顶层赋值的左值直接用作 dst；透传行原样输出。
    """
    stmts = parse_hir(text)
    _emit_node._counter = 0
    out = []
    for s in stmts:
        if s["kind"] == "let":
            _emit_node(s["expr"], s["dst"], out)
        elif s["kind"] == "raw":
            out.append(s["text"])
    return "\n".join(out)


# ---------------------------------------------------------------------------
# 抬升：MIR → HIR
# ---------------------------------------------------------------------------

_OP_LINE = re.compile(r"^op:(OP-[A-Z0-9]+):([A-Za-z_]\w*):(.*)$")
_CONST_LINE = re.compile(r"^const:([A-Za-z_]\w*):(-?\d+(?:\.\d+)?)$")
#: 只折**生成器产生的临时量**（`__h` / `__c` / `__t` 前缀），
#: 用户变量一律不折 —— 折了会改变可读性，也会让"这个值后来被改过"变得不可见。
_TEMP_RE = re.compile(r"^__(?:h|c|t)\d+$")
_MIR2HIR_NAME = {v: k for k, v in _HO.HIR_TO_MIR.items()}


def _render(node):
    if "var" in node:
        return node["var"]
    if "num" in node:
        return node["num"]
    return "%s(%s)" % (node["op"], ", ".join(_render(a) for a in node["args"]))


def mir_to_hir(text):
    """MIR 函数体 → HIR 文本。**只折临时量**，其余原样透传。

    返回 `(hir_text, ok)`：`ok=False` 表示有算子无法映射回 HIR 名
    （例如 `OP-ROW` 这种没有 family 的），此时整体退回纯透传 —— 宁可弱，不可错。
    """
    raw_lines = [l for l in (text or "").split("\n") if l.strip()]
    # 先判断能否全部映射；不能就整段透传（保证恒等）
    for l in raw_lines:
        m = _OP_LINE.match(l)
        if m and m.group(1) not in _MIR2HIR_NAME:
            return "\n".join("raw %s" % x for x in raw_lines), False

    # **只折"恰好被消费一次"的临时量**。
    # 无人消费的（块末尾的死值）若被折进 env，就再也不会被发出 → 整条算子消失
    # （实测 4 个函数：colmax_loop / earlyret / endsemi / while2d）。
    uses, consumer = {}, {}
    for l in raw_lines:
        m = _OP_LINE.match(l)
        if m:
            for a in m.group(3).split(":"):
                uses[a] = uses.get(a, 0) + 1
                consumer[a] = m.group(1)
    # `OP-FILLA` 的第 3 实参是**标量值**（C 侧是 `double`）。把它折成表达式会让
    # 重降级生成一个数组临时量 → gcc 报 "expected double but argument is of type
    # mlc_array"（实测 `filla` 就挂在最后这一步）。这类"实参不是数组"的位置不折。
    _NO_FOLD_CONSUMER = {"OP-FILLA"}
    foldable = {k for k, v in uses.items()
                if v == 1 and _TEMP_RE.match(k)
                and consumer.get(k) not in _NO_FOLD_CONSUMER}

    env = {}      # 临时量 -> 表达式节点
    emitted = []
    for l in raw_lines:
        m = _CONST_LINE.match(l)
        if m:
            name, val = m.group(1), m.group(2)
            if name in foldable:
                env[name] = {"num": val}
                continue
            emitted.append("raw " + l)
            continue
        m = _OP_LINE.match(l)
        if m:
            oid, dst, args = m.group(1), m.group(2), m.group(3).split(":")
            nodes = [env.pop(a, {"var": a}) for a in args]
            node = {"op": _MIR2HIR_NAME[oid], "args": nodes}
            if dst in foldable:
                env[dst] = node
            else:
                emitted.append("%s = %s" % (dst, _render(node)))
            continue
        emitted.append("raw " + l)
    return "\n".join(emitted), True


def hir_wrap(func_name, args, rets, body_hir):
    """拼出完整的 HIR 文本（`hir 1` + 头 + 体）。"""
    lines = ["hir 1", "func: %s" % func_name]
    for name, typ in args:
        lines.append("  param %s %s" % (name, typ))
    for name, typ in rets:
        lines.append("  ret %s %s" % (name, typ))
    for ln in (body_hir or "").split("\n"):
        if ln.strip():
            lines.append("  " + ln)
    return "\n".join(lines) + "\n"
