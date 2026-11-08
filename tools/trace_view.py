# -*- coding: utf-8 -*-
"""把 `trace.jsonl` 渲染成一个可读的静态页（无脚本、无外链、双主题）。

## 为什么用静态 HTML 而不是交互页

追踪是**证据**，不是仪表盘。证据要能贴进 issue、能存进仓库、能在十年后打开 ——
所以不依赖任何脚本与网络。
"""
import argparse
import html
import io
import json
import os
import sys

CSS = """
:root{--bg:#0f1115;--card:#171a21;--fg:#e6e9ef;--dim:#9aa4b2;--ok:#37d67a;
--fail:#ff5c5c;--skip:#8b93a1;--line:#252a33;--ctl:#5b9dff;--dat:#f5a524}
@media(prefers-color-scheme:light){:root{--bg:#f6f7f9;--card:#fff;--fg:#1b1f24;
--dim:#5b636e;--line:#e3e6ea}}
*{box-sizing:border-box}
body{margin:0;padding:30px;background:var(--bg);color:var(--fg);
font:14px/1.6 -apple-system,"Segoe UI","Noto Sans SC",sans-serif}
h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--dim);margin-bottom:20px}
table{width:100%;border-collapse:collapse;background:var(--card);
border:1px solid var(--line);border-radius:12px;overflow:hidden}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--line);
font-size:13px;vertical-align:top}
th{color:var(--dim);font-size:12px;font-weight:600}
tr:last-child td{border-bottom:none}
.mono{font-family:ui-monospace,Consolas,monospace}
.b{display:inline-block;padding:1px 7px;border-radius:999px;font-size:11px;font-weight:600}
.ok{background:rgba(55,214,122,.15);color:var(--ok)}
.fail{background:rgba(255,92,92,.15);color:var(--fail)}
.skip{background:rgba(139,147,161,.18);color:var(--skip)}
.ctl{color:var(--ctl)}.dat{color:var(--dat)}
.note{margin-top:16px;color:var(--dim);font-size:13px}
"""


def render(rows, title, src):
    ok = sum(1 for r in rows if r.get("status") == "ok")
    bad = [r for r in rows if r.get("status") == "fail"]
    trs = []
    for r in rows:
        kind = r.get("kind", "")
        cls = "ctl" if kind == "control" else "dat"
        label = "控" if kind == "control" else "数"
        detail = r.get("detail") or {}
        ds = " · ".join("%s=%s" % (k, v) for k, v in list(detail.items())[:4])
        trs.append(
            '<tr><td class="mono">%s</td><td class="mono">%s</td>'
            '<td><span class="%s">%s</span></td><td>%s</td>'
            '<td class="mono">%s → %s</td><td class="mono">%s</td>'
            '<td><span class="b %s">%s</span></td><td class="mono">%d ms</td>'
            '<td class="mono" style="color:var(--dim)">%s</td></tr>'
            % (html.escape(r.get("step", "")), html.escape(r.get("module", "")),
               cls, label, html.escape(r.get("action", "")),
               html.escape(str(r.get("in", ""))), html.escape(str(r.get("out", ""))),
               html.escape(ds[:70]),
               r.get("status", ""), html.escape(r.get("status", "")),
               int(r.get("ms", 0)), html.escape(ds[:80])))

    return """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>链路追踪 · %s</title><style>%s</style></head><body>
<h1>链路追踪：%s</h1>
<div class="sub">共 <b>%d</b> 步 ｜ 通过 <b>%d</b> ｜ 失败 <b>%d</b> ｜ 来源 <span class="mono">%s</span></div>
<table><tr><th>步</th><th>模块</th><th>类型</th><th>动作</th><th>输入 → 输出（摘要）</th>
<th>细节</th><th>状态</th><th>耗时</th><th>values</th></tr>%s</table>
<div class="note">
摘要 = 内容的 sha256 前 12 位。它让「这一步入的是哪一份数据」变成可核对的事实，
而不是「我记得我传的是那个文件」。<br>
类型：<span class="ctl">控</span> = 控制流（谁触发谁）｜
<span class="dat">数</span> = 数据流（传的是什么）。
</div>
</body></html>""" % (html.escape(title), CSS, html.escape(title),
                     len(rows), ok, len(bad), html.escape(src), "\n".join(trs))


def main():
    ap = argparse.ArgumentParser(description="trace.jsonl → 静态 HTML")
    ap.add_argument("jsonl")
    ap.add_argument("-o", "--out", default=None)
    a = ap.parse_args()
    rows = [json.loads(l) for l in io.open(a.jsonl, encoding="utf-8") if l.strip()]
    title = os.path.splitext(os.path.basename(a.jsonl))[0]
    out = a.out or (os.path.splitext(a.jsonl)[0] + ".html")
    io.open(out, "w", encoding="utf-8", newline="\n").write(render(rows, title, a.jsonl))
    print("已写出 %s（%d 步）" % (out, len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
