# -*- coding: utf-8 -*-
"""**调用链峰值**：修掉 mem_sections 的低估方向。

    python tools/mem_callchain.py <MIR 目录> --limit 262144
    python tools/mem_callchain.py --selftest

## 为什么需要它（R1050）

`mem_sections` 的口径是「每个函数各自求和，再对函数取最大」——那解决了
**高估**（不同函数的数组不会同时存在），但它仍**低估**：函数 A 调 B 时，
A 的数组与 B 的数组**同时活着**。

真实峰值应沿调用链累加：

    peak(A) = own(A) + Σ peak(callee)

这是**保守上界**（假设所有被调者同时在栈上），但对**非递归**的调用图是安全
且可算的。**递归一律拒绝**——静态无法展开栈深度，报出来比给个假数字好。

## 口径

* `own(f)` = 该函数内所有 `arg/ret` 数组字节数之和（同 mem_budget）；
* `peak(f)` = `own(f) + Σ peak(child)`；
* 环 -> 记入 `recursive`，其 peak 标 `None`（**不给数字**，避免用假值参与比较）；
* 形状未知的数组不计入，但计数。

退出码：
    0 = 无超限（或有但已列出）
    1 = 自证失败
    2 = 缺输入
"""
import argparse
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "translate"))

F64 = 8


def _prod(shape):
    n = 1
    for d in shape:
        n *= int(d)
    return n


def parse(text):
    """返回 (funcs, calls)：funcs={f: own_bytes}, calls={f: [callee]}。"""
    funcs = {}
    calls = {}
    cur = None
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("func:"):
            cur = s[5:]
            funcs[cur] = 0
            calls.setdefault(cur, [])
            continue
        if cur is None:
            continue
        m = re.match(r"^(arg|ret):[A-Za-z_]\w*:(\w+)(?::([\d,]+))?$", s)
        if m and m.group(2) != "i64" and m.group(3):
            funcs[cur] += _prod([int(x) for x in m.group(3).split(",") if x]) * F64
            continue
        if s.startswith("call:"):
            # call:<rets>:<callee>:<args...>
            parts = s.split(":")
            if len(parts) >= 3 and parts[2]:
                calls[cur].append(parts[2])
            continue
        if s == "end":
            cur = None
    return funcs, calls


def peak_chain(funcs, calls):
    """返回 (peak, recursive, cycles)。

    用显式栈做 DFS 并检测环；命中环的函数标 None（不给数字）。
    """
    memo = {}
    recursive = set()
    cycles = []

    def visit(f, stack):
        if f in memo:
            return memo[f]
        if f in stack:
            idx = stack.index(f)
            cyc = stack[idx:] + [f]
            cycles.append(cyc)
            for x in cyc:
                recursive.add(x)
            return None
        own = funcs.get(f, 0)
        total = own
        ok = True
        for c in calls.get(f, []):
            if c not in funcs:          # 外部/未定义函数：不参与
                continue
            v = visit(c, stack + [f])
            if v is None:
                ok = False
            else:
                total += v
        memo[f] = None if not ok else total
        return memo[f]

    for f in funcs:
        visit(f, [])
    return memo, recursive, cycles


def _selftest():
    """两向自证：链式累加、递归必须不给数字、外部函数不参与。"""
    good = bad = 0

    mir = ("func:a\narg:x:f64:10,10\ncall:y:b:Z:x\nend\n"
           "func:b\narg:z:f64:10,10\nret:w:f64:10,10\nend\n")
    funcs, calls = parse(mir)
    memo, rec, _c = peak_chain(funcs, calls)
    # a: own 800, b: own 1600 -> a 峰值 2400
    if memo.get("a") == 2400 and memo.get("b") == 1600:
        good += 1
    else:
        bad += 1
        print("  [selftest] 链式累加不对：%r" % (memo,))

    mir2 = ("func:r\narg:x:f64:8\ncall:y:r:Z:x\nend\n")
    f2, c2 = parse(mir2)
    m2, rec2, cyc2 = peak_chain(f2, c2)
    if m2.get("r") is None and "r" in rec2 and cyc2:
        good += 1
    else:
        bad += 1
        print("  [selftest] 递归未被识别或不给数字：%r / %r" % (m2, rec2))

    mir3 = ("func:e\narg:x:f64:8\ncall:y:notdefined:Z:x\nend\n")
    f3, c3 = parse(mir3)
    m3, _r3, _c3 = peak_chain(f3, c3)
    if m3.get("e") == 64:
        good += 1
    else:
        bad += 1
        print("  [selftest] 外部函数不应参与累加：%r" % (m3,))

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="调用链峰值")
    ap.add_argument("src", nargs="?")
    ap.add_argument("--limit", type=int, default=262144)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ns = ap.parse_args(argv)

    if ns.selftest:
        return _selftest()
    if not ns.src or not os.path.isdir(ns.src):
        print("mem_callchain: 缺输入（目录不存在）")
        return 2

    import mir as M
    funcs, calls = {}, {}
    files = 0
    for fn in sorted(os.listdir(ns.src)):
        if not fn.endswith(".m"):
            continue
        try:
            txt, _st = M.to_mir(io.open(os.path.join(ns.src, fn),
                                        encoding="utf-8", errors="replace").read())
        except Exception:                      # noqa: BLE001
            continue
        files += 1
        f1, c1 = parse(txt)
        funcs.update(f1)
        calls.update(c1)
    if not funcs:
        print("mem_callchain: 缺输入（没有解析出函数）")
        return 2

    memo, rec, cycles = peak_chain(funcs, calls)
    rows = sorted(((k, v, funcs.get(k, 0)) for k, v in memo.items()),
                  key=lambda x: -(x[1] if x[1] is not None else -1))
    over = [r for r in rows if r[1] is not None and r[1] > ns.limit]

    if ns.json:
        print(json.dumps({"files": files, "funcs": len(funcs),
                          "limit": ns.limit, "recursive": sorted(rec),
                          "cycles": cycles,
                          "rows": [{"func": f, "peak": p, "own": o}
                                   for f, p, o in rows]},
                         ensure_ascii=False, indent=1))
        return 0

    print("[chain] %s ｜ 文件 %d ｜ 函数 %d ｜ 上限 %d B"
          % (os.path.basename(ns.src.rstrip("\\/")), files, len(funcs), ns.limit))
    print("  **沿调用链累加后超限 %d 个**" % len(over))
    for f, p, o in over[:8]:
        print("    %-24s 峰值 %8d B（其中自身 %6d）" % (f[:24], p, o))
    if rec:
        print("  递归 %d 个（静态无法展开，**不给数字**）：%s"
              % (len(rec), "、".join(sorted(rec)[:4])))
    if cycles:
        print("  环示例：%s" % (" -> ".join(cycles[0][:5]),))
    return 0


if __name__ == "__main__":
    sys.exit(main())
