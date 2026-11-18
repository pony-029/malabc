# -*- coding: utf-8 -*-
"""**总报告**：一页看完这个转换器能干什么、不能干什么（含版本对比与图）。

    python tools/full_report.py --links <three_links 目录> --mir <MIR> --c2m <c2m.json>

## 与上一版的差别（R966）

1. **顶部目录导航**（8 节锚点）+ 每节标题带 KPI 徽章；
2. **图形**：规模表每行带比例条、三段/HIR/反向用 `conic-gradient` 环形图；
3. **版本对比**：每次生成都往 `flow/report-history.jsonl` 追加一行关键数字，
   页面顶部直接显示"较上次：+/-了多少" —— 这样"报告有没有变"不再是感觉问题；
4. 首页 `flow/index.html` 的入口由 `tools/report_index_link.py` 负责插入。

## 数字来源（一手不填）

| 节 | 来源 |
|---|---|
| ① 规模 | `flow/bench_all.json` |
| ② 三段链路 | three_links 的 `index.html` |
| ③ 反向 C→MATLAB | `c2m --json` |
| ④ 边界用例 | 从 ② 里按 `edge_` 前缀筛 |
| ⑤ HIR 参与率 | 数 MIR 的 `# @m2c hir-emitted` |
| ⑥ 脑状态 | `brain.brief()` |
| ⑦ 未映射类别 | `flow/unmapped.json` |
| ⑧ 数据来源 | 写死路径 + 复现命令 |

退出码：
    0 = 八节齐全
    1 = 有来源缺失（缺的节标未量）
    2 = 全部缺失
"""
import argparse
import io
import json
import os
import re
import sys
import time
from string import Template

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
HISTORY = os.path.join(ROOT, "flow", "report-history.jsonl")


def _json(p):
    if not p or not os.path.isfile(p):
        return None
    try:
        return json.load(io.open(p, encoding="utf-8"))
    except ValueError:
        return None


def _bench():
    d = _json(os.path.join(ROOT, "flow", "bench_all.json"))
    return (d or {}).get("recs") if d else None


def _links(d):
    if not d:
        return None
    p = os.path.join(d, "index.html")
    if not os.path.isfile(p):
        return None
    s = io.open(p, encoding="utf-8").read()
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", s, re.S):
        cells = [re.sub(r"<[^>]+>", "", c).strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
        if len(cells) >= 6 and cells[0] and cells[0] != "函数":
            out.append(cells[:7])
    return out or None


def _hir(mir_path):
    if not mir_path or not os.path.isfile(mir_path):
        return None
    s = io.open(mir_path, encoding="utf-8", errors="replace").read()
    funcs = len(re.findall(r"(?m)^func:", s))
    hir = len(re.findall(r"(?m)^# @m2c hir-emitted", s))
    return {"funcs": funcs, "hir": hir,
            "rate": (100.0 * hir / funcs) if funcs else 0.0}


def _brief():
    try:
        import brain
        return brain.brief(multi=True).splitlines()
    except Exception:                        # noqa: BLE001
        return []


def _metrics(bench, links, c2m, hir):
    m = {}
    if bench:
        m["proj"] = len(bench)
        m["m_files"] = sum((r.get("m_files") or 0) for r in bench)
        m["c_files"] = sum((r.get("c_files") or 0) for r in bench)
        m["m_funcs"] = sum((r.get("m_funcs") or 0) for r in bench)
        m["c_funcs"] = sum((r.get("c_funcs") or 0) for r in bench)
    if links:
        n = len(links)
        m["link_n"] = n
        m["link1"] = sum(1 for c in links if "通过" in c[3])
        m["link2"] = sum(1 for c in links if "通过" in c[4])
        m["link3"] = sum(1 for c in links if "通过" in c[5])
    if c2m:
        m["c2m_files"] = c2m.get("n_files")
        m["c2m_ops"] = (c2m.get("total") or {}).get("ops")
        m["c2m_ok"] = (c2m.get("n_files") or 0) - (c2m.get("bad") or 0)
    if hir:
        m["hir_funcs"] = hir["funcs"]
        m["hir_rate"] = round(hir["rate"], 1)
    return m


def _delta(cur):
    """与上一次生成对比，返回 {key: 差}。第一次生成返回空。"""
    if not os.path.isfile(HISTORY):
        return {}
    prev = None
    for ln in io.open(HISTORY, encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        try:
            prev = json.loads(ln)
        except ValueError:
            continue
    if not prev:
        return {}
    old = prev.get("metrics") or {}
    return {k: cur[k] - old.get(k, 0) for k in cur
            if isinstance(cur.get(k), (int, float))
            and isinstance(old.get(k), (int, float)) and cur[k] != old.get(k)}


def _remember(cur):
    io.open(HISTORY, "a", encoding="utf-8", newline="\n").write(
        json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "metrics": cur},
                   ensure_ascii=False) + "\n")


CSS = """
 :root{--bg:#f5f7fb;--fg:#0f172a;--mut:#64748b;--card:#fff;--bd:#e2e8f0;
        --ok:#059669;--bad:#dc2626;--warn:#d97706;--accent:#2563eb;--accent2:#7c3aed}
 @media (prefers-color-scheme:dark){:root{--bg:#0b1120;--fg:#e5e7eb;--mut:#94a3b8;
   --card:#111827;--bd:#1f2937;--ok:#34d399;--bad:#f87171;--warn:#fbbf24;
   --accent:#60a5fa;--accent2:#a78bfa}}
 *{box-sizing:border-box}
 html{scroll-behavior:smooth}
 body{margin:0;padding:0 0 60px;background:var(--bg);color:var(--fg);
      font:14.5px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}
 .wrap{max-width:1160px;margin:0 auto;padding:0 20px}
 header{background:var(--card);border-bottom:1px solid var(--bd);padding:26px 0 14px;margin-bottom:6px}
 h1{font-size:27px;margin:0 0 6px;letter-spacing:.2px}
 .sub{color:var(--mut);font-size:12.5px;margin:0}
 .sub b{color:var(--fg)}
 nav.toc{position:sticky;top:0;z-index:9;background:var(--card);
         border-bottom:1px solid var(--bd);padding:8px 0;margin:0 0 18px}
 nav.toc a{display:inline-block;margin:2px 10px 2px 0;padding:3px 9px;border-radius:8px;
           font-size:12.5px;color:var(--mut);text-decoration:none;
           border:1px solid var(--bd);background:var(--bg)}
 nav.toc a:hover{color:var(--accent);border-color:var(--accent)}
 h2{font-size:16px;margin:30px 0 10px;padding-left:11px;border-left:3px solid var(--accent);
    display:flex;align-items:center;gap:10px;scroll-margin-top:56px}
 h2 .badge{font:600 11.5px ui-monospace,Consolas,monospace;color:#fff;background:var(--accent);
           padding:2px 8px;border-radius:999px}
 h2 .badge.warn{background:var(--warn)} h2 .badge.bad{background:var(--bad)}
 .panel{background:var(--card);border:1px solid var(--bd);border-radius:14px;
        padding:16px 18px;overflow-x:auto}
 table{width:100%;border-collapse:collapse;font-size:13px}
 th,td{padding:6px 9px;border-bottom:1px solid var(--bd);text-align:left;white-space:nowrap}
 th{color:var(--mut);font-weight:600;font-size:11.5px}
 td.n{font-variant-numeric:tabular-nums;text-align:right}
 td.c{text-align:center}
 tr.sum td{font-weight:650;border-top:2px solid var(--bd);
           background:color-mix(in srgb,var(--accent) 6%,transparent)}
 .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(132px,1fr));gap:11px}
 .kpi{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:12px 14px}
 .kpi b{display:block;font-size:21px;font-variant-numeric:tabular-nums;line-height:1.2}
 .kpi span{color:var(--mut);font-size:11.5px}
 .kpi .d{font-size:11px;margin-top:2px}
 .ok{color:var(--ok)} .bad{color:var(--bad)} .warn{color:var(--warn)}
 .rowbar{display:flex;align-items:center;gap:8px}
 .rowbar .t{flex:1;height:7px;border-radius:999px;background:var(--bd);overflow:hidden}
 .rowbar .t i{display:block;height:100%;background:var(--accent)}
 .donuts{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;
         margin:0 0 14px}
 .donut{background:var(--card);border:1px solid var(--bd);border-radius:14px;
        padding:14px;text-align:center}
 .donut .ring{width:88px;height:88px;border-radius:50%;margin:0 auto 8px;
              display:grid;place-items:center}
 .donut .ring span{width:64px;height:64px;border-radius:50%;background:var(--card);
                   display:grid;place-items:center;font-weight:650;font-size:15px;
                   font-variant-numeric:tabular-nums}
 .donut .lb{font-size:12px;color:var(--mut)}
 .brain{margin:4px 0;font-size:13px;background:color-mix(in srgb,var(--accent2) 8%,transparent);
        border-radius:8px;padding:7px 10px}
 .note{color:var(--mut);font-size:12.5px;margin:9px 0 0}
 .miss{color:var(--bad);font-size:13px}
 code{font:12px ui-monospace,Consolas,monospace;
      background:color-mix(in srgb,var(--fg) 6%,transparent);padding:1px 4px;border-radius:4px}
 .delta{font:600 12px ui-monospace,Consolas,monospace}
"""


def _donut(pct, label, sub):
    p = max(0.0, min(100.0, pct))
    color = "var(--ok)" if p >= 90 else ("var(--warn)" if p >= 50 else "var(--bad)")
    return ("<div class='donut'><div class='ring' style='background:conic-gradient("
            "%s %.1f%%, var(--bd) 0)'><span>%.0f%%</span></div>"
            "<div class='lb'>%s<br><b>%s</b></div></div>" % (color, p, p, label, sub))


def render(bench, links, c2m, hir, brief, src, delta):
    now = time.strftime("%Y-%m-%d %H:%M")
    m = _metrics(bench, links, c2m, hir)

    # ---- KPI（带 delta）----
    def d(k, unit=""):
        v = delta.get(k)
        if not v:
            return ""
        return "<span class='d %s'>%s%d%s</span>" % (
            "ok" if v > 0 else "bad", "+" if v > 0 else "", v, unit)

    kpis = [
        ("%s" % m.get("proj", "—"), "工程（全量）", d("proj")),
        ("%s" % m.get("m_files", "—"), "源 .m", d("m_files")),
        ("%s" % m.get("c_files", "—"), "生成 .c", d("c_files")),
        ("%s / %s" % (m.get("c_funcs", "—"), m.get("m_funcs", "—")),
         "生成 / 源函数", ""),
        ("%s/%s" % (m.get("link1", "—"), m.get("link_n", "—")), "三段 ① 通过",
         d("link1")),
        ("%.0f%%" % m.get("hir_rate", 0) if hir else "—", "HIR 参与率",
         d("hir_rate", "pp")),
    ]
    kpi_html = "".join(
        "<div class='kpi'><b>%s</b><span>%s</span>%s</div>" % (v, k, dd)
        for v, k, dd in kpis)

    # ---- ① 规模 ----
    if bench:
        mx = max([(r.get("c_funcs") or 0) for r in bench] + [1])
        rows = "".join(
            "<tr><td><code>%s</code></td><td class='n'>%s</td><td class='n'>%s</td>"
            "<td class='n'>%s / %s</td><td class='n'>%s</td>"
            "<td><div class='rowbar'><div class='t'><i style='width:%.0f%%'></i></div>"
            "<span class='n'>%s</span></div></td><td class='n'>%s/%s</td></tr>"
            % (r.get("name"), r.get("m_files"), r.get("c_files"),
               r.get("c_funcs"), r.get("m_funcs"), r.get("ledger_dup") or 0,
               100.0 * (r.get("c_funcs") or 0) / mx, r.get("c_funcs"),
               r.get("compile_ok") or 0, r.get("compile_total") or 0)
            for r in bench)
        sec1 = ("<table><tr><th>工程</th><th>.m</th><th>.c</th>"
                "<th>生成 / 源函数</th><th>重名丢弃</th><th>生成函数占比</th>"
                "<th>编译抽样</th></tr>%s"
                "<tr class='sum'><td>合计</td><td class='n'>%s</td><td class='n'>%s</td>"
                "<td class='n'>%s / %s</td><td class='n'>—</td><td></td>"
                "<td class='n'>—</td></tr></table>"
                "<p class='note'>重名丢弃是<b>有意的</b>：MATLAB 允许多目录同名函数，"
                "C 不能重载，整份文件被跳过。它和「丢失（缺陷）」必须分开看。</p>"
                % (rows, m.get("m_files"), m.get("c_files"),
                   m.get("c_funcs"), m.get("m_funcs")))
    else:
        sec1 = "<p class='miss'>未量（缺 flow/bench_all.json）</p>"

    # ---- ② 三段 ----
    if links:
        n = m["link_n"]
        dons = (_donut(100.0 * m["link1"] / n, "① MATLAB→MIR", "%d/%d" % (m["link1"], n))
                + _donut(100.0 * m["link2"] / n, "② MIR→C", "%d/%d" % (m["link2"], n))
                + _donut(100.0 * m["link3"] / n, "③ C→MIR 反推", "%d/%d" % (m["link3"], n)))
        rows = "".join(
            "<tr><td><code>%s</code></td><td class='n'>%s</td>"
            "<td class='c %s'>%s</td><td class='c %s'>%s</td><td class='c %s'>%s</td>"
            "<td>%s</td></tr>"
            % (c[0], c[1],
               "ok" if "通过" in c[3] else "bad", c[3],
               "ok" if "通过" in c[4] else "bad", c[4],
               "ok" if "通过" in c[5] else "bad", c[5],
               (c[6] if len(c) > 6 else "")[:44])
            for c in links)
        sec2 = (dons + "<table><tr><th>函数</th><th>未映射</th><th>① MIR</th>"
                "<th>② C</th><th>③ 反推</th><th>说明</th></tr>%s</table>"
                "<p class='note'>① 未映射 = 0 才算过；② 要求 build + gcc + "
                "<b>真跑出数</b>；③ 要求算子多重集与源 MIR 相等。</p>" % rows)
    else:
        sec2 = "<p class='miss'>未量（缺 three_links 的 index.html）</p>"

    # ---- ③ 反向 ----
    if c2m:
        t = c2m["total"]
        okn = c2m["n_files"] - c2m["bad"]
        dons = _donut(100.0 * okn / max(1, c2m["n_files"]), "完全往返",
                      "%d/%d 文件" % (okn, c2m["n_files"]))
        dons += _donut(100.0 * t["ops"] / max(1, t["ops"] + t["todo"]),
                       "算子还原率", "%d/%d" % (t["ops"], t["ops"] + t["todo"]))
        rows = "".join(
            "<tr><td><code>%s</code></td><td class='n'>%d</td><td class='n'>%d</td>"
            "<td class='n %s'>%d</td></tr>"
            % (f["file"], f["funcs"], f["ops"],
               "ok" if f["todo"] == 0 else "warn", f["todo"])
            for f in c2m["files"])
        sec3 = (dons + "<table><tr><th>C 文件</th><th>函数</th><th>op 还原</th>"
                "<th>TODO</th></tr>%s</table>"
                "<p class='note'>链路 <code>C → cmir.c_to_mir → MIR → .m</code>；"
                "认不出的算子写成 <code>%% TODO</code> 而不是猜，"
                "所以 <code>todo=0</code> 才算完整往返。</p>" % rows)
    else:
        sec3 = "<p class='miss'>未量（缺 c2m 的 --json）</p>"

    # ---- ④ 边界 ----
    edge = [c for c in (links or []) if c[0].startswith("edge_")]
    if edge:
        rows = "".join(
            "<tr><td><code>%s</code></td><td class='c %s'>%s</td>"
            "<td class='c %s'>%s</td><td class='c %s'>%s</td></tr>"
            % (c[0], "ok" if "通过" in c[3] else "bad", c[3],
               "ok" if "通过" in c[4] else "bad", c[4],
               "ok" if "通过" in c[5] else "bad", c[5])
            for c in edge)
        sec4 = ("<table><tr><th>用例（极限形态）</th><th>① MIR</th><th>② C</th>"
                "<th>③ 反推</th></tr>%s</table>"
                "<p class='note'>分别压：多函数+多返回值、三层嵌套+提前 return、"
                "纯标量、n=1、n=200、算子密集。<b>纯标量那条曾整段编译失败</b>"
                "（返回值是指针形参而算子要数组指针），正是它暴露的。</p>" % rows)
    else:
        sec4 = "<p class='miss'>三段结果里没有 edge_ 开头的用例</p>"

    # ---- ⑤ HIR ----
    sec5 = (_donut(hir["rate"], "HIR 参与率",
                   "%d/%d 函数" % (hir["hir"], hir["funcs"]))
            + "<p class='note'>判据：MIR 里每个函数前是否有 "
            "<code># @m2c hir-emitted</code> —— HIR 真参与、而不是被绕过的证据。</p>"
            ) if hir else "<p class='miss'>未量（缺 MIR 路径）</p>"

    # ---- ⑥ 脑 ----
    sec6 = ("".join("<p class='brain'>%s</p>" % b.replace("<", "&lt;")
                    for b in brief) or "<p class='miss'>未量</p>")

    # ---- ⑦ 未映射 ----
    un = _json(os.path.join(ROOT, "flow", "unmapped.json"))
    if un and un.get("kinds"):
        base = float(un.get("total") or 1)
        rows = "".join(
            "<tr><td><code>%s</code></td><td class='n'>%d</td><td class='n'>%.0f%%</td>"
            "<td><div class='rowbar'><div class='t'>"
            "<i style='width:%.0f%%;background:var(--bad)'></i></div></div></td></tr>"
            % (k, v, 100.0 * v / base, 100.0 * v / base)
            for k, v in list(un["kinds"].items())[:10])
        sec7 = ("<div class='kpis'><div class='kpi'><b>%d</b>"
                "<span>抽样函数文件</span></div><div class='kpi'><b>%d</b>"
                "<span>未映射语句</span></div></div>"
                "<table><tr><th>类别</th><th>条数</th><th>占比</th><th></th></tr>"
                "%s</table><p class='note'>来源 <code>%s</code>。%s</p>"
                % (un.get("files") or 0, un.get("total") or 0, rows,
                   un.get("source") or "?", un.get("note") or ""))
    else:
        sec7 = "<p class='miss'>未量（缺 flow/unmapped.json）</p>"

    # ---- ⑧ 来源 ----
    sec8 = ("<table><tr><th>本节</th><th>数据来源</th><th>复现命令</th></tr>"
            + "".join("<tr><td>%s</td><td><code>%s</code></td>"
                      "<td><code>%s</code></td></tr>" % (a, b, c)
                      for a, b, c in src) + "</table>")

    dl = ", ".join("%s %+d" % (k, v) for k, v in list(delta.items())[:6]) \
        if delta else "首次生成（无可比基线）"

    tpl = Template("""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MATLAB ⇄ C 总报告</title><style>$css</style></head><body>
<header><div class="wrap">
<h1>MATLAB ⇄ C 总报告</h1>
<p class="sub">生成于 <b>$now</b> ｜ 八个章节的全部数字均来自工具产物，无一手填<br>
<span class="delta">较上次：$dl</span></p>
</div></header>
<nav class="toc"><div class="wrap">
<a href="#s1">① 规模</a><a href="#s2">② 三段链路</a><a href="#s3">③ C→MATLAB</a>
<a href="#s4">④ 边界极限</a><a href="#s5">⑤ HIR</a><a href="#s6">⑥ 脑状态</a>
<a href="#s7">⑦ 未映射</a><a href="#s8">⑧ 数据来源</a>
</div></nav>
<div class="wrap">
<div class="kpis">$kpis</div>

<h2 id="s1">① 规模：全量目录实测</h2><div class="panel">$sec1</div>
<h2 id="s2">② 三段链路：MATLAB → MIR → C → 反推 MIR</h2><div class="panel">$sec2</div>
<h2 id="s3">③ 反向链路：C → MATLAB</h2><div class="panel">$sec3</div>
<h2 id="s4">④ 边界与极限用例</h2><div class="panel">$sec4</div>
<h2 id="s5">⑤ HIR 是否真的参与</h2><div class="panel">$sec5</div>
<h2 id="s6">⑥ 脑状态（感知 / 知识 / 成长）</h2><div class="panel">$sec6</div>
<h2 id="s7">⑦ 未映射类别（真实工程的主要障碍）</h2><div class="panel">$sec7</div>
<h2 id="s8">⑧ 数据来源与复现</h2><div class="panel">$sec8</div>
</div></body></html>
""")
    return tpl.substitute(css=CSS, now=now, dl=dl, kpis=kpi_html, sec1=sec1,
                          sec2=sec2, sec3=sec3, sec4=sec4, sec5=sec5, sec6=sec6,
                          sec7=sec7, sec8=sec8)


def main(argv=None):
    ap = argparse.ArgumentParser(description="总报告")
    ap.add_argument("--links", help="three_links 输出目录")
    ap.add_argument("--mir", help="用于统计 HIR 参与率的 project.mir")
    ap.add_argument("--c2m", help="c2m --json 的输出")
    ap.add_argument("-o", "--out", default=os.path.join(ROOT, "flow", "full_report.html"))
    ap.add_argument("--no-history", action="store_true",
                    help="不往 report-history.jsonl 追加（调试用）")
    ns = ap.parse_args(argv)

    bench = _bench()
    links = _links(ns.links)
    hir = _hir(ns.mir)
    c2 = _json(ns.c2m)
    brief = _brief()
    cur = _metrics(bench, links, c2, hir)
    delta = _delta(cur)
    src = [
        ("① 规模", "flow/bench_all.json", "python tools/bench_all.py --max-big 8"),
        ("② 三段链路", "%s/index.html" % (ns.links or "?"),
         "python tools/three_links_report.py <目录> -o <目录> --limit 40"),
        ("③ C→MATLAB", ns.c2m or "?",
         "python tools/c2m.py <C 目录> -o <目录> --json <文件>"),
        ("⑤ HIR", ns.mir or "?",
         "python matlabc_toc.py <目录> -o <目录>  # 见 .m2c/project.mir"),
        ("⑥ 脑状态", "flow/brain-state.json", "python tools/brain.py senses"),
        ("⑦ 未映射", "flow/unmapped.json", "python tools/unmapped_stats.py <目录>"),
    ]
    missing = [n for n, v in (("bench_all", bench), ("three_links", links),
                              ("hir", hir), ("c2m", c2)) if v is None]
    io.open(ns.out, "w", encoding="utf-8", newline="\n").write(
        render(bench, links, c2, hir, brief, src, delta))
    if not ns.no_history:
        _remember(cur)
    print("[full] -> %s（%.1f KB）" % (os.path.relpath(ns.out, ROOT),
                                       os.path.getsize(ns.out) / 1024.0))
    print("[full] 较上次：%s" % (", ".join("%s %+d" % (k, v)
                                        for k, v in delta.items()) or "无变化/首次"))
    if len(missing) == 4:
        print("[full] 缺输入：四个来源都没有")
        return 2
    if missing:
        print("[full] 缺：%s（对应节标未量）" % "、".join(missing))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
