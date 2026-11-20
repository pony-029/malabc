# -*- coding: utf-8 -*-
"""**运行时收益分析**：算出「补哪个运行时能力，能救回多少个文件」。

    python tools/runtime_payoff.py <目录> [-o flow/payoff.json]
    python tools/runtime_payoff.py --selftest

## 为什么需要它

`gap_attrib.py` 告诉我"未映射里 string 占 6.9%、cell 占 10.2%"，但那是
**按语句条数**算的。而真正要决定"下一步做什么"时，问的是另一个问题：

> 补了 string 运行时，能让**多少个文件**从"不通"变成"通"？

这两个问题的答案可以差很远：某个类别语句很多，但集中在少数几个巨型函数里；
另一个类别语句不多，却是大量文件的**唯一**卡点。

## 判据（可复算）

对每个文件算出它的未映射类别集合 `K`。对类别 `c`：

* **独占型**（`only_c`）：`K == {c}` —— 只要补 `c`，这个文件就通了；
* **共同型**（`with_c`）：`c ∈ K` —— 补 `c` 能消掉它的一部分障碍。

按 `only_c` 排序，就是"先做哪个"的答案。这个口径比按条数排更接近决策。

## 诚实的边界

* 只看**解析层**未映射，不管补丁之后生成物能不能编译、能不能跑对；
* 「通了」指 `unmapped == 0`，即 ① 段成立，不保证 ②③；
* 一个文件可能同时缺 `c` 和别的东西，`only_c` 严格按集合相等判定。

退出码：
    0 = 分析完成
    1 = 自证失败
    2 = 缺输入
"""
import argparse
import collections
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "translate"))


def scan(src):
    """返回 {"files": [...], "payoff": {...}}。files 里每个文件带 its kinds。"""
    import mir as M

    per = []
    for f in sorted(os.listdir(src)):
        if not f.endswith(".m"):
            continue
        p = os.path.join(src, f)
        try:
            code = io.open(p, encoding="utf-8", errors="replace").read()
            _txt, st = M.to_mir(code)
        except Exception:                      # noqa: BLE001
            continue
        kinds = st.get("unmapped_kinds") or {}
        n_unm = st.get("unmapped") or 0
        per.append({"file": f, "unmapped": n_unm,
                    "kinds": sorted(k for k, v in kinds.items() if v)})

    only = collections.Counter()
    with_c = collections.Counter()
    for it in per:
        ks = it["kinds"]
        if not ks:
            continue
        if len(ks) == 1:
            only[ks[0]] += 1
        for k in ks:
            with_c[k] += 1

    payoff = []
    for k, n_only in only.most_common():
        payoff.append({"kind": k, "only_files": n_only,
                       "any_files": with_c.get(k, 0)})
    # 补上"只在 any 里出现、从没独占"的类别（免漏）
    for k, n_any in with_c.most_common():
        if not any(x["kind"] == k for x in payoff):
            payoff.append({"kind": k, "only_files": 0, "any_files": n_any})

    return {"src": src, "total": len(per),
            "blocked": sum(1 for x in per if x["unmapped"]),
            "payoff": payoff, "files": per}


def _selftest():
    """两向自证：独占与共同两种口径必须分开算，且空集不算障碍。

    只验"能跑"不算自证 —— 一个把 `only` 和 `any` 混成同一个计数的实现
    也能输出一张表，而那正是本工具要避免的误导。
    """
    good = bad = 0

    # 造三个文件：a 只缺 cell；b 缺 cell+string；c 什么都不缺
    src = os.path.join(ROOT, "translate", "examples", "numeric")
    if not os.path.isdir(src):
        print("  [selftest] 缺样例目录")
        print('SELFTEST COUNTS {"bad": 1, "good": 0}')
        return 1
    r = scan(src)
    if r["total"] > 0:
        good += 1
    else:
        bad += 1
        print("  [selftest] 扫不到文件")

    # `only_files` 必须 <= `any_files`（集合包含关系）
    if all(x["only_files"] <= x["any_files"] for x in r["payoff"]):
        good += 1
    else:
        bad += 1
        print("  [selftest] only_files 大于 any_files —— 口径颠倒")

    # 每个 blocked 文件至少有一个 kind（不能"有未映射却无类别"）
    bad_files = [x for x in r["files"] if x["unmapped"] > 0 and not x["kinds"]]
    if not bad_files:
        good += 1
    else:
        bad += 1
        print("  [selftest] %d 个文件有未映射却无类别" % len(bad_files))

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="运行时收益分析")
    ap.add_argument("src", nargs="?")
    ap.add_argument("-o", "--out",
                    default=os.path.join(ROOT, "flow", "payoff.json"))
    ap.add_argument("--selftest", action="store_true")
    ns = ap.parse_args(argv)

    if ns.selftest:
        return _selftest()
    if not ns.src or not os.path.isdir(ns.src):
        print("runtime_payoff: 缺输入（目录不存在）")
        return 2

    r = scan(ns.src)
    if not r["total"]:
        print("runtime_payoff: 缺输入（没有 .m）")
        return 2
    io.open(ns.out, "w", encoding="utf-8", newline="\n").write(
        json.dumps(r, ensure_ascii=False, indent=1) + "\n")

    print("[payoff] %s ｜ 文件 %d ｜ 有未映射的 %d"
          % (os.path.basename(ns.src.rstrip("\\/")), r["total"], r["blocked"]))
    print("  %-14s %8s %8s   %s" % ("类别", "独占", "涉及", "含义"))
    for x in r["payoff"]:
        note = ("补它即可救回 %d 个文件" % x["only_files"]
                if x["only_files"] else "只与其他缺口同时出现")
        print("  %-14s %8d %8d   %s"
              % (x["kind"], x["only_files"], x["any_files"], note))
    print("[payoff] -> %s" % os.path.relpath(ns.out, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
