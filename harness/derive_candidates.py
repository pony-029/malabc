# -*- coding: utf-8 -*-
"""R103：把 flaky 追捕的**候选集从测试文件推导出来**，而不是人工挑。

为什么要它：R102b 的 11 条候选是**按关键词人工挑的**。R103 用一次独立的
覆盖度自检发现它**不完整** —— 两条 watch/增量用例带隐式小超时
（`test_p150_watch_and_incrjson_and_taint_svg` 3s、`test_p161_watch_gate` 5s）
根本没进候选。人工挑的清单**不可重跑、不可审计**（R98 ⑮ / R99 ④ 同一形状）。

本脚本把候选定义成**四条机器可判的模式**：
  P1 绝对墙钟断言：`assert` 行里同时出现时间量、数值比较、以及「秒/ms」语义；
  P2 隐式小超时：测试体里 `timeout=<n>` 且 `n <= 120`（超时直接 error ⇒ 也是阈值）；
  P3 预算开关：测试体里出现 `--elapsed-budget`；
  P4 名字族：`reproducib|determinis|byte_identical|hashseed|double_run|perf|benchmark`。

输出**分级**差集（尺度写在判据里，R90 ①）：
  * **高**：`P1 绝对墙钟断言` 或 `P2 隐式超时 <= 30s`  ⇒ 必须在候选集里，否则**判红**；
  * **中**：`P2 隐式超时 30–120s` ⇒ 只报告（余量 ≥ 2 个数量级的情形会被逐条说明）；
  * **低**：仅 `P4 名字族` 命中 ⇒ 只报告（名字只是**提名**，无任何数值阈值）。

为什么必须分级：不分级时 33 条里 22 条会被判红，其中绝大多数是
`impact > 0` 这类误匹配与「名字里带 deterministic」的良性双跑对比 ——
一个**常亮的判据**和没有判据一样（R83 ④：陈旧的红与真坏长得一样）。
⚠ 命中的**可能是**阈值，所以本脚本**只负责提名**，定性仍靠追捕装置逐条重复跑。
"""
from __future__ import print_function

import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hunt_flaky_r102 as H     # noqa: E402

TESTFILE = H.TESTFILE
SECS = re.compile(u"秒|s（|ms|毫秒|上界|耗时|超时")
NUMCMP = re.compile(r"[<>]=?\s*[0-9]+(?:\.[0-9]+)?")
TIMEVAR = re.compile(r"\bdt\b|\belapsed|_t0|_t1|\bt0\b|\bt1\b|wall|duration|\bms\b")
NAME_PAT = re.compile(r"reproducib|determinis|byte_identical|hashseed|double_run"
                      r"|perf|benchmark", re.I)
TIMEOUT = re.compile(r"timeout\s*=\s*([0-9]+(?:\.[0-9]+)?)")


def spans(text):
    """返回 [(起始行, 用例名)]，行号 1 起。"""
    L = text.split("\n")
    out = []
    for i, ln in enumerate(L):
        m = re.match(r"def (test_\w+)", ln)
        if m:
            out.append((i + 1, m.group(1)))
    return out


def owner(defs, n):
    best = None
    for ln, name in defs:
        if ln <= n:
            best = (ln, name)
        else:
            break
    return best


def main():
    text = io.open(TESTFILE, "rb").read().decode("utf-8")
    L = text.split("\n")
    defs = spans(text)
    hits = {}
    for i, ln in enumerate(L, 1):
        s = ln.strip()
        o = owner(defs, i)
        if not o:
            continue
        name = o[1]
        why, tier = [], 2
        # P1：绝对墙钟断言
        if s.startswith("assert") and TIMEVAR.search(s) and NUMCMP.search(s):
            why.append("P1 绝对墙钟断言")
            tier = 0
        # P2：隐式超时（超时直接 error ⇒ 也是阈值）
        m = TIMEOUT.search(s)
        if m and float(m.group(1)) <= 120 and not s.startswith("def "):
            v = float(m.group(1))
            why.append("P2 隐式超时 %gs" % v)
            tier = min(tier, 0 if v <= 30 else 1)
        # P3：预算开关
        if "--elapsed-budget" in s:
            why.append("P3 预算开关")
        if why:
            rec = hits.setdefault(name, {"why": [], "tier": 2})
            rec["why"].extend(why)
            rec["tier"] = min(rec["tier"], tier)
    for ln, name in defs:
        if NAME_PAT.search(name):
            rec = hits.setdefault(name, {"why": [], "tier": 2})
            rec["why"].append("P4 名字族")

    cand = set(n for n, _w in H.CANDIDATES)
    derived = set(hits)
    TIER = {0: u"高", 1: u"中", 2: u"低"}

    print("推导出候选 %d 条；硬编码候选 %d 条" % (len(derived), len(cand)))
    print("尺度：高 = P1 或 P2<=30s；中 = P2 30–120s；低 = 仅 P4 名字族")
    print("-" * 78)
    for name in sorted(derived, key=lambda n: (hits[n]["tier"], n)):
        tag = "IN " if name in cand else u"漏 "
        print("  [%s][%s] %-56s %s"
              % (tag, TIER[hits[name]["tier"]], name,
                 u"；".join(hits[name]["why"][:3])))
    print("-" * 78)
    extra = sorted(cand - derived)
    if extra:
        print(u"在候选里但四条模式未命中（只报告，不判红）：")
        for n in extra:
            print("  - %s" % n)

    hard = sorted(n for n in derived
                  if hits[n]["tier"] == 0 and n not in cand)
    soft = sorted(n for n in derived
                  if hits[n]["tier"] == 1 and n not in cand)
    if soft:
        print(u"\n中档未纳入（建议补跑，未判红）：%s" % soft)
    if hard:
        print(u"\n=== 候选集不完备（高檔 %d 条被漏）===" % len(hard))
        for n in hard:
            print("  - %s   %s" % (n, u"；".join(hits[n]["why"][:3])))
        print(u"\n修正方式：纳入 `hunt_flaky_r102.CANDIDATES` 并补跑，"
              u"或在候选表里写明**为何排除**（不许默不作声）。")
        return 1
    print(u"\n高档全覆盖（无遗漏）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
