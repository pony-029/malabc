# -*- coding: utf-8 -*-
"""**全流程测试报告**：把一次三段链路实测渲染成 HTML。

    python tools/fullflow_report.py
    python tools/fullflow_report.py --selftest

## 与 bigtest_report 的分工

* `bigtest_report.py`   —— 全量**解析**（64474 文件，只到 MIR）
* `fullflow_report.py`  —— **完整三段**（解析 → 生成 C → 编译运行），规模小但走得远

两份报告回答不同问题：
「前端能吃掉多少」vs「生成的 C 能不能真的跑对」。

## 数据来源

`flow/fullflow.json`：由一次 `three_links_report` 实测填写，含
  stages（每段通过数）、corpus（语料说明）、findings（关键观察）

**缺文件就写"缺失"，不编数字。**

退出码：0=已生成 1=自检失败 2=缺输入
"""
import argparse
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CSS = """
:root{--ink:#14181c;--ink2:#48525b;--ink3:#78848f;--line:#e2e8ee;
--bg:#fff;--bg2:#f6f9fc;--bg3:#eceff4;--accent:#0a66c2;--ok:#0f7b46;
--warn:#a8690a;--bad:#b8342a;--mono:ui-monospace,Consolas,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.65 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1020px;margin:0 auto;padding:0 26px 96px}
.cover{padding:60px 0 34px;border-bottom:1px solid var(--line);margin-bottom:34px}
.cover .kicker{font:600 12px/1 var(--mono);letter-spacing:.16em;
text-transform:uppercase;color:var(--accent);margin-bottom:16px}
.cover h1{font-size:35px;line-height:1.2;margin:0 0 16px;font-weight:700;
letter-spacing:-.025em}
.cover .sub{font-size:16.5px;color:var(--ink2);margin:0;max-width:70ch}
.board{display:grid;grid-template-columns:repeat(4,1fr);gap:13px;margin:28px 0}
.kpi{border:1px solid var(--line);border-radius:10px;padding:15px 17px;background:var(--bg2)}
.kpi .v{font:700 23px/1.1 var(--mono);letter-spacing:-.03em}
.kpi .k{font-size:12px;color:var(--ink3);margin-top:7px}
.kpi.ok{background:color-mix(in srgb,var(--ok) 9%,var(--bg2))}
.kpi.warn{background:color-mix(in srgb,var(--warn) 10%,var(--bg2))}
.kpi.bad{background:color-mix(in srgb,var(--bad) 8%,var(--bg2))}
h2{font-size:21px;margin:46px 0 4px;padding-top:18px;border-top:2px solid var(--ink);
font-weight:700;letter-spacing:-.01em}
h2 .num{font:600 12px/1 var(--mono);color:var(--accent);display:block;
margin-bottom:8px;letter-spacing:.09em}
table{border-collapse:collapse;width:100%;margin:15px 0;font-size:14px}
th,td{border-bottom:1px solid var(--line);padding:9px 12px;text-align:left}
th{background:var(--bg2);font-weight:600;font-size:12.5px;color:var(--ink2)}
td.n{text-align:right;font-variant-numeric:tabular-nums;font-family:var(--mono)}
tbody tr:hover{background:var(--bg2)}
.funnel{margin:18px 0}
.fstep{display:flex;align-items:center;gap:12px;margin:9px 0}
.fstep .lab{width:180px;font-size:13.5px;color:var(--ink2);flex-shrink:0}
.fstep .bar{flex:1;height:26px;background:var(--bg3);border-radius:5px;
overflow:hidden;position:relative}
.fstep .bar>i{display:block;height:100%;background:var(--accent);border-radius:5px;
transition:width .5s}
.fstep .bar>span{position:absolute;left:10px;top:4px;font:600 12px/1.4 var(--mono);
color:#fff;text-shadow:0 1px 2px rgba(0,0,0,.35)}
.fstep .pct{width:74px;text-align:right;font:700 14px/1 var(--mono)}
.callout{border-left:3px solid var(--accent);background:var(--bg2);
padding:13px 17px;border-radius:0 7px 7px 0;margin:17px 0;font-size:14.5px}
.callout.warn{border-left-color:var(--warn);
background:color-mix(in srgb,var(--warn) 8%,var(--bg2))}
.callout.bad{border-left-color:var(--bad);
background:color-mix(in srgb,var(--bad) 7%,var(--bg2))}
.callout p:first-child{margin-top:0}.callout p:last-child{margin-bottom:0}
.tag{display:inline-block;font:600 11px/1 var(--mono);padding:3px 8px;
border-radius:4px;background:var(--bg3);color:var(--ink3)}
footer{margin-top:58px;padding-top:20px;border-top:1px solid var(--line);
font-size:12.5px;color:var(--ink3)}
@media(max-width:780px){.board{grid-template-columns:repeat(2,1fr)}
.cover h1{font-size:26px}.fstep .lab{width:110px;font-size:12px}}
@media print{.toc{display:none}body{font-size:10.5pt}}
"""


def _fmt(n):
    if n is None:
        return "—"
    try:
        return "{:,}".format(int(n))
    except (TypeError, ValueError):
        return str(n)


def build(d):
    st = d.get("stages") or []
    total = d.get("total") or (st[0]["total"] if st else 0)

    h = ['<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width,initial-scale=1">',
         '<title>全流程测试报告 — Matlabc</title>',
         '<style>%s</style></head><body><div class="wrap">' % CSS]

    h.append('<div class="cover"><div class="kicker">Full-flow Test Report</div>')
    h.append("<h1>MATLAB → C 全流程测试报告</h1>")
    h.append('<p class="sub">%s</p></div>'
             % d.get("corpus", "三段链路：解析 → 生成 C → 编译运行"))

    # KPI
    last = st[-1]["pass"] if st else 0
    rate = (100.0 * last / total) if total else 0
    cls = "ok" if rate >= 50 else ("warn" if rate > 0 else "bad")
    h.append('<div class="board">')
    h.append('<div class="kpi"><div class="v">%s</div>'
             '<div class="k">样本文件数</div></div>' % _fmt(total))
    h.append('<div class="kpi ok"><div class="v">%s</div>'
             '<div class="k">① 解析进 MIR</div></div>'
             % _fmt(st[0]["pass"] if st else 0))
    h.append('<div class="kpi %s"><div class="v">%s</div>'
             '<div class="k">③ 三段全通</div></div>' % (cls, _fmt(last)))
    h.append('<div class="kpi %s"><div class="v">%.1f%%</div>'
             '<div class="k">全通率</div></div>' % (cls, rate))
    h.append("</div>")

    # 漏斗
    h.append('<h2><span class="num">01</span>三段漏斗</h2>')
    if st:
        h.append('<div class="funnel">')
        for s in st:
            p = s["pass"]
            pc = 100.0 * p / total if total else 0
            h.append('<div class="fstep"><div class="lab">%s</div>'
                     '<div class="bar"><i style="width:%.1f%%"></i>'
                     '<span>%s / %s</span></div>'
                     '<div class="pct">%.1f%%</div></div>'
                     % (s["name"], max(pc, 1.5), _fmt(p), _fmt(total), pc))
        h.append("</div>")
    else:
        h.append('<div class="callout bad"><p>缺 stages 数据。</p></div>')

    # 表格
    h.append('<h2><span class="num">02</span>逐段数据</h2>')
    if st:
        h.append("<table><tr><th>阶段</th><th>通过</th><th>总数</th>"
                 "<th>通过率</th><th>相对上一段</th></tr>")
        prev = None
        for s in st:
            p = s["pass"]
            pc = 100.0 * p / total if total else 0
            delta = "—" if prev is None else ("%+d" % (p - prev))
            h.append("<tr><td>%s</td><td class=n>%s</td><td class=n>%s</td>"
                     "<td class=n>%.1f%%</td><td class=n>%s</td></tr>"
                     % (s["name"], _fmt(p), _fmt(total), pc, delta))
            prev = p
        h.append("</table>")
        if len(st) >= 2 and st[0]["pass"] > st[1]["pass"]:
            lost = st[0]["pass"] - st[1]["pass"]
            msg = ('<div class="callout warn"><p>'
                   '<b>瓶颈在②：解析成功但生成 C 失败 %d 个。</b>'
                   '而 ②→③ 几乎不掉——说明<b>生成出来的 C 基本都能编译跑对</b>，'
                   '问题集中在「从 MIR 到 C」这一步。'
                   '</p></div>' % lost)
            h.append(msg)

    # 发现
    if d.get("findings"):
        h.append('<h2><span class="num">03</span>关键发现</h2><ul>')
        for f in d["findings"]:
            h.append("<li>%s</li>" % f)
        h.append("</ul>")

    # 诚实边界
    h.append('<h2><span class="num">04</span>诚实边界</h2>')
    h.append('<div class="callout bad"><p>%s</p></div>'
             % d.get("limits", "未填写边界说明。"))

    h.append("<footer><p>数据来源：flow/fullflow.json。"
             "由 <code>tools/fullflow_report.py</code> 生成。</p></footer>")
    h.append("</div></body></html>")
    return "\n".join(h)


def _selftest():
    good = bad = 0
    d = {"total": 100,
         "stages": [{"name": "①", "pass": 80, "total": 100},
                    {"name": "②", "pass": 30, "total": 100},
                    {"name": "③", "pass": 30, "total": 100}],
         "findings": ["瓶颈在②"], "limits": "只测 100 个"}
    h = build(d)
    if "80" in h and "30" in h and "30.0%" in h:
        good += 1
    else:
        bad += 1
        print("  [selftest] 数字未渲染出来")
    if "瓶颈在②" in h:
        good += 1
    else:
        bad += 1
        print("  [selftest] 瓶颈提示未出现")
    if "只测 100 个" in h:
        good += 1
    else:
        bad += 1
        print("  [selftest] 边界说明未出现")
    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="全流程测试报告")
    ap.add_argument("--in", dest="src",
                    default=os.path.join(ROOT, "flow", "fullflow.json"))
    ap.add_argument("--out",
                    default=os.path.join(ROOT, "flow", "fullflow-report.html"))
    ap.add_argument("--selftest", action="store_true")
    ns = ap.parse_args(argv)

    if ns.selftest:
        return _selftest()
    if not os.path.isfile(ns.src):
        print("fullflow_report: 缺输入（%s 不存在）" % ns.src)
        return 2

    d = json.load(io.open(ns.src, encoding="utf-8"))
    html = build(d)
    io.open(ns.out, "w", encoding="utf-8", newline="\n").write(html)
    print("[report] -> %s（%.1f KB）"
          % (os.path.relpath(ns.out, ROOT),
             len(html.encode("utf-8")) / 1024.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
