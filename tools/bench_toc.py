# -*- coding: utf-8 -*-
"""**MATLAB→C 转换实测包裹**：对多个 .m 工程跑一遍主线，量四个数并出 HTML。

    python tools/bench_toc.py                  # 跑全部工程
    python tools/bench_toc.py --only yalmip    # 只跑一个
    python tools/bench_toc.py --html-only      # 只按现有读数重生 HTML

## 量的四个数

1. **转换**：`--to-c` 是否跑完（大工程上最容易发生的是"跑到一半中止"）
2. **完全实现**：生成的 `.c` 里**不含** `MLC_UNIMPLEMENTED` 的比例
   —— 编译通过率回答不了这个：残缺的函数体仍是合法 C
3. **编译**：gcc `-c` 逐个编
4. **耗时**

## 为什么失败也要记

真实工程第一个文件就可能报错，而"整棵树中止"和"跳过它继续"是两种产品行为。
这个包裹**记录失败原因**而不是只留一个红叉 —— 理由写得出来，下一轮才有得修。
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
TOC = os.path.join(ROOT, "matlabc_toc.py")
FLOW = os.path.join(ROOT, "flow")
DATA = os.path.join(FLOW, "toc_bench.json")
HTML = os.path.join(FLOW, "toc_bench.html")
OUTBASE = r"E:\temp\matlabc\_toc_bench"

PROJECTS = [
    {"id": "yalmip", "name": "YALMIP（真实 MATLAB 工程）",
     "path": r"E:\temp\matlabc\yalmip", "timeout": 1800,
     "note": "1682 个 .m：优化建模工具箱，跨文件调用最密的一类"},
    {"id": "scale_m", "name": "规模语料 scale_m",
     "path": r"E:\temp\matlabc\scale_m", "timeout": 900,
     "note": "169 个函数：55 算子 × 3 体量 + 4 控制流"},
    {"id": "annot3", "name": "annot3", "path": r"E:\temp\matlabc\annot3",
     "timeout": 900, "note": "93 个 .m 的中等工程"},
    {"id": "kern", "name": "kern 数值库（真实风格）",
     "path": os.path.join(ROOT, "translate", "examples", "kern"),
     "timeout": 300, "note": "10 个文件：多文件 + 跨文件调用，按人写的方式组织"},
]


def _mfiles(path):
    n = 0
    for base, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        n += sum(1 for f in files if f.endswith(".m"))
    return n


def _cstats(gen):
    """(生成的 .c 数, 完全实现数) —— 完全实现 = 文件里没有 MLC_UNIMPLEMENTED。"""
    src = os.path.join(gen, "src", "gen")
    if not os.path.isdir(src):
        return 0, 0
    files = [f for f in os.listdir(src) if f.endswith(".c")]
    good = 0
    for f in files:
        s = io.open(os.path.join(src, f), encoding="utf-8", errors="replace").read()
        if "MLC_UNIMPLEMENTED" not in s:
            good += 1
    return len(files), good


def _compile(gen, limit=0):
    """逐个 gcc -c；返回 (通过, 总数, 首个错误)。大工程用 limit 截断。"""
    src = os.path.join(gen, "src", "gen")
    if not os.path.isdir(src):
        return 0, 0, ""
    files = sorted(f for f in os.listdir(src) if f.endswith(".c"))
    if limit:
        files = files[:limit]
    ok, first_err = 0, ""
    for f in files:
        r = subprocess.run(["gcc", "-std=c99", "-c", "-o", os.devnull,
                            os.path.join(src, f),
                            "-I", os.path.join(gen, "include"),
                            "-I", os.path.join(ROOT, "c_runtime", "include")],
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=120)
        if r.returncode == 0:
            ok += 1
        elif not first_err:
            for ln in r.stdout.decode("utf-8", "replace").splitlines():
                if "error" in ln:
                    first_err = ln.strip()[:160]
                    break
    return ok, len(files), first_err


def run_one(proj):
    out = os.path.join(OUTBASE, proj["id"])
    t0 = time.time()
    status, err = "ok", ""
    cmd = [PY, TOC, proj["path"], "-o", out]
    try:
        r = subprocess.run(cmd, cwd=ROOT, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=proj["timeout"])
        if r.returncode != 0:
            status = "fail"
            txt = r.stdout.decode("utf-8", "replace")
            for ln in txt.splitlines():
                if any(k in ln for k in ("不合法", "失败", "Traceback", "error")):
                    err = ln.strip()[:200]
                    break
            if not err:
                err = txt.strip().splitlines()[-1][:200] if txt.strip() else ""
    except subprocess.TimeoutExpired:
        status, err = "timeout", "超过 %d 秒上限" % proj["timeout"]
    elapsed = round(time.time() - t0, 1)

    gen = os.path.join(out, "build", "gen")
    nc, good = _cstats(gen)
    cok, ctotal, cerr = _compile(gen, limit=60) if nc else (0, 0, "")
    return {"id": proj["id"], "name": proj["name"], "path": proj["path"],
            "note": proj["note"], "status": status, "error": err,
            "elapsed": elapsed, "mfiles": _mfiles(proj["path"]),
            "cfiles": nc, "full": good, "compile_ok": cok,
            "compile_total": ctotal, "compile_err": cerr}


def load():
    if not os.path.isfile(DATA):
        return []
    try:
        return json.load(io.open(DATA, encoding="utf-8"))
    except (ValueError, OSError):
        return []


def render(recs):
    from string import Template

    okr = [r for r in recs if r["status"] == "ok"]
    tot_m = sum(r["mfiles"] for r in recs)
    tot_c = sum(r["cfiles"] for r in recs)
    tot_f = sum(r["full"] for r in recs)
    rate = 100.0 * tot_f / tot_c if tot_c else 0.0

    cards = []
    for r in recs:
        color = {"ok": "#2ea043", "timeout": "#d29922", "fail": "#cf222e"}[r["status"]]
        badge = {"ok": "转换成功", "timeout": "超时", "fail": "转换失败"}[r["status"]]
        full_pct = 100.0 * r["full"] / r["cfiles"] if r["cfiles"] else 0.0
        wide = 0.0 if not tot_c else 100.0 * r["cfiles"] / tot_c
        rows = [
            ("源 .m 文件", format(r["mfiles"], ","), "%.1f" % (100.0 * r["mfiles"] / tot_m if tot_m else 0)),
            ("生成 .c", format(r["cfiles"], ","), "%.1f" % wide),
            ("完全实现", "%s（%.1f%%）" % (format(r["full"], ","), full_pct),
             "%.1f" % full_pct),
        ]
        if r["compile_total"]:
            cw = 100.0 * r["compile_ok"] / r["compile_total"]
            rows.append(("抽样编译（前 %d 个）" % r["compile_total"],
                         "%d / %d" % (r["compile_ok"], r["compile_total"]),
                         "%.1f" % cw))
        tr = "".join(
            "<tr><td>{}</td><td class='num'>{}</td>"
            "<td><div class='bar'><span style='width:{}%;background:{}'></span></div></td></tr>"
            .format(k, v, max(float(p), 1.2), color) for k, v, p in rows)
        err = ""
        if r["error"]:
            err = "<p class='err'>{}</p>".format(r["error"].replace("<", "&lt;"))
        if r["compile_err"]:
            err += "<p class='err'>编译：{}</p>".format(
                r["compile_err"].replace("<", "&lt;"))
        cards.append("""
    <section class="card">
      <header>
        <h2>{name} <span class="badge" style="background:{color}">{badge}</span></h2>
        <p class="meta"><code>{path}</code> ｜ 耗时 <b>{elapsed} s</b></p>
        <p class="note">{note}</p>
      </header>
      <table>{tr}</table>
      {err}
    </section>""".format(name=r["name"], color=color, badge=badge,
                         path=r["path"].replace(chr(92), "/"),
                         elapsed=r["elapsed"], note=r["note"], tr=tr, err=err))

    tpl = Template("""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MATLAB → C 转换实测 · matlabc</title>
<style>
  :root{--bg:#f6f8fa;--fg:#1f2328;--mut:#57606a;--card:#fff;--line:#d0d7de}
  @media (prefers-color-scheme:dark){
    :root{--bg:#0d1117;--fg:#e6edf3;--mut:#8b949e;--card:#161b22;--line:#30363d}
  }
  *{box-sizing:border-box}
  body{margin:0;padding:34px 20px;background:var(--bg);color:var(--fg);
       font:15px/1.65 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
  .wrap{max-width:1060px;margin:0 auto}
  h1{font-size:27px;margin:0 0 6px;letter-spacing:-.01em}
  .sub{color:var(--mut);margin:0 0 24px}
  .hero{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));
        gap:12px;margin:0 0 24px}
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
  td.num{text-align:right;font-variant-numeric:tabular-nums;width:130px;
         font-weight:600}
  .bar{height:7px;background:var(--line);border-radius:999px;overflow:hidden}
  .bar span{display:block;height:100%;border-radius:999px;opacity:.85}
  .err{margin:10px 0 0;padding:8px 10px;border-radius:8px;font-size:12.5px;
       background:rgba(207,34,46,.08);color:#cf222e;word-break:break-all}
  footer{color:var(--mut);font-size:12.5px;margin-top:22px;text-align:center}
</style></head><body><div class="wrap">
  <h1>MATLAB → C 转换实测</h1>
  <p class="sub">对多个 .m 工程跑主线 <code>matlabc_toc.py</code> ｜ $when ｜ $n 个工程（成功 $nok）</p>
  <div class="hero">
    <div class="kpi"><b>$km</b><span>源 .m 文件</span></div>
    <div class="kpi"><b>$kc</b><span>生成 .c</span></div>
    <div class="kpi"><b>$kr%</b><span>完全实现率</span></div>
    <div class="kpi"><b>$kt s</b><span>合计耗时</span></div>
  </div>
  $cards
  <footer>由 <code>tools/bench_toc.py</code> 生成 — 数字全部来自实跑；失败与超时如实记录，并写明原因</footer>
</div></body></html>
""")
    return tpl.substitute(when=time.strftime("%Y-%m-%d %H:%M"), n=len(recs),
                          nok=len(okr), km=format(tot_m, ","),
                          kc=format(tot_c, ","), kr="%.1f" % rate,
                          kt="%.1f" % sum(r["elapsed"] for r in recs),
                          cards="\n".join(cards))


def main(argv=None):
    ap = argparse.ArgumentParser(description="MATLAB→C 多工程实测 + HTML")
    ap.add_argument("--only", action="append", metavar="ID")
    ap.add_argument("--html-only", action="store_true")
    ns = ap.parse_args(argv)

    recs = load()
    if not ns.html_only:
        done = {r["id"]: r for r in recs}
        for p in PROJECTS:
            if ns.only and p["id"] not in ns.only:
                continue
            print("[toc] %s …" % p["name"], flush=True)
            r = run_one(p)
            print("[toc] %s -> %s ｜ %s s ｜ .m %d -> .c %d ｜ 完全实现 %d"
                  % (p["name"], r["status"], r["elapsed"], r["mfiles"],
                     r["cfiles"], r["full"]), flush=True)
            done[r["id"]] = r
        recs = [done[p["id"]] for p in PROJECTS if p["id"] in done]
        io.open(DATA, "w", encoding="utf-8", newline="\n").write(
            json.dumps(recs, ensure_ascii=False, indent=2) + "\n")

    if not recs:
        print("[toc] 没有读数")
        return 2
    io.open(HTML, "w", encoding="utf-8", newline="\n").write(render(recs))
    print("[toc] HTML -> %s" % HTML)
    return 0


if __name__ == "__main__":
    sys.exit(main())
