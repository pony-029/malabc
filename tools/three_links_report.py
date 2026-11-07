# -*- coding: utf-8 -*-
"""三段链路大规模测试 → **自包含 HTML 报告**（离线可开、无外部请求）。

## 判什么

对每个 `.m` 跑三段，每段都给"过/不过"的**客观依据**：

| 段 | 判据 | 依据 |
|---|---|---|
| ① MATLAB → MIR | 未映射语句数 = 0 | `mir.py` 输出里的 `unmapped:` 计数 |
| ② MIR → C | 构建成功 + **gcc 编译通过** | `m2c build` 退出码 + gcc 退出码 |
| ③ C → MIR | 算子 id 多重集相等 | `cmir.py` 反推后与源 MIR 比对 |

②还额外跑一次生成的 exe：能跑出数才算"真的能执行"（R629 那次"能生成不能算"的教训）。

## 用法

    python tools/three_links_report.py <目录或文件...> -o <输出目录> --limit 25

产物：`index.html` + `detail/<函数>.html`（每个函数一页，含三段真实文本）。
"""
import argparse
import collections
import html
import io
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from translate import cmir as CM            # noqa: E402

MIR_PY = os.path.join(ROOT, "translate", "mir.py")
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release", "m2c.exe")
RT = os.path.join(ROOT, "c_runtime")
WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"

#: 不生成 `mlc_op_*` 调用、由发射器内联展开的算子（口径，不是缺陷）
INLINE_EMITTED = {"OP-MASK", "OP-FIND2", "OP-FIND3", "OP-ISEQUAL", "OP-ISEQUALK",
                  "OP-COPY", "OP-SETIDX", "OP-SETIDX2"}


def _run(cmd, timeout=300, cwd=None):
    return subprocess.run(cmd, stdin=subprocess.DEVNULL, timeout=timeout, cwd=cwd,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def _ops(text):
    c = collections.Counter()
    for ln in text.splitlines():
        if ln.startswith("op:"):
            c[ln.split(":")[1]] += 1
    return c


def analyze_one(src, d):
    """跑三段，返回一行记录。"""
    stem = os.path.splitext(os.path.basename(src))[0]
    rec = {"name": stem, "src": src, "link1": "skip", "link2": "skip",
           "link3": "skip", "mir": "", "c": "", "back": "", "run": "",
           "unmapped": 0, "ops": 0, "note": ""}

    mir = os.path.join(d, stem + ".mir")
    r = _run([sys.executable, MIR_PY, src, "-o", mir])
    if r.returncode != 0 or not os.path.isfile(mir):
        msg = r.stdout.decode("utf-8", "replace")
        if "没有识别到 function" in msg or "没有识别到函数" in msg:
            rec["note"] = "无顶层 function（脚本/纯文档）"
        else:
            rec["link1"] = "fail"
            rec["note"] = msg.strip().splitlines()[-1][:120] if msg.strip() else "mir 失败"
        return rec

    text = io.open(mir, encoding="utf-8").read()
    rec["mir"] = text
    rec["unmapped"] = text.count("unmapped:")
    rec["ops"] = sum(_ops(text).values())
    rec["link1"] = "ok" if rec["unmapped"] == 0 else "fail"
    if rec["link1"] != "ok":
        rec["note"] = "%d 条未映射" % rec["unmapped"]
        return rec

    gen = os.path.join(d, "g_" + stem)
    r = _run([M2C, "build", "--mir", mir, "--out", gen, "--name", stem])
    if r.returncode != 0:
        rec["link2"] = "fail"
        rec["note"] = "m2c build 失败"
        return rec

    cpath = None
    for dp, _dn, fns in os.walk(os.path.join(gen, "src")):
        for f in fns:
            if f.endswith(".c") and f not in ("main.c", "selftest.c"):
                cpath = os.path.join(dp, f)
                break
        if cpath:
            break
    if not cpath:
        rec["link2"] = "fail"
        rec["note"] = "没生成 .c"
        return rec
    rec["c"] = io.open(cpath, encoding="utf-8", errors="replace").read()

    exe = os.path.join(d, stem + ".exe")
    cc = _run(["gcc", "-std=c99", "-O1",
               "-I", os.path.join(gen, "include"), "-I", os.path.join(RT, "include"),
               os.path.join(gen, "src", "gen.c"), os.path.join(gen, "src", "main.c"),
               os.path.join(RT, "src", "mlc_runtime.c"),
               os.path.join(RT, "src", "mlc_ops.c"), "-o", exe, "-lm"], timeout=180)
    if cc.returncode != 0:
        rec["link2"] = "fail"
        rec["note"] = "gcc 编译失败"
        return rec

    run = _run([exe], timeout=30)
    rec["run"] = run.stdout.decode("utf-8", "replace").strip()[:200]
    rec["link2"] = "ok" if run.returncode == 0 and rec["run"] else "fail"
    if rec["link2"] != "ok":
        rec["note"] = "生成物跑不出数"
        return rec

    back, _st = CM.c_to_mir(rec["c"], stem)
    rec["back"] = back
    a, b = _ops(text), _ops(back)
    missing = {k: v for k, v in (a - b).items() if k not in INLINE_EMITTED}
    extra = {k: v for k, v in (b - a).items() if k not in INLINE_EMITTED}
    if not missing and not extra:
        rec["link3"] = "ok"
    else:
        rec["link3"] = "fail"
        rec["note"] = "算子序列变化：%r" % ((missing, extra),)
    return rec


CSS = """
:root{--bg:#f5f7fb;--card:#fff;--fg:#0f172a;--mut:#64748b;--bd:#e2e8f0;
 --ok:#059669;--okbg:#ecfdf5;--fail:#dc2626;--failbg:#fef2f2;
 --skip:#94a3b8;--skipbg:#f1f5f9;--accent:#2563eb}
[data-theme="dark"]{--bg:#0b1120;--card:#111827;--fg:#e5e7eb;--mut:#94a3b8;
 --bd:#1f2937;--ok:#34d399;--okbg:#052e2b;--fail:#f87171;--failbg:#3f1212;
 --skip:#64748b;--skipbg:#1e293b;--accent:#60a5fa}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
 font:14px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}
header{padding:26px 30px 16px;background:var(--card);border-bottom:1px solid var(--bd)}
h1{margin:0 0 6px;font-size:19px;font-weight:680;letter-spacing:.2px}
.sub{color:var(--mut);font-size:12.5px}
.wrap{padding:20px 30px 70px;max-width:1240px;margin:0 auto}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
 gap:12px;margin:6px 0 22px}
.kpi{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:14px 16px}
.kpi .v{font:660 26px/1.15 ui-monospace,Consolas,monospace}
.kpi .k{color:var(--mut);font-size:11.5px;margin-top:4px;letter-spacing:.03em}
.bar{height:8px;border-radius:999px;background:color-mix(in srgb,var(--fg) 8%,transparent);
 overflow:hidden;display:flex;margin-top:9px}
.bar i{display:block;height:100%}
h2{font-size:14.5px;margin:26px 0 8px;font-weight:660}
table{width:100%;border-collapse:collapse;background:var(--card);
 border:1px solid var(--bd);border-radius:14px;overflow:hidden}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--bd);font-size:13px}
th{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--mut);font-weight:640}
tr:last-child td{border-bottom:none}
.mono{font-family:ui-monospace,Consolas,monospace}
.b{display:inline-block;min-width:52px;text-align:center;font-size:11.5px;
 font-weight:660;padding:2px 8px;border-radius:999px}
.b.ok{color:var(--ok);background:var(--okbg)}
.b.fail{color:var(--fail);background:var(--failbg)}
.b.skip{color:var(--skip);background:var(--skipbg)}
a{color:var(--accent);text-decoration:none;font-weight:600}
a:hover{text-decoration:underline}
.filters{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}
button{background:var(--card);color:var(--fg);border:1px solid var(--bd);
 border-radius:9px;padding:7px 13px;cursor:pointer;font-size:12.5px}
button.on{border-color:var(--accent);color:var(--accent)}
pre{background:var(--card);border:1px solid var(--bd);border-radius:12px;
 padding:12px 14px;overflow:auto;font:12px/1.6 ui-monospace,Consolas,monospace;
 max-height:420px;white-space:pre-wrap;word-break:break-word}
.note{color:var(--mut);font-size:12px}
"""

JS = """
function setTheme(){var r=document.documentElement;
 r.dataset.theme=r.dataset.theme==='dark'?'':'dark';}
function filt(k,btn){document.querySelectorAll('button[data-f]').forEach(function(b){
 b.classList.toggle('on', b===btn);});
 document.querySelectorAll('tr[data-s]').forEach(function(tr){
 tr.style.display=(k==='all'||tr.dataset.s.indexOf(k)>=0)?'':'none';});}
"""


def _badge(s):
    cls = {"ok": "ok", "fail": "fail", "skip": "skip"}[s]
    txt = {"ok": "通过", "fail": "失败", "skip": "跳过"}[s]
    return '<span class="b %s">%s</span>' % (cls, txt)


def write_report(recs, outdir, kind_block=""):
    os.makedirs(outdir, exist_ok=True)
    det = os.path.join(outdir, "detail")
    os.makedirs(det, exist_ok=True)

    n = len(recs)
    l1 = sum(1 for r in recs if r["link1"] == "ok")
    l2 = sum(1 for r in recs if r["link2"] == "ok")
    l3 = sum(1 for r in recs if r["link3"] == "ok")
    full = sum(1 for r in recs if r["link3"] == "ok")

    def pct(a):
        return 100.0 * a / n if n else 0

    def kpi(v, k, color=None):
        st = ' style="color:%s"' % color if color else ""
        return ('<div class="kpi"><div class="v"%s>%s</div>'
                '<div class="k">%s</div></div>' % (st, v, k))

    kpis = (kpi(n, "函数总数")
            + kpi("%d <span class='note'>(%.0f%%)</span>" % (l1, pct(l1)),
                  "① MATLAB → MIR 通过", "var(--ok)")
            + kpi("%d <span class='note'>(%.0f%%)</span>" % (l2, pct(l2)),
                  "② MIR → C 编译并跑出数", "var(--ok)")
            + kpi("%d <span class='note'>(%.0f%%)</span>" % (l3, pct(l3)),
                  "③ C → MIR 算子守恒", "var(--ok)")
            + kpi("%d <span class='note'>(%.0f%%)</span>" % (full, pct(full)),
                  "三段全通", "var(--accent)"))

    bar = ('<div class="bar">'
           '<i style="width:%.1f%%;background:var(--ok)"></i>'
           '<i style="width:%.1f%%;background:var(--accent)"></i>'
           '<i style="width:%.1f%%;background:var(--fail)"></i></div>'
           % (pct(l1), pct(l2), max(0.0, 100 - pct(l1))))

    rows = []
    for r in recs:
        page = "detail/%s.html" % r["name"]
        st = " ".join(x for x in (r["link1"], r["link2"], r["link3"]))
        rows.append(
            '<tr data-s="%s"><td><b>%s</b></td>'
            '<td class="mono">%d</td><td class="mono">%d</td>'
            '<td>%s</td><td>%s</td><td>%s</td>'
            '<td class="note">%s</td>'
            '<td><a href="%s">详情 →</a></td></tr>'
            % (st, html.escape(r["name"]), r["unmapped"], r["ops"],
               _badge(r["link1"]), _badge(r["link2"]), _badge(r["link3"]),
               html.escape(r["note"][:60]), page))

        html_detail = u"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>%s — 三段链路</title><style>%s</style></head><body>
<header><h1>%s</h1><div class="sub">源：%s</div></header>
<div class="wrap">
<h2>① MATLAB → MIR　（算子 %d ｜ 未映射 %d）</h2><pre>%s</pre>
<h2>② 生成的 C</h2><pre>%s</pre>
<h2>② 运行输出</h2><pre>%s</pre>
<h2>③ C → MIR（反推）</h2><pre>%s</pre>
<p class="note">口径：不生成 mlc_op_* 调用而由发射器内联展开的算子
（MASK / FIND2 / FIND3 / ISEQUAL / COPY / SETIDX），在 ③ 里不计为差异。</p>
</div></body></html>""" % (
            html.escape(r["name"]), CSS, html.escape(r["name"]),
            html.escape(os.path.basename(r["src"])),
            r["ops"], r["unmapped"], html.escape(r["mir"][:6000]),
            html.escape(r["c"][:6000]), html.escape(r["run"] or "(未运行)"),
            html.escape(r["back"][:6000]))
        io.open(os.path.join(det, r["name"] + ".html"), "w",
                encoding="utf-8", newline="\n").write(html_detail)

    doc = u"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>三段链路大规模测试</title><style>%s</style></head><body>
<header>
  <h1>三段链路大规模测试：MATLAB → MIR → C → MIR</h1>
  <div class="sub">%d 个函数 ｜ 每段的通过都有客观依据（未映射计数 / gcc 退出码 / 算子多重集）</div>
</header>
<div class="wrap">
  <div class="kpis">%s</div>
  %s
  %s
  <h2>逐函数结果</h2>
  <div class="filters">
    <button data-f onclick="filt('all',this)" class="on">全部</button>
    <button data-f onclick="filt('ok',this)">三段全通</button>
    <button data-f onclick="filt('fail',this)">含失败</button>
    <button onclick="setTheme()">明暗切换</button>
  </div>
  <table>
    <tr><th>函数</th><th>未映射</th><th>算子</th>
        <th>① MIR</th><th>② C</th><th>③ 反推</th><th>说明</th><th></th></tr>
    %s
  </table>
  <p class="note" style="margin-top:16px">
  ②「通过」= m2c 构建成功 + gcc 编译通过 + 生成的 exe 真的跑出输出（不只是"能生成"）。<br>
  ③「通过」= 从生成的 C 反推出的算子 id 多重集与源 MIR 相等。
  </p>
</div>
<script>%s</script></body></html>""" % (CSS, n, kpis, bar, kind_block, "\n".join(rows), JS)

    p = os.path.join(outdir, "index.html")
    io.open(p, "w", encoding="utf-8", newline="\n").write(doc)
    return p, (n, l1, l2, l3, full)


def collect(paths, limit):
    files = []
    for p in paths:
        if os.path.isfile(p) and p.endswith(".m"):
            files.append(p)
        elif os.path.isdir(p):
            got = sorted(os.path.join(p, f) for f in os.listdir(p) if f.endswith(".m"))
            files.extend(got[:limit] if limit else got)
    return files


def main():
    ap = argparse.ArgumentParser(description="三段链路大规模测试 → HTML 报告")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--limit", type=int, default=25)
    a = ap.parse_args()

    if not os.path.isfile(M2C):
        print("m2c 未构建：cd rust/m2c && cargo build --release")
        return 2
    if os.path.isdir(a.out) and os.listdir(a.out):
        print("输出目录非空，拒绝写入：%s（避免与旧产物静默合并）" % a.out)
        return 2

    files = collect(a.paths, a.limit)
    if not files:
        print("没有找到 .m")
        return 2
    base = WORK if os.path.isdir(WORK) else None
    d = tempfile.mkdtemp(prefix="m2c_3l_rpt_", dir=base)

    recs = []
    for i, f in enumerate(files, 1):
        sys.stdout.write("\r[%d/%d] %s   " % (i, len(files), os.path.basename(f)))
        sys.stdout.flush()
        recs.append(analyze_one(f, d))
    sys.stdout.write("\n")

    # 失败原因的**类型聚合**：报告要能回答"卡在哪"，而不只是"过了几个"。
    kinds = collections.Counter()
    for r in recs:
        for ln in (r.get("mir") or "").splitlines():
            if ln.startswith("# why:"):
                kinds[ln[6:].strip()] += 1
        if not r.get("mir"):
            kinds["(源解析失败)"] += 1
    total_kind = sum(kinds.values())
    krows = "".join(
        '<tr><td><span class="mono">%s</span></td><td class="mono">%d</td>'
        '<td><div class="bar"><i style="width:%.1f%%;background:var(--fail)"></i></div></td></tr>'
        % (html.escape(k), v, 100.0 * v / total_kind if total_kind else 0)
        for k, v in kinds.most_common(10))

    if krows:
        kblock = ('\n  <h2>① 阶段失败原因（按卡点类型聚合，共 %d 条）</h2>\n'
                  '  <table><tr><th>卡点</th><th>条数</th><th>占比</th></tr>%s</table>\n'
                  % (total_kind, krows))
    else:
        kblock = ""
    p, (n, l1, l2, l3, full) = write_report(recs, a.out, kblock)
    print("三段：① %d/%d ｜ ② %d/%d ｜ ③ %d/%d ｜ 三段全通 %d"
          % (l1, n, l2, n, l3, n, full))
    print("已写出 %s（%.1f KB）" % (p, os.path.getsize(p) / 1024.0))
    print("产物目录：%s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
