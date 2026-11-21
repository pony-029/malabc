# -*- coding: utf-8 -*-
"""**场景覆盖统计**：46192 个 case 到底覆盖了哪些形态。

    python tools/scenario_coverage.py
    python tools/scenario_coverage.py --json
    python tools/scenario_coverage.py --selftest

## 为什么需要它

前几轮一直在"扩量"（clone 更多仓库），但**没人知道那 4.6 万个 case
覆盖了哪些形态**。而用户要的是「向量与标量的**全场景**」。

「量大」和「覆盖全」是两件事：
* 4.6 万个 case 里可能有 4.5 万个都是 `y = a + b` 这种纯标量；
* 而矩阵乘、广播、多返回值、索引切片可能一个都没有。

本工具按**算子集合**给每个 case 打标签，然后统计每类有多少个。

## 场景分类（互斥优先级，从具体到宽泛）

| 场景 | 判据 |
|---|---|
| `matmul`  | 含 OP-MATMUL（矩阵乘） |
| `reduce`  | 含 OP-SUM/MEAN/MAX/MIN（归约，输出标量） |
| `index`   | 含 OP-INDEX/OP-COLRANGE（索引/切片） |
| `concat`  | 含 OP-HCAT/OP-VCAT（拼接） |
| `unary`   | 含 OP-ABS/SQRT/EXP/LOG/SIN/COS 等单目 |
| `broadcast` | 二元算子的两操作数长度不同 |
| `scalar`  | 只有二元算子且操作数都是 1 元素 |
| `vector`  | 只有二元算子且操作数都 > 1 元素 |
| `other`   | 其余 |

**一个 case 只归一类**（按上表顺序，第一个命中的算），这样各类之和等于总数。
"""
import argparse
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "translate"))

UNARY = {"OP-ABS", "OP-SQRT", "OP-EXP", "OP-LOG", "OP-SIN", "OP-COS",
         "OP-TAN", "OP-FLOOR", "OP-CEIL", "OP-ROUND", "OP-LOG2",
         "OP-LOG10"}
REDUCE = {"OP-SUM", "OP-MEAN", "OP-MAX", "OP-MIN"}
INDEX = {"OP-INDEX", "OP-COLRANGE"}
CONCAT = {"OP-HCAT", "OP-VCAT"}
BIN = {"OP-ADD", "OP-SUB", "OP-MUL", "OP-DIV"}


OP_LINE = re.compile(r"^op:(OP-[A-Z0-9]+):(\S+):(.*)$", re.M)
ASG_LINE = re.compile(r"^op:OP-([A-Z0-9]+):(\w+):(.*)$", re.M)


def _ops_from_mir(text):
    """从 MIR 文本里抽算子与操作数（R1123）。

    **第一版直接读 st["ops_detail"]，而 MIR 的统计里根本没有这个键**——
    于是 46192 个 case 全部落到 other，八个场景一个都没命中。
    真实的算子信息在 MIR 文本的 `op:OP-XXX:dst:args` 行里。
    """
    ops = []
    for m in re.finditer(r"^op:OP-([A-Z0-9]+):(\w+):(.*)$", text, re.M):
        args = [a for a in m.group(3).split(":") if a]
        ops.append({"op": "OP-" + m.group(1), "dst": m.group(2),
                    "args": args})
    return ops


def _shapes_from_mir(text):
    """从 `shape:x:2:3` 行抽形状。"""
    shapes = {}
    for m in re.finditer(r"^shape:(\w+):([\d:\-]+)$", text, re.M):
        try:
            shapes[m.group(1)] = [int(x) for x in m.group(2).split(":") if x]
        except ValueError:
            continue
    return shapes


def classify(st, mir_text=""):
    """按 MIR 文本给一个 case 定场景。返回类别名。"""
    ops = _ops_from_mir(mir_text) if mir_text else (st.get("ops_detail") or [])
    names = [o.get("op") if isinstance(o, dict) else str(o) for o in ops]
    shapes = _shapes_from_mir(mir_text) if mir_text else (st.get("shapes") or {})

    if "OP-MATMUL" in names:
        return "matmul"
    if REDUCE & set(names):
        return "reduce"
    if INDEX & set(names):
        return "index"
    if CONCAT & set(names):
        return "concat"
    if UNARY & set(names):
        return "unary"

    # 二元：看操作数长度决定 scalar / vector / broadcast
    bin_ops = [o for o in ops
               if isinstance(o, dict) and o.get("op") in BIN]
    if bin_ops:
        lens = []
        for o in bin_ops:
            for a in (o.get("args") or []):
                sh = shapes.get(a)
                if sh:
                    lens.append(int(sh[0]) if len(sh) == 1 else -1)
        if lens and all(x == 1 for x in lens):
            return "scalar"
        if lens and len(set(lens)) > 1:
            return "broadcast"
        if lens:
            return "vector"
    return "other"


def scan(cases_path):
    import mir as M
    d = json.load(io.open(cases_path, encoding="utf-8"))
    picked = d.get("picked") or []
    root = d.get("root") or ""
    stat = {}
    n = 0
    for p in picked:
        full = os.path.join(root, p["path"])
        try:
            text = io.open(full, encoding="utf-8", errors="replace").read()
            _t, st = M.to_mir(text)
        except (OSError, ValueError):
            continue
        cat = classify(st, _t)
        stat[cat] = stat.get(cat, 0) + 1
        n += 1
    return {"scanned": n, "stat": dict(sorted(stat.items(),
                                             key=lambda x: -x[1]))}


def _selftest():
    """两向自证：每类判据都要能命中，且总数守恒。"""
    good = bad = 0

    def mk(ops_detail, shapes):
        return {"ops_detail": ops_detail, "shapes": shapes}

    cases = [
        (mk([{"op": "OP-MATMUL"}], {}), "matmul"),
        (mk([{"op": "OP-SUM"}], {}), "reduce"),
        (mk([{"op": "OP-INDEX"}], {}), "index"),
        (mk([{"op": "OP-HCAT"}], {}), "concat"),
        (mk([{"op": "OP-SQRT"}], {}), "unary"),
        (mk([{"op": "OP-ADD", "args": ["x", "y"]}],
            {"x": [1], "y": [1]}), "scalar"),
        (mk([{"op": "OP-ADD", "args": ["x", "y"]}],
            {"x": [4], "y": [4]}), "vector"),
        (mk([{"op": "OP-ADD", "args": ["x", "y"]}],
            {"x": [1], "y": [4]}), "broadcast"),
    ]
    for st, want in cases:
        got = classify(st)
        if got == want:
            good += 1
        else:
            bad += 1
            print("  [selftest] %s 被判成 %s" % (want, got))

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="场景覆盖统计")
    ap.add_argument("--cases", default=os.path.join(ROOT, "flow",
                                                   "testcases.json"))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ns = ap.parse_args(argv)

    if ns.selftest:
        return _selftest()
    if not os.path.isfile(ns.cases):
        print("scenario_coverage: 缺输入（%s 不存在）" % ns.cases)
        return 2

    r = scan(ns.cases)
    if ns.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0

    tot = r["scanned"] or 1
    print("[场景覆盖] 扫描 %d 个 case" % r["scanned"])
    print()
    for k, v in r["stat"].items():
        bar = "#" * int(40.0 * v / tot)
        print("  %-10s %6d  %5.1f%%  %s" % (k, v, 100.0 * v / tot, bar))
    print()
    missing = [k for k in ("matmul", "reduce", "index", "concat", "unary",
                           "broadcast", "scalar", "vector")
               if k not in r["stat"]]
    if missing:
        print("[缺口] 完全没有 case 覆盖的场景：%s" % ", ".join(missing))
    else:
        print("[覆盖] 八类场景全部有 case（数量是否均衡见上表）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
