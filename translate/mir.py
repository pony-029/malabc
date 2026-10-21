# -*- coding: utf-8 -*-
"""MATLAB 源码 → MIR 文本（R434 / Week1）。

职责边界（刻意划清）：
  * 本模块**不翻译**任何语句。它只做两件事：
      ① 把源码切成「函数 / 参数 / 返回值 / 语句行」；
      ② 逐行调用 `translate/operators.py` 的 `parse_line`，把命中的行写成
         `op:` 行，没命中的原样写成 `unmapped:` 行。
  * 真正的代码生成在 Rust 侧（`rust/m2c`）：MIR → C。

为什么用行式文本而不是 JSON：零依赖约束下，Rust 侧自己写 JSON 解析器是负债；
MIR 只被这台机器的两个程序读写，行式格式足够，而且 diff 可读。

类型标注（**不猜**）：默认所有参数/返回都是 `f64`（`mlc_array`）。
需要 `int64_t` 标量（例如下标）时，在 .m 里显式写一行注释：

    % @m2c i64 i          # 把参数 i 声明成 int64 标量

没有这行标注，`mlc_op_index` 的索引参数就不是 i64 —— 发射器会发
`TODO(OP-INDEX)` 而不是替你猜一个类型。

用法：
    python translate/mir.py <file.m>            # 打到 stdout
    python translate/mir.py <file.m> -o out.mir
"""
from __future__ import absolute_import

import argparse
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from translate import operators  # noqa: E402

#: `function [a, b] = name(x, y)` / `function y = name(x)` / `function name(x)`
_FUNC_RE = re.compile(
    r"^\s*function\s+(?:\[(?P<outs>[^\]]*)\]\s*=\s*|(?P<out1>[A-Za-z_]\w*)\s*=\s*)?"
    r"(?P<name>[A-Za-z_]\w*)\s*\((?P<args>[^)]*)\)")
#: `% @m2c i64 i` —— 显式类型标注
_ANNO_RE = re.compile(r"^\s*%\s*@m2c\s+(?P<type>i64|f64)\s+(?P<names>[A-Za-z_][\w\s,]*)$")
#: `if i > 1` —— 只认「标量与整数字面量/变量」的六种比较；其余进 unmapped。
_IF_RE = re.compile(r"^if\s+(?P<var>[A-Za-z_]\w*)\s*"
                    r"(?P<cmp>==|~=|<=|>=|<|>)\s*(?P<rhs>[A-Za-z_\w]+)$")
#: `while i < 3` —— 与 if 同一套条件语法。
#:
#: ⚠ 本版**没有标量赋值语句**，所以 while 的循环变量无法在体内改变：
#: 真实 .m 里的 while 多半会变成死循环。因此样例故意不含 while，
#: 它只在 MIR 层被支持并自证（见 rust/m2c --selftest）。
_WHILE_RE = re.compile(r"^while\s+(?P<var>[A-Za-z_]\w*)\s*"
                       r"(?P<cmp>==|~=|<=|>=|<|>)\s*(?P<rhs>[A-Za-z_\w]+)$")
_CMP = {"==": "eq", "~=": "ne", "<": "lt", "<=": "le", ">": "gt", ">=": "ge"}

#: `for i = 1:3` —— 只认整数边界（变量名或字面量），复杂形式进 unmapped。
_FOR_RE = re.compile(r"^for\s+(?P<var>[A-Za-z_]\w*)\s*=\s*(?P<a>[\w]+)\s*:\s*(?P<b>[\w]+)\s*$")

#: `% @m2c shape x 3` / `% @m2c shape x 3,3` —— 形状必须**显式**说明。
#: 没有它，发射器不知道 `mlc_array_init` 该给多大，只能发 TODO。
_SHAPE_RE = re.compile(r"^\s*%\s*@m2c\s+shape\s+(?P<name>[A-Za-z_]\w*)\s+(?P<dims>[\d,\s]+)$")
#: `% @m2c local n i64` —— 声明一个局部 i64 标量（数组临时由算子输出隐式产生）
_LOCAL_RE = re.compile(r"^\s*%\s*@m2c\s+local\s+(?P<name>[A-Za-z_]\w*)\s+i64$")
#: `lhs = rhs` 的通用形状（算子识别失败后才会走到这里）
_ASSIGN_SPLIT = re.compile(r"^([A-Za-z_]\w*)\s*=\s*(.+)$")
#: 纯整数或纯名字
_ATOM = re.compile(r"^(\d+|[A-Za-z_]\w*)$")
#: 标量二元：`a + 1`
_BIN = re.compile(r"^([A-Za-z_]\d*\w*|\d+)\s*([+\-*/])\s*([A-Za-z_]\w*|\d+)$")
_BIN_OP = {"+": "add", "-": "sub", "*": "mul", "/": "div"}
_CALL = re.compile(r"^([A-Za-z_]\w*)\s*\((.*)\)$")


def _clean(line):
    """去掉行内注释（`%` 之后），保留字符串里的 %（本版无字符串常量）。"""
    out = []
    for ch_i, ch in enumerate(line):
        if ch == "%":
            break
        out.append(ch)
    return "".join(out).rstrip()


def split_functions(source):
    """粗切函数块。返回 [{name, args, rets, lines}]。

    只处理「顶层 function」，不处理嵌套/局部函数（本版明确不支持，
    遇到就整体进 unmapped —— 之后由更细的解析器接手）。
    """
    funcs = []
    cur = None
    depth = 0
    for raw in (source or "").splitlines():
        m = _FUNC_RE.match(raw)
        if m and depth == 0:
            outs = m.group("outs")
            if outs is not None:
                rets = [x.strip() for x in outs.split(",") if x.strip()]
            elif m.group("out1"):
                rets = [m.group("out1").strip()]
            else:
                rets = []
            args = [x.strip() for x in (m.group("args") or "").split(",")
                    if x.strip()]
            cur = {"name": m.group("name"), "args": args, "rets": rets,
                   "lines": [], "types": {}, "shapes": {},
                   "locals": []}
            funcs.append(cur)
            depth = 1
            continue
        if cur is None:
            continue
        code = _clean(raw).strip()
        # 块开始/结束要按**深度**记账：第一版直接在第一处 `end` 就把函数收掉，
        # 于是 while/if/for 之后的语句被整段丢弃（生成的函数悄悄变短）。
        if code.startswith("for ") or code.startswith("while ") or \
                code.startswith("if "):
            depth += 1
            cur["lines"].append(raw)
            continue
        if code == "end" or code.startswith("end "):
            depth -= 1
            if depth <= 0:
                depth = 0
                cur = None
            else:
                cur["lines"].append(raw)
            continue
        lm = _LOCAL_RE.match(raw)
        if lm:
            cur["locals"].append(lm.group("name"))
            continue
        sm = _SHAPE_RE.match(raw)
        if sm:
            dims = [d.strip() for d in sm.group("dims").split(",") if d.strip()]
            cur["shapes"][sm.group("name")] = dims
            continue
        am = _ANNO_RE.match(raw)
        if am:
            for n in re.split(r"[,\s]+", am.group("names").strip()):
                if n:
                    cur["types"][n] = am.group("type")
            continue
        cur["lines"].append(raw)
    return funcs


def _var_line(kind, name, f):
    """`arg:x:f64:3` —— 形状已知就写出来，不知道就不写（发射器会发 TODO）。"""
    dt = f["types"].get(name, "f64")
    dims = f["shapes"].get(name) or []
    if dims:
        return "%s:%s:%s:%s" % (kind, name, dt, ",".join(dims))
    return "%s:%s:%s" % (kind, name, dt)


def to_mir(source):
    """返回 (mir_text, stats)。

    stats: {functions, ops, unmapped, per_op} —— 门与报告都用它，
    避免"读一行 OK 就当覆盖率"。
    """
    funcs = split_functions(source)
    fnames = set(f["name"] for f in funcs)
    n_calls = [0]
    out = ["version 3"]
    n_ops = 0
    n_unmapped = 0
    per_op = {}
    for f in funcs:
        out.append("func:%s" % f["name"])
        for a in f["args"]:
            out.append(_var_line("arg", a, f))
        for r in f["rets"]:
            out.append(_var_line("ret", r, f))
        for l in f.get("locals") or []:
            out.append("var:%s:i64" % l)
        blocks = []                    # 块栈："for" / "if"
        for line in f["lines"]:
            code = _clean(line).strip()
            if not code:
                continue
            if code == "else":
                if blocks and blocks[-1] == "if":
                    out.append("else")
                else:
                    out.append("unmapped:%s" % code)
                continue
            if code == "end" or code.startswith("end "):
                if blocks:
                    out.append("end")      # 收束块
                    blocks.pop()
                continue
            fm = _FOR_RE.match(code)
            if fm:
                out.append("for:%s:%s:%s" % (fm.group("var"), fm.group("a"),
                                             fm.group("b")))
                blocks.append("for")
                continue
            im = _IF_RE.match(code)
            if im:
                out.append("if:%s:%s:%s" % (im.group("var"),
                                            _CMP[im.group("cmp")],
                                            im.group("rhs")))
                blocks.append("if")
                continue
            wm = _WHILE_RE.match(code)
            if wm:
                out.append("while:%s:%s:%s" % (wm.group("var"),
                                               _CMP[wm.group("cmp")],
                                               wm.group("rhs")))
                blocks.append("while")
                continue
            # **先判调用**：`f(x)` 与 `v(i)` 在词法上无法区分，
            # 只有"f 是不是本文件里的函数"能决定它是调用还是下标。
            am0 = _ASSIGN_SPLIT.match(code)
            if am0:
                cm0 = _CALL.match(am0.group(2).strip().rstrip(";").strip())
                if cm0 and cm0.group(1) in fnames:
                    args = [x.strip() for x in cm0.group(2).split(",")
                            if x.strip()]
                    out.append("call:%s:%s:%s"
                               % (am0.group(1), cm0.group(1), ":".join(args)))
                    n_calls[0] += 1
                    continue
            use = operators.parse_line(code)
            if use is None:
                # 不是算子：可能是**标量赋值**或**同文件函数调用**（都不是猜）
                am = _ASSIGN_SPLIT.match(code)
                if am:
                    lhs = am.group(1)
                    rhs = am.group(2).strip().rstrip(";").strip()
                    if _ATOM.match(rhs):
                        out.append("set:%s:%s" % (lhs, rhs))
                        continue
                    bm = _BIN.match(rhs)
                    if bm:
                        out.append("setb:%s:%s:%s:%s"
                                   % (lhs, _BIN_OP[bm.group(2)],
                                      bm.group(1), bm.group(3)))
                        continue
                    cm = _CALL.match(rhs)
                    if cm and cm.group(1) in fnames:
                        args = [x.strip() for x in cm.group(2).split(",")
                                if x.strip()]
                        out.append("call:%s:%s:%s"
                                   % (lhs, cm.group(1), ":".join(args)))
                        n_calls[0] += 1
                        continue
                out.append("unmapped:%s" % code)
                n_unmapped += 1
                continue
            args = [x.strip() for x in use["args"]]
            out.append("op:%s:%s:%s"
                       % (use["operator"], use["lhs"], ":".join(args)))
            n_ops += 1
            per_op[use["operator"]] = per_op.get(use["operator"], 0) + 1
        while blocks:
            out.append("end")              # 容错：没写 end 的块也收束
            blocks.pop()
        out.append("end")
    stats = {"functions": len(funcs), "ops": n_ops,
             "unmapped": n_unmapped, "per_op": per_op,
             "calls": n_calls[0]}
    return "\n".join(out) + "\n", stats


def main(argv=None):
    ap = argparse.ArgumentParser(description="MATLAB → MIR")
    ap.add_argument("source")
    ap.add_argument("-o", "--out", default=None)
    args = ap.parse_args(argv)

    try:
        src = io.open(args.source, encoding="utf-8", errors="replace").read()
    except (IOError, OSError) as exc:
        print("读不了 %s：%s" % (args.source, exc))
        return 2
    text, stats = to_mir(src)
    if not stats["functions"]:
        print("没有识别到 function（本版只处理顶层 function）")
        return 1
    if args.out:
        io.open(args.out, "w", encoding="utf-8", newline="").write(text)
        print("[ok] %s（函数 %d / 算子 %d / 未映射 %d）"
              % (args.out, stats["functions"], stats["ops"],
                 stats["unmapped"]))
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
