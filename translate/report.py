# -*- coding: utf-8 -*-
"""转换过程可视化：一条命令生成**自包含 HTML** 报告。

    python translate/report.py <某个.m 或 目录> [-o report.html] [--limit 12]

每个函数一张卡片，四栏对照：

    ① MATLAB 源码   ② MIR（中间表示）   ③ 生成的 C   ④ 运行结果

并按**真实状态**着色（这是重点 —— 不把"能编译"说成"能算"）：

| 状态 | 含义 |
|---|---|
| `numeric` | 真的跑出了数值 |
| `stub` | 生成了，但函数里有未映射语句 → 是桩 |
| `shape` | 入参没有形状注解 → 连跑都跑不了 |
| `rejected` | `varargin`/struct/cell 之类，签名无法用固定 C 签名表达 |
| `error` | 编译或运行失败（最需要盯的一类） |

为什么放在 `translate/` 而不是 `tools/`：`tools/` 下的脚本会被**自动识别成门**
（需要七处登记），而这是一个给人看的报告生成器，不是判据。
"""
import argparse
import html
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RT = os.path.join(ROOT, "c_runtime")
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release", "m2c.exe")
MIR_PY = os.path.join(HERE, "mir.py")

COLORS = {
    "numeric": ("#16a34a", "#dcfce7"),
    "stub": ("#d97706", "#fef3c7"),
    "shape": ("#7c3aed", "#ede9fe"),
    "rejected": ("#64748b", "#f1f5f9"),
    "skipped": ("#94a3b8", "#f1f5f9"),
    "error": ("#dc2626", "#fee2e2"),
}


def _run(cmd, cwd=None, timeout=600):
    return subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=timeout)


def analyze(m, workdir):
    """把一个 .m 走完整链路，返回一张卡需要的数据。"""
    card = {"file": os.path.basename(m), "src": "", "mir": "", "c": "",
            "run": "", "status": "error", "name": ""}
    try:
        card["src"] = open(m, encoding="utf-8", errors="replace").read().strip()
    except IOError:
        return card

    mir = os.path.join(workdir, os.path.basename(m) + ".mir")
    r = _run([sys.executable, MIR_PY, m, "-o", mir], timeout=300)
    if r.returncode != 0 or not os.path.isfile(mir):
        card["run"] = (r.stdout or b"").decode("utf-8", "replace")[-600:]
        return card

    text = open(mir, encoding="utf-8", errors="replace").read()
    card["mir"] = text.strip()

    func = ""
    reject = False
    unmapped = 0
    shape_missing = False
    for ln in text.splitlines():
        if ln.startswith("func:"):
            func = ln[5:].strip()
        elif ln.startswith("reject:"):
            reject = True
        elif ln.startswith("unmapped:"):
            unmapped += 1
        elif ln.startswith("arg:"):
            p = ln.split(":")
            if len(p) < 4 or not p[3].strip():
                shape_missing = True
    card["name"] = func

    if not func:
        # 没有顶层 function（例如 `Contents.m` 这类纯文档）：中性跳过，
        # **不算 error** —— 让 error 这个分类只表示"真的编译/运行失败"。
        card["status"] = "skipped"
        card["run"] = "该文件没有顶层 function（脚本或纯文档），不参与转换。"
        return card

    if reject:
        card["status"] = "rejected"
        card["run"] = "签名无法用固定 C 签名表达（varargin / struct / cell）—— 拒绝，而不是猜。"
        return card
    if unmapped:
        card["status"] = "stub"
    elif shape_missing:
        card["status"] = "shape"

    gen = os.path.join(workdir, "gen_" + os.path.splitext(os.path.basename(m))[0])
    r = _run([M2C, "build", "--mir", mir, "--out", gen,
              "--name", os.path.splitext(os.path.basename(m))[0]], timeout=300)
    if r.returncode != 0:
        card["status"] = "error"
        card["run"] = r.stdout.decode("utf-8", "replace")[-800:]
        return card

    parts = []
    for dirpath, _dn, fns in os.walk(os.path.join(gen, "src")):
        for fn in fns:
            if fn.endswith(".c") and fn != "main.c":
                parts.append(os.path.join(dirpath, fn))
    card["c"] = "\n\n".join(open(p, encoding="utf-8", errors="replace").read().strip()
                            for p in parts)[:6000]

    if card["status"] == "stub":
        card["run"] = "函数是**桩**（含未映射语句）—— 不跑，也不假装有结果。"
        return card
    if card["status"] == "shape":
        card["run"] = "入参缺形状注解 —— 无法构造输入，跳过着色为 shape。"
        return card

    exe = os.path.join(workdir, "run_" + os.path.splitext(os.path.basename(m))[0] + ".exe")
    cc = shutil.which("gcc") or shutil.which("clang")
    if cc is None:
        card["run"] = "没有 C 编译器，跳过运行。"
        return card
    r = _run([cc, "-std=c99", "-O1",
              "-I", os.path.join(gen, "include"), "-I", os.path.join(RT, "include"),
              os.path.join(gen, "src", "gen.c"), os.path.join(gen, "src", "main.c"),
              os.path.join(RT, "src", "mlc_runtime.c"),
              os.path.join(RT, "src", "mlc_ops.c"), "-o", exe, "-lm"], timeout=600)
    if r.returncode != 0:
        card["status"] = "error"
        card["run"] = r.stdout.decode("utf-8", "replace")[-900:]
        return card
    r = _run([exe], timeout=120)
    out = r.stdout.decode("utf-8", "replace").strip()
    if out:
        card["status"] = "numeric"          # 真的跑出了数值
        card["run"] = out
    else:
        card["status"] = "error"            # 退出但无输出：与「静默算错」同类
        card["run"] = "(进程退出，但没有任何输出)"
    return card


PAGE = u"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MATLAB → C 转换报告</title>
<style>
:root{--bg:#f8fafc;--card:#fff;--fg:#0f172a;--mut:#64748b;--bd:#e2e8f0;--code:#0f172a;--codebg:#f8fafc}
[data-theme="dark"]{--bg:#0b1120;--card:#111827;--fg:#e5e7eb;--mut:#94a3b8;--bd:#1f2937;--code:#e5e7eb;--codebg:#0b1120}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
 font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}
header{padding:20px 24px;border-bottom:1px solid var(--bd);display:flex;
 align-items:center;gap:16px;flex-wrap:wrap}
h1{font-size:18px;margin:0;font-weight:650}
.sub{color:var(--mut);font-size:12.5px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(520px,1fr));
 gap:16px;padding:18px 24px 40px}
.card{background:var(--card);border:1px solid var(--bd);border-radius:10px;overflow:hidden}
.hd{display:flex;align-items:center;gap:10px;padding:10px 14px;border-bottom:1px solid var(--bd)}
.nm{font-weight:650;font-family:ui-monospace,Consolas,monospace}
.badge{font-size:11.5px;font-weight:650;padding:2px 8px;border-radius:999px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:0}
.pane{border-right:1px solid var(--bd);border-bottom:1px solid var(--bd);min-width:0}
.pane:nth-child(2n){border-right:none}
.ttl{font-size:11px;letter-spacing:.06em;text-transform:uppercase;
 color:var(--mut);padding:6px 12px;border-bottom:1px dashed var(--bd)}
pre{margin:0;padding:10px 12px;overflow:auto;max-height:260px;
 font:12px/1.55 ui-monospace,Consolas,monospace;color:var(--code);background:var(--codebg);
 white-space:pre-wrap;word-break:break-word}
button{background:var(--card);color:var(--fg);border:1px solid var(--bd);
 border-radius:8px;padding:6px 12px;cursor:pointer;font-size:12.5px}
.stat{display:flex;gap:14px;flex-wrap:wrap}
.stat b{font-weight:700}
</style></head><body>
<header>
  <h1>MATLAB → MIR → C 转换报告</h1>
  <span class="sub">__SUMMARY__</span>
  <button onclick="var r=document.documentElement;
    r.dataset.theme = r.dataset.theme==='dark' ? '' : 'dark';">切换主题</button>
</header>
<div class="cards">__CARDS__</div>
</body></html>
"""

CARD = u"""<div class="card">
  <div class="hd">
    <span class="nm">__NAME__</span>
    <span class="badge" style="color:__C__;background:__BG__">__STATUS__</span>
    <span class="sub">__FILE__</span>
  </div>
  <div class="grid">
    <div class="pane"><div class="ttl">① MATLAB 源码</div><pre>__SRC__</pre></div>
    <div class="pane"><div class="ttl">② MIR</div><pre>__MIR__</pre></div>
    <div class="pane"><div class="ttl">③ 生成的 C</div><pre>__C__CODE__</pre></div>
    <div class="pane"><div class="ttl">④ 运行结果</div><pre>__RUN__</pre></div>
  </div>
</div>"""


def build(path, out, limit):
    if os.path.isdir(path):
        files = []
        for dirpath, _dn, fns in os.walk(path):
            for fn in sorted(fns):
                if fn.endswith(".m"):
                    files.append(os.path.join(dirpath, fn))
        files.sort()
    else:
        files = [path]
    files = files[:limit]

    work = tempfile.mkdtemp(prefix="m2c_report_")
    cards, counts = [], {}
    try:
        for m in files:
            card = analyze(m, work)
            counts[card["status"]] = counts.get(card["status"], 0) + 1
            c, bg = COLORS.get(card["status"], ("#334155", "#f1f5f9"))
            cards.append(CARD
                         .replace("__NAME__", html.escape(card["name"] or card["file"]))
                         .replace("__FILE__", html.escape(card["file"]))
                         .replace("__STATUS__", card["status"])
                         .replace("__C__", c).replace("__BG__", bg)
                         .replace("__SRC__", html.escape(card["src"]))
                         .replace("__MIR__", html.escape(card["mir"]))
                         .replace("__C__CODE__", html.escape(card["c"]))
                         .replace("__RUN__", html.escape(card["run"])))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    total = len(files)
    summary = "共 %d 个函数 ｜ " % total + " ｜ ".join(
        "%s %d" % (k, v) for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))
    doc = PAGE.replace("__SUMMARY__", html.escape(summary)).replace("__CARDS__", "\n".join(cards))
    open(out, "w", encoding="utf-8", newline="\n").write(doc)
    print(summary)
    print("已写出 %s（%.1f KB）" % (out, os.path.getsize(out) / 1024.0))
    return counts


def main():
    ap = argparse.ArgumentParser(description="MATLAB → C 转换报告（HTML）")
    ap.add_argument("source")
    ap.add_argument("-o", "--out", default="report.html")
    ap.add_argument("--limit", type=int, default=12)
    a = ap.parse_args()
    if not os.path.isfile(M2C):
        print("m2c 未构建：cargo build --release（rust/m2c）")
        return 2
    counts = build(a.source, a.out, a.limit)
    return 0 if counts.get("error", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
