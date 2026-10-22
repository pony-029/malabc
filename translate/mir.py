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
import hashlib
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
#: `zeros(3)` / `ones(2,3)` —— 多维常量
_FILL_RE = re.compile(r"^(zeros|ones)\s*\(\s*([\d,\s]+)\s*\)$")
_FILL_VAL = {"zeros": "0", "ones": "1"}

#: 带调用/下标的二元式：`r + v(1)` / `sum(v) + w`
_EXPR_BIN = re.compile(r"^(\S.*?)\s*([+\-*/])\s*(\S.*?)$")
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
    for raw_no, raw in enumerate((source or "").splitlines(), 1):
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
                   "lines": [], "line_nos": [], "line0": raw_no,
                   "types": {}, "shapes": {}, "locals": []}
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
            cur["line_nos"].append(raw_no)
            continue
        if code == "end" or code.startswith("end "):
            depth -= 1
            if depth <= 0:
                depth = 0
                cur = None
            else:
                cur["lines"].append(raw)
                cur["line_nos"].append(raw_no)
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
        cur["line_nos"].append(raw_no)
    return funcs


def _var_line(kind, name, f):
    """`arg:x:f64:3` —— 形状已知就写出来，不知道就不写（发射器会发 TODO）。"""
    dt = f["types"].get(name, "f64")
    dims = f["shapes"].get(name) or []
    if dims:
        return "%s:%s:%s:%s" % (kind, name, dt, ",".join(dims))
    return "%s:%s:%s" % (kind, name, dt)


#: 表达式里的一个"原子"：名字 / 整数 / 调用或下标
_EXPR_SIDE = re.compile(r"^(?:([A-Za-z_]\w*)\s*\(\s*([A-Za-z_]\w*|\d+)\s*\)"
                        r"|(\d+)|([A-Za-z_]\w*))$")


def _side_atom(text):
    """把表达式的一侧解析成 ('call', fname, arg) / ('num', n) / ('name', n)。"""
    m = _EXPR_SIDE.match(text.strip())
    if not m:
        return None
    if m.group(1):
        return ("call", m.group(1), m.group(2))
    if m.group(3):
        return ("num", m.group(3))
    if m.group(4):
        return ("name", m.group(4))
    return None


def _lower_binary(lhs, left, op, right, fnames, emit, counter, src_line=0):
    """把 `lhs = left op right` 降级；两侧都可以是 调用/下标。

    为什么要降级：MIR 是**语句级**的，没有嵌套表达式。真实代码里
    `r = r + v(1)`、`s = sum(v) + w` 到处都是 —— 直接在 MIR 里塞表达式，
    等于把"求值顺序"这个语义问题藏进发射器。拆成两条语句，顺序就写明了。

    `src_line` 会写到**每一条**派生语句前：同一条 MATLAB 语句拆成三条 C
    语句时，三条都应能回到同一行，不能只有第一条有映射。
    """
    def _emit(line):
        if src_line:
            emit("# src:%d" % src_line)
        emit(line)

    sides = []
    for text in (left, right):
        side = _side_atom(text)
        if side is None:
            return False
        sides.append(side)

    operands = []
    for side in sides:
        if side[0] == "call":
            _, fname, arg = side
            counter[0] += 1
            tmp = "__t%d" % counter[0]
            if fname in fnames:
                _emit("call:%s:%s:%s" % (tmp, fname, arg))
            else:
                # 先问算子目录：`sum(z)` 是归约，不是"对 z 取名为 sum 的下标"
                use = operators.parse_line("%s = %s(%s);" % (tmp, fname, arg))
                if use is not None and use["operator"] != "OP-INDEX":
                    _emit("op:%s:%s:%s"
                          % (use["operator"], tmp, ":".join(use["args"])))
                else:
                    _emit("op:OP-INDEX:%s:%s:%s" % (tmp, fname, arg))
            operands.append(tmp)
        elif side[0] == "num":
            # 立即数 → 形状 [1] 的 mlc_array（MATLAB 里标量就是 1×1）
            counter[0] += 1
            tmp = "__k%d" % counter[0]
            _emit("const:%s:%s" % (tmp, side[1]))
            operands.append(tmp)
        else:
            operands.append(side[1])

    # 算子 ID 是 `OP-ADD`（与 operators.py 的目录一致），不是 C 函数名的 `add`
    _emit("op:OP-%s:%s:%s:%s"
          % (_BIN_OP[op].upper(), lhs, operands[0], operands[1]))
    return True


def oid0_is_slice(oid):
    return oid == "OP-SLICE"


#: unmapped 的原因分类（顺序即优先级：先判更"硬"的语义）。
_KIND_RULES = (
    ("cell", lambda t: "{" in t or "}" in t),
    ("struct", lambda t: ".(" in t.replace(" ", "") or
                         ("." in t and "(" in t and ")" in t
                          and not t.startswith("function"))),
    ("control", lambda t: t.startswith(("switch", "case", "try", "catch",
                                        "break", "continue", "return"))),
    # 块标记：上一层的 if 没被识别时，else/otherwise 会落到这里
    ("blockmarker", lambda t: t.strip() in ("else", "end", "otherwise")),
    # 纯副作用调用：不产生数据，移植时可安全降级为注释
    ("sideeffect", lambda t: t.split("(")[0].strip() in (
        "clc", "clear", "clear all", "close all", "more on", "more off",
        "disp", "display", "fprintf", "printf", "error", "warning", "assert",
        "tic", "toc", "drawnow", "pause")),
    ("slice2d", lambda t: "(" in t and ("," in t or ":" in t)),
    ("nested", lambda t: t.count("(") >= 2),
)


def _unmapped_kind(text):
    """给一条未映射语句归因；判不出来就老实写 other。"""
    t = (text or "").strip()
    for name, pred in _KIND_RULES:
        try:
            if pred(t):
                return name
        except Exception:      # noqa: BLE001 - 归因失败不该影响转换
            continue
    return "other"


def _emit_unmapped(out, kinds, text):
    """写一条 unmapped，并记下它的原因（分类只影响报告，不影响语义）。"""
    kind = _unmapped_kind(text)
    out.append("# why:%s" % kind)
    kinds[kind] = kinds.get(kind, 0) + 1
    out.append("unmapped:%s" % text)


def to_mir(source, extra_names=None, header=True, skip_names=None):
    """返回 (mir_text, stats)。

    stats: {functions, ops, unmapped, per_op} —— 门与报告都用它，
    避免"读一行 OK 就当覆盖率"。

    `extra_names`：**整个工程**的函数名。目录转换时传入 ——
    否则跨文件调用会被当成"未知名字"而拒绝，而单文件视角看不出这是错的。
    """
    src_norm = (source or "").replace("\r\n", "\n").replace("\r", "\n")
    src_hash = hashlib.sha256(src_norm.encode("utf-8")).hexdigest()
    funcs = split_functions(source)
    if skip_names:
        funcs = [f for f in funcs if f["name"] not in skip_names]
    fnames = set(f["name"] for f in funcs)
    if extra_names:
        fnames |= set(extra_names)
    n_calls = [0]
    n_tmp = [0]
    n_ops_delta = [0]
    out = ["version 3"] if header else []
    n_ops = 0
    n_unmapped = 0
    per_op = {}
    unmapped_kinds = {}
    for f in funcs:
        out.append("# source_sha256:%s" % src_hash)
        out.append("func:%s" % f["name"])
        # 可变参数（cell）无法用固定签名表达：显式拒绝，绝不伪装成一个 f64
        _va = [n for n in list(f["args"]) + list(f["rets"])
               if n in ("varargin", "varargout")]
        if _va:
            out.append("reject:%s" % ",".join(_va))
        # 已知标量：i64 参数（下标源），后续的标量赋值/循环变量会继续加入
        _types = f.get("types") or {}
        scalar_names = set(n for n in f["args"]
                           if (_types.get(n) or "") == "i64")
        for a in f["args"]:
            out.append(_var_line("arg", a, f))
        for r in f["rets"]:
            out.append(_var_line("ret", r, f))
        for l in f.get("locals") or []:
            out.append("var:%s:i64" % l)
        # 标量名 = i64 标注过 + 局部标量；其余都是数组（mlc_array）
        scalars = set(f.get("locals") or [])
        for _n, _t in list(f["types"].items()):
            if _t == "i64":
                scalars.add(_n)
        blocks = []                    # 块栈："for" / "if"
        for line_i, line in enumerate(f["lines"]):
            src_line = (f.get("line_nos") or [0] * len(f["lines"]))[line_i]
            code = _clean(line).strip()
            if not code:
                continue
            if src_line:
                out.append("# src:%d" % src_line)
            if code == "else":
                if blocks and blocks[-1] == "if":
                    out.append("else")
                else:
                    _emit_unmapped(out, unmapped_kinds, code)
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
            if use is not None and use["operator"] == "OP-INDEX":
                idx = use["args"][1] if len(use["args"]) > 1 else ""
                if not idx.isdigit() and idx not in scalar_names:
                    # `sqrt(x)` / `foo(x)` 这类：x 不是已知标量，
                    # 那它不是"取下标"，而是我们**不支持**的函数调用
                    use = None
            if use is None:
                # 不是算子：可能是**标量赋值**或**同文件函数调用**（都不是猜）
                am = _ASSIGN_SPLIT.match(code)
                if am:
                    lhs = am.group(1)
                    rhs = am.group(2).strip().rstrip(";").strip()
                    if _ATOM.match(rhs):
                        scalar_names.add(lhs)
                        out.append("set:%s:%s" % (lhs, rhs))
                        continue
                    fm0 = _FILL_RE.match(rhs)
                    if fm0:
                        dims = [d.strip() for d in fm0.group(2).split(",")
                                if d.strip()]
                        out.append("fill:%s:%s:%s"
                                   % (lhs, ",".join(dims),
                                      _FILL_VAL[fm0.group(1)]))
                        n_ops_delta[0] += 1
                        continue
                    bm = _BIN.match(rhs)
                    # `setb` 生成的是 `int64_t x = ...`，只能用**标量**左值。
                    # `r = v * 2` 里的 r 是数组 —— 早先它被误判成标量赋值，
                    # 生成的 C 里出现 `r = v * 2;`（mlc_array 不能这么算）。
                    if bm and lhs in scalars and bm.group(1) in scalars \
                            and (bm.group(3).isdigit() or bm.group(3) in scalars):
                        out.append("setb:%s:%s:%s:%s"
                                   % (lhs, _BIN_OP[bm.group(2)],
                                      bm.group(1), bm.group(3)))
                        continue
                    # 两侧带调用/下标的二元式：降级成多条语句
                    em = _EXPR_BIN.match(rhs)
                    if em and _lower_binary(lhs, em.group(1), em.group(2),
                                            em.group(3), fnames, out.append,
                                            n_tmp, src_line):
                        n_ops_delta[0] += 1
                        continue
                    cm = _CALL.match(rhs)
                    if cm and cm.group(1) in fnames:
                        args = [x.strip() for x in cm.group(2).split(",")
                                if x.strip()]
                        out.append("call:%s:%s:%s"
                                   % (lhs, cm.group(1), ":".join(args)))
                        n_calls[0] += 1
                        continue
                _emit_unmapped(out, unmapped_kinds, code)
                n_unmapped += 1
                continue
            args = [x.strip() for x in use["args"]]
            if oid0_is_slice(use["operator"]) and "end" in args:
                # `end` 必须由**已声明**的形状解析；没有形状就如实放弃
                shp = (f.get("shapes") or {}).get(args[0])
                if not shp:
                    _emit_unmapped(out, unmapped_kinds, code)
                    n_unmapped += 1
                    continue
                args = [str(shp[0]) if a == "end" else a for a in args]
            oid = use["operator"]
            # MATLAB 的 `*` 是**矩阵乘**，`.*` 才是元素级。文本层两者都映射到
            # OP-MUL（因为不认识形状），这里在**知道形状之后**才升级：
            # 两个操作数都是 2-D 且内维匹配 -> OP-MATMUL；写了 `.*` -> 保持元素级。
            if oid == "OP-MUL" and len(args) == 2 and ".*" not in code:
                sa = (f.get("shapes") or {}).get(args[0])
                sb = (f.get("shapes") or {}).get(args[1])
                if sa and sb and len(sa) == 2 and len(sb) == 2 \
                        and sa[1] == sb[0]:
                    oid = "OP-MATMUL"
            out.append("op:%s:%s:%s" % (oid, use["lhs"], ":".join(args)))
            n_ops += 1
            per_op[use["operator"]] = per_op.get(use["operator"], 0) + 1
        while blocks:
            out.append("end")              # 容错：没写 end 的块也收束
            blocks.pop()
        out.append("end")
    # 同一条 MATLAB 语句可能被降级成多条语句；连续重复的 `# src` 只保留一条，
    # 否则 MIR 会看起来像“同一行写了两遍”。
    dedup = []
    for x in out:
        if x.startswith("# src:") and dedup and dedup[-1] == x:
            continue
        dedup.append(x)
    out = dedup
    # **统计以 MIR 文本为准**：降级/展开会追加语句，用计数器容易漏计
    # （实测 `zerosum` 生成了 3 条算子语句，计数器仍显示 10）。
    ops_lines = [x for x in out if x.startswith("op:")]
    unmapped_lines = [x for x in out if x.startswith("unmapped:")]
    per_op_final = {}
    for x in ops_lines:
        oid = x.split(":")[1]
        per_op_final[oid] = per_op_final.get(oid, 0) + 1
    stats = {"functions": len(funcs), "ops": len(ops_lines),
             "unmapped": len(unmapped_lines), "per_op": per_op_final,
             "unmapped_kinds": unmapped_kinds,
             "calls": sum(1 for x in out if x.startswith("call:"))}
    return "\n".join(out) + "\n", stats


SELFTEST = True


def _selftest(argv=None):
    """自证：`name(x)` 到底是**下标**还是**不支持的函数调用**。

    两者词法上不可区分，只能靠"x 是不是已知标量"来判。判错的后果不是报错，
    而是**静默变义**：`sqrt(x)` 会被当成索引，MIR、统计、对拍全跟着错。
    """
    good = 0
    bad = 0

    def chk(cond, name):
        nonlocal good, bad
        if cond:
            good += 1
        else:
            bad += 1
            print("  [FAIL] %s" % name)

    t1, _ = to_mir("function y = f(v)\n% @m2c shape v 3\n% @m2c shape y 1\n"
                   "y = v(2);\nend\n")
    chk("op:OP-INDEX:y:v:2" in t1, "立即数下标应识别为 OP-INDEX")

    t2, _ = to_mir("function y = f(v, i)\n% @m2c shape v 3\n"
                   "% @m2c i64 i\n% @m2c shape y 1\ny = v(i);\nend\n")
    chk("op:OP-INDEX:y:v:i" in t2, "标量变量下标应识别为 OP-INDEX")

    t3, _ = to_mir("function y = f(x)\n% @m2c shape x 3\n% @m2c shape y 3\n"
                   "y = sqrt(x);\nend\n")
    chk("OP-INDEX" not in t3, "sqrt(x) 不得被识别成 OP-INDEX")
    chk("unmapped:y = sqrt(x);" in t3, "sqrt(x) 应如实进 unmapped")

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="MATLAB → MIR")
    ap.add_argument("source", nargs="?")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--selftest", action="store_true",
                    help="自证：下标 vs 未知函数调用")
    ap.add_argument("--recursive", action="store_true",
                    help="目录模式下递归子目录（真实工程必需）")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    import os

    if os.path.isdir(args.source):
        # **目录级转换**：真实 MATLAB 工程是一堆 .m 互相调用；
        # 单文件视角会把跨文件调用当成未知名字。
        files = []
        if args.recursive:
            for dp, dn, fn in os.walk(args.source):
                dn[:] = sorted(d for d in dn if not d.startswith("."))
                for f in sorted(fn):
                    if f.lower().endswith(".m"):
                        files.append(os.path.join(dp, f))
        else:
            for fn in sorted(os.listdir(args.source)):
                p = os.path.join(args.source, fn)
                if fn.lower().endswith(".m") and os.path.isfile(p):
                    files.append(p)

        names, kept, skipped = set(), [], []
        for p in files:
            try:
                src0 = io.open(p, encoding="utf-8", errors="replace").read()
            except (IOError, OSError) as exc:
                print("读不了 %s：%s" % (p, exc))
                return 2
            fs = split_functions(src0)
            dup = [f["name"] for f in fs if f["name"] in names]
            if dup and len(dup) == len(fs):
                # 整个文件的函数都重名：跳过，别用后一份覆盖前一份
                skipped.append((p, dup[0]))
                continue
            kept.append(p)
            for f in fs:
                names.add(f["name"])
        if skipped:
            print("[warn] 跳过 %d 个重名文件（MATLAB 允许多目录同名，C 里不行）："
                  % len(skipped))
            for p, nm in skipped[:5]:
                print("        %s -> %s" % (p, nm))
        files = kept
        if not files:
            print("目录里没有 .m 文件：%s" % args.source)
            return 1
        total = {"functions": 0, "ops": 0, "unmapped": 0, "per_op": {},
                 "calls": 0}
        body = None
        emitted = set()
        dropped = 0
        for p in files:
            src = io.open(p, encoding="utf-8", errors="replace").read()
            fs = split_functions(src)
            skip = {f["name"] for f in fs if f["name"] in emitted}
            if skip:
                dropped += len(skip)
            t, st = to_mir(src, extra_names=names, header=(body is None),
                           skip_names=skip)
            body = t if body is None else body + t
            emitted |= {f["name"] for f in fs if f["name"] not in skip} \
                if skip else emitted | {f["name"] for f in fs}
            for k in ("functions", "ops", "unmapped", "calls"):
                total[k] += st[k]
            for k, v in st["per_op"].items():
                total["per_op"][k] = total["per_op"].get(k, 0) + v
        text, stats = body, total
        stats["files"] = len(files)
        if dropped:
            print("[warn] 同名函数已丢弃 %d 个（只保留第一次出现）" % dropped)
        if args.out:
            io.open(args.out, "w", encoding="utf-8", newline="").write(text)
            print("[ok] %s（%d 个 .m / 函数 %d / 算子 %d / 未映射 %d）"
                  % (args.out, len(files), stats["functions"], stats["ops"],
                     stats["unmapped"]))
            return 0
        sys.stdout.write(text)
        return 0

    try:
        src = io.open(args.source, encoding="utf-8-sig",
                      errors="replace").read()
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
