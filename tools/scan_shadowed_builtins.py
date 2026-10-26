# -*- coding: utf-8 -*-
"""scan_shadowed_builtins.py —— 扫出「被当作下标、其实是未声明的名字」的语句。

## 为什么需要它

同一类**静默误判**已经出现过四次：`isempty` / `numel` / `sqrt` / `find`。
机制完全相同：

    y = find(x);      →  op:OP-INDEX:y:find:x        ← "对名为 find 的数组取下标"

算子表里没有这个名字，`parse_line` 就退回取下标 —— **不报错、不计数、结果全错**。
它是所有缺陷里最危险的一种：生成物能编译、能运行，只是答案是错的。

## 判据（不需要内置名单）

`OP-INDEX` 的第一个参数（被取下标的名字）若在该函数里**从未声明**
（不是形参 / 返回值 / 局部量 / 任何语句的左值），那它一定不是数组 ——
真实代码里不会对一个从未赋值的数组取下标。**这就是误判的签名。**

## 用法

    python tools/scan_shadowed_builtins.py translate/examples/numeric
    python tools/scan_shadowed_builtins.py C:\\Temp\\yalmip --recursive
"""
import collections
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

#: 语句左值可能来自这些前缀（声明来源）
_LHS_KINDS = ("op", "fill", "set", "setb", "const", "call", "call2")


def _blocks(mir_text):
    """把 MIR 切成 (函数名, 行列表)。"""
    cur, body = None, []
    for ln in mir_text.splitlines():
        if ln.startswith("func:"):
            if cur:
                yield cur, body
            cur, body = ln[5:].strip(), []
        elif ln.startswith("end") and cur:
            yield cur, body
            cur, body = None, []
        elif cur is not None:
            body.append(ln)
    if cur:
        yield cur, body


def scan(mir_text):
    """返回 [(函数名, 数组名, 语句)]。"""
    out = []
    for name, body in _blocks(mir_text):
        declared = set()
        for ln in body:
            if ln.startswith(("arg:", "ret:")):
                declared.add(ln.split(":")[1])
            elif ln.startswith("var:"):
                declared.add(ln[4:].split(":")[0])
        for ln in body:
            kind = ln.split(":")[0]
            if kind not in _LHS_KINDS:
                continue
            parts = ln.split(":")
            if kind == "op":
                lhs = parts[2] if len(parts) > 2 else ""
                if len(parts) > 3 and parts[1] == "OP-INDEX":
                    arr = parts[3]
                    if arr not in declared:
                        out.append((name, arr, ln))
            else:
                lhs = parts[1] if len(parts) > 1 else ""
            if kind == "call2" and len(parts) > 2:
                for x in lhs.split(","):
                    declared.add(x.strip())
            elif lhs:
                declared.add(lhs)
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("用法: python tools/scan_shadowed_builtins.py <目录或.m> "
              "[--recursive] [--top N]")
        return 2
    target = argv[0]
    rec = "--recursive" in argv
    top = 20
    if "--top" in argv:
        top = int(argv[argv.index("--top") + 1])

    mir = os.path.join(os.environ.get("TEMP", "/tmp"), "scan_shadow.mir")
    cmd = [sys.executable, os.path.join(ROOT, "translate", "mir.py"), target,
           "-o", mir]
    if rec:
        cmd.append("--recursive")
    r = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=900)
    if r.returncode != 0:
        print(r.stdout.decode("utf-8", "replace")[-400:])
        return 2

    import io
    text = io.open(mir, encoding="utf-8", errors="replace").read()
    rows = scan(text)
    if not rows:
        print("没有发现「未声明却取下标的数组名」—— 这类误判为 0")
        return 0

    c = collections.Counter(r[1] for r in rows)
    print("发现 %d 处疑似误判，涉及 %d 个不同的名字："
          % (len(rows), len(c)))
    for nm, cnt in c.most_common(top):
        fns = sorted(set(r[0] for r in rows if r[1] == nm))[:3]
        print("  %-14s %3d 次   例: %s" % (nm, cnt, ", ".join(fns)))
    return 1


if __name__ == "__main__":
    sys.exit(main())
