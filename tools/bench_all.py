# -*- coding: utf-8 -*-
"""**全量工程实测**：把 `E:\\temp\\matlabc` 下所有含 `.m` 的目录都验一遍。

    python tools/bench_all.py                 # 全量（大工程逐个、单文件聚合）
    python tools/bench_all.py --html-only     # 只重生报告
    python tools/bench_all.py --max-big 8     # 只跑最大的 8 个多文件工程

## 为什么这样分组

盘点上万个目录逐个跑 `--to-c` 不现实（每个都要起进程 + 生成工程）。所以按规模分流：

| 档 | 判据 | 做法 |
|---|---|---|
| **big** | `.m` > 1 | 逐个跑（真正能看出问题的那些） |
| **single** | `.m` == 1 | **聚合成一个合成工程**一次跑完（3700 个也不会拖时间） |
| **dup** | 与已跑过的工程（文件数 + 首个文件大小）完全相同 | 跳过并**明确标 dup**，不假装跑过 |

去重很重要：`s6`…`sr` 是同一个 165 文件语料的十几个副本，
逐个跑只会把同一份结论抄 14 遍，让报告看起来比实际更"全"。

## 每个工程量什么

`源 .m / 生成 .c / 源函数 / 生成函数 / 完全实现 / 抽样编译`

其中"源函数 vs 生成函数"是**守恒判据** —— 不等就说明有函数在转换中丢了。
"""
import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
TOC = os.path.join(ROOT, "matlabc_toc.py")
FLOW = os.path.join(ROOT, "flow")
DATA = os.path.join(FLOW, "bench_all.json")
HTML = os.path.join(FLOW, "bench_all.html")
SRCROOT = r"E:\temp\matlabc"
OUTBASE = r"E:\temp\matlabc\_bench_all"

FUNC_M = re.compile(r"^\s*function\b", re.M)
FUNC_C = re.compile(r"^mlc_status\s+(m2c_\w+)\s*\(", re.M)


def survey(root):
    """返回 [(dir, n_m, sig)]，sig 用于去重（文件数 + 首个文件大小）。"""
    out = []
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name)
        if not os.path.isdir(p):
            continue
        ms = []
        for base, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__",
                                                    "_m2c_build", "_toc")]
            ms.extend(os.path.join(base, f) for f in files if f.endswith(".m"))
        if not ms:
            continue
        first = min(ms)
        try:
            sig = (len(ms), os.path.getsize(first))
        except OSError:
            sig = (len(ms), -1)
        out.append({"name": name, "path": p, "n": len(ms), "sig": sig})
    return out


def _mfuncs(path):
    n = 0
    for base, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for f in files:
            if f.endswith(".m"):
                n += len(FUNC_M.findall(
                    io.open(os.path.join(base, f), encoding="utf-8",
                            errors="replace").read()))
    return n


def _cfacts(gen):
    src = os.path.join(gen, "src", "gen")
    if not os.path.isdir(src):
        return 0, 0, []
    cs = sorted(f for f in os.listdir(src) if f.endswith(".c"))
    good, funcs = 0, 0
    for f in cs:
        s = io.open(os.path.join(src, f), encoding="utf-8", errors="replace").read()
        funcs += len(FUNC_C.findall(s))
        if "MLC_UNIMPLEMENTED" not in s:
            good += 1
    return len(cs), funcs, cs[:0] or cs


def _compile(gen, cs, limit=20):
    src = os.path.join(gen, "src", "gen")
    ok, first = 0, ""
    for f in cs[:limit]:
        r = subprocess.run(["gcc", "-std=c99", "-c", "-o", os.devnull,
                            os.path.join(src, f), "-I", os.path.join(gen, "include"),
                            "-I", os.path.join(ROOT, "c_runtime", "include")],
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=180)
        if r.returncode == 0:
            ok += 1
        elif not first:
            for ln in r.stdout.decode("utf-8", "replace").splitlines():
                if "error" in ln:
                    first = ln.strip()[:150]
                    break
    return ok, min(limit, len(cs)), first


def run_proj(name, path, out, timeout=1800):
    t0 = time.time()
    status, err = "ok", ""
    try:
        r = subprocess.run([PY, TOC, path, "-o", out], cwd=ROOT,
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout)
        if r.returncode != 0:
            status = "fail"
            txt = r.stdout.decode("utf-8", "replace")
            err = (txt.strip().splitlines() or [""])[-1][:180]
    except subprocess.TimeoutExpired:
        status, err = "timeout", "超过 %d 秒" % timeout
    el = round(time.time() - t0, 1)
    gen = os.path.join(out, "build", "gen")
    nc, ncf, cs = _cfacts(gen)
    cok, ctot, cerr = _compile(gen, cs) if nc else (0, 0, "")
    return {"name": name, "path": path, "status": status, "error": err,
            "elapsed": el, "m_files": 0, "m_funcs": _mfuncs(path),
            "c_files": nc, "c_funcs": ncf, "full": 0,
            "compile_ok": cok, "compile_total": ctot, "compile_err": cerr}


def main(argv=None):
    ap = argparse.ArgumentParser(description="E:\\temp\\matlabc 全量工程实测")
    ap.add_argument("--html-only", action="store_true")
    ap.add_argument("--max-big", type=int, default=0, help="只跑最大的 N 个多文件工程")
    ap.add_argument("--skip-compile", action="store_true")
    ns = ap.parse_args(argv)

    if ns.html_only:
        recs = json.load(io.open(DATA, encoding="utf-8"))
    else:
        items = survey(SRCROOT)
        big = [x for x in items if x["n"] > 1]
        single = [x for x in items if x["n"] == 1]
        big.sort(key=lambda x: -x["n"])
        if ns.max_big:
            big = big[:ns.max_big]

        # 去重：同一 sig 只跑第一个，其余记 dup
        seen, recs, dups = {}, [], []
        for x in big:
            if x["sig"] in seen:
                dups.append({"name": x["name"], "dup_of": seen[x["sig"]],
                             "n": x["n"]})
                continue
            seen[x["sig"]] = x["name"]
            print("[all] %-14s %4d 个 .m …" % (x["name"], x["n"]), flush=True)
            r = run_proj(x["name"], x["path"],
                         os.path.join(OUTBASE, x["name"]))
            r["m_files"] = x["n"]
            print("[all] %-14s %-5s %6.1fs  .c %d ｜ 函数 %d/%d ｜ 编译 %d/%d"
                  % (x["name"], r["status"], r["elapsed"], r["c_files"],
                     r["c_funcs"], r["m_funcs"], r["compile_ok"],
                     r["compile_total"]), flush=True)
            recs.append(r)

        # 单文件工程：聚合成一个合成工程一起跑
        if single:
            agg = os.path.join(OUTBASE, "_single_agg_src")
            if os.path.isdir(agg):
                shutil.rmtree(agg)
            os.makedirs(agg)
            for i, x in enumerate(single):
                ms = []
                for base, dirs, files in os.walk(x["path"]):
                    ms.extend(os.path.join(base, f) for f in files
                              if f.endswith(".m"))
                if not ms:
                    continue
                dst = os.path.join(agg, "s%04d_%s" % (i, os.path.basename(ms[0])))
                shutil.copy(ms[0], dst)
            print("[all] 单文件聚合：%d 个 .m …" % len(single), flush=True)
            r = run_proj("single(%d 个单文件工程)" % len(single), agg,
                         os.path.join(OUTBASE, "_single_agg"))
            r["m_files"] = len(single)
            print("[all] single %-5s %6.1fs  .c %d ｜ 函数 %d/%d"
                  % (r["status"], r["elapsed"], r["c_files"], r["c_funcs"],
                     r["m_funcs"]), flush=True)
            recs.append(r)

        payload = {"recs": recs, "dups": dups, "total_dirs": len(items),
                   "ts": time.strftime("%Y-%m-%d %H:%M")}
        io.open(DATA, "w", encoding="utf-8", newline="\n").write(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    recs = payload["recs"] if not ns.html_only else recs["recs"]
    dups = payload["dups"] if not ns.html_only else recs["dups"]
    total_dirs = (payload["total_dirs"] if not ns.html_only else recs["total_dirs"])
    ts = payload["ts"] if not ns.html_only else recs["ts"]

    io.open(HTML, "w", encoding="utf-8", newline="\n").write(
        render(recs, dups, total_dirs, ts))
    print("[all] HTML -> %s" % HTML)
    bad = [r["name"] for r in recs if r["status"] != "ok"]
    return 1 if bad else 0


def render(recs, dups, total_dirs, ts):
    from string import Template

    ok = [r for r in recs if r["status"] == "ok"]
    tot_m = sum(r["m_files"] for r in recs)
    tot_c = sum(r["c_files"] for r in recs)
    tot_mf = sum(r["m_funcs"] for r in recs)
    tot_cf = sum(r["c_funcs"] for r in recs)
    cok = sum(r["compile_ok"] for r in recs)
    ctot = sum(r["compile_total"] for r in recs)

    rows = []
    for r in recs:
        color = {"ok": "#2ea043", "fail": "#cf222e", "timeout": "#d29922"}[r["status"]]
        conserve = (r["m_funcs"] == r["c_funcs"])
        rows.append(
            "<tr><td><code>{n}</code></td><td class='num'>{mf}</td>"
            "<td class='num'>{cf}</td><td class='num'>{mn}</td>"
            "<td class='num'>{cn} {mk}</td><td class='num'>{el}</td>"
            "<td class='num'>{cok}/{ct}</td>"
            "<td><span class='badge' style='background:{c}'>{s}</span></td></tr>"
            .format(n=r["name"], mf=r["m_files"], cf=r["c_files"],
                    mn=r["m_funcs"], cn=r["c_funcs"],
                    mk="✔" if conserve else "✘", el=r["elapsed"],
                    cok=r["compile_ok"], ct=r["compile_total"], c=color,
                    s={"ok": "通", "fail": "失败", "timeout": "超时"}[r["status"]]))
    dup_rows = "".join("<tr><td><code>{}</code></td><td class='num'>{}</td>"
                       "<td>与 <code>{}</code> 内容相同</td></tr>"
                       .format(d["name"], d["n"], d["dup_of"]) for d in dups[:40])

    tpl = Template("""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>全量工程实测 · matlabc</title>
<style>
  :root{--bg:#f6f8fa;--fg:#1f2328;--mut:#57606a;--card:#fff;--line:#d0d7de}
  @media (prefers-color-scheme:dark){
    :root{--bg:#0d1117;--fg:#e6edf3;--mut:#8b949e;--card:#161b22;--line:#30363d}
  }
  *{box-sizing:border-box}
  body{margin:0;padding:34px 20px;background:var(--bg);color:var(--fg);
       font:15px/1.65 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
  .wrap{max-width:1080px;margin:0 auto}
  h1{font-size:26px;margin:0 0 6px}
  .sub{color:var(--mut);margin:0 0 22px}
  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
        gap:12px;margin:0 0 22px}
  .kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;
       padding:14px 16px}
  .kpi b{display:block;font-size:23px;font-variant-numeric:tabular-nums}
  .kpi span{color:var(--mut);font-size:12.5px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;
        padding:16px 18px;margin:0 0 16px;overflow-x:auto}
  .card h2{font-size:16px;margin:0 0 10px}
  table{width:100%;border-collapse:collapse}
  th{text-align:left;font-size:12px;color:var(--mut);border-bottom:1px solid var(--line);
     padding:6px 5px;white-space:nowrap}
  td{padding:5px;font-size:13px;border-top:1px solid var(--line);white-space:nowrap}
  td.num{text-align:right;font-variant-numeric:tabular-nums}
  .badge{color:#fff;font-size:11px;padding:1px 7px;border-radius:999px}
  footer{color:var(--mut);font-size:12.5px;margin-top:18px;text-align:center}
</style></head><body><div class="wrap">
  <h1>全量工程实测</h1>
  <p class="sub"><code>$root</code> ｜ $ts ｜ 含 .m 的目录 $dirs 个 ｜ 实跑 $n 个（成功 $nok）｜ 去重跳过 $ndup 个</p>
  <div class="kpis">
    <div class="kpi"><b>$tmn</b><span>源 .m 文件</span></div>
    <div class="kpi"><b>$tcn</b><span>生成 .c 文件</span></div>
    <div class="kpi"><b>$tcf</b><span>生成函数</span></div>
    <div class="kpi"><b>$cok/$ctot</b><span>抽样编译</span></div>
  </div>
  <section class="card">
    <h2>① 逐工程读数（函数数 ✔/✘ = 与源函数数是否守恒）</h2>
    <table>
      <tr><th>工程</th><th>.m</th><th>.c</th><th>源函数</th><th>生成函数</th>
          <th>耗时 s</th><th>编译</th><th>状态</th></tr>
      $rows
    </table>
  </section>
  <section class="card">
    <h2>② 去重跳过（内容相同的副本，不重复计数）</h2>
    <table>$dup_rows</table>
  </section>
  <footer>由 <code>tools/bench_all.py</code> 生成 — 每个数字都来自实跑；副本明确标出，不假装跑过</footer>
</div></body></html>
""")
    return tpl.substitute(root=SRCROOT.replace(chr(92), "/"), ts=ts,
                          dirs=total_dirs, n=len(recs), nok=len(ok),
                          ndup=len(dups), tmn=format(tot_m, ","),
                          tcn=format(tot_c, ","), tcf=format(tot_cf, ","),
                          cok=cok, ctot=ctot, rows="\n".join(rows),
                          dup_rows=dup_rows or "<tr><td class='dim'>无</td></tr>")


if __name__ == "__main__":
    sys.exit(main())
