# -*- coding: utf-8 -*-
"""统计一个目录下 .m 的**降级率**与未映射类别，写 flow/unmapped.json。

    python tools/unmapped_stats.py <目录> [-o flow/unmapped.json]

## 为什么要有"降级率"

三段链路的 ① 是**二值**判据（未映射必须为 0）。在真实工程上，一个函数
哪怕只有 3 条不认识，也会记成"失败"——于是 40 个真实函数得到 `0/40`，
而它们其实分别降级了 60%、85%、92%……

`0/40` 和 `35/40` 在**决策上**是两回事：前者会让人以为"完全不能用"，
后者才告诉你"再补 5 类语法就能过半"。所以这里给每个文件算

    rate = 1 - unmapped / (unmapped + ops)

其中 `ops` 是成功降级的算子/语句数（来自 `mir.to_mir` 的统计）。

## 输出

    {source, files, total_unmapped, kinds, avg_rate, files_over_90, per_file:[...]}

`avg_rate` 是**按文件平均**（不是按语句加权）—— 因为关心的是"有多少函数可用"，
而不是"总语句里多少可用"。

退出码：
    0 = 统计完成
    2 = 缺输入（目录不存在或没有 .m）
"""
import argparse
import collections
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "translate"))
import mir as M  # noqa: E402


def scan(src):
    kinds = collections.Counter()
    per_file = []
    total = 0
    for f in sorted(os.listdir(src)):
        if not f.endswith(".m"):
            continue
        p = os.path.join(src, f)
        try:
            code = io.open(p, encoding="utf-8", errors="replace").read()
            _t, st = M.to_mir(code)
        except Exception as e:                 # noqa: BLE001
            per_file.append({"file": f, "unmapped": None, "ops": None,
                             "rate": None, "error": str(e)[:80]})
            continue
        un = st.get("unmapped") or 0
        ops = st.get("ops") or 0
        total += un
        for k, v in (st.get("unmapped_kinds") or {}).items():
            kinds[k] += v
        rate = (1.0 - float(un) / (un + ops)) if (un + ops) else 1.0
        per_file.append({"file": f, "unmapped": un, "ops": ops,
                         "rate": round(rate, 3)})
    ok = [r for r in per_file if r["rate"] is not None]
    avg = round(sum(r["rate"] for r in ok) / len(ok), 3) if ok else 0.0
    return {
        "source": src,
        "files": len(per_file),
        "total_unmapped": total,
        "kinds": dict(kinds.most_common()),
        "avg_rate": avg,
        "files_over_90": sum(1 for r in ok if r["rate"] >= 0.9),
        "files_zero": sum(1 for r in ok if r["unmapped"] == 0),
        "per_file": sorted(per_file, key=lambda r: (r["rate"] is None, r["rate"])),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="降级率与未映射类别统计")
    ap.add_argument("src")
    ap.add_argument("-o", "--out", default=os.path.join(ROOT, "flow", "unmapped.json"))
    ns = ap.parse_args(argv)
    if not os.path.isdir(ns.src):
        print("unmapped_stats: 缺输入（目录不存在）")
        return 2
    d = scan(ns.src)
    if not d["files"]:
        print("unmapped_stats: 缺输入（没有 .m）")
        return 2
    io.open(ns.out, "w", encoding="utf-8", newline="\n").write(
        json.dumps(d, ensure_ascii=False, indent=1) + "\n")
    print("[stats] %s ｜ 文件 %d ｜ 未映射 %d ｜ 平均降级率 %.1f%% ｜ "
          "≥90%% 的 %d 个 ｜ 全降级 %d 个"
          % (ns.src, d["files"], d["total_unmapped"], 100 * d["avg_rate"],
             d["files_over_90"], d["files_zero"]))
    print("[stats] -> %s" % os.path.relpath(ns.out, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
