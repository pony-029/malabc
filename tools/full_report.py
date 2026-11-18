# -*- coding: utf-8 -*-
"""**总报告**：把全量目录实测 + 三段链路 + HIR 参与率 + 脑状态汇成一页 HTML。

    python tools/full_report.py --links <three_links 输出目录> --mir <某工程 MIR>

## 为什么单独一页

`bench_all.html` 只讲"目录级转换"，`three_links/index.html` 只讲"三段链路"，
而需要拍板的那个问题——**这个转换器现在到底能干什么、不能干什么**——
要同时看到：规模（多少工程通过）、深度（三段链路各段通过率）、
机制（HIR 是否真的参与）、健康（知识库/感知状态）。

## 数字从哪来（不接受手填）

* 规模：读 `flow/bench_all.json`（工具产出）
* 三段：**解析** three_links 的 `index.html` 表格（工具产出）
* HIR：直接数 MIR 里的 `# @m2c hir-emitted` 行（产物）
* 脑状态：`brain.brief()`（工具产出）

手填的数字下一轮就分不清"量过"和"记得"，所以这里一个都不许手填。

退出码：
    0 = 报告已生成
    1 = 有数据源缺失（报告仍生成，但缺的那块标"未量"）
    2 = 缺输入（三个来源全缺）
"""
import argparse
import io
import json
import os
import re
import sys
from string import Template

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def _bench():
    p = os.path.join(ROOT, "flow", "bench_all.json")
    if not os.path.isfile(p):
        return None
    try:
        return json.load(io.open(p, encoding="utf-8")).get("recs") or []
    except ValueError:
        return None


def _links(d):
    """解析 three_links 的 index.html 表格 → [(函数, ①, ②, ③)]。"""
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
            out.append(cells[:6])
    return out or None


def _hir(mir_path):
    """HIR 参与率：`# @m2c hir-emitted` 行数 / func 数。"""
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


def render(bench, links, hir, brief):
    # ---- 规模 ----
    rows = []
    tot_m = tot_c = tot_f = tot_g = 0
    if bench:
        for r in bench:
            tot_m += r.get("m_files") or 0
            tot_c += r.get("c_files") or 0
            tot_f += r.get("m_funcs") or 0
            tot_g += r.get("c_funcs") or 0
            ok = r.get("compile_ok") or 0
            ct = r.get("compile_total") or 0
            rows.append(
                "<tr><td><code>%s</code></td><td class='n'>%s</td>"
                "<td class='n'>%s</td><td class='n'>%s / %s</td>"
                "<td class='n'>%s</td><td class='n'>%s/%s</td></tr>"
                % (r.get("name"), r.get("m_files"), r.get("c_files"),
                   r.get("c_funcs"), r.get("m_funcs"),
                   r.get("ledger_dup") or 0, ok, ct))
    bench_html = ("<table><tr><th>工程</th><th>.m</th><th>.c</th>"
                  "<th>生成/源函数</th><th>重名丢弃</th><th>编译</th></tr>"
                  + "".join(rows) +
                  "<tr class='sum'><td>合计</td><td class='n'>%d</td>"
                  "<td class='n'>%d</td><td class='n'>%d / %d</td>"
                  "<td class='n'>—</td><td class='n'>—</td></tr></table>"
                  % (tot_m, tot_c, tot_g, tot_f)) if bench else \
                 "<p class='miss'>未量（缺 flow/bench_all.json）</p>"

    # ---- 三段链路 ----
    if links:
        s1 = sum(1 for c in links if "通过" in c[3])
        s2 = sum(1 for c in links if "通过" in c[4])
        s3 = sum(1 for c in links if "通过" in c[5])
        n = len(links)
        fails = [c for c in links if "失败" in c[5]]
        lrows = "".join(
            "<tr><td><code>%s</code></td><td class='n'>%s</td>"
            "<td class='c'>%s</td><td class='c'>%s</td><td class='c'>%s</td>"
            "<td>%s</td></tr>" % (c[0], c[1], c[3], c[4], c[5], c[6] if len(c) > 6 else "")
            for c in links)
        links_html = (
            "<div class='kpis'><div class='kpi'><b>%d/%d</b><span>① MATLAB→MIR</span></div>"
            "<div class='kpi'><b>%d/%d</b><span>② MIR→C（编译+跑数）</span></div>"
            "<div class='kpi'><b>%d/%d</b><span>③ C→MIR 反推</span></div></div>"
            "<table><tr><th>函数</th><th>未映射</th><th>① MIR</th><th>② C</th>"
            "<th>③ 反推</th><th>说明</th></tr>%s</table>"
            % (s1, n, s2, n, s3, n, lrows))
        link_note = ("③ 的失败项：%s" % ("、".join(c[0] for c in fails)
                                        if fails else "无"))
    else:
        links_html = "<p class='miss'>未量（缺 three_links 的 index.html）</p>"
        link_note = ""

    # ---- HIR ----
    if hir:
        hir_html = ("<div class='kpis'><div class='kpi'><b>%d</b><span>函数数</span></div>"
                    "<div class='kpi'><b>%d</b><span>HIR 降级产出</span></div>"
                    "<div class='kpi'><b>%.0f%%</b><span>HIR 参与率</span></div></div>"
                    "<p class='note'>判据：MIR 里每个函数前是否有 "
                    "<code># @m2c hir-emitted</code>（算子区由 HIR 降级产出）。"
                    "这是 HIR 真的参与、而不是被绕过的直接证据。</p>"
                    % (hir["funcs"], hir["hir"], hir["rate"]))
    else:
        hir_html = "<p class='miss'>未量（缺 MIR 路径）</p>"

    brief_html = "".join("<p class='brain'>%s</p>" % b.replace("<", "&lt;")
                         for b in brief) or "<p class='miss'>未量</p>"

    tpl = Template("""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MATLAB→C 总报告</title>
<style>
 :root{--bg:#f6f8fa;--fg:#1f2328;--mut:#57606a;--card:#fff;--bd:#d0d7de;--ok:#1a7f37;--bad:#cf222e}
 @media (prefers-color-scheme:dark){:root{--bg:#0d1117;--fg:#e6edf3;--mut:#8b949e;
   --card:#161b22;--bd:#30363d;--ok:#3fb950;--bad:#f85149}}
 *{box-sizing:border-box}
 body{margin:0;padding:32px 20px;background:var(--bg);color:var(--fg);
      font:14.5px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
 .wrap{max-width:1080px;margin:0 auto}
 h1{font-size:25px;margin:0 0 4px}
 .sub{color:var(--mut);margin:0 0 24px;font-size:13px}
 h2{font-size:16px;margin:26px 0 10px;padding-left:10px;border-left:3px solid var(--bd)}
 .panel{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:16px 18px}
 table{width:100%;border-collapse:collapse;font-size:13px}
 th,td{padding:7px 9px;border-bottom:1px solid var(--bd);text-align:left}
 th{color:var(--mut);font-weight:600;font-size:12px}
 td.n{font-variant-numeric:tabular-nums;text-align:right}
 td.c{text-align:center}
 tr.sum td{font-weight:650;border-top:2px solid var(--bd)}
 .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
       gap:12px;margin:0 0 14px}
 .kpi{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:13px 15px}
 .kpi b{display:block;font-size:22px;font-variant-numeric:tabular-nums}
 .kpi span{color:var(--mut);font-size:12px}
 .brain{margin:3px 0;font-size:13px;background:rgba(110,64,201,.07);
        border-radius:8px;padding:6px 10px}
 .note{color:var(--mut);font-size:12.5px;margin:8px 0 0}
 .miss{color:var(--bad);font-size:13px}
 code{font:12px ui-monospace,Consolas,monospace}
</style></head><body><div class="wrap">
<h1>MATLAB → C 总报告</h1>
<p class="sub">规模 · 三段链路 · HIR 参与 · 脑状态 —— 数字全部由工具产出，无一手填</p>

<h2>一、规模（全量目录实测）</h2>
<div class="panel">$bench</div>

<h2>二、三段链路（MATLAB→MIR→C→反推 MIR）</h2>
<div class="panel">$links$note</div>

<h2>三、HIR 是否真的参与</h2>
<div class="panel">$hir</div>

<h2>四、脑状态</h2>
<div class="panel">$brief</div>
</div></body></html>
""")
    return tpl.substitute(bench=bench_html, links=links_html,
                          note=("<p class='note'>%s</p>" % link_note) if link_note else "",
                          hir=hir_html, brief=brief_html)


def main(argv=None):
    ap = argparse.ArgumentParser(description="总报告")
    ap.add_argument("--links", help="three_links 输出目录")
    ap.add_argument("--mir", help="用于统计 HIR 参与率的 project.mir")
    ap.add_argument("-o", "--out", default=os.path.join(ROOT, "flow", "full_report.html"))
    ns = ap.parse_args(argv)

    bench, links, hir, brief = _bench(), _links(ns.links), _hir(ns.mir), _brief()
    missing = [name for name, v in (("bench_all.json", bench),
                                    ("three_links", links),
                                    ("mir", hir)) if v is None]
    io.open(ns.out, "w", encoding="utf-8", newline="\n").write(
        render(bench, links, hir, brief))
    print("[full] -> %s" % os.path.relpath(ns.out, ROOT))
    if len(missing) == 3:
        print("[full] 缺输入：三个来源都没有")
        return 2
    if missing:
        print("[full] 缺：%s（对应块标'未量'）" % "、".join(missing))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
