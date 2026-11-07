# -*- coding: utf-8 -*-
"""**任务级 KPI**：给定若干目录，跑"相互转换"，输出通过率与逐项证据。

## 为什么要它（`docs/DESIGN_TOPLEVEL.md` 阶段 2）

过去用的 KPI 是"大库 numeric 率"（YALMIP 2185 函数里能算几个）。
但那个数被三件事稀释：84% 的函数差 2~6 类卡点、48% 在签名层就被拒、
而用户真正关心的是"**我这一批函数能不能转**"。

本工具把 KPI 换成**任务级**：按目录聚合，给出
"这批里能双向转换的有几个、卡在哪、失败明细是什么"。

## 用法

    python tools/task_kpi.py <目录...> [--min 90] [--json out.json]

`--min` 是门槛：低于它就返回非 0（CI 用）。默认 90（对**任务集**），
扫真实大库时应显式给 `--min 0`（那里没有门槛意义）。

## 与 `roundtrip.py` 的关系

单个函数的判定完全复用 `roundtrip.verdict` —— 只做聚合与门槛，
不另写一套判据，避免两处逻辑漂移。
"""
import argparse
import collections
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from translate import roundtrip as RT     # noqa: E402
import tools.parity_report as PR          # noqa: E402


def collect(dirs):
    """目录 → [(工程名, [.m 路径...])]"""
    out = []
    for d in dirs:
        if os.path.isfile(d) and d.endswith(".m"):
            out.append((os.path.splitext(os.path.basename(d))[0], [d]))
            continue
        if not os.path.isdir(d):
            continue
        files = sorted(os.path.join(d, f) for f in os.listdir(d)
                       if f.endswith(".m"))
        out.append((os.path.basename(os.path.normpath(d)), files))
    return out


def main():
    ap = argparse.ArgumentParser(description="任务级 KPI：双向转换通过率")
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--min", type=float, default=90.0,
                    help="通过率门槛（%%），低于则返回非 0")
    ap.add_argument("--json", default=None, help="把结果写成 JSON")
    ap.add_argument("--verbose", action="store_true", help="打印每个失败项的原因")
    a = ap.parse_args()

    if not os.path.isfile(RT.M2C):
        print("缺 m2c：cd rust/m2c && cargo build --release")
        return 2
    cli = PR._octave_cli()
    if cli is None:
        print("缺 Octave/MATLAB：只能验「能生成」，无法验「算得一样」")
        return 2

    base = RT.WORK if os.path.isdir(RT.WORK) else None
    d = tempfile.mkdtemp(prefix="m2c_kpi_", dir=base)

    rows, agg = [], collections.Counter()
    reasons = collections.Counter()          # 跳过/失败的原因聚合（可行动性）
    for proj, files in collect(a.dirs):
        c = collections.Counter()
        fails = []
        for f in files:
            rec = RT.roundtrip_one(f, cli, d)
            v = RT.verdict(rec)
            c[v] += 1
            agg[v] += 1
            if v != "ok":
                note = rec["note"] or "数值不一致"
                # 归一化：把 "12 条未映射" 折成 "未映射"，便于聚合
                if "条未映射" in note:
                    note = "有未映射语句"
                reasons["%s ｜ %s" % (v, note)] += 1
            if v == "fail":
                fails.append((rec["name"], rec["note"] or "数值不一致"))
        total = c["ok"] + c["fail"]
        rate = (100.0 * c["ok"] / total) if total else 0.0
        rows.append({"project": proj, "total": len(files), "ok": c["ok"],
                     "fail": c["fail"], "skip": c["skip"], "rate": rate,
                     "fails": fails})
        bar = "#" * int(round(rate / 5.0))
        print("%-16s 共 %3d ｜ 通过 %3d ｜ 失败 %2d ｜ 跳过 %2d ｜ %5.1f%% %s"
              % (proj, len(files), c["ok"], c["fail"], c["skip"], rate, bar))
        if a.verbose:
            for n, why in fails[:6]:
                print("      ✗ %-22s %s" % (n, why))

    total = agg["ok"] + agg["fail"]
    rate = (100.0 * agg["ok"] / total) if total else 0.0
    print("-" * 64)
    print("合计：通过 %d / %d ｜ 失败 %d ｜ 跳过 %d ｜ **%.1f%%**（门槛 %.0f%%）"
          % (agg["ok"], total, agg["fail"], agg["skip"], rate, a.min))

    # 只看百分比什么都说明不了；"为什么没通过"才是下一步的依据
    if reasons:
        print("\n未通过原因（按条数）：")
        for k, v in reasons.most_common(6):
            print("  %-42s %3d" % (k[:42], v))

    if a.json:
        io.open(a.json, "w", encoding="utf-8", newline="\n").write(
            json.dumps({"rate": rate, "ok": agg["ok"], "fail": agg["fail"],
                        "skip": agg["skip"], "projects": rows},
                       ensure_ascii=False, indent=2))
        print("已写出 %s" % a.json)

    return 0 if rate >= a.min else 1


if __name__ == "__main__":
    sys.exit(main())
