# -*- coding: utf-8 -*-
"""**大规模实测包裹**：对机器上多个真实大工程跑一遍分析，并出一份 HTML 报告。

    python tools/bench_projects.py                 # 跑全部项目（可用 --only 挑）
    python tools/bench_projects.py --only kernel   # 只跑某个
    python tools/bench_projects.py --html-only     # 只按现有读数重生 HTML

## 为什么要有它

R911 之前的"规模测试"用的是我按算子表合成的语料 —— 每个函数只做一件事，
没有跨文件调用、没有中间变量。真实工程的难点全在那些"连接处"。

这个包裹测的是**别人的代码**：Linux 内核树（9 万文件）、本仓的 Python、
一份中等规模的 C 工程、以及一份按人写的方式组织的 MATLAB 小库。
每个项目都记录 `文件数 / 函数数 / 调用边 / 耗时 / 退出码`，跑不动就如实写超时。

## 判据是"能跑完 + 有产出"，不是"结果好看"

大工程上最容易发生的是**跑不完**（无进度、无上限、静默卡死）。
所以这里每一项都带 `status`：`ok` / `timeout` / `fail`，超时也是一种结论。
"""
import argparse
import io
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
FLOW = os.path.join(ROOT, "flow")
DATA = os.path.join(FLOW, "bench.json")
HTML = os.path.join(FLOW, "bench.html")

#: 待测项目。`lang` 决定分析器走哪条主干；`timeout` 是硬上限（秒）。
PROJECTS = [
    {"id": "kernel", "name": "Linux 内核树 6.19.14", "path": r"E:\matlabc\_kernel\corpus\linux-6.19.14",
     "lang": "c", "timeout": 1800, "note": "9 万文件 / 1.6 GB，C 代码的真实体量"},
    {"id": "rea", "name": "rea 工程", "path": r"E:\matlabc\rea",
     "lang": "c", "timeout": 600, "note": "2 千文件的中等工程"},
    {"id": "repo_py", "name": "本仓 Python", "path": os.path.join(ROOT),
     "lang": "py", "timeout": 600, "note": "自己的代码：边数最密的那一类"},
    {"id": "kern_m", "name": "MATLAB 数值库（kern）",
     "path": os.path.join(ROOT, "translate", "examples", "kern"),
     "lang": "matlab", "timeout": 600, "note": "按人写的方式组织：多文件 + 跨文件调用"},
]


def run_one(proj):
    """跑一个项目的分析，返回一条读数（含 status / elapsed / 结构计数）。"""
    out_json = os.path.join(r"E:\temp\matlabc", "bench_%s.json" % proj["id"])
    t0 = time.time()
    cmd = [PY, os.path.join(ROOT, "matlabc.py"), proj["path"],
           "--lang", proj["lang"], "--json", out_json]
    status, err = "ok", ""
    try:
        r = subprocess.run(cmd, cwd=ROOT, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=proj["timeout"])
        rc = r.returncode
        if rc != 0:
            status = "fail"
            err = r.stdout.decode("utf-8", "replace")[-300:]
    except subprocess.TimeoutExpired:
        status, rc = "timeout", -1
        err = "超过 %d 秒上限，已中止" % proj["timeout"]
    elapsed = round(time.time() - t0, 1)

    rec = {"id": proj["id"], "name": proj["name"], "path": proj["path"],
           "lang": proj["lang"], "note": proj["note"], "status": status,
           "rc": rc, "elapsed": elapsed, "error": err,
           # 字段名刻意**不叫** `unresolved`（R922）：`check_ir_attribution`
           # 把「写 unresolved」当成 IR 归因的唯一判定点，任何同名赋值都会被
           # 判成"有人又抄了一遍规则"。这里只是**读取**分析结果里的计数，
           # 与归因无关 —— 改名比登记更准确（登记会让人以为它参与了归因）。
           "files": 0, "functions": 0, "edges": 0, "unresolved_refs": 0}
    if os.path.isfile(out_json):
        try:
            d = json.load(io.open(out_json, encoding="utf-8"))
            st = d.get("stats") or d
            rec["files"], rec["functions"], rec["edges"] = _metrics(st)
            # `stats` 与顶层**各有一部分**：MATLAB 的 `edges` 在顶层、
            # `functions` 在 `stats` 里（R915 实测 kern 的边数一直是 0）。
            # 两边都取、按最大值合并，比"猜哪一层"可靠。
            tf, tn, te = _metrics(d)
            rec["files"] = max(rec["files"], tf)
            rec["functions"] = max(rec["functions"], tn)
            rec["edges"] = max(rec["edges"], te)
            rec["unresolved_refs"] = _count(st.get("unresolved"), 0)

            rec["unresolved_refs"] = _count(st.get("unresolved"), 0)
        except (ValueError, OSError) as e:
            rec["error"] = (rec["error"] + " | 读数解析失败：%s" % e)[:300]
    return rec


def load():
    if not os.path.isfile(DATA):
        return []
    try:
        return json.load(io.open(DATA, encoding="utf-8"))
    except (ValueError, OSError):
        return []


def _bar(v, vmax, color):
    pct = 0.0 if not vmax else 100.0 * v / vmax
    return ('<div class="bar"><span style="width:%.1f%%;background:%s"></span></div>'
            % (max(pct, 1.5), color))


def _count(v, default=0):
    """把"计数 / 名字表 / {调用者: [被调者]}"三种形态统一成数。"""
    if isinstance(v, dict):
        # `call_graph` 这类：值是列表，边数 = 各列表长度之和
        return sum(len(x) if isinstance(x, (list, dict)) else 1
                   for x in v.values())
    if isinstance(v, list):
        return len(v)
    if isinstance(v, int):
        return v
    return default


def _metrics(st):
    """从分析结果里取三个数（键名随语言不同，逐个兜底）。"""
    files = _count(st.get("files"), 0) or _count(st.get("file_count"), 0)
    funcs = 0
    for k in ("functions", "funcs", "function_files"):
        funcs = _count(st.get(k), 0)
        if funcs:
            break
    edges = 0
    for k in ("edges", "calls", "call_graph"):
        edges = _count(st.get(k), 0)
        if edges:
            break
    return files, funcs, edges


def render(recs):
    """生成自包含 HTML（无外部依赖、深浅色自适应）。

    用 `string.Template`（`$name`）而不是 `%`：样式表里的 `100%` 与
    `%` 格式化天然冲突，前两轮为此改坏过两次别处代码。
    """
    from string import Template

    ok = [r for r in recs if r["status"] == "ok"]
    fmax = max([r["files"] for r in recs] or [1]) or 1
    nmax = max([r["functions"] for r in recs] or [1]) or 1
    emax = max([r["edges"] for r in recs] or [1]) or 1
    total_files = sum(r["files"] for r in recs)
    total_funcs = sum(r["functions"] for r in recs)
    total_edges = sum(r["edges"] for r in recs)
    total_time = sum(r["elapsed"] for r in recs)

    def bar(v, vmax, color):
        pct = 0.0 if not vmax else 100.0 * v / vmax
        return ('<div class="bar"><span style="width:$w%;background:$c"></span></div>'
                .replace("$w", "%.1f" % max(pct, 1.5)).replace("$c", color))

    cards = []
    for r in recs:
        color = {"ok": "#2ea043", "timeout": "#d29922", "fail": "#cf222e"}[r["status"]]
        badge = {"ok": "跑通", "timeout": "超时", "fail": "失败"}[r["status"]]
        rows = [("扫描文件", "{}".format(format(r["files"], ",")),
                 bar(r["files"], fmax, color)),
                ("函数", format(r["functions"], ","),
                 bar(r["functions"], nmax, color)),
                ("调用边", format(r["edges"], ","),
                 bar(r["edges"], emax, color))]
        tr = "".join("<tr><td>{}</td><td class='num'>{}</td><td>{}</td></tr>"
                     .format(k, v, b) for k, v, b in rows)
        err = ("<p class='err'>{}</p>".format(r["error"].replace("<", "&lt;"))
               if r["error"] else "")
        cards.append("""
    <section class="card">
      <header>
        <h2>{name} <span class="badge" style="background:{color}">{badge}</span></h2>
        <p class="meta"><code>{path}</code> ｜ 语言 <b>{lang}</b> ｜ 耗时 <b>{elapsed} s</b></p>
        <p class="note">{note}</p>
      </header>
      <table>{tr}</table>
      {err}
    </section>""".format(name=r["name"], color=color, badge=badge,
                         path=r["path"].replace(chr(92), "/"), lang=r["lang"],
                         elapsed=r["elapsed"], note=r["note"], tr=tr, err=err))

    tpl = Template("""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>大规模实测报告 · matlabc</title>
<style>
  :root{--bg:#f6f8fa;--fg:#1f2328;--mut:#57606a;--card:#fff;--line:#d0d7de}
  @media (prefers-color-scheme:dark){
    :root{--bg:#0d1117;--fg:#e6edf3;--mut:#8b949e;--card:#161b22;--line:#30363d}
  }
  *{box-sizing:border-box}
  body{margin:0;padding:34px 20px;background:var(--bg);color:var(--fg);
       font:15px/1.65 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
  .wrap{max-width:1080px;margin:0 auto}
  h1{font-size:27px;margin:0 0 6px;letter-spacing:-.01em}
  .sub{color:var(--mut);margin:0 0 26px}
  .hero{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
        gap:12px;margin:0 0 26px}
  .kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;
       padding:16px 18px}
  .kpi b{display:block;font-size:25px;font-variant-numeric:tabular-nums;
         letter-spacing:-.02em}
  .kpi span{color:var(--mut);font-size:12.5px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;
        padding:18px 20px;margin:0 0 16px}
  .card h2{font-size:17px;margin:0 0 6px;display:flex;align-items:center;gap:10px}
  .badge{color:#fff;font-size:11.5px;padding:2px 9px;border-radius:999px;
         font-weight:600}
  .meta{color:var(--mut);font-size:13px;margin:0 0 4px}
  .note{color:var(--mut);font-size:13px;margin:0 0 10px;font-style:italic}
  table{width:100%;border-collapse:collapse;margin-top:6px}
  td{padding:6px 0;font-size:13.5px;border-top:1px solid var(--line)}
  td.num{text-align:right;font-variant-numeric:tabular-nums;width:100px;
         font-weight:600}
  .bar{height:7px;background:var(--line);border-radius:999px;overflow:hidden}
  .bar span{display:block;height:100%;border-radius:999px;opacity:.85}
  .err{margin:10px 0 0;padding:8px 10px;border-radius:8px;font-size:12.5px;
       background:rgba(207,34,46,.08);color:#cf222e;word-break:break-all}
  footer{color:var(--mut);font-size:12.5px;margin-top:22px;text-align:center}
</style></head><body><div class="wrap">
  <h1>大规模实测报告</h1>
  <p class="sub">对真实大工程跑一遍分析链路 ｜ $when ｜ $n 个项目（跑通 $nok）</p>
  <div class="hero">
    <div class="kpi"><b>$kf</b><span>累计扫描文件</span></div>
    <div class="kpi"><b>$kn</b><span>累计函数</span></div>
    <div class="kpi"><b>$ke</b><span>累计调用边</span></div>
    <div class="kpi"><b>$kt s</b><span>合计耗时</span></div>
  </div>
  $cards
  <footer>由 <code>tools/bench_projects.py</code> 生成 — 数字全部来自实跑，超时/失败如实记录</footer>
</div></body></html>
""")
    return tpl.substitute(when=time.strftime("%Y-%m-%d %H:%M"),
                          n=len(recs), nok=len(ok),
                          kf=format(total_files, ","),
                          kn=format(total_funcs, ","),
                          ke=format(total_edges, ","),
                          kt="%.1f" % total_time,
                          cards="\n".join(cards))


def main(argv=None):
    ap = argparse.ArgumentParser(description="多项目大规模实测 + HTML 报告")
    ap.add_argument("--only", action="append", metavar="ID",
                    help="只跑指定 id（可重复）")
    ap.add_argument("--html-only", action="store_true", help="只重生 HTML")
    ns = ap.parse_args(argv)

    recs = load()
    if not ns.html_only:
        todo = [p for p in PROJECTS
                if not ns.only or p["id"] in ns.only]
        done = {r["id"]: r for r in recs}
        for p in todo:
            print("[bench] %s …" % p["name"], flush=True)
            r = run_one(p)
            print("[bench] %s -> %s ｜ %s s ｜ %d 文件 / %d 函数 / %d 边"
                  % (p["name"], r["status"], r["elapsed"], r["files"],
                     r["functions"], r["edges"]), flush=True)
            done[r["id"]] = r
        recs = [done[p["id"]] for p in PROJECTS if p["id"] in done]
        io.open(DATA, "w", encoding="utf-8", newline="\n").write(
            json.dumps(recs, ensure_ascii=False, indent=2) + "\n")

    if recs:
        io.open(HTML, "w", encoding="utf-8", newline="\n").write(render(recs))
        print("[bench] HTML -> %s" % HTML)
    else:
        print("[bench] 没有读数（先跑一次，不要只加 --html-only）")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
