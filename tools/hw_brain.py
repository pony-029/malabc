# -*- coding: utf-8 -*-
"""**硬件映射的小脑与大脑**：哪些结论是确定的，哪些必须升级。

    python tools/hw_brain.py <MIR 目录> --profile tools/targets/mcu_256k.json
    python tools/hw_brain.py --selftest

## 为什么硬件映射特别需要这一层

内存分段、算子变体选择这些事，**有 90% 是纯确定性推导**（小脑）：
数组多大、段容量多少、头文件里有没有这个符号 —— 全是可复算的。

但有四类情况**不能靠猜**，必须显式升级（大脑）：

| 信号 | 在本场景的含义 | 为什么不能猜 |
|---|---|---|
| `S1` 无先例 | 这个算子/这种形状组合在知识库里没有先例 | 猜错会生成编不过的 C |
| `S2` 复发 | 同一函数反复超限 | 说明当前分流规则对它不适用 |
| `S3` 无见证 | 形状未知（`arg:x:f64` 无维度） | **把「不知道」当 0 会让预算假通过** |
| `S4` 未归类 | profile 没声明这个段 / 这个 ISA | 生成器不知道该往哪放 |

本工具**不调用大模型**，只做两件事：
1. 跑小脑的全部确定性推导；
2. 用四信号标出"必须人/模型裁决"的点，并给出**结构化的问题描述**。

## 与 `brain_llm` 的关系

`brain_llm.escalate()` 是通用的三层分工入口（本地 → 四信号 → 大模型）。
本工具是它在**硬件映射领域**的适配器：把 `mem_sections` / `op_backends` 的
结果翻译成那套信号，而不是另造一套判据。**判据只有一处，避免两份清单。**

退出码：
    0 = 无升级点（全部可确定性完成）
    1 = 有升级点（这是**结论**，不是错误）
    2 = 缺输入
"""
import argparse
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "translate"))


def collect(src, profile_path):
    """跑小脑，收集信号。返回 dict。"""
    import mem_sections as MS
    import op_backends as OB

    prof = MS.load_profile(profile_path)
    arrays, unknown = MS.scan_arrays(src)
    per, viol = MS.check(arrays, prof)

    isa_order, accel = OB.load_isa(profile_path)
    have = OB.declared_symbols()
    ops = OB.build(isa_order, accel, have)

    sig = {}

    # S3 无见证：形状未知的数组 —— 它们既不能算峰值，也不能定段
    sig["S3_no_witness"] = unknown

    # S4 未归类：profile 声明的段之外，数组还可能落在哪？此处体现为
    # 「ISA 声明了但头文件里没有对应符号」—— 生成器不知道该用哪个符号
    unclassified = []
    for x in ops["scalar_fallback"]:
        for isa in x["wanted"]:
            unclassified.append("%s@%s" % (x["op"], isa))
    sig["S4_unknown_kinds"] = unclassified

    # S2 复发：段超限（超幅 > 25%）**或**跨调用链峰值超限。
    #
    # 后半条是 R1056 补的：`mem_sections` 只看「每个函数各自」，会低估——
    # 函数 A 调 B 时两者数组同时活着。所以 S2 必须同时问一次调用链，
    # 否则「各段都很宽裕」和「某条链已经爆了」可以同时成立，而小脑只看到前者。
    repeat = []
    for v in viol:
        ratio = float(v["over_by"]) / v["capacity"]
        if ratio > 0.25:
            repeat.append("%s 超 %.0f%%" % (v["section"], ratio * 100))
    try:
        import mem_callchain as MC
        import mir as M
        funcs, calls = {}, {}
        for fn in sorted(os.listdir(src)):
            if not fn.endswith(".m"):
                continue
            txt, _st = M.to_mir(io.open(os.path.join(src, fn),
                                        encoding="utf-8",
                                        errors="replace").read())
            f1, c1 = MC.parse(txt)
            funcs.update(f1)
            calls.update(c1)
        if funcs:
            memo, _rec, _cyc = MC.peak_chain(funcs, calls)
            limit = max(s["capacity_bytes"] for s in prof["sections"])
            for f, p in memo.items():
                if p is not None and p > limit:
                    repeat.append("调用链 %s 峰值 %d B 超上限 %d B"
                                  % (f, p, limit))
    except Exception as e:                     # noqa: BLE001
        # 不静默：拿不到跨链数字时要说出来，否则 S2 会"看起来查过了"
        repeat.append("跨链峰值未取到（%s）" % type(e).__name__)
    sig["S2_repeat"] = repeat

    # S1 无先例：算子数 / 形状全部未知的函数（无从判断）
    funcs_total = len(set(a[0] for a in arrays)) or 0
    sig["S1_no_precedent"] = 1 if (unknown > 0 and unknown >= len(arrays)) else 0

    return {"profile": profile_path, "sections": per, "violations": viol,
            "unknown_shape": unknown, "ops_total": ops["count"],
            "scalar_fallback": ops["fallback_count"], "signals": sig,
            "funcs": funcs_total}


def verdict(r):
    """把信号翻成「小脑能不能自己定」的结论 + 升级问题清单。"""
    s = r["signals"]
    need = []
    if s["S3_no_witness"]:
        need.append({
            "signal": "S3",
            "why": "有 %d 个数组没有形状标注，峰值的下界算不准" % s["S3_no_witness"],
            "ask": "这些数组的实际维度是多少？或者它们能否改成由常量初始化？",
        })
    if s["S4_unknown_kinds"]:
        need.append({
            "signal": "S4",
            "why": "profile 声明了 %d 个算子想要的 ISA 变体，但头文件里没有对应符号"
                   % len(s["S4_unknown_kinds"]),
            "ask": "这些算子在本板子上是「没有向量实现」还是「符号名不同」？",
        })
    if s["S2_repeat"]:
        need.append({
            "signal": "S2",
            "why": "有段超限幅度超过 25%%：%s" % "、".join(s["S2_repeat"][:3]),
            "ask": "这个段的分流阈值是否该调，还是该对具体函数做 Tiling？",
        })
    if s["S1_no_precedent"]:
        need.append({
            "signal": "S1",
            "why": "全部数组形状未知，等于没有可依据的先例",
            "ask": "这一批代码是否应当先补形状注解，而不是继续推导？",
        })
    return {"decidable": not need, "escalate": need}


def _selftest():
    """两向自证：没有缺口时必须判"可自决"；有缺口时必须逐条点名。

    只验"能跑"不算自证 —— 一个永远返回空 escalate 的实现会让所有硬件
    决策都"看起来可自决"，而它恰恰丢掉了大脑那一层。
    """
    good = bad = 0

    clean = {"signals": {"S1_no_precedent": 0, "S2_repeat": [],
                         "S3_no_witness": 0, "S4_unknown_kinds": []}}
    v = verdict(clean)
    if v["decidable"] is True and not v["escalate"]:
        good += 1
    else:
        bad += 1
        print("  [selftest] 无缺口却报升级：%r" % (v,))

    dirty = {"signals": {"S1_no_precedent": 0, "S2_repeat": ["tcm 超 30%"],
                         "S3_no_witness": 3, "S4_unknown_kinds": ["OP-ADD@simd128"]}}
    v2 = verdict(dirty)
    sigs = sorted(x["signal"] for x in v2["escalate"])
    if v2["decidable"] is False and sigs == ["S2", "S3", "S4"]:
        good += 1
    else:
        bad += 1
        print("  [selftest] 三条升级点未逐条点名：%r" % (sigs,))

    if all(x.get("ask") for x in v2["escalate"]):
        good += 1
    else:
        bad += 1
        print("  [selftest] 升级点缺少可回答的问题（ask 为空）")

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="硬件映射的小脑/大脑")
    ap.add_argument("src", nargs="?")
    ap.add_argument("--profile")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ns = ap.parse_args(argv)

    if ns.selftest:
        return _selftest()
    if not ns.src or not os.path.isdir(ns.src):
        print("hw_brain: 缺输入（MIR 目录不存在）")
        return 2
    if not ns.profile or not os.path.isfile(ns.profile):
        print("hw_brain: 缺输入（--profile 不存在）")
        return 2

    try:
        r = collect(ns.src, ns.profile)
    except (IOError, OSError, ValueError) as e:
        print("hw_brain: 取数失败（%s: %s）" % (type(e).__name__, e))
        return 2
    v = verdict(r)
    r["verdict"] = v

    if ns.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0 if v["decidable"] else 1

    print("[小脑] 确定性部分（可复算，不需外部裁决）")
    for x in r["sections"]:
        print("  段 %-8s %8d / %8d B（%.0f%%）"
              % (x["name"], x["used"], x["capacity"],
                 100.0 * x["used"] / x["capacity"]))
    print("  算子 %d 个，其中退回标量 %d 个"
          % (r["ops_total"], r["scalar_fallback"]))
    print("  形状未知数组 %d 个" % r["unknown_shape"])

    if v["decidable"]:
        print("[大脑] 无升级点 —— 全部可由小脑自决")
        return 0
    print("[大脑] **必须升级 %d 项**（小脑不能猜）" % len(v["escalate"]))
    for x in v["escalate"]:
        print("  %s  %s" % (x["signal"], x["why"]))
        print("      问：%s" % x["ask"])
    return 1


if __name__ == "__main__":
    sys.exit(main())
