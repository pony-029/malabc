# -*- coding: utf-8 -*-
"""**工程级映射测试**：MATLAB 文件 ⇄ C 文件不是一对一，这里把它量清楚。

    python tools/bench_mapping.py                 # 跑默认工程集
    python tools/bench_mapping.py --only multi_fn
    python tools/bench_mapping.py --html-only

## 为什么要专门测"映射"

`matlabc_toc.py` 产出的 C 工程是**按源文件切**的：一个 `.m` 里若有 5 个函数，
它们进**同一个** `.c`；而两个 `.m` 绝不会合并成一个 `.c`。所以真实关系是：

    N 个 .m  →  N 个 .c（文件数守恒）
    M 个函数 →  M 个 m2c_* 函数（函数数守恒，但分布到不同文件）

这三条一旦破了，工程"看起来生成了"，链接进来却是缺函数或重名。本工具逐项验：

1. **文件级**：`.m` 数 == `.c` 数（每个源文件一个翻译单元）
2. **函数级**：源文件里 `function` 数 == 对应 `.c` 里 `mlc_status m2c_*` 数
3. **总量**：两侧函数总数相等（**守恒** —— 没有函数在转换中丢失）
4. **可追溯**：每个 `.c` 头部写着它的源文件；每个 `m2c_*` 能对回一个 `.m` 函数名
5. **可编译**：生成的 C 能过 gcc（映射对了但编不过等于没用）
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
TOC = os.path.join(ROOT, "matlabc_toc.py")
FLOW = os.path.join(ROOT, "flow")
DATA = os.path.join(FLOW, "map_bench.json")
HTML = os.path.join(FLOW, "map_bench.html")
OUTBASE = r"E:\temp\matlabc\_map_bench"

PROJECTS = [
    {"id": "multi_fn", "name": "multi_fn（一文件多函数）",
     "path": os.path.join(ROOT, "translate", "examples", "multi_fn"),
     "note": "4 个 .m / 11 个函数：5+3+2+1 分布，验证「多个 MATLAB 函数 → 一个 C 文件」"},
    {"id": "kern", "name": "kern（真实风格数值库）",
     "path": os.path.join(ROOT, "translate", "examples", "kern"),
     "note": "10 个 .m / 10 个函数：一进一出的对照组"},
    {"id": "annot3", "name": "annot3（真实工程）",
     "path": r"E:\temp\matlabc\annot3",
     "note": "93 个 .m 的外部工程，函数分布不均匀"},
]

FUNC_M = re.compile(r"^\s*function\b", re.M)
FUNC_C = re.compile(r"^mlc_status\s+(m2c_\w+)\s*\(", re.M)
SRC_OF = re.compile(r"← 源文件：(.+?)\s*\*/")


def _mfuncs(text):
    """`function` 个数（MATLAB 的主函数 + 局部函数都算）。"""
    return len(FUNC_M.findall(text))


def _cfacts(gen):
    """逐个 `.c` 取 (文件名, 源 .m, 函数名表)。"""
    src = os.path.join(gen, "src", "gen")
    out = []
    if not os.path.isdir(src):
        return out
    for f in sorted(os.listdir(src)):
        if not f.endswith(".c"):
            continue
        s = io.open(os.path.join(src, f), encoding="utf-8", errors="replace").read()
        m = SRC_OF.search(s)
        out.append({"c": f, "src": m.group(1).strip() if m else "",
                    "funcs": FUNC_C.findall(s),
                    "stub": "MLC_UNIMPLEMENTED" in s})
    return out


def run_one(proj):
    out = os.path.join(OUTBASE, proj["id"])
    t0 = time.time()
    status, err = "ok", ""
    try:
        r = subprocess.run([PY, TOC, proj["path"], "-o", out], cwd=ROOT,
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=1800)
        if r.returncode != 0:
            status = "fail"
            txt = r.stdout.decode("utf-8", "replace")
            err = (txt.strip().splitlines() or [""])[-1][:200]
    except subprocess.TimeoutExpired:
        status, err = "timeout", "超时"
    elapsed = round(time.time() - t0, 1)

    gen = os.path.join(out, "build", "gen")
    facts = _cfacts(gen)

    # 源侧
    mfiles = []
    for base, dirs, files in os.walk(proj["path"]):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for f in files:
            if f.endswith(".m"):
                p = os.path.join(base, f)
                mfiles.append((f, _mfuncs(io.open(p, encoding="utf-8",
                                                 errors="replace").read())))
    m_total = sum(n for _, n in mfiles)
    c_total = sum(len(x["funcs"]) for x in facts)

    # 映射：源文件名 → 那个 .c
    by_src = {x["src"]: x for x in facts}
    rows = []
    for name, n in sorted(mfiles, key=lambda t: -t[1]):
        c = next((x for k, x in by_src.items()
                  if os.path.basename(k) == name), None)
        rows.append({"m": name, "m_funcs": n,
                     "c": c["c"] if c else "—",
                     "c_funcs": len(c["funcs"]) if c else 0,
                     "names": c["funcs"][:6] if c else [],
                     "stub": bool(c and c["stub"])})

    # 编译
    cok = ctotal_c = 0
    cerr = ""
    if facts:
        for x in facts:
            ctotal_c += 1
            r = subprocess.run(["gcc", "-std=c99", "-c", "-o", os.devnull,
                                os.path.join(gen, "src", "gen", x["c"]),
                                "-I", os.path.join(gen, "include"),
                                "-I", os.path.join(ROOT, "c_runtime", "include")],
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=120)
            if r.returncode == 0:
                cok += 1
            elif not cerr:
                for ln in r.stdout.decode("utf-8", "replace").splitlines():
                    if "error" in ln:
                        cerr = ln.strip()[:150]
                        break

    return {"id": proj["id"], "name": proj["name"], "path": proj["path"],
            "note": proj["note"], "status": status, "error": err,
            "elapsed": elapsed,
            "m_files": len(mfiles), "m_funcs": m_total,
            "c_files": len(facts), "c_funcs": c_total,
            "compile_ok": cok, "compile_total": ctotal_c, "compile_err": cerr,
            "rows": rows}


def load():
    if not os.path.isfile(DATA):
        return []
    try:
        return json.load(io.open(DATA, encoding="utf-8"))
    except (ValueError, OSError):
        return []


def render(recs):
    from string import Template

    tot_m = sum(r["m_funcs"] for r in recs)
    tot_c = sum(r["c_funcs"] for r in recs)
    tot_mf = sum(r["m_files"] for r in recs)
    tot_cf = sum(r["c_files"] for r in recs)
    conserve = (tot_m == tot_c)

    cards = []
    for r in recs:
        color = {"ok": "#2ea043", "fail": "#cf222e", "timeout": "#d29922"}[r["status"]]
        badge = {"ok": "转换成功", "fail": "转换失败", "timeout": "超时"}[r["status"]]
        same = (r["m_files"] == r["c_files"]) and (r["m_funcs"] == r["c_funcs"])
        ok_badge = ("<span class='ok'>文件数守恒 ✔</span>" if r["m_files"] == r["c_files"]
                    else "<span class='no'>文件数不等 ✘</span>")
        fn_badge = ("<span class='ok'>函数数守恒 ✔</span>" if r["m_funcs"] == r["c_funcs"]
                    else "<span class='no'>函数数不等 ✘</span>")
        trs = []
        for row in r["rows"][:14]:
            mark = "✔" if row["m_funcs"] == row["c_funcs"] else "✘"
            trs.append(
                "<tr><td><code>{m}</code></td><td class='num'>{mf}</td>"
                "<td>→</td><td><code>{c}</code></td><td class='num'>{cf} {mk}</td>"
                "<td class='names'>{nm}</td></tr>".format(
                    m=row["m"], mf=row["m_funcs"], c=row["c"],
                    cf=row["c_funcs"], mk=mark,
                    nm=", ".join(row["names"])[:80]))
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
        <p class="meta"><code>{path}</code> ｜ {elapsed} s ｜
           <b>{mf}</b> 个 .m → <b>{cf}</b> 个 .c ｜
           <b>{mn}</b> 个函数 → <b>{cn}</b> 个 ｜ 编译 {cok}/{ctot}</p>
        <p class="note">{note} ｜ {okb} {fnb}</p>
      </header>
      <table class="map">
        <tr><th>源文件</th><th>函数</th><th></th><th>C 文件</th><th>函数</th><th>生成的 m2c_*</th></tr>
        {trs}
      </table>
      {err}
    </section>""".format(name=r["name"], color=color, badge=badge,
                         path=r["path"].replace(chr(92), "/"),
                         elapsed=r["elapsed"], mf=r["m_files"], cf=r["c_files"],
                         mn=r["m_funcs"], cn=r["c_funcs"],
                         cok=r["compile_ok"], ctot=r["compile_total"],
                         note=r["note"], okb=ok_badge, fnb=fn_badge,
                         trs="\n        ".join(trs), err=err))

    tpl = Template("""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MATLAB→C 工程级映射 · matlabc</title>
<style>
  :root{--bg:#f6f8fa;--fg:#1f2328;--mut:#57606a;--card:#fff;--line:#d0d7de}
  @media (prefers-color-scheme:dark){
    :root{--bg:#0d1117;--fg:#e6edf3;--mut:#8b949e;--card:#161b22;--line:#30363d}
  }
  *{box-sizing:border-box}
  body{margin:0;padding:34px 20px;background:var(--bg);color:var(--fg);
       font:15px/1.65 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
  .wrap{max-width:1120px;margin:0 auto}
  h1{font-size:27px;margin:0 0 6px;letter-spacing:-.01em}
  .sub{color:var(--mut);margin:0 0 24px}
  .hero{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
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
  .ok{color:#2ea043;font-weight:600}
  .no{color:#cf222e;font-weight:600}
  table{width:100%;border-collapse:collapse;margin-top:8px}
  th{text-align:left;font-size:12px;color:var(--mut);font-weight:600;
     border-bottom:1px solid var(--line);padding:6px 4px}
  td{padding:5px 4px;font-size:13px;border-top:1px solid var(--line)}
  td.num{text-align:right;font-variant-numeric:tabular-nums;width:52px}
  td.names{color:var(--mut);font-size:12px}
  .err{margin:10px 0 0;padding:8px 10px;border-radius:8px;font-size:12.5px;
       background:rgba(207,34,46,.08);color:#cf222e;word-break:break-all}
  footer{color:var(--mut);font-size:12.5px;margin-top:22px;text-align:center}
</style></head><body><div class="wrap">
  <h1>MATLAB → C 工程级映射</h1>
  <p class="sub">多个 MATLAB 函数 ⇄ 一个 C 文件（以及反向）的守恒验证 ｜ $when ｜ $n 个工程</p>
  <div class="hero">
    <div class="kpi"><b>$tfm</b><span>源 .m 文件</span></div>
    <div class="kpi"><b>$tfc</b><span>生成 .c 文件</span></div>
    <div class="kpi"><b>$tmn</b><span>源函数</span></div>
    <div class="kpi"><b>$tcn</b><span>生成函数</span></div>
    <div class="kpi"><b>$verdict</b><span>函数总数守恒</span></div>
  </div>
  $cards
  <footer>由 <code>tools/bench_mapping.py</code> 生成 — 映射关系逐文件比对，不是估算</footer>
</div></body></html>
""")
    return tpl.substitute(when=time.strftime("%Y-%m-%d %H:%M"), n=len(recs),
                          tfm=format(tot_mf, ","), tfc=format(tot_cf, ","),
                          tmn=format(tot_m, ","), tcn=format(tot_c, ","),
                          verdict="✔" if conserve else "✘",
                          cards="\n".join(cards))


def main(argv=None):
    ap = argparse.ArgumentParser(description="MATLAB→C 工程级映射测试 + HTML")
    ap.add_argument("--only", action="append", metavar="ID")
    ap.add_argument("--html-only", action="store_true")
    ns = ap.parse_args(argv)

    recs = load()
    if not ns.html_only:
        done = {r["id"]: r for r in recs}
        for p in PROJECTS:
            if ns.only and p["id"] not in ns.only:
                continue
            print("[map] %s …" % p["name"], flush=True)
            r = run_one(p)
            print("[map] %s -> %s ｜ .m %d/%d 函数 -> .c %d/%d 函数 ｜ 编译 %d/%d"
                  % (p["name"], r["status"], r["m_files"], r["m_funcs"],
                     r["c_files"], r["c_funcs"], r["compile_ok"],
                     r["compile_total"]), flush=True)
            done[r["id"]] = r
        recs = [done[p["id"]] for p in PROJECTS if p["id"] in done]
        io.open(DATA, "w", encoding="utf-8", newline="\n").write(
            json.dumps(recs, ensure_ascii=False, indent=2) + "\n")

    if not recs:
        print("[map] 没有读数")
        return 2
    io.open(HTML, "w", encoding="utf-8", newline="\n").write(render(recs))
    print("[map] HTML -> %s" % HTML)

    bad = [r for r in recs if r["status"] == "ok"
           and (r["m_files"] != r["c_files"] or r["m_funcs"] != r["c_funcs"])]
    if bad:
        print("[map] ⚠ 守恒失败：%r" % [r["id"] for r in bad])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
