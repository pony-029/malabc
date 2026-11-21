# -*- coding: utf-8 -*-
"""**降级比例**（ANE 第二十一章 失效安全与优雅降级）。

    python tools/degradation_ratio.py <C 工程目录> [--limit 0.10]
    python tools/degradation_ratio.py <目录> --json
    python tools/degradation_ratio.py --selftest

## 问题

生成器碰上不支持的算子时，会产出 `MLC_UNIMPLEMENTED`（值层面的降级）。
这是**正确**的设计——比返回一个"看起来对"的值好。

但若一个工程里 60% 的算子都是 UNIMPLEMENTED，那生成的 C
**编译通过、运行不报错、但什么都不做**。这正是规范第二十一章要防的
「静默降级」：**单个降级是诚实的，大量降级等于没实现**。

## 判据

    ratio = 含 MLC_UNIMPLEMENTED 的算子调用点 / 总算子调用点

`ratio > limit`（默认 0.10）即判「降级过多」。

口径写死：
* 只数 `mlc_op_*` 调用点（生成器确实产出的那些）；
* 每个调用点若其后 3 行内出现 `MLC_UNIMPLEMENTED`，记为降级；
* **无调用点**时 ratio 记 0 且单独报 `no_calls`——不能把"没有"算作"很好"。

## 诚实边界

* 只看生成物文本，不做控制流分析：一个算子在 `if` 的某一分支里降级，
  这里会整体记为降级；
* 不含运行期才暴露的降级（如 `mlc_op_*` 内部返回 UNIMPLEMENTED）。

退出码：0=比例在限内 1=超限（**结论**，不是错误）2=缺输入
"""
import argparse
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OP_CALL = re.compile(r"\b(mlc_op_[a-z0-9_]+)\s*\(")
UNIMP = "MLC_UNIMPLEMENTED"


def scan_dir(d):
    """返回 {files, calls, degraded, detail}。"""
    files = 0
    calls = 0
    degraded = 0
    detail = []
    for base, _ds, fs in os.walk(d):
        for fn in fs:
            if not fn.endswith(".c"):
                continue
            files += 1
            p = os.path.join(base, fn)
            try:
                lines = io.open(p, encoding="utf-8",
                               errors="replace").read().splitlines()
            except OSError:
                continue
            for i, ln in enumerate(lines):
                for m in OP_CALL.finditer(ln):
                    calls += 1
                    window = "\n".join(lines[i:i + 4])
                    if UNIMP in window:
                        degraded += 1
                        detail.append({"file": os.path.relpath(p, d),
                                       "line": i + 1, "op": m.group(1)})
    return {"files": files, "calls": calls, "degraded": degraded,
            "detail": detail}


def judge(stats, limit):
    calls = stats["calls"]
    if not calls:
        return {"ratio": 0.0, "limit": limit, "over": False,
                "no_calls": True}
    ratio = float(stats["degraded"]) / calls
    return {"ratio": round(ratio, 4), "limit": limit,
            "over": ratio > limit, "no_calls": False}


def _selftest():
    """两向自证：低于限判过、高于限判超、无调用点必须单独标出。"""
    good = bad = 0

    j = judge({"calls": 100, "degraded": 5}, 0.10)
    if not j["over"] and j["ratio"] == 0.05:
        good += 1
    else:
        bad += 1
        print("  [selftest] 5%% 应判过：%r" % (j,))

    j2 = judge({"calls": 100, "degraded": 30}, 0.10)
    if j2["over"]:
        good += 1
    else:
        bad += 1
        print("  [selftest] 30%% 应判超限")

    j3 = judge({"calls": 0, "degraded": 0}, 0.10)
    if j3["no_calls"] and not j3["over"]:
        good += 1
    else:
        bad += 1
        print("  [selftest] 无调用点未单独标出")

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="降级比例")
    ap.add_argument("src", nargs="?")
    ap.add_argument("--limit", type=float, default=0.10)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ns = ap.parse_args(argv)

    if ns.selftest:
        return _selftest()
    if not ns.src or not os.path.isdir(ns.src):
        print("degradation_ratio: 缺输入（目录不存在）")
        return 2

    st = scan_dir(ns.src)
    j = judge(st, ns.limit)
    r = dict(st)
    r.pop("detail", None)
    r.update(j)

    if ns.json:
        r["detail"] = st["detail"][:20]
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 1 if j["over"] else 0

    if j["no_calls"]:
        print("[降级] %s ｜ C 文件 %d ｜ **没有找到任何 mlc_op_* 调用点**"
              % (os.path.basename(ns.src.rstrip("\\/")), st["files"]))
        print("  没有调用点不等于「降级很少」，请确认生成物是否完整")
        return 0

    print("[降级] %s ｜ C 文件 %d ｜ 调用点 %d ｜ 降级 %d ｜ 比例 %.1f%%（上限 %.0f%%）"
          % (os.path.basename(ns.src.rstrip("\\/")), st["files"],
             st["calls"], st["degraded"], j["ratio"] * 100, ns.limit * 100))
    if j["over"]:
        print("  **降级过多**：%d 个调用点里 %d 个返回 UNIMPLEMENTED"
              % (st["calls"], st["degraded"]))
        for d in st["detail"][:5]:
            print("    %s:%d  %s" % (d["file"], d["line"], d["op"]))
        return 1
    print("  在限内")
    return 0


if __name__ == "__main__":
    sys.exit(main())
