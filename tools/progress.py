# -*- coding: utf-8 -*-
"""**模块级完成度盘点**（回答"到底完成了吗"）

    python tools/progress.py            # 打印表格
    python tools/progress.py --md       # 输出 markdown（贴进报告）

## 为什么要有它

前二十几轮我一直在产出"本轮读数"（+2pp、多一张图、修一个门），却**从来没产出过
"整体到哪了"**。而后者才是决策依据：局部指标会让人以为在推进，模块级的红黄绿
才会暴露真正的短板（比如"反向链路 3/40"）。

## 判据来源（全部读产物，一手不填）

| 维度 | 来源 |
|---|---|
| 正向规模 | `flow/bench_all.json` |
| 降级率 | `flow/unmapped.json`（`avg_rate`） |
| 反向链路 | `c2m --json` 的输出（`stub_files` / `total.ops`） |
| 门禁 | `flow/gates.json`（harness 分组结论） |
| 大脑 | `brain.brief()` + `flow/brain-growth.jsonl` |

## 红黄绿的判据（写死，避免"感觉不错"）

* **绿**：有第三方可复核的门/判据在守，且当前为绿
* **黄**：有实现、能跑，但关键指标低于可用线
* **红**：能力基本缺失或当前失败

退出码：
    0 = 盘点完成
    2 = 缺输入（连一个产物都没有）
"""
import argparse
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def _j(p):
    if not os.path.isfile(p):
        return None
    try:
        return json.load(io.open(p, encoding="utf-8"))
    except ValueError:
        return None


def collect():
    d = {}
    d["bench"] = (_j(os.path.join(ROOT, "flow", "bench_all.json")) or {}).get("recs")
    d["un"] = _j(os.path.join(ROOT, "flow", "unmapped.json"))
    d["gates"] = _j(os.path.join(ROOT, "flow", "gates.json"))
    d["g41"] = _j(os.path.join(ROOT, "flow", "gates41.json"))
    # 反向链路：取最近一次 c2m 的 json（调用方用 -o 指定过路径的，这里找 flow 里那份）
    d["c2m"] = _j(os.path.join(ROOT, "flow", "c2m.json"))
    try:
        import brain
        d["brief"] = brain.brief(multi=True).splitlines()
        d["brain"] = brain.snapshot()
    except Exception:                      # noqa: BLE001
        d["brief"], d["brain"] = [], {}
    return d


def rows(d):
    out = []
    b = d["bench"] or []
    m_tot = sum((r.get("m_funcs") or 0) for r in b)
    c_tot = sum((r.get("c_funcs") or 0) for r in b)
    rate = (100.0 * c_tot / m_tot) if m_tot else 0.0

    # ① 正向链路
    if b:
        out.append(("MATLAB→C 正向", "绿" if rate >= 95 else "黄",
                    "%d/%d 函数（%.1f%%），%d 个工程"
                    % (c_tot, m_tot, rate, len(b))))
    else:
        out.append(("MATLAB→C 正向", "红", "无实测数据"))

    # ② 解析降级率（真实工程）
    un = d["un"] or {}
    if un.get("avg_rate") is not None:
        r = 100.0 * un["avg_rate"]
        out.append(("解析降级率（真实代码）", "绿" if r >= 90 else ("黄" if r >= 50 else "红"),
                    "%.1f%%（%d 文件，未映射 %d 条）"
                    % (r, un.get("files") or 0,
                       un.get("total_unmapped") or un.get("total") or 0)))
    else:
        out.append(("解析降级率（真实代码）", "红", "未量"))

    # ③ 反向链路
    c2 = d["c2m"] or {}
    if c2:
        n = c2.get("n_files") or 0
        stub = c2.get("stub_files") or 0
        okn = n - (c2.get("bad") or 0) - stub
        out.append(("C→MATLAB 反向", "绿" if okn >= 0.8 * n else ("黄" if okn else "红"),
                    "真实往返 %d/%d（空壳 %d）" % (okn, n, stub)))
    else:
        out.append(("C→MATLAB 反向", "黄", "有实现（c2m），本次未量"))

    # ④ 门禁：**41 门 + harness 分组两条都要报**（R981）
    g = d["gates"] or {}
    g41 = d.get("g41") or {}
    if g41.get("total"):
        failed = g41.get("failed") or []
        out.append(("门禁（41 道护栏）",
                    "绿" if not failed else "红",
                    "%d/%d 通过%s"
                    % (g41.get("passed", 0), g41.get("total", 0),
                       ("，红：" + "、".join(x.replace(".py", "") for x in failed[:3]))
                       if failed else "")))
    elif g.get("total"):
        out.append(("门禁（harness 分组）",
                    "绿" if g.get("passed") == g.get("total") else "红",
                    "%s/%s 组" % (g.get("passed"), g.get("total"))))
    else:
        out.append(("门禁", "黄", "未跑"))
    if g.get("total"):
        out.append(("harness 分组复查",
                    "绿" if g.get("passed") == g.get("total") else "红",
                    "%s/%s 组" % (g.get("passed"), g.get("total"))))

    # ⑤ 大脑
    br = d["brain"] or {}
    if br:
        out.append(("大脑/小脑机制",
                    "绿" if br.get("coverage", 0) >= 100 else "黄",
                    "%d 条 / 见证 %.0f%% / 快照 %d 次 / 咨询 %d"
                    % (br.get("total", 0), br.get("coverage", 0),
                       _snaps(), br.get("usage", 0))))
    else:
        out.append(("大脑/小脑机制", "红", "不可用"))
    return out


def _snaps():
    p = os.path.join(ROOT, "flow", "brain-growth.jsonl")
    if not os.path.isfile(p):
        return 0
    return sum(1 for ln in io.open(p, encoding="utf-8") if ln.strip())


def main(argv=None):
    ap = argparse.ArgumentParser(description="模块级完成度盘点")
    ap.add_argument("--md", action="store_true", help="输出 markdown")
    ns = ap.parse_args(argv)

    d = collect()
    if not any(d.get(k) for k in ("bench", "un", "gates", "brain")):
        print("progress: 缺输入（一个产物都没有）")
        return 2
    rs = rows(d)
    if ns.md:
        print("| 模块 | 状态 | 依据 |")
        print("|---|---|---|")
        for name, col, why in rs:
            print("| %s | %s | %s |" % (name, col, why))
    else:
        print("%-22s %-4s %s" % ("模块", "状态", "依据"))
        for name, col, why in rs:
            print("%-22s %-4s %s" % (name, col, why))
    if d.get("brief"):
        print("")
        for ln in d["brief"]:
            print(ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
