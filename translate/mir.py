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
#: `for i = 1:3` —— 只认整数边界（变量名或字面量），复杂形式进 unmapped。
_FOR_RE = re.compile(r"^for\s+(?P<var>[A-Za-z_]\w*)\s*=\s*(?P<a>[\w]+)\s*:\s*(?P<b>[\w]+)\s*$")

#: `% @m2c shape x 3` / `% @m2c shape x 3,3` —— 形状必须**显式**说明。
#: 没有它，发射器不知道 `mlc_array_init` 该给多大，只能发 TODO。
_SHAPE_RE = re.compile(r"^\s*%\s*@m2c\s+shape\s+(?P<name>[A-Za-z_]\w*)\s+(?P<dims>[\d,\s]+)$")


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
                   "lines": [], "types": {}, "shapes": {}}
            funcs.append(cur)
            depth = 1
            continue
        if cur is None:
            continue
        # `end` 收束（只认顶层 end）
        if raw.strip() == "end":
            depth = 0
            cur = None
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
    out = ["version 2"]
    n_ops = 0
    n_unmapped = 0
    per_op = {}
    for f in funcs:
        out.append("func:%s" % f["name"])
        for a in f["args"]:
            out.append(_var_line("arg", a, f))
        for r in f["rets"]:
            out.append(_var_line("ret", r, f))
        depth = 0
        for line in f["lines"]:
            code = _clean(line).strip()
            if not code:
                continue
            if code == "end" or code.startswith("end "):
                if depth:
                    out.append("end")      # 收束循环体
                    depth -= 1
                continue
            fm = _FOR_RE.match(code)
            if fm:
                out.append("for:%s:%s:%s" % (fm.group("var"), fm.group("a"),
                                             fm.group("b")))
                depth += 1
                continue
            use = operators.parse_line(code)
            if use is None:
                out.append("unmapped:%s" % code)
                n_unmapped += 1
                continue
            args = [x.strip() for x in use["args"]]
            out.append("op:%s:%s:%s"
                       % (use["operator"], use["lhs"], ":".join(args)))
            n_ops += 1
            per_op[use["operator"]] = per_op.get(use["operator"], 0) + 1
        while depth:
            out.append("end")              # 容错：没写 end 的循环也收束
            depth -= 1
        out.append("end")
    stats = {"functions": len(funcs), "ops": n_ops,
             "unmapped": n_unmapped, "per_op": per_op}
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
