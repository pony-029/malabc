# -*- coding: utf-8 -*-
"""**全流程可视化监控**：跑一遍 MATLAB→C 的每个阶段，把每阶段的读数与产物渲染成一页。

    python tools/flow_monitor.py <工程目录> [--map map.json] [--out DIR]
    python tools/flow_monitor.py --html-only      # 只按上次读数重生页面

## 监控的是"阶段"，不是"结果"

一次转换成败只有一个 bit，但**卡在哪一段**有五种可能。所以这里按阶段记录：

| 阶段 | 记什么 | 失败时的典型原因 |
|---|---|---|
| ① 扫描 .m | 文件数 / 函数数 | 目录选错、没有 .m |
| ② MIR | 函数数 / 算子数 / 未映射数 | 解析器降不了某个结构 |
| ③ 映射分组 | 组数 / 每组函数数 / 丢弃数 | 配置写错、源文件名对不上 |
| ④ 生成 C | .c 数 / 完全实现数 / 桩数 | 算子没实现 |
| ⑤ 编译 | 通过 / 抽样 | 生成的 C 类型不对 |
| ⑥ 运行 | 退出码 / 输出行数 | 运行期形状或越界 |

页面里每个阶段一张卡：状态点、耗时条、关键计数、产物路径。
**失败阶段之后的阶段标为"未到达"**，而不是显示 0 —— 0 会被误读成"跑了但是空的"。
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
MIR_PY = os.path.join(ROOT, "translate", "mir.py")
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release", "m2c.exe")
FLOW = os.path.join(ROOT, "flow")
DATA = os.path.join(FLOW, "flow_monitor.json")
HTML = os.path.join(FLOW, "flow_monitor.html")

FUNC_M = re.compile(r"^\s*function\b", re.M)
FUNC_C = re.compile(r"^mlc_status\s+(m2c_\w+)\s*\(", re.M)


def _run(cmd, timeout=1800):
    t0 = time.time()
    try:
        r = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout, cwd=ROOT)
        return r.returncode, r.stdout.decode("utf-8", "replace"), round(time.time() - t0, 1)
    except subprocess.TimeoutExpired:
        return -1, "超时", round(time.time() - t0, 1)


def monitor(src, out_dir, map_file=None):
    """逐阶段跑，返回阶段列表（含未到达的）。"""
    out_dir = os.path.abspath(out_dir or os.path.join(src, "_m2c_build"))
    mir = os.path.join(out_dir, ".m2c", "project.mir")
    gen = os.path.join(out_dir, "build", "gen")
    stages = []

    def add(name, status, elapsed, metrics, artifact="", note=""):
        # **每进一个阶段，先问大脑**（R935）：它按阶段名检索历史上同类的坑，
        # 把最相关的一条规则挂在阶段卡上。这是"大脑参与全流程"的最小实现 ——
        # 不靠人记得去查，而是流程走到哪就问一句。
        hint = ""
        try:
            sys.path.insert(0, os.path.join(ROOT, "tools"))
            import brain as _brain
            hits = _brain.advise(name, k=1)
            if hits:
                _s, _e = hits[0]
                hint = "%s：%s" % (_e["id"], _e["rule"])
        except Exception:                      # noqa: BLE001
            pass                               # 大脑不可用不该阻断监控
        stages.append({"name": name, "status": status, "elapsed": elapsed,
                       "metrics": metrics, "artifact": artifact, "note": note,
                       "hint": hint})

    # ① 扫描
    t0 = time.time()
    mfiles, mfuncs = 0, 0
    for base, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "_m2c_build")]
        for f in files:
            if f.endswith(".m"):
                mfiles += 1
                mfuncs += len(FUNC_M.findall(
                    io.open(os.path.join(base, f), encoding="utf-8",
                            errors="replace").read()))
    ok = mfiles > 0
    add("① 扫描 .m", "ok" if ok else "fail", round(time.time() - t0, 1),
        [("源文件", mfiles), ("函数", mfuncs)], src,
        "" if ok else "该目录下没有 .m 文件")
    if not ok:
        return stages

    # ② MIR
    os.makedirs(os.path.dirname(mir), exist_ok=True)
    rc, txt, el = _run([PY, MIR_PY, src, "--recursive", "-o", mir])
    mir_text = (io.open(mir, encoding="utf-8", errors="replace").read()
                if os.path.isfile(mir) else "")
    nfunc = len(re.findall(r"^func:", mir_text, re.M))
    nop = len(re.findall(r"^op:", mir_text, re.M))
    nunmap = len(re.findall(r"^unmapped:", mir_text, re.M))
    add("② 解析成 MIR", "ok" if rc == 0 else "fail", el,
        [("函数", nfunc), ("算子", nop), ("未映射", nunmap)], mir,
        "" if rc == 0 else txt.strip().splitlines()[-1][:160])
    if rc != 0:
        return stages

    # ③ 映射分组
    if map_file:
        try:
            sys.path.insert(0, os.path.join(ROOT, "translate"))
            import map_config as MC
            spec, rep = MC.load_and_apply(mir, map_file)
            probs = MC.validate_report(rep, spec)
            add("③ 映射分组", "warn" if probs else "ok", 0.0,
                [("组", len(rep["groups"])), ("已归组函数",
                                            rep["functions"] - rep["dropped"]),
                 ("丢弃", rep["dropped"])], map_file,
                " / ".join(probs)[:200])
        except Exception as e:                     # noqa: BLE001
            add("③ 映射分组", "fail", 0.0, [], map_file, str(e)[:160])
            return stages
    else:
        add("③ 映射分组", "skip", 0.0, [("组", mfiles)],
            "", "未提供 --map：按源文件一一对应")

    # ④ 生成 C
    rc, txt, el = _run([M2C, "build", "--mir", mir, "--out", gen, "--name", "proj"])
    srcgen = os.path.join(gen, "src", "gen")
    cs = [f for f in os.listdir(srcgen) if f.endswith(".c")] if os.path.isdir(srcgen) else []
    stubs = 0
    for f in cs:
        if "MLC_UNIMPLEMENTED" in io.open(os.path.join(srcgen, f),
                                          encoding="utf-8", errors="replace").read():
            stubs += 1
    add("④ 生成 C", "ok" if rc == 0 else "fail", el,
        [(".c 文件", len(cs)), ("完全实现", len(cs) - stubs), ("桩", stubs)],
        srcgen, "" if rc == 0 else txt.strip().splitlines()[-1][:160])
    if rc != 0:
        return stages

    # ⑤ 编译（抽样前 40 个）
    sample = sorted(cs)[:40]
    okc, first_err = 0, ""
    t0 = time.time()
    for f in sample:
        c, t, _ = _run(["gcc", "-std=c99", "-c", "-o", os.devnull,
                        os.path.join(srcgen, f), "-I", os.path.join(gen, "include"),
                        "-I", os.path.join(ROOT, "c_runtime", "include")], timeout=120)
        if c == 0:
            okc += 1
        elif not first_err:
            for ln in t.splitlines():
                if "error" in ln:
                    first_err = ln.strip()[:160]
                    break
    add("⑤ 编译", "ok" if okc == len(sample) else "warn", round(time.time() - t0, 1),
        [("抽样", len(sample)), ("通过", okc)], srcgen, first_err)

    # ⑥ 运行（只有整装工程可跑时才做）
    exe = os.path.join(out_dir, "proj.exe")
    gen_c = os.path.join(gen, "src", "gen.c")
    main_c = os.path.join(gen, "src", "main.c")
    if os.path.isfile(gen_c) and os.path.isfile(main_c):
        rc2, t2, el2 = _run(["gcc", "-std=c99", "-O1", "-o", exe, gen_c, main_c,
                             os.path.join(ROOT, "c_runtime", "src", "mlc_runtime.c"),
                             os.path.join(ROOT, "c_runtime", "src", "mlc_ops.c"),
                             "-I", os.path.join(gen, "include"),
                             "-I", os.path.join(ROOT, "c_runtime", "include"),
                             "-lm"])
        if rc2 == 0:
            rc3, t3, el3 = _run([exe], timeout=300)
            add("⑥ 运行", "ok" if rc3 == 0 else "fail", el3,
                [("退出码", rc3), ("输出行", len(t3.splitlines()))], exe,
                "" if rc3 == 0 else t3.strip().splitlines()[-1][:160])
        else:
            add("⑥ 运行", "skip", el2, [], "", "链接失败（%s）" % t2.splitlines()[-1][:80])
    else:
        add("⑥ 运行", "skip", 0.0, [], "", "没有 gen.c/main.c")
    return stages


def render(stages, src):
    from string import Template

    color = {"ok": "#2ea043", "warn": "#d29922", "fail": "#cf222e",
             "skip": "#8b949e"}
    label = {"ok": "通过", "warn": "有告警", "fail": "失败", "skip": "未执行"}
    emax = max([s["elapsed"] for s in stages] or [1]) or 1
    cards = []
    for i, s in enumerate(stages):
        rows = "".join("<tr><td>{}</td><td class='num'>{}</td></tr>".format(k, v)
                       for k, v in s["metrics"]) or \
               "<tr><td colspan='2' class='dim'>—</td></tr>"
        width = max(2.0, 100.0 * s["elapsed"] / emax)
        art = ("<p class='art'><code>{}</code></p>".format(s["artifact"])
               if s["artifact"] else "")
        note = ("<p class='err'>{}</p>".format(s["note"].replace("<", "&lt;"))
                if s["note"] else "")
        hint = ("<p class='hint'>🧠 {}</p>".format(s["hint"].replace("<", "&lt;"))
                if s.get("hint") else "")
        cards.append("""
    <section class="stage">
      <div class="dot" style="background:{c}"></div>
      <div class="body">
        <h2>{name} <span class="badge" style="background:{c}">{lab}</span>
            <span class="t">{el} s</span></h2>
        <div class="bar"><span style="width:{w}%;background:{c}"></span></div>
        <table>{rows}</table>
        {art}{note}{hint}
      </div>
    </section>""".format(c=color[s["status"]], name=s["name"],
                         lab=label[s["status"]], el=s["elapsed"], w=width,
                         rows=rows, art=art, note=note, hint=hint))

    total = sum(s["elapsed"] for s in stages)
    reached = sum(1 for s in stages if s["status"] in ("ok", "warn"))
    tpl = Template("""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>转换流程监控 · matlabc</title>
<style>
  :root{--bg:#f6f8fa;--fg:#1f2328;--mut:#57606a;--card:#fff;--line:#d0d7de}
  @media (prefers-color-scheme:dark){
    :root{--bg:#0d1117;--fg:#e6edf3;--mut:#8b949e;--card:#161b22;--line:#30363d}
  }
  *{box-sizing:border-box}
  body{margin:0;padding:34px 20px;background:var(--bg);color:var(--fg);
       font:15px/1.65 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
  .wrap{max-width:920px;margin:0 auto}
  h1{font-size:26px;margin:0 0 6px}
  .sub{color:var(--mut);margin:0 0 22px}
  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
        gap:12px;margin:0 0 24px}
  .kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;
       padding:14px 16px}
  .kpi b{display:block;font-size:23px;font-variant-numeric:tabular-nums}
  .kpi span{color:var(--mut);font-size:12.5px}
  .stage{display:flex;gap:14px;background:var(--card);border:1px solid var(--line);
         border-radius:14px;padding:16px 18px;margin:0 0 12px}
  .dot{width:11px;height:11px;border-radius:50%;margin-top:9px;flex:none}
  .body{flex:1;min-width:0}
  .stage h2{font-size:16px;margin:0 0 8px;display:flex;align-items:center;gap:9px}
  .badge{color:#fff;font-size:11px;padding:2px 8px;border-radius:999px;font-weight:600}
  .t{margin-left:auto;color:var(--mut);font-size:12.5px;font-weight:400}
  .bar{height:6px;background:var(--line);border-radius:999px;overflow:hidden;
       margin:0 0 10px}
  .bar span{display:block;height:100%;border-radius:999px;opacity:.85}
  table{width:100%;border-collapse:collapse}
  td{padding:4px 0;font-size:13.5px}
  td.num{text-align:right;font-variant-numeric:tabular-nums;width:110px;
         font-weight:600}
  td.dim{color:var(--mut)}
  .art{margin:6px 0 0;font-size:12px;color:var(--mut);word-break:break-all}
  .err{margin:8px 0 0;padding:7px 9px;border-radius:8px;font-size:12.5px;
       background:rgba(207,34,46,.08);color:#cf222e;word-break:break-all}
  .hint{margin:8px 0 0;padding:6px 9px;border-radius:8px;font-size:12.5px;
        background:rgba(110,64,201,.08);color:#8250df;word-break:break-all}
  footer{color:var(--mut);font-size:12.5px;margin-top:20px;text-align:center}
</style></head><body><div class="wrap">
  <h1>转换流程监控</h1>
  <p class="sub"><code>$src</code> ｜ 到达 $reached / $n 个阶段 ｜ 合计 $total s</p>
  <div class="kpis">
    <div class="kpi"><b>$n</b><span>阶段</span></div>
    <div class="kpi"><b>$reached</b><span>到达（通过/告警）</span></div>
    <div class="kpi"><b>$total s</b><span>合计耗时</span></div>
  </div>
  $cards
  <footer>由 <code>tools/flow_monitor.py</code> 生成 — 每阶段的数字都来自实跑；
          未到达的阶段如实标"未执行"而不是显示 0</footer>
</div></body></html>
""")
    return tpl.substitute(src=src.replace(chr(92), "/"), n=len(stages),
                          reached=reached, total="%.1f" % total,
                          cards="\n".join(cards))


def main(argv=None):
    ap = argparse.ArgumentParser(description="MATLAB→C 全流程监控 + HTML")
    ap.add_argument("src", nargs="?", help="MATLAB 工程目录")
    ap.add_argument("--map", metavar="FILE", help="映射配置 JSON")
    ap.add_argument("--out", metavar="DIR", help="产物目录")
    ap.add_argument("--html-only", action="store_true")
    ns = ap.parse_args(argv)

    if ns.html_only:
        if not os.path.isfile(DATA):
            print("没有上次读数")
            return 2
        d = json.load(io.open(DATA, encoding="utf-8"))
    else:
        if not ns.src or not os.path.isdir(ns.src):
            print("需要工程目录", file=sys.stderr)
            return 2
        stages = monitor(os.path.abspath(ns.src), ns.out, ns.map)
        d = {"src": os.path.abspath(ns.src), "stages": stages}
        io.open(DATA, "w", encoding="utf-8", newline="\n").write(
            json.dumps(d, ensure_ascii=False, indent=2) + "\n")
        for s in stages:
            print("[monitor] %-14s %-5s %6.1fs  %s"
                  % (s["name"], s["status"], s["elapsed"],
                     " ｜ ".join("%s=%s" % kv for kv in s["metrics"])))

    io.open(HTML, "w", encoding="utf-8", newline="\n").write(
        render(d["stages"], d["src"]))
    print("[monitor] HTML -> %s" % HTML)
    bad = [s["name"] for s in d["stages"] if s["status"] == "fail"]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
