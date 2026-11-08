# -*- coding: utf-8 -*-
"""生成 `flow/catalog.html`：**一处列全所有流程图**。

## 为什么要有它

`flow/` 下并存三套图集，各自的发现路径不同：

| 体系 | 形态 | 发现方式 |
|---|---|---|
| `flow/figures/` | 18 张可交互 HTML | `flow/index.html` 的卡片 |
| `flow/diagrams/` | 13 张 SVG（中英各一份） | README 内嵌 |
| `flow/archify/` | 早期双版体系 | 历史 |

结果：**没有任何一处能回答"一共有几张图、哪张过期了"**。这个页面就是那个地方。

## 状态列是算出来的，不是写的

每张交互图都记着自己渲染时的 `meta.repository.revision`。
与当前 HEAD 比较即可得出"落后 N 个提交"——**没有这份回执的图，根本不知道自己过期了**。
"""
import io
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLOW = os.path.join(ROOT, "flow")


def git(*args):
    # 子进程必须切 stdin（`check_subprocess_hygiene` 的门，R728 踩到过）
    r = subprocess.run(["git"] + list(args), cwd=ROOT,
                       stdin=subprocess.DEVNULL, timeout=120,
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return r.stdout.decode("utf-8", "replace").strip()


def head():
    return git("rev-parse", "HEAD")


def lag(rev):
    """rev..HEAD 的提交数；不可解析返回 None。"""
    if not rev or not re.fullmatch(r"[a-fA-F0-9]{40}", rev or ""):
        return None
    out = git("rev-list", "--count", "%s..HEAD" % rev)
    try:
        return int(out)
    except ValueError:
        return None


def _id_by_dir():
    """从 `flow/index.html` 取 目录 → 编号 的映射（旧图标题里没有 F 编号）。"""
    p = os.path.join(FLOW, "index.html")
    if not os.path.isfile(p):
        return {}
    h = io.open(p, encoding="utf-8").read()
    out = {}
    for m in re.finditer(r'<span class="id">(F\d\d)</span>(.*?)</h3>.*?href="figures/([^/]+)/', h, re.S):
        out[m.group(3)] = m.group(1)
    return out


def figures():
    base = os.path.join(FLOW, "figures")
    idmap = _id_by_dir()
    rows = []
    for d in sorted(os.listdir(base)):
        p = os.path.join(base, d)
        if not os.path.isdir(p):
            continue
        cand = os.path.join(p, "candidate.json")
        if not os.path.isfile(cand):
            continue
        try:
            j = json.load(io.open(cand, encoding="utf-8"))
        except Exception:                                  # noqa: BLE001
            continue
        meta = j.get("meta") or {}
        out = meta.get("output") or ""
        html = os.path.join(p, out)
        if not os.path.isfile(html):
            hs = [f for f in os.listdir(p) if f.endswith(".html")]
            html = os.path.join(p, hs[0]) if hs else None
        rev = (meta.get("repository") or {}).get("revision")
        m = re.search(r"(F\d\d)", meta.get("title") or "")
        fid = m.group(1) if m else idmap.get(d, "")
        rows.append({
            "id": fid,
            "title": re.sub(r"^F\d+\s*", "", meta.get("title") or d),
            "dir": d,
            "html": os.path.relpath(html, FLOW).replace("\\", "/") if html else "",
            "rev": rev or "",
            "lag": lag(rev),
            "kind": "交互",
        })
    return rows


def diagrams():
    base = os.path.join(FLOW, "diagrams")
    if not os.path.isdir(base):
        return []
    names = sorted(os.listdir(base))
    out = {}
    for n in names:
        if not n.endswith(".svg"):
            continue
        m = re.match(r"(f\d+)-(.+?)(\.zh-CN)?\.svg$", n)
        if not m:
            continue
        fid = m.group(1).upper()
        e = out.setdefault(fid, {"id": fid, "title": m.group(2).replace("-", " "),
                                 "zh": "", "en": ""})
        if m.group(3):
            e["zh"] = n
        else:
            e["en"] = n
    rows = []
    for fid in sorted(out):
        e = out[fid]
        rows.append({"id": fid, "title": e["title"], "dir": "diagrams",
                     "html": e["zh"] or e["en"], "en": e["en"], "zh": e["zh"],
                     "rev": "", "lag": None, "kind": "SVG"})
    return rows


CSS = """
:root{--bg:#0f1115;--card:#171a21;--fg:#e6e9ef;--dim:#9aa4b2;--ok:#37d67a;
--warn:#f5a524;--line:#252a33;--accent:#5b9dff}
@media(prefers-color-scheme:light){:root{--bg:#f6f7f9;--card:#fff;--fg:#1b1f24;
--dim:#5b636e;--line:#e3e6ea}}
*{box-sizing:border-box}
body{margin:0;padding:32px;background:var(--bg);color:var(--fg);
font:15px/1.65 -apple-system,"Segoe UI","Noto Sans SC",sans-serif}
h1{font-size:26px;margin:0 0 6px}
.sub{color:var(--dim);margin-bottom:22px}
table{width:100%;border-collapse:collapse;background:var(--card);
border:1px solid var(--line);border-radius:12px;overflow:hidden;margin-bottom:26px}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line);font-size:14px}
th{color:var(--dim);font-size:13px;font-weight:600}
tr:last-child td{border-bottom:none}
.mono{font-family:ui-monospace,Consolas,monospace}
.b{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:600}
.now{background:rgba(55,214,122,.15);color:var(--ok)}
.stale{background:rgba(245,165,36,.16);color:var(--warn)}
.na{background:rgba(154,164,178,.16);color:var(--dim)}
a{color:var(--accent)}
"""


def render(figs, svgs):
    n_stale = sum(1 for r in figs if r["lag"] not in (None, 0))
    h = head()

    def badge(r):
        """**三档有语义**，不是"落后 N 个提交"（那个数字每次提交都变，等于噪声）。

        0 → 现行；1~10 → 略旧（还在同一批改动里）；>10 → 已过时（跨代了）。
        """
        if r["lag"] is None:
            return '<span class="b na">无回执</span>'
        if r["lag"] == 0:
            return '<span class="b now">现行</span>'
        if r["lag"] <= 10:
            return '<span class="b now">近期</span>'
        return '<span class="b stale">已过时</span>'

    tr = []
    for r in figs:
        tr.append('<tr><td class="mono">%s</td><td>%s</td><td>%s</td>'
                  '<td><a href="%s">打开</a></td></tr>'
                  % (r["id"] or "-", r["title"], badge(r), r["html"]))
    ts = []
    for r in svgs:
        links = []
        if r.get("zh"):
            links.append('<a href="diagrams/%s">中</a>' % r["zh"])
        if r.get("en"):
            links.append('<a href="diagrams/%s">EN</a>' % r["en"])
        ts.append('<tr><td class="mono">%s</td><td>%s</td><td>%s</td></tr>'
                  % (r["id"], r["title"], " · ".join(links)))

    return """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>流程图目录 · MATLABC</title><style>%s</style></head><body>
<h1>流程图目录</h1>
<div class="sub">共 <b>%d</b> 张交互图 + <b>%d</b> 张静态 SVG ｜ 其中 <b>%d</b> 张交互图落后于当前代码（%s）
｜ 返回 <a href="index.html">图集首页</a></div>

<h2 style="font-size:18px;margin:0 0 10px">交互图（可点开、可缩放）</h2>
<table><tr><th>编号</th><th>标题</th><th>状态</th><th>入口</th></tr>%s</table>

<h2 style="font-size:18px;margin:0 0 10px">静态分层图（中英双版）</h2>
<table><tr><th>编号</th><th>标题</th><th>打开</th></tr>%s</table>

<h2 style="font-size:18px;margin:0 0 10px">怎么读</h2>
<p class="sub">
① 先看 <a href="index.html#f-f30">F30</a>（五层总览）与 <a href="index.html#f-f34">F34</a>（图集地图）；
② 想懂一条语句的去向，看 <a href="index.html#f-f31">F31</a>；
③ 要生成 C 工程，看 <a href="index.html#f-f32">F32</a> 与 <a href="index.html#f-f35">F35</a>；
④ 想确认「数值真的对」，看 <a href="index.html#f-f36">F36</a> 与 <a href="index.html#f-f33">F33</a>。
</p>
</body></html>""" % (CSS, len(figs), len(svgs), n_stale, h[:8], "\n".join(tr), "\n".join(ts))


def main():
    figs = figures()
    svgs = diagrams()
    for r in figs:
        if r["lag"] not in (None, 0):
            print("  落后 %2d 个提交：%s %s" % (r["lag"], r["id"], r["title"][:40]))
    p = os.path.join(FLOW, "catalog.html")
    io.open(p, "w", encoding="utf-8", newline="\n").write(render(figs, svgs))
    print("已写出 flow/catalog.html（交互 %d ｜ SVG %d）" % (len(figs), len(svgs)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
