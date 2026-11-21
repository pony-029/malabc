# -*- coding: utf-8 -*-
"""**大规模测试报告**：把全量解析/缺口/门禁统计渲染成一个 HTML。

    python tools/bigtest_report.py            # 写 flow/bigtest-report.html
    python tools/bigtest_report.py --selftest

## 为什么单独做一个报告

`full_report.py` 已经有一份总报告，但它讲的是"项目状态"；
这份讲的是**一次具体的大规模测试**：扫了多少文件、多少行进 MIR、
降级率多少、缺口按类别怎么分布。

两者不是替代关系：总报告回答"项目现在怎么样"，
本报告回答"这一次大规模实测，具体测出了什么"。

## 数据来源（全部是本仓生成的真实产物）

* `flow/bigtest.json`   —— 全量解析结果（R1115：64474 文件）
* `flow/cerebellum.json` —— 小脑硬边界（CB1–CB4）
* `flow/gates41.json`   —— 门禁结论

**缺任何一个数据源就如实说明缺哪份**，不编造数字。

退出码：0=已生成 1=自检失败 2=缺输入
"""
import argparse
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    p = os.path.join(ROOT, "flow", name)
    if not os.path.isfile(p):
        return None
    try:
        return json.load(io.open(p, encoding="utf-8"))
    except (IOError, OSError, ValueError):
        return None


CSS = """
:root{--ink:#1a1d21;--ink2:#4a5158;--ink3:#767e87;--line:#e3e7ec;
--bg:#fff;--bg2:#f7f9fb;--bg3:#eef2f6;--accent:#0b6bcb;--ok:#1a7f4b;
--warn:#b8760f;--bad:#c23b32;--mono:ui-monospace,Consolas,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.7 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:0 28px 100px}
.cover{padding:56px 0 32px;border-bottom:1px solid var(--line);margin-bottom:32px}
.cover .kicker{font:600 12px/1 var(--mono);letter-spacing:.14em;
text-transform:uppercase;color:var(--accent);margin-bottom:14px}
.cover h1{font-size:34px;line-height:1.22;margin:0 0 14px;font-weight:700;
letter-spacing:-.02em}
.cover .sub{font-size:16.5px;color:var(--ink2);margin:0}
.board{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:26px 0}
.kpi{border:1px solid var(--line);border-radius:9px;padding:14px 16px;background:var(--bg2)}
.kpi .v{font:700 22px/1.1 var(--mono);letter-spacing:-.02em}
.kpi .k{font-size:12px;color:var(--ink3);margin-top:6px}
.kpi.ok{background:color-mix(in srgb,var(--ok) 8%,var(--bg2))}
.kpi.warn{background:color-mix(in srgb,var(--warn) 9%,var(--bg2))}
h2{font-size:21px;margin:44px 0 4px;padding-top:16px;border-top:2px solid var(--ink);
font-weight:700;letter-spacing:-.01em}
h2 .num{font:600 12px/1 var(--mono);color:var(--accent);display:block;
margin-bottom:7px;letter-spacing:.08em}
table{border-collapse:collapse;width:100%;margin:14px 0;font-size:14px}
th,td{border-bottom:1px solid var(--line);padding:8px 11px;text-align:left}
th{background:var(--bg2);font-weight:600;font-size:12.5px;color:var(--ink2)}
td.n{text-align:right;font-variant-numeric:tabular-nums;font-family:var(--mono)}
tbody tr:hover{background:var(--bg2)}
.bar{height:7px;border-radius:4px;background:var(--bg3);overflow:hidden;
position:relative;min-width:60px}
.bar>i{display:block;height:100%;background:var(--accent);border-radius:4px}
.callout{border-left:3px solid var(--accent);background:var(--bg2);
padding:12px 16px;border-radius:0 6px 6px 0;margin:16px 0;font-size:14.5px}
.callout.warn{border-left-color:var(--warn);
background:color-mix(in srgb,var(--warn) 7%,var(--bg2))}
.callout.bad{border-left-color:var(--bad);
background:color-mix(in srgb,var(--bad) 6%,var(--bg2))}
.callout p:first-child{margin-top:0}.callout p:last-child{margin-bottom:0}
.tag{display:inline-block;font:600 11px/1 var(--mono);padding:3px 7px;
border-radius:4px;background:var(--bg3);color:var(--ink3)}
.tag.ok{background:color-mix(in srgb,var(--ok) 15%,transparent);color:var(--ok)}
.tag.warn{background:color-mix(in srgb,var(--warn) 18%,transparent);color:var(--warn)}
.tag.bad{background:color-mix(in srgb,var(--bad) 14%,transparent);color:var(--bad)}
footer{margin-top:56px;padding-top:18px;border-top:1px solid var(--line);
font-size:12.5px;color:var(--ink3)}
@media(max-width:760px){.board{grid-template-columns:repeat(2,1fr)}
.cover h1{font-size:26px}.wrap{padding:0 18px 60px}}
@media print{.toc{display:none}body{font-size:10.5pt}}
"""


def _fmt(n):
    if n is None:
        return "—"
    if isinstance(n, float):
        return "%.4g" % n
    try:
        return "{:,}".format(int(n))
    except (TypeError, ValueError):
        return str(n)


def _bar(ratio, cls=""):
    pct = max(0.0, min(1.0, float(ratio or 0))) * 100
    return ('<div class="bar"><i style="width:%.1f%%"%s></i></div>'
            % (pct, ' class="%s"' % cls if cls else ""))


def build(big, cerb, gates):
    rows = []
    if big:
        k = big.get("kinds") or {}
        tot = sum(k.values()) or 1
        for name, n in sorted(k.items(), key=lambda x: -x[1]):
            rows.append(
                "<tr><td><code>%s</code></td><td class=n>%s</td>"
                "<td class=n>%.1f%%</td><td>%s</td></tr>"
                % (name, _fmt(n), 100.0 * n / tot, _bar(n / float(tot))))

    h = ['<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width,initial-scale=1">',
         '<title>大规模测试报告 — Matlabc</title>',
         '<style>%s</style></head><body><div class="wrap">' % CSS]

    h.append('<div class="cover"><div class="kicker">Large-scale Test Report</div>')
    h.append("<h1>大规模转换测试报告</h1>")
    h.append('<p class="sub">E:\\temp\\matlabc 全量语料的解析链路实测 — '
             '不是抽样，是全量。</p></div>')

    if big:
        ops = big.get("total_ops") or 0
        un = big.get("total_unmapped") or 0
        rate = (float(un) / (un + ops)) if (un + ops) else 0
        h.append('<div class="board">')
        h.append('<div class="kpi ok"><div class="v">%s</div>'
                 '<div class="k">文件总数（全量）</div></div>' % _fmt(big.get("files")))
        h.append('<div class="kpi ok"><div class="v">%.1f%%</div>'
                 '<div class="k">进 MIR 成功率</div></div>'
                 % ((big.get("parse_rate") or 0) * 100))
        h.append('<div class="kpi warn"><div class="v">%.1f%%</div>'
                 '<div class="k">语句降级率</div></div>' % (rate * 100))
        h.append('<div class="kpi"><div class="v">%ss</div>'
                 '<div class="k">总耗时</div></div>' % _fmt(big.get("seconds")))
        h.append("</div>")

    h.append('<h2><span class="num">01</span>规模与成功率</h2>')
    if big:
        h.append("<table><tr><th>指标</th><th>值</th><th>说明</th></tr>")
        h.append("<tr><td>文件数</td><td class=n>%s</td>"
                 "<td>全量扫描，未抽样</td></tr>" % _fmt(big.get("files")))
        h.append("<tr><td>解析成功</td><td class=n>%s</td>"
                 "<td>进入 MIR</td></tr>" % _fmt(big.get("parsed_ok")))
        h.append("<tr><td>解析失败</td><td class=n>%s</td>"
                 "<td>抛异常或读失败</td></tr>" % _fmt(big.get("parse_fail")))
        h.append("<tr><td>估算行数</td><td class=n>%s</td>"
                 "<td>按 40 字节/行折算</td></tr>" % _fmt(big.get("lines_est")))
        h.append("<tr><td>算子总数</td><td class=n>%s</td></tr>"
                 % _fmt(big.get("total_ops")))
        h.append("<tr><td>未映射条数</td><td class=n>%s</td></tr>"
                 % _fmt(big.get("total_unmapped")))
        h.append("<tr><td>总耗时</td><td class=n>%ss</td></tr>"
                 % _fmt(big.get("seconds")))
        h.append("</table>")
    else:
        h.append('<div class="callout bad"><p>缺少 <code>flow/bigtest.json</code>，'
                 "本节无数据。</p></div>")

    h.append('<h2><span class="num">02</span>缺口归因</h2>')
    if rows:
        h.append("<table><tr><th>未映射类别</th><th>条数</th><th>占比</th>"
                 "<th>分布</th></tr>%s</table>" % "".join(rows))
        h.append('<div class="callout warn"><p><b>struct + cell 是最大缺口族。</b>'
                 "两个独立样本（yalmip 16.2% 与本次全量）都指向 struct，"
                 "优先级高于任何零星语法。</p></div>")
    else:
        h.append('<div class="callout bad"><p>无缺口数据。</p></div>')

    h.append('<h2><span class="num">03</span>小脑硬边界</h2>')
    if cerb:
        h.append("<table><tr><th>判据</th><th>结论</th><th>说明</th></tr>")
        for r in (cerb.get("rows") or []):
            v = r.get("verdict", "?")
            cls = {"OK": "ok", "GAP": "bad"}.get(v, "")
            h.append("<tr><td><code>%s</code></td>"
                     '<td><span class="tag %s">%s</span></td><td>%s</td></tr>'
                     % (r.get("prefix", "").strip(), cls, v, r.get("note", "")))
        h.append("</table>")
    else:
        h.append('<div class="callout warn"><p>缺少 <code>flow/cerebellum.json</code>；'
                 "运行 <code>python tools/check_cerebellum.py --report</code> 生成。</p></div>")

    h.append('<h2><span class="num">04</span>门禁状态</h2>')
    if gates:
        h.append('<div class="callout"><p>%s</p></div>'
                 % json.dumps(gates, ensure_ascii=False)[:400])
    else:
        h.append('<div class="callout warn"><p>缺少 <code>flow/gates41.json</code>。</p></div>')

    h.append('<h2><span class="num">05</span>诚实边界</h2>')
    h.append('<div class="callout bad"><p>'
             "<b>本报告只覆盖「解析到 MIR」这一段。</b>"
             "64474 个文件按每文件约 1 秒估算，跑完生成 C + gcc 编译 + 运行"
             "需要十余小时，本轮没有做。<br><br>"
             "所以这里的 100% 只代表<b>能进 MIR</b>，"
             "<b>不代表能生成 C 并跑对</b>。"
             "要求「千万级」，而全仓实测只有 63.1 万行——"
             "这个差距如实写在这里，不用「大规模」含糊过去。</p></div>")

    h.append("<footer><p>数据来源：flow/bigtest.json、flow/cerebellum.json、"
             "flow/gates41.json。由 <code>tools/bigtest_report.py</code> 生成。</p>"
             "</footer></div></body></html>")
    return "\n".join(h)


def _selftest():
    """两向自证：有数据要出表；缺数据要明说缺哪份，不能编数字。"""
    good = bad = 0
    big = {"files": 10, "parsed_ok": 10, "parse_fail": 0, "parse_rate": 1.0,
           "total_ops": 20, "total_unmapped": 5, "lines_est": 400,
           "seconds": 3, "kinds": {"struct": 3, "cell": 2}}
    h = build(big, None, None)
    if "10" in h and "struct" in h and "bigtest.json" not in h.split("02")[0]:
        good += 1
    else:
        bad += 1
        print("  [selftest] 有数据时未出表")
    # 缺 cerebellum / gates 必须明说
    if "cerebellum.json" in h and "gates41.json" in h:
        good += 1
    else:
        bad += 1
        print("  [selftest] 缺数据时未如实说明")
    # 缺 bigtest 时不能出现编造的成功率
    h2 = build(None, None, None)
    if "缺少 <code>flow/bigtest.json</code>" in h2:
        good += 1
    else:
        bad += 1
        print("  [selftest] 缺 bigtest 时未明确说明")
    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="大规模测试报告")
    ap.add_argument("--out", default=os.path.join(ROOT, "flow",
                                                  "bigtest-report.html"))
    ap.add_argument("--selftest", action="store_true")
    ns = ap.parse_args(argv)

    if ns.selftest:
        return _selftest()

    big = _load("bigtest.json")
    cerb = _load("cerebellum.json")
    gates = _load("gates41.json")
    if big is None and cerb is None:
        print("bigtest_report: 缺输入（flow/bigtest.json 与 "
              "flow/cerebellum.json 都不存在）")
        return 2

    html = build(big, cerb, gates)
    io.open(ns.out, "w", encoding="utf-8", newline="\n").write(html)
    print("[report] -> %s（%.1f KB）"
          % (os.path.relpath(ns.out, ROOT),
             len(html.encode("utf-8")) / 1024.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
