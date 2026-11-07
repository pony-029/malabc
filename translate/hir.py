# -*- coding: utf-8 -*-
"""HIR 解析与降级（委派产物 pony-hh，经机器验收后修正）。

> 委派自本地模型 `pony_hh`（R692）。**原始产物未通过验收**，本文件是在其基础上修正后的版本；
> 具体缺陷与修正记录在 `docs/PLAN_TRACKER.md` 的 R692 小节。

HIR 是语义层：表达式是树、算子带 family、值带类型。MIR 只是它机械降级后的三地址形式。
这条边界是硬的 —— **HIR 里不允许出现临时量与 `OP-*` id**。
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
        # 数字字面量（含负号与小数）—— 委派版本在这里直接报错，已补
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
        raise ValueError("无法识别的行：%s" % s)
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
    args = [_emit_node(a, None, out) for a in node["args"]]
    if dst is None:
        _emit_node._counter = getattr(_emit_node, "_counter", 0) + 1
        dst = "__h%d" % _emit_node._counter
    out.append("op:%s:%s:%s" % (mir_id, dst, ":".join(args)))
    return dst


def hir_to_mir(text):
    """HIR 文本 → MIR 语句行（不含 func:/arg:/ret:，只产出 `op:` 与 `const:`）。

    临时量从 `__h1` 起全局递增；顶层赋值的左值直接用作 dst。
    """
    stmts = parse_hir(text)
    _emit_node._counter = 0
    out = []
    for s in stmts:
        if s["kind"] == "let":
            _emit_node(s["expr"], s["dst"], out)
    return "\n".join(out)
