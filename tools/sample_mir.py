# -*- coding: utf-8 -*-
"""**抽样跑 MIR**：从大规模合成用例池里抽样，验真实有效性与场景分布。

    python tools/sample_mir.py --dir E:/temp/gen_3m --n 10000
    python tools/sample_mir.py --selftest

## 为什么把它放进 tools/

之前这个脚本写在临时目录里，于是 R1128 改 `classify` 签名时**全仓搜不到它**，
端到端仍然退化成"形状全空"。**放进仓库、能被 grep 到，才改得动。**

## 两个指标必须分开

* `valid_rate` —— 生成的文件能不能进 MIR 且有算子（验生成器）
* `degrade_rate` —— 进 MIR 后有多少语句未映射（验前端能力）

R1106 踩过：16.2% 与 2.5% 是两个不同的分母，混着引用会得出相反结论。

## 形状必须传 src

`classify(st, mir_text, src)` 的第三个参数是**原始 MATLAB 文本**。
MIR 不输出 `shape:`（R1127 实测），不传 src 就只能判出 other。
本脚本每次调用都传 `text`，并在自证里**专测这一条**。

退出码：0=已产出 1=自检失败 2=缺输入
"""
import argparse
import io
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "translate"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import mir as M                       # noqa: E402
from scenario_coverage import classify  # noqa: E402


def run(d, n, seed=42):
    fs = sorted(f for f in os.listdir(d) if f.endswith(".m"))
    random.seed(seed)
    pick = random.sample(fs, min(n, len(fs)))

    ok = fail = 0
    ops_tot = un_tot = 0
    stat = {}
    fails = []
    for fn in pick:
        p = os.path.join(d, fn)
        try:
            text = io.open(p, encoding="utf-8", errors="replace").read()
            mir_t, st = M.to_mir(text)
        except Exception as e:                      # noqa: BLE001
            fail += 1
            if len(fails) < 10:
                fails.append((fn, type(e).__name__))
            continue
        if (st.get("ops") or 0) <= 0:
            fail += 1
            if len(fails) < 10:
                fails.append((fn, "no_ops"))
            continue
        ok += 1
        ops_tot += st.get("ops") or 0
        un_tot += st.get("unmapped") or 0
        # **第三个参数必须传 text** —— 不传就判不出形状（R1128 的坑）
        cat = classify(st, mir_t, text)
        stat[cat] = stat.get(cat, 0) + 1

    return {
        "dir": d, "sampled": len(pick), "valid": ok, "invalid": fail,
        "valid_rate": round(ok / len(pick), 4) if pick else 0,
        "ops_total": ops_tot, "unmapped_total": un_tot,
        "degrade_rate": round(float(un_tot) / (un_tot + ops_tot), 4)
        if (un_tot + ops_tot) else 0,
        "scenes": dict(sorted(stat.items(), key=lambda x: -x[1])),
        "fail_samples": fails,
    }


def _selftest():
    """两向自证：**传 src 与不传 src 必须判出不同的结果**。"""
    good = bad = 0
    src = "function y = f(a, b)\na = [1 2 3 4];\nb = [5 6 7 8];\ny = a + b;\nend\n"
    mir_t, st = M.to_mir(src)

    with_src = classify(st, mir_t, src)
    if with_src in ("vector", "binary"):
        good += 1
    else:
        bad += 1
        print("  [selftest] 传 src 后未判出 vector：%r" % with_src)

    # 不传 src 时应退化为 other（证明"这个参数真的必要"）
    without = classify(st, mir_t)
    if without == "other":
        good += 1
    else:
        bad += 1
        print("  [selftest] 不传 src 竟也能判出 %r —— 说明 src 没被用到" % without)

    # 两种结果必须不同，否则说明 src 被忽略
    if with_src != without:
        good += 1
    else:
        bad += 1
        print("  [selftest] 传与不传结果相同（%r）" % with_src)

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="抽样跑 MIR")
    ap.add_argument("--dir", default=r"E:\temp\gen_3m")
    ap.add_argument("--n", type=int, default=10000)
    ap.add_argument("--out", default=os.path.join(ROOT, "flow",
                                                 "sample-mir.json"))
    ap.add_argument("--selftest", action="store_true")
    ns = ap.parse_args(argv)

    if ns.selftest:
        return _selftest()
    if not os.path.isdir(ns.dir):
        print("sample_mir: 缺输入（%s 不存在）" % ns.dir)
        return 2

    r = run(ns.dir, ns.n)
    io.open(ns.out, "w", encoding="utf-8", newline="\n").write(
        json.dumps(r, ensure_ascii=False, indent=1) + "\n")
    print("sampled=%d valid=%d invalid=%d rate=%.2f%%"
          % (r["sampled"], r["valid"], r["invalid"], r["valid_rate"] * 100))
    print("ops=%d un=%d degrade=%.1f%%"
          % (r["ops_total"], r["unmapped_total"], r["degrade_rate"] * 100))
    print("scenes: %s" % json.dumps(r["scenes"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
