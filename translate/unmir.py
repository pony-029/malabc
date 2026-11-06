# -*- coding: utf-8 -*-
"""MIR → MATLAB（回译）。**反向链路的第一半。**

## 为什么先做这一半

“C 工程与 MATLAB 相互转换”有两个方向。正向（MATLAB → MIR → C）已通；
反向若直接从 C 文本解析，要先写一个 C 前端，成本高、且容易“看起来能跑”。

先做 `MIR → MATLAB` 的收益是**可验证**：拿语料跑
`.m → MIR → .m'`，再让 Octave 跑 `.m'`，与原函数的真值比对。
`MIR` 是两种语言共同的中点，从它回译不需要理解 C 的语法糖。

## 范围（明确边界）

只支持语料实际用到的那批算子（见 `_BIN` / `_FN`）。不认识的算子**整条跳过并计数**，
绝不猜 —— 回译最大的风险是“生成一份看起来对、但语义变了”的 .m。

## 用法

    python translate/unmir.py <x.mir> -o out.m
"""
import argparse
import io
import os
import re
import sys

#: 二元算子 → MATLAB 运算符（MIR 里 OP-MUL 是**逐元素**，矩阵乘是 OP-MATMUL）
_BIN = {
    "OP-ADD": "+", "OP-SUB": "-", "OP-MUL": ".*", "OP-DIV": "./",
}

#: 一元/归约算子 → MATLAB 函数名（参数按顺序传入）
_FN = {
    "OP-SUM": "sum", "OP-MEAN": "mean", "OP-MAX": "max", "OP-MIN": "min",
    "OP-ABS": "abs", "OP-SQRT": "sqrt", "OP-LOG10": "log10",
    "OP-SIN": "sin", "OP-COS": "cos", "OP-EXP": "exp", "OP-FLOOR": "floor",
    "OP-CEIL": "ceil", "OP-ROUND": "round", "OP-LENGTH": "length",
    "OP-NUMEL": "numel", "OP-NNZ": "nnz", "OP-ANY": "any", "OP-ALL": "all",
    "OP-ISEMPTY": "isempty", "OP-ISEQUAL": "isequal", "OP-ISEQUALK": "isequal",
    # `OP-FIND` 不在这里：它的参数是 `(数组, 阈值, 比较码)`（如 `op:OP-FIND:y:x:0:2`），
    # 直接展开成 `find(x, 0, 2)` 会被 MATLAB 当成 `find(X,K,'direction')` 而报错。
    # 要回译得先把比较码翻成 `x > 0`，本轮不做 —— 宁可跳过，也不生成"能跑但语义错"的代码。
    "OP-TRANSPOSE": "__transpose__",
}

_CMP = {"lt": "<", "le": "<=", "gt": ">", "ge": ">=", "eq": "==", "ne": "~="}


class Unmirror(object):
    def __init__(self):
        self.lines = []          # 输出行
        self.indent = 1
        self.sub = {}            # 临时量 → MATLAB 表达式（就地内联）
        self.skipped = []        # 无法回译的算子

    # ---------- 小工具 ----------
    def _name(self, tok):
        """`__t4` -> `m2c_t4`：MATLAB 标识符不能以下划线开头。"""
        if tok.startswith("__"):
            return "m2c_" + tok[2:]
        return tok

    def _e(self, tok):
        """取一个 token 的 MATLAB 表达式；**只**展开 `__` 临时量。

        早前对所有名字都查 `self.sub`，结果把 `acc`（真变量）也换成常量 0，
        整条累加链被抹掉 —— 输出仍然是合法 MATLAB，只是算错。
        """
        if tok.startswith("__"):
            # 已内联的（const/setb 结果）用表达式；否则用改名后的变量名
            return self.sub.get(tok, self._name(tok))
        return tok

    def _emit(self, text):
        self.lines.append("  " * self.indent + text)

    # ---------- 主流程 ----------
    def run(self, text):
        name, args, rets = "f", [], []
        for raw in text.splitlines():
            ln = raw.strip()
            if not ln or ln.startswith("#") or ln.startswith("version "):
                continue
            if ln.startswith("func:"):
                name = ln[5:].strip()
                continue
            if ln.startswith("arg:"):
                p = ln.split(":")
                args.append(p[1].strip())
                continue
            if ln.startswith("ret:"):
                p = ln.split(":")
                rets.append(p[1].strip())
                continue
            if ln.startswith("var:"):
                continue                     # 临时量：内联，不声明
            if ln.startswith("const:"):
                p = ln.split(":")
                if p[1].startswith("__"):
                    self.sub[p[1]] = p[2]        # 临时量：内联
                else:
                    self._emit("%s = %s;" % (p[1], p[2]))   # 真变量：赋值
                continue
            if ln.startswith("fill:"):
                p = ln.split(":")
                dims = p[2].split(",")
                lhs = p[1]
                val = p[3]
                if len(dims) == 2 and val in ("0", "1"):
                    fn = "zeros" if val == "0" else "ones"
                    self._emit("%s = %s(%s, %s);" % (lhs, fn, dims[0], dims[1]))
                else:
                    self.skipped.append(ln)
                continue
            if ln.startswith("set:"):
                p = ln.split(":")
                self._emit("%s = %s;" % (p[1], self._e(p[2])))
                continue
            if ln.startswith("setb:"):
                # setb:tmp:add:a:b / sub / mul
                p = ln.split(":")
                tmp, op, a, b = p[1], p[2], p[3], p[4]
                sym = {"add": "+", "sub": "-", "mul": "*"}.get(op)
                if sym is None:
                    self.skipped.append(ln)
                    continue
                expr = "(%s %s %s)" % (self._e(a), sym, self._e(b))
                if tmp.startswith("__"):
                    self.sub[tmp] = expr        # 临时量：内联
                else:
                    # **真变量的自增必须落地成赋值**。
                    # 早前一律内联，`i = i + 1` 被吞掉 -> 回译出的 while 永不退出
                    # （往返判据里 3 个函数 20s 超时，就是这个）。
                    self._emit("%s = %s;" % (tmp, expr))
                continue
            if ln.startswith("for:"):
                p = ln.split(":")
                self._emit("for %s = %s:%s" % (p[1], self._e(p[2]), self._e(p[3])))
                self.indent += 1
                continue
            if ln.startswith("while:"):
                p = ln.split(":")
                cond = "%s %s %s" % (self._e(p[1]), _CMP.get(p[2], "=="), self._e(p[3]))
                self._emit("while %s" % cond)
                self.indent += 1
                continue
            if ln.startswith("if:"):
                p = ln.split(":")
                cond = "%s %s %s" % (self._e(p[1]), _CMP.get(p[2], "=="), self._e(p[3]))
                self._emit("if %s" % cond)
                self.indent += 1
                continue
            if ln == "else":
                self.indent = max(1, self.indent - 1)
                self._emit("else")
                self.indent += 1
                continue
            if ln == "end":
                self.indent = max(1, self.indent - 1)
                self._emit("end")
                continue
            if ln.startswith("op:"):
                self._op(ln)
                continue
            self.skipped.append(ln)

        lhs = ("[%s]" % ", ".join(rets)) if len(rets) > 1 else (rets[0] if rets else "y")
        head = "function %s = %s(%s)" % (lhs, name, ", ".join(args))
        body = list(self.lines)
        if not body:
            body = ["  %s = %s;" % (rets[0] if rets else "y", args[0] if args else "0")]
        # MIR 末尾的 `end` 已经关掉函数体；再补一个就是语法错误
        if body and body[-1].strip() == "end":
            return "\n".join([head] + body + [""])
        return "\n".join([head] + body + ["end", ""])

    def _op(self, ln):
        p = ln.split(":")
        oid, dst = p[1], p[2]
        dst = self._name(dst)      # 一处改名，覆盖下面所有分支
        a = p[3:]

        if oid in _BIN and len(a) >= 2:
            self._emit("%s = %s %s %s;" % (dst, self._e(a[0]), _BIN[oid], self._e(a[1])))
            return
        if oid == "OP-MATMUL" and len(a) >= 2:
            self._emit("%s = %s * %s;" % (dst, self._e(a[0]), self._e(a[1])))
            return
        if oid == "OP-INDEX" and len(a) >= 2:
            self._emit("%s = %s(%s);" % (dst, self._e(a[0]), self._e(a[1])))
            return
        if oid == "OP-SLICE" and len(a) >= 3:
            self._emit("%s = %s(%s:%s);"
                       % (dst, self._e(a[0]), self._e(a[1]), self._e(a[2])))
            return
        if oid == "OP-FLATTEN" and len(a) >= 1:
            self._emit("%s = %s(:);" % (dst, self._e(a[0])))
            return
        if oid == "OP-HCAT" and len(a) >= 2:
            self._emit("%s = [%s %s];" % (dst, self._e(a[0]), self._e(a[1])))
            return
        if oid == "OP-VCAT" and len(a) >= 2:
            self._emit("%s = [%s; %s];" % (dst, self._e(a[0]), self._e(a[1])))
            return
        if oid == "OP-SETIDX" and len(a) >= 3:
            # setidx:dst:val:idx  ->  dst(idx) = val
            self._emit("%s(%s) = %s;" % (dst, self._e(a[2]), self._e(a[1])))
            return
        if oid == "OP-SETIDX2" and len(a) >= 3:
            self._emit("%s(%s, %s) = %s;"
                       % (dst, self._e(a[0]), self._e(a[1]), self._e(a[2])))
            return
        if oid == "OP-TRANSPOSE" and len(a) >= 1:
            self._emit("%s = %s.';" % (dst, self._e(a[0])))
            return
        if oid in _FN:
            fn = _FN[oid]
            if fn == "__transpose__":
                self._emit("%s = %s.';" % (dst, self._e(a[0])))
            else:
                self._emit("%s = %s(%s);"
                           % (dst, fn, ", ".join(self._e(x) for x in a)))
            return
        self.skipped.append(ln)


def convert(mir_path, out_path):
    text = io.open(mir_path, encoding="utf-8", errors="replace").read()
    u = Unmirror()
    code = u.run(text)
    io.open(out_path, "w", encoding="utf-8", newline="\n").write(code)
    return u.skipped


def main():
    ap = argparse.ArgumentParser(description="MIR → MATLAB（回译，反向链路第一半）")
    ap.add_argument("mir")
    ap.add_argument("-o", "--out", default=None)
    a = ap.parse_args()
    out = a.out or os.path.splitext(a.mir)[0] + "_back.m"
    skipped = convert(a.mir, out)
    print("已写出 %s" % out)
    if skipped:
        print("未能回译 %d 条（不猜，直接跳过）：" % len(skipped))
        for s in skipped[:6]:
            print("   " + s[:88])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
