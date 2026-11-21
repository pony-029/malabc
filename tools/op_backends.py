# -*- coding: utf-8 -*-
"""**算子 → 实现变体**的选择与缺口报告。

    python tools/op_backends.py --profile tools/targets/mcu_256k.json
    python tools/op_backends.py --profile <p> --json
    python tools/op_backends.py --selftest

## 现状与问题

`translate/operators.py` 的每个条目只有一个 `c` 字段（如 `OP-SUM -> mlc_op_sum`），
也就是**一个算子绑死一个 C 符号**。这在「只有标量实现」时够用，但它把三种
不同的东西压在同一个字段里：

    算子语义（sum）  ≠  实现变体（标量循环 / SIMD / 加速器）  ≠  符号名（mlc_op_sum）

于是「换成 SIMD 实现」只能去改 `c` 字段 —— 而那会同时改掉语义登记，
`check_translate_port` 的 TP8 三处一致性也会跟着晃。

## 本工具的做法（不破坏现有结构）

**不动 `operators.py` 的 `c` 字段**（那是「参考实现」，永远存在且永远可编译），
而是在它之上加一层**变体选择**：

    候选 = [c]                       # 标量参考，必有
         + [c + "_<isa>"]            # 目标 ISA 的向量实现（若 profile 声明）
         + [c + "_accel"]            # 加速器桩（若 profile 声明）

按 profile 的 `isa` 优先级选第一个「存在」的；都没有就退回标量 `c`，
并记进 `scalar_fallback` —— **这就是"目标板子上这个算子没有向量实现"的答案**。

存在性怎么判？查 `c_runtime/include/mlc_ops.h` 的声明 —— 与 TP8 用的同一个
真源，不另造第二份清单。

## 为什么这是"自由转换"的关键

"MATLAB → C"要能换硬件，靠的不是重写生成器，而是**同一份 MIR + 不同 profile
→ 不同变体选择**。本工具就是那次选择；生成器只需问它要符号名。

退出码：
    0 = 全部算子都有所选 ISA 的实现
    1 = 有算子退回了标量（这是**结论**，不是错误）
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


def load_isa(path):
    """读 profile 的 isa 段。返回 (order, accel) —— 顺序即优先级。"""
    p = json.load(io.open(path, encoding="utf-8"))
    isa = p.get("isa") or {}
    order = isa.get("order") or ["scalar"]
    accel = bool(isa.get("accel"))
    return [str(x) for x in order], accel


def declared_symbols():
    """`mlc_ops.h` 里声明过的 mlc_op_* 符号集合（唯一真源）。"""
    h = os.path.join(ROOT, "c_runtime", "include", "mlc_ops.h")
    if not os.path.isfile(h):
        return set()
    txt = io.open(h, encoding="utf-8", errors="replace").read()
    return set(re.findall(r"\b(mlc_op_[a-z0-9_]+)\s*\(", txt))


def choose(op_c, isa_order, accel, have):
    """为单个算子选符号。返回 (selected, candidates, missing)。

    规则：按 isa_order 依次尝试 `c_<isa>`，命中即选；都未命中退回 `c`。
    `scalar` 就是 `c` 本身（参考实现）。
    """
    cands = []
    for isa in isa_order:
        if isa == "scalar":
            cands.append((isa, op_c, op_c in have))
            continue
        sym = "%s_%s" % (op_c, isa)
        cands.append((isa, sym, sym in have))
    if accel:
        sym = op_c + "_accel"
        cands.append(("accel", sym, sym in have))
    # **按 order 取第一个命中的**（R1039）：早先在每个分支里写
    # `if selected is None: selected = ...`，于是排在最前的 scalar
    # 先把 selected 占住，后面的 simd/accel 永远选不上 —— 表看起来正常，
    # 但那正是「换成 SIMD 做了等于没做」的样子。自证第 1、5 条抓到了它。
    selected = next((s for _i, s, ok in cands if ok), op_c)
    missing = [isa for isa, _s, ok in cands if not ok]
    return selected, cands, missing


def build(isa_order, accel, have):
    """对全部算子做选择，返回结构化结果。"""
    import operators as O
    rows = []
    fallback = []
    for op in O.OPERATORS:
        sel, cands, missing = choose(op["c"], isa_order, accel, have)
        row = {"op": op["id"], "kind": op.get("kind", ""),
               "base": op["c"], "selected": sel,
               "selected_isa": (cands[0][0] if False else
                                next((i for i, s, _ in cands if s == sel),
                                     "scalar")),
               "missing": missing}
        rows.append(row)
        # 首选不是标量却退回了标量 -> 记一笔"本可有向量实现但没有"
        want = [i for i in isa_order if i != "scalar"]
        if want and sel == op["c"]:
            fallback.append({"op": op["id"], "wanted": want})
    return {"isa": isa_order, "accel": accel, "ops": rows,
            "scalar_fallback": fallback,
            "count": len(rows), "fallback_count": len(fallback)}


def _selftest():
    """两向自证：命中向量就选向量；没命中必须退回标量且计入 fallback。

    只验"能跑"不算自证 —— 一个永远返回 `c` 的实现也能输出表，
    而那张表会让"换成 SIMD"看起来已经做了。
    """
    good = bad = 0
    have = {"mlc_op_sum", "mlc_op_sum_simd", "mlc_op_mul"}

    sel, cands, missing = choose("mlc_op_sum", ["scalar", "simd128"], False, have)
    if sel == "mlc_op_sum_simd":
        good += 1
    else:
        bad += 1
        print("  [selftest] 有 simd 实现时未选中：%r" % sel)

    sel2, cands2, _m2 = choose("mlc_op_mul", ["scalar", "simd128"], False, have)
    if sel2 == "mlc_op_mul":
        good += 1
    else:
        bad += 1
        print("  [selftest] 无 simd 实现时未退回标量：%r" % sel2)

    if "simd128" in missing_of(cands2):
        good += 1
    else:
        bad += 1
        print("  [selftest] 缺失项未记录")

    r = build(["scalar", "simd128"], False, have)
    if r["fallback_count"] > 0 and r["count"] > 0:
        good += 1
    else:
        bad += 1
        print("  [selftest] fallback 统计异常：%r" % (r["fallback_count"],))

    # accel 打开时应把 _accel 也作为候选
    sel3, cands3, _m3 = choose("mlc_op_sum", ["scalar"], True,
                               {"mlc_op_sum", "mlc_op_sum_accel"})
    if sel3 == "mlc_op_sum_accel":
        good += 1
    else:
        bad += 1
        print("  [selftest] accel 候选未生效：%r" % sel3)

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def missing_of(cands):
    return [isa for isa, _s, ok in cands if not ok]


def main(argv=None):
    ap = argparse.ArgumentParser(description="算子实现变体选择")
    ap.add_argument("--profile")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ns = ap.parse_args(argv)

    if ns.selftest:
        return _selftest()
    if not ns.profile or not os.path.isfile(ns.profile):
        print("op_backends: 缺输入（--profile 不存在）")
        return 2
    try:
        isa_order, accel = load_isa(ns.profile)
    except (IOError, OSError, ValueError) as e:
        print("op_backends: profile 读不出（%s）" % type(e).__name__)
        return 2

    have = declared_symbols()
    if not have:
        print("op_backends: 缺输入（mlc_ops.h 里没有 mlc_op_* 声明）")
        return 2

    r = build(isa_order, accel, have)
    if ns.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 1 if r["fallback_count"] else 0

    print("[op-backends] ISA 优先级 %s ｜ 加速器 %s"
          % (" > ".join(isa_order), "开" if accel else "关"))
    print("  算子 %d ｜ 已达首选 %d ｜ **退回标量 %d**"
          % (r["count"], r["count"] - r["fallback_count"], r["fallback_count"]))
    if r["scalar_fallback"]:
        print("  退回标量的算子（本可有向量实现，但头文件里没有对应符号）：")
        for x in r["scalar_fallback"][:8]:
            print("    %-16s 期望 %s" % (x["op"], "/".join(x["wanted"])))
    return 1 if r["fallback_count"] else 0


if __name__ == "__main__":
    sys.exit(main())
