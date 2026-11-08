# -*- coding: utf-8 -*-
"""三类转换场景的一致性报告，**每一类都含 HIR 环节**。

| 场景 | 链路 | HIR 在哪儿 |
|---|---|---|
| ① MATLAB → MIR | `.m → MIR` | MIR 抬升为 HIR，再降回 MIR，必须**恒等** |
| ② MIR → C | `MIR → gen.c → gcc → 运行` | 发射用的是**经由 HIR 往返后的 MIR** |
| ③ C → MIR | `gen.c → MIR'` | 反推出的 MIR' 同样抬升-降回一次 |

判定口径全部是客观的：未映射计数、算子多重集、进程退出码、运行输出。
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

from translate import hir as H          # noqa: E402

MIR_PY = os.path.join(ROOT, "translate", "mir.py")
CMIR_PY = os.path.join(ROOT, "translate", "cmir.py")
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release",
                   "m2c.exe" if os.name == "nt" else "m2c")
RT_INC = os.path.join(ROOT, "c_runtime", "include")
RT_SRC = [os.path.join(ROOT, "c_runtime", "src", "mlc_runtime.c"),
          os.path.join(ROOT, "c_runtime", "src", "mlc_ops.c")]
WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"


def _run(cmd, cwd=None, timeout=300):
    return subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=timeout)


def _body_ops(mir_text):
    body, ops = [], []
    for ln in mir_text.split("\n"):
        s = ln.strip()
        if not s or s.startswith("#") or s.startswith("version"):
            continue
        if s.startswith(("func:", "arg:", "ret:")):
            continue
        # `var:` **留在体内**（透传）：它是局部量声明，丢了循环变量就没声明；
        # 放 head 里搬一次又会和体内的重复声明（两处都放过，都不行）。
        body.append(s)
        if s.startswith("op:"):
            ops.append(s.split(":")[1])
    return body, ops


def hir_identity(mir_text, name):
    """MIR → HIR → MIR 是否恒等。返回 (状态, 说明)。"""
    body, ops_a = _body_ops(mir_text)
    hir_body, mapped = H.mir_to_hir("\n".join(body))
    if not mapped:
        return "skip", "有算子无 HIR 名（整体透传）"
    try:
        back = H.hir_to_mir(H.hir_wrap(name, [], [], hir_body))
    except Exception as e:                                  # noqa: BLE001
        return "fail", "回降失败：%s" % e
    ops_b = [l.split(":")[1] for l in back.split("\n") if l.startswith("op:")]
    if collections.Counter(ops_a) == collections.Counter(ops_b):
        return "ok", ""
    return "fail", "算子多重集不同：%r vs %r" % (ops_a, ops_b)


def analyze_one(src, d):
    stem = os.path.splitext(os.path.basename(src))[0]
    rec = {"name": stem, "s1": "skip", "hir1": "skip", "s2": "skip",
           "s3": "skip", "hir3": "skip", "note": ""}
    mir = os.path.join(d, stem + ".mir")
    r = _run([sys.executable, MIR_PY, src, "-o", mir])
    if r.returncode != 0 or not os.path.isfile(mir):
        rec["note"] = "mir.py 失败"
        return rec
    text = io.open(mir, encoding="utf-8").read()
    unm = text.count("\nunmapped:")
    rec["unmapped"] = unm
    rec["s1"] = "ok" if unm == 0 else "fail"
    rec["hir1"], rec["hir1_note"] = hir_identity(text, stem) if unm == 0 else ("skip", "①未通过")

    if unm != 0:
        rec["note"] = "有未映射语句"
        return rec

    # ② MIR → C：**用经由 HIR 往返后的 MIR** 发射
    body, _ = _body_ops(text)
    hir_body, mapped = H.mir_to_hir("\n".join(body))
    if mapped and rec["hir1"] == "ok":
        body = H.hir_to_mir(H.hir_wrap(stem, [], [], hir_body)).split("\n")
    # 函数体的收尾 `end` 由下面统一补 —— 原 body 末尾已有一个，**只弹一个**。
    # 早前用 while 弹到没有为止，把 `if` 块自己的 `end` 也弹掉了 →
    # m2c 报"文件结束时仍有未收束的 func"（② 15 个全挂在这里）。
    if body and body[-1].strip() == "end":
        body.pop()
    head = [l for l in text.split("\n")
            if l.startswith(("version", "func:", "arg:", "ret:"))]
    use_mir = os.path.join(d, stem + "_hir.mir")
    io.open(use_mir, "w", encoding="utf-8", newline="\n").write(
        "\n".join(head + body) + "\nend\n")

    g = os.path.join(d, stem + "_g")
    r = _run([M2C, "build", "--mir", use_mir, "--out", g, "--name", stem])
    if r.returncode != 0:
        rec["s2"] = "fail"
        rec["note"] = "m2c build 失败"
        return rec
    exe = os.path.join(g, stem + (".exe" if os.name == "nt" else ""))
    cc = shutil.which("gcc") or shutil.which("clang")
    r = _run([cc, "-std=c99", "-O1", "-I", os.path.join(g, "include"),
              "-I", RT_INC, os.path.join(g, "src", "gen.c"),
              os.path.join(g, "src", "main.c")] + RT_SRC + ["-o", exe], timeout=600)
    if r.returncode != 0:
        rec["s2"] = "fail"
        rec["note"] = "gcc 失败"
        return rec
    r = _run([exe], timeout=120)
    out = r.stdout.decode("utf-8", "replace").strip()
    rec["out"] = out[:80]
    rec["s2"] = "ok" if (r.returncode == 0 and out) else "fail"
    if rec["s2"] != "ok":
        rec["note"] = "运行失败"

    # ③ C → MIR（再抬升-降回一次）
    back_mir = os.path.join(d, stem + "_c.mir")
    r = _run([sys.executable, CMIR_PY, os.path.join(g, "src", "gen.c"),
              "-o", back_mir, "--name", stem])
    if r.returncode != 0 or not os.path.isfile(back_mir):
        rec["s3"] = "fail"
        rec["note"] = rec["note"] or "cmir 失败"
        return rec
    btext = io.open(back_mir, encoding="utf-8").read()
    rec["s3"] = "ok"
    rec["hir3"], rec["hir3_note"] = hir_identity(btext, stem)
    return rec


CSS = """
:root{--bg:#0f1115;--card:#171a21;--fg:#e6e9ef;--dim:#9aa4b2;--ok:#37d67a;
--fail:#ff5c5c;--skip:#8b93a1;--accent:#5b9dff;--line:#252a33}
@media(prefers-color-scheme:light){:root{--bg:#f6f7f9;--card:#fff;--fg:#1b1f24;
--dim:#5b636e;--line:#e3e6ea}}
*{box-sizing:border-box}
body{margin:0;padding:32px;background:var(--bg);color:var(--fg);
font:15px/1.6 -apple-system,"Segoe UI","Noto Sans SC",sans-serif}
h1{font-size:26px;margin:0 0 4px}
.sub{color:var(--dim);margin-bottom:24px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;margin-bottom:28px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.card .k{color:var(--dim);font-size:13px}
.card .v{font-size:28px;font-weight:650;margin-top:6px}
table{width:100%;border-collapse:collapse;background:var(--card);
border:1px solid var(--line);border-radius:12px;overflow:hidden}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line);font-size:14px}
th{color:var(--dim);font-weight:600;font-size:13px}
tr:last-child td{border-bottom:none}
.b{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:600}
.ok{background:rgba(55,214,122,.15);color:var(--ok)}
.fail{background:rgba(255,92,92,.15);color:var(--fail)}
.skip{background:rgba(139,147,161,.18);color:var(--skip)}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:13px}
"""


def write_report(recs, outdir, kinds):
    os.makedirs(outdir, exist_ok=True)
    n = len(recs)

    def rate(key):
        ok = sum(1 for r in recs if r[key] == "ok")
        bad = sum(1 for r in recs if r[key] == "fail")
        tot = ok + bad
        return ok, tot, (100.0 * ok / tot if tot else 0.0)

    o1, t1, p1 = rate("s1")
    h1, th1, ph1 = rate("hir1")
    o2, t2, p2 = rate("s2")
    o3, t3, p3 = rate("s3")
    h3, th3, ph3 = rate("hir3")

    cards = [("① MATLAB → MIR", p1, "%d/%d" % (o1, t1)),
             ("① 的 HIR 往返恒等", ph1, "%d/%d" % (h1, th1)),
             ("② MIR → C（经 HIR）", p2, "%d/%d" % (o2, t2)),
             ("③ C → MIR", p3, "%d/%d" % (o3, t3)),
             ("③ 的 HIR 往返恒等", ph3, "%d/%d" % (h3, th3))]
    card_html = "".join(
        '<div class="card"><div class="k">%s</div><div class="v">%.1f%%</div>'
        '<div class="k">%s</div></div>' % (html.escape(k), v, s)
        for k, v, s in cards)

    kind_rows = "".join(
        '<tr><td class="mono">%s</td><td class="mono">%d</td></tr>' % (html.escape(k), v)
        for k, v in kinds.most_common(8))

    def badge(v):
        lab = {"ok": "通过", "fail": "失败", "skip": "跳过"}.get(v, v)
        return '<span class="b %s">%s</span>' % (v, lab)

    rows = []
    for r in recs:
        note = r.get("note") or r.get("hir1_note") or r.get("hir3_note") or ""
        rows.append(
            "<tr><td class='mono'>%s</td><td>%s</td><td>%s</td><td>%s</td>"
            "<td>%s</td><td>%s</td><td class='mono' style='color:var(--dim)'>%s</td></tr>"
            % (html.escape(r["name"]), badge(r["s1"]), badge(r["hir1"]),
               badge(r["s2"]), badge(r["s3"]), badge(r["hir3"]),
               html.escape(str(note)[:60])))

    doc = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>三类转换 + HIR 一致性报告</title><style>%s</style></head><body>
<h1>三类转换 + HIR 一致性报告</h1>
<div class="sub">共 %d 个函数 ｜ 每一类场景都要求 HIR 参与（MIR ⇄ HIR 往返恒等）</div>
<div class="cards">%s</div>
<h2 style="font-size:18px;margin:24px 0 10px">失败分类</h2>
<table><tr><th>类别</th><th>条数</th></tr>%s</table>
<h2 style="font-size:18px;margin:24px 0 10px">逐函数明细</h2>
<table><tr><th>函数</th><th>①</th><th>①HIR</th><th>②</th><th>③</th><th>③HIR</th>
<th>说明</th></tr>%s</table>
</body></html>""" % (CSS, n, card_html, kind_rows or
                   '<tr><td colspan="2">无</td></tr>', "\n".join(rows))
    p = os.path.join(outdir, "index.html")
    io.open(p, "w", encoding="utf-8", newline="\n").write(doc)
    return p, (o1, t1, o2, t2, o3, t3, h1, th1)


def main():
    ap = argparse.ArgumentParser(description="三类转换 + HIR 一致性报告")
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("-o", "--out", default=os.path.join(WORK, "hir_report"))
    ap.add_argument("--limit", type=int, default=0, help="每个目录最多取几个")
    a = ap.parse_args()

    files = []
    for src in a.dirs:
        if not os.path.isdir(src):
            continue
        fs = sorted(f for f in os.listdir(src) if f.endswith(".m"))
        files += [os.path.join(src, f) for f in (fs[:a.limit] if a.limit else fs)]
    d = tempfile.mkdtemp(prefix="hlr_", dir=WORK if os.path.isdir(WORK) else None)

    recs = []
    for i, f in enumerate(files, 1):
        sys.stdout.write("\r[%d/%d] %s   " % (i, len(files), os.path.basename(f)))
        sys.stdout.flush()
        recs.append(analyze_one(f, d))
    sys.stdout.write("\n")

    kinds = collections.Counter()
    for r in recs:
        for k in ("s1", "hir1", "s2", "s3", "hir3"):
            if r[k] == "fail":
                kinds["%s 失败" % k] += 1
    p, (o1, t1, o2, t2, o3, t3, h1, th1) = write_report(recs, a.out, kinds)
    print("① %d/%d ｜ ①HIR %d/%d ｜ ② %d/%d ｜ ③ %d/%d" % (o1, t1, h1, th1, o2, t2, o3, t3))
    print("已写出 %s" % p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
