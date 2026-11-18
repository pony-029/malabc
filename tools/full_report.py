# -*- coding: utf-8 -*-
"""**总报告**：一页看完这个转换器能干什么、不能干什么。

    python tools/full_report.py --links <three_links 目录> --mir <MIR> --c2m <c2m.json>

## 七节，全部来自工具产物

| 节 | 来源 |
|---|---|
| ① 规模（全量目录） | `flow/bench_all.json` |
| ② 三段链路（M→MIR→C→反推） | three_links 的 `index.html` |
| ③ **反向链路 C→MATLAB** | `c2m --json` 的统计 |
| ④ 边界/极限用例 | 从 ② 里按 `edge_` 前缀单列 |
| ⑤ HIR 参与率 | 数 MIR 里的 `# @m2c hir-emitted` |
| ⑥ 脑状态 | `brain.brief()` |
| ⑦ 数据来源与复现命令 | 写死路径 + 命令（可照着重跑） |

一个数字都不许手填 —— 手填的数字下一轮就分不清"量过"和"记得"。

退出码：
    0 = 七节齐全
    1 = 有来源缺失（缺的那节标"未量"）
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


CSS = """
 :root{--bg:#f5f7fb;--fg:#0f172a;--mut:#64748b;--card:#fff;--bd:#e2e8f0;
        --ok:#059669;--bad:#dc2626;--warn:#d97706;--accent:#2563eb}
 @media (prefers-color-scheme:dark){:root{--bg:#0b1120;--fg:#e5e7eb;--mut:#94a3b8;
   --card:#111827;--bd:#1f2937;--ok:#34d399;--bad:#f87171;--warn:#fbbf24;--accent:#60a5fa}}
 *{box-sizing:border-box}
 body{margin:0;padding:30px 20px;background:var(--bg);color:var(--fg);
      font:14.5px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}
 .wrap{max-width:1120px;margin:0 auto}
 h1{font-size:26px;margin:0 0 6px;letter-spacing:.2px}
 .sub{color:var(--mut);font-size:12.5px;margin:0 0 8px}
 .sub code{font-size:11.5px}
 h2{font-size:15.5px;margin:28px 0 10px;padding-left:11px;border-left:3px solid var(--accent)}
 .panel{background:var(--card);border:1px solid var(--bd);border-radius:14px;
        padding:15px 18px;overflow-x:auto}
 table{width:100%;border-collapse:collapse;font-size:13px}
 th,td{padding:6px 9px;border-bottom:1px solid var(--bd);text-align:left;white-space:nowrap}
 th{color:var(--mut);font-weight:600;font-size:11.5px;letter-spacing:.02em}
 td.n{font-variant-numeric:tabular-nums;text-align:right}
 td.c{text-align:center}
 tr.sum td{font-weight:650;border-top:2px solid var(--bd);background:color-mix(in srgb,var(--accent) 6%,transparent)}
 .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:11px;margin:0 0 14px}
 .kpi{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:12px 14px}
 .kpi b{display:block;font-size:21px;font-variant-numeric:tabular-nums;line-height:1.2}
 .kpi span{color:var(--mut);font-size:11.5px}
 .ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}
 .brain{margin:4px 0;font-size:13px;background:color-mix(in srgb,var(--accent) 7%,transparent);
        border-radius:8px;padding:6px 10px}
 .note{color:var(--mut);font-size:12.5px;margin:9px 0 0}
 .miss{color:var(--bad);font-size:13px}
 .bar{display:flex;height:9px;border-radius:999px;overflow:hidden;background:var(--bd);margin:6px 0 2px}
 .bar i{display:block;height:100%}
 code{font:12px ui-monospace,Consolas,monospace;background:color-mix(in srgb,var(--fg) 6%,transparent);
      padding:1px 4px;border-radius:4px}
"""


def render(bench, links, c2m, hir, brief, src):
    now = time.strftime("%Y-%m-%d %H:%M")

    # ---- KPI ----
    n_proj = len(bench) if bench else 0
    s_m = sum((r.get("m_files") or 0) for r in bench) if bench else 0
    s_c = sum((r.get("c_files") or 0) for r in bench) if bench else 0
    s_f = sum((r.get("m_funcs") or 0) for r in bench) if bench else 0
    s_g = sum((r.get("c_funcs") or 0) for r in bench) if bench else 0
    allpass = 0
    if links:
        allpass = sum(1 for c in links
                      if "通过" in c[3] and "通过" in c[4] and "通过" in c[5])

    kpis = [
        ("%d" % n_proj, "工程（全量）"),
        ("%d" % s_m, "源 .m"),
        ("%d" % s_c, "生成 .c"),
        ("%d / %d" % (s_g, s_f), "生成 / 源函数"),
        ("%d / %d" % (allpass, len(links)) if links else "未量", "三段全通"),
        ("%.0f%%" % hir["rate"] if hir else "未量", "HIR 参与率"),
    ]
    kpi_html = "".join("<div class='kpi'><b>%s</b><span>%s</span></div>" % (v, k)
                       for v, k in kpis)

    # ---- ① 规模 ----
    if bench:
        rows = []
        for r in bench:
            ok, ct = r.get("compile_ok") or 0, r.get("compile_total") or 0
            rows.append(
                "<tr><td><code>%s</code></td><td class='n'>%s</td>"
                "<td class='n'>%s</td><td class='n'>%s / %s</td>"
                "<td class='n'>%s</td><td class='n'>%s/%s</td></tr>"
                % (r.get("name"), r.get("m_files"), r.get("c_files"),
                   r.get("c_funcs"), r.get("m_funcs"),
                   r.get("ledger_dup") or 0, ok, ct))
        sec1 = ("<table><tr><th>工程</th><th>.m</th><th>.c</th>"
                "<th>生成 / 源函数</th><th>重名丢弃</th><th>编译抽样</th></tr>"
                + "".join(rows) +
                "<tr class='sum'><td>合计</td><td class='n'>%d</td><td class='n'>%d</td>"
                "<td class='n'>%d / %d</td><td class='n'>—</td><td class='n'>—</td></tr></table>"
                "<p class='note'>「重名丢弃」是**有意的**：MATLAB 允许多目录同名函数"
                "（如 <code>@sdpvar/cos.m</code> 与 <code>cos.m</code>），C 不能重载，"
                "整份文件被跳过。它和「丢失（缺陷）」必须分开看。</p>"
                % (s_m, s_c, s_g, s_f))
    else:
        sec1 = "<p class='miss'>未量（缺 flow/bench_all.json）</p>"

    # ---- ② 三段 ----
    if links:
        s1 = sum(1 for c in links if "通过" in c[3])
        s2 = sum(1 for c in links if "通过" in c[4])
        s3 = sum(1 for c in links if "通过" in c[5])
        n = len(links)
        lr = "".join(
            "<tr><td><code>%s</code></td><td class='n'>%s</td>"
            "<td class='c %s'>%s</td><td class='c %s'>%s</td><td class='c %s'>%s</td>"
            "<td>%s</td></tr>"
            % (c[0], c[1],
               "ok" if "通过" in c[3] else "bad", c[3],
               "ok" if "通过" in c[4] else "bad", c[4],
               "ok" if "通过" in c[5] else "bad", c[5],
               (c[6] if len(c) > 6 else "")[:46])
            for c in links)
        sec2 = (
            "<div class='kpis'>"
            "<div class='kpi'><b>%d/%d</b><span>① MATLAB→MIR</span></div>"
            "<div class='kpi'><b>%d/%d</b><span>② MIR→C（编译+跑数）</span></div>"
            "<div class='kpi'><b>%d/%d</b><span>③ C→MIR 反推</span></div></div>"
            "<div class='bar'><i style='width:%.0f%%;background:var(--ok)'></i>"
            "<i style='width:%.0f%%;background:var(--warn)'></i>"
            "<i style='width:%.0f%%;background:var(--bad)'></i></div>"
            "<table><tr><th>函数</th><th>未映射</th><th>① MIR</th><th>② C</th>"
            "<th>③ 反推</th><th>说明</th></tr>%s</table>"
            "<p class='note'>① 未映射 = 0 才算过；② 要求 build 成功 + gcc 通过 + "
            "<b>真跑出数</b>；③ 要求反推 MIR 与源 MIR 的算子多重集相等。</p>"
            % (s1, n, s2, n, s3, n,
               100.0 * s1 / n, 100.0 * s2 / n, 100.0 * s3 / n, lr))
    else:
        sec2 = "<p class='miss'>未量（缺 three_links 的 index.html）</p>"

    # ---- ③ 反向 C→MATLAB ----
    if c2m:
        rows = "".join(
            "<tr><td><code>%s</code></td><td class='n'>%d</td><td class='n'>%d</td>"
            "<td class='n %s'>%d</td></tr>"
            % (f["file"], f["funcs"], f["ops"],
               "ok" if f["todo"] == 0 else "warn", f["todo"])
            for f in c2m["files"])
        t = c2m["total"]
        sec3 = (
            "<div class='kpis'>"
            "<div class='kpi'><b>%d</b><span>反推出的函数</span></div>"
            "<div class='kpi'><b>%d</b><span>还原的算子</span></div>"
            "<div class='kpi'><b>%d</b><span>未识别（TODO）</span></div>"
            "<div class='kpi'><b>%d/%d</b><span>完全往返的文件</span></div></div>"
            "<table><tr><th>C 文件</th><th>函数</th><th>op 还原</th><th>TODO</th></tr>"
            "%s</table>"
            "<p class='note'>链路：<code>C → cmir.c_to_mir → MIR → .m</code>。"
            "认不出的算子写成 <code>%% TODO(op: …)</code> <b>而不是猜</b> —— "
            "所以 <code>todo=0</code> 才有资格叫「完整往返」。</p>"
            % (t["funcs"], t["ops"], t["todo"],
               c2m["n_files"] - c2m["bad"], c2m["n_files"], rows))
    else:
        sec3 = "<p class='miss'>未量（缺 c2m 的 --json 输出）</p>"

    # ---- ④ 边界用例 ----
    if links:
        edge = [c for c in links if c[0].startswith("edge_")]
        if edge:
            rows = "".join(
                "<tr><td><code>%s</code></td><td class='c %s'>%s</td>"
                "<td class='c %s'>%s</td><td class='c %s'>%s</td></tr>"
                % (c[0],
                   "ok" if "通过" in c[3] else "bad", c[3],
                   "ok" if "通过" in c[4] else "bad", c[4],
                   "ok" if "通过" in c[5] else "bad", c[5])
                for c in edge)
            sec4 = ("<table><tr><th>用例（极限形态）</th><th>① MIR</th>"
                    "<th>② C</th><th>③ 反推</th></tr>%s</table>"
                    "<p class='note'>这些用例与「按算子表合成」的语料不同："
                    "它们分别压多函数多返回值、三层嵌套 + 提前 return、纯标量、"
                    "n=1、n=200、算子密集。<b>纯标量那一条曾整段编译失败</b>"
                    "（返回值是指针形参、算子要数组指针），正是它暴露的。</p>" % rows)
        else:
            sec4 = "<p class='miss'>three_links 结果里没有 edge_ 开头的用例</p>"
    else:
        sec4 = "<p class='miss'>未量</p>"

    # ---- ⑤ HIR ----
    if hir:
        sec5 = ("<div class='kpis'><div class='kpi'><b>%d</b><span>函数数</span></div>"
                "<div class='kpi'><b>%d</b><span>HIR 降级产出</span></div>"
                "<div class='kpi'><b>%.0f%%</b><span>参与率</span></div></div>"
                "<p class='note'>判据：MIR 里每个函数前是否有 "
                "<code># @m2c hir-emitted</code>。这是 HIR 真参与、"
                "而不是被绕过的直接证据。</p>"
                % (hir["funcs"], hir["hir"], hir["rate"]))
    else:
        sec5 = "<p class='miss'>未量（缺 MIR 路径）</p>"

    # ---- ⑥ 脑状态 ----
    sec6 = ("".join("<p class='brain'>%s</p>" % b.replace("<", "&lt;")
                    for b in brief) or "<p class='miss'>未量</p>")

    # ---- ⑦ 来源 ----
    sec7 = "<table><tr><th>本节</th><th>数据来源</th><th>复现命令</th></tr>" + "".join(
        "<tr><td>%s</td><td><code>%s</code></td><td><code>%s</code></td></tr>"
        % (a, b, c) for a, b, c in src) + "</table>"

    tpl = Template("""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MATLAB ⇄ C 总报告</title><style>$css</style></head><body><div class="wrap">
<h1>MATLAB ⇄ C 总报告</h1>
<p class="sub">生成于 $now ｜ 七个章节的全部数字均来自工具产物，无一手填</p>
<div class="kpis">$kpis</div>

<h2>① 规模：全量目录实测</h2>
<div class="panel">$sec1</div>

<h2>② 三段链路：MATLAB → MIR → C → 反推 MIR</h2>
<div class="panel">$sec2</div>

<h2>③ 反向链路：C → MATLAB</h2>
<div class="panel">$sec3</div>

<h2>④ 边界与极限用例</h2>
<div class="panel">$sec4</div>

<h2>⑤ HIR 是否真的参与</h2>
<div class="panel">$sec5</div>

<h2>⑥ 脑状态（感知 / 知识 / 成长）</h2>
<div class="panel">$sec6</div>

<h2>⑦ 数据来源与复现</h2>
<div class="panel">$sec7</div>
</div></body></html>
""")
    return tpl.substitute(css=CSS, now=now, kpis=kpi_html, sec1=sec1, sec2=sec2,
                          sec3=sec3, sec4=sec4, sec5=sec5, sec6=sec6, sec7=sec7)


def main(argv=None):
    ap = argparse.ArgumentParser(description="总报告")
    ap.add_argument("--links", help="three_links 输出目录")
    ap.add_argument("--mir", help="用于统计 HIR 参与率的 project.mir")
    ap.add_argument("--c2m", help="c2m --json 的输出")
    ap.add_argument("-o", "--out", default=os.path.join(ROOT, "flow", "full_report.html"))
    ns = ap.parse_args(argv)

    bench = _bench()
    links = _links(ns.links)
    hir = _hir(ns.mir)
    c2 = _json(ns.c2m)
    brief = _brief()
    src = [
        ("① 规模", "flow/bench_all.json", "python tools/bench_all.py --max-big 8"),
        ("② 三段链路", "%s/index.html" % (ns.links or "?"),
         "python tools/three_links_report.py <目录> -o <目录> --limit 40"),
        ("③ C→MATLAB", ns.c2m or "?", "python tools/c2m.py <C 目录> -o <目录> --json <文件>"),
        ("⑤ HIR", ns.mir or "?", "python matlabc_toc.py <目录> -o <目录>  # 看 .m2c/project.mir"),
        ("⑥ 脑状态", "flow/brain-state.json + flow/failures.json", "python tools/brain.py senses"),
    ]
    missing = [n for n, v in (("bench_all", bench), ("three_links", links),
                              ("hir", hir), ("c2m", c2)) if v is None]
    io.open(ns.out, "w", encoding="utf-8", newline="\n").write(
        render(bench, links, c2, hir, brief, src))
    size = os.path.getsize(ns.out)
    print("[full] -> %s（%.1f KB）" % (os.path.relpath(ns.out, ROOT), size / 1024.0))
    if len(missing) == 4:
        print("[full] 缺输入：四个来源都没有")
        return 2
    if missing:
        print("[full] 缺：%s（对应节标'未量'）" % "、".join(missing))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
