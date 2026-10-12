# -*- coding: utf-8 -*-
"""C 前端分页静态站点渲染（`--lang c --browse` 的站点主体）。

为什么分页
----------
C 前端原有的单页报告 `c_report.html` 把「全部函数 + 全部调用边 + 全部未解析调用
+ 全部 include 边」一次性灌进一个 HTML。小样本没问题，但语料级规模下不可用：

* 实测 `fs` 子树（2,085 文件 / 3.8 万函数 / 11.6 万调用边）单页已 **30.6 MB**；
* 逐行线性外推整棵 Linux 内核（62,704 文件 / 74.3 万函数 / 706 万调用边）
  ⇒ 单页约 **1 GB**，浏览器无法解析，渲染本身也要十几分钟。

本模块改为「小文件分页」：页面数与 C 文件数同阶，**单页恒为 KB 级**。

    index.html          概览：KPI 卡片 + 告警构成（SVG 环形）+ 规则表 + 目录分组文件清单
    file/<扁平名>.html   每个 C 文件一页：函数表 / include / 告警明细 / 出入调用 / 未解析
    rule/<kind>.html    每条检查规则一页：按文件聚合计数的 TOP + 有界明细
    browse.css          站点样式（调用方传入的基础样式 + 本模块自有片段）

两条硬约束
----------
1. **零 JS、零 CDN**：所有图表在服务端算成 SVG 后注入，断网双击即可打开。
   （R75 教训：外链 Chart.js 一旦被 CDN 拖慢，整页脚本都不执行，KPI/图表全空白。）
2. **路径口径用 `path` 相对 `root` 重算，不用 `rel`**：本模块**不 import
   `matlabc` 的任何符号**，而 `rel` 是谁算的、按哪个根算的都不在它的契约里：
   R90 之前 `rel` 相对**当前工作目录**算，语料级规模下 `main.c` / `core.c`
   必然重名、页面名会互相覆盖（R76/R78 的 C-2 站点就是靠这里绕开的）；
   **R90 起 `rel` 已改为相对被分析根，但本模块的判据不建立在那上面** ——
   「上游口径变了而没人重新审这个渲染器」正是 C28-6 记下的那类隐患。
   所以这里**一律自己算**，不看 `rel`。

本模块只依赖标准库，且**不借用 matlabc 的任何符号**（`renderers/` 子树的
import 期回边由图门 G1/G7 钉住，借用必须走 `renderers/_late.py`）。
"""

import html as html_mod
import io
import math
import os
import re

# ---------------------------------------------------------------------------
# 样式：browse.css = 调用方传入的基础样式（BROWSE_CSS）+ 本片段。
# 本模块只补自己用到的 .cs-* 类；基础样式里已有的类不重复定义。
# ---------------------------------------------------------------------------
CSITE_CSS = """
.cs-cards{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}
.cs-card{flex:1 1 150px;min-width:150px;border:1px solid #d0d7de;border-radius:8px;padding:10px 12px}
.cs-card .num{display:block;font-size:22px;font-weight:600}
.cs-card .lbl{font-size:12px;color:#57606a}
.cs-cols{display:flex;flex-wrap:wrap;gap:20px;align-items:flex-start}
.cs-fig{margin:10px 0}
table.cs-t{border-collapse:collapse;width:100%;font-size:13px}
table.cs-t th,table.cs-t td{border:1px solid #d0d7de;padding:3px 7px;text-align:left;vertical-align:top}
table.cs-t thead th{background:#f6f8fa}
.cs-mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}
.cs-num{text-align:right;font-variant-numeric:tabular-nums}
details.cs-dir{border:1px solid #d0d7de;border-radius:6px;margin:4px 0;padding:4px 8px}
details.cs-dir>summary{cursor:pointer;font-weight:600}
.cs-legend{display:flex;flex-wrap:wrap;gap:10px;font-size:13px;margin:8px 0}
.cs-legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px}
.cs-note{background:#fff8c5;border:1px solid #d4a72c;border-radius:6px;padding:6px 9px;font-size:13px}
.cs-lvl-error{color:#cf222e;font-weight:600}
.cs-lvl-warning{color:#9a6700}
.cs-lvl-note{color:#57606a}
.cs-snip{background:#f6f8fa;border-left:3px solid #d0d7de;padding:3px 8px;font-family:ui-monospace,Consolas,monospace;font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere}
:root[data-theme="dark"] .cs-card,:root[data-theme="dark"] details.cs-dir{border-color:#30363d}
:root[data-theme="dark"] table.cs-t th,:root[data-theme="dark"] table.cs-t td{border-color:#30363d}
:root[data-theme="dark"] table.cs-t thead th{background:#161b22}
:root[data-theme="dark"] .cs-note{background:#2d2a1b;border-color:#9e6a03}
:root[data-theme="dark"] .cs-snip{background:#0d1117;border-left-color:#30363d}
@media print{details.cs-dir{break-inside:avoid}}
"""

# 规则配色：显式登记，保证「同一条规则在任何页面上颜色恒定」（纯索引取色会随
# 页面内规则集合变化而漂移，同一张图在两个页面上不同色是误导）。
KIND_COLORS = {
    "c_uninit_pointer": "#cf222e",
    "c_array_oob": "#bc4c00",
    "c_use_after_free": "#8250df",
    "c_double_free": "#a40e26",
    "c_buffer_overflow": "#bf3989",
    "c_missing_return": "#9a6700",
    "c_missing_guard": "#0550ae",
    "c_missing_doc": "#6e7781",
    "c_unused_static": "#1a7f37",
    "c_too_many_params": "#0969da",
}
_KIND_COLOR_FALLBACK = (
    "#0969da", "#cf222e", "#1a7f37", "#9a6700", "#8250df", "#0a3069",
    "#bf3989", "#bc4c00", "#116329", "#6e7781",
)


def _esc(v):
    if v is None:
        return ""
    return html_mod.escape(u"%s" % (v,))


def _num(n):
    try:
        return u"{:,}".format(int(n))
    except (TypeError, ValueError):
        return u"%s" % (n,)


def _flat(rel):
    """把相对路径扁平化成安全的单层文件名。

    为什么扁平化而不是映射成多级目录：Windows 的 MAX_PATH=260，语料里的相对
    路径本身就有 150+ 字符，再加 `file/` 前缀与 `.html` 后缀会溢出；扁平化后
    文件名长度只与路径长度同阶，且不产生新目录（少一层 FS 压力）。
    """
    s = (rel or u"").replace(u"\\", u"/")
    s = re.sub(r"[^A-Za-z0-9._-]+", u"__", s)
    s = s.strip(u"_")
    return s or u"_"


def _kind_color(kind):
    if kind in KIND_COLORS:
        return KIND_COLORS[kind]
    return _KIND_COLOR_FALLBACK[abs(hash(kind)) % len(_KIND_COLOR_FALLBACK)] \
        if kind else "#6e7781"


def _clip(s, n):
    """裁剪过长标签：保留尾部（路径的辨识度在尾部），前缀用省略号。"""
    s = u"%s" % (s if s is not None else u"")
    if len(s) <= n:
        return s
    return u"\u2026" + s[-(n - 1):]


def _bar_svg(rows, label_w=250, bar_w=430, bar_h=15, gap=7, color="#0969da"):
    """水平条形图（服务端 SVG）。rows = [(label, value, href or None)]。"""
    rows = [r for r in rows if r[1] > 0]
    if not rows:
        return u'<p class="muted">（无数据）</p>'
    vmax = max(r[1] for r in rows) or 1
    W = label_w + bar_w + 120
    H = len(rows) * (bar_h + gap) + gap
    nclip = max(8, int(label_w / 6.6))
    out = [u'<svg class="cs-fig" viewBox="0 0 %d %d" width="100%%" '
           u'height="%d" role="img" aria-label="条形图">' % (W, H, H)]
    y = gap
    for (label, value, href) in rows:
        w = max(1.0, float(value) * bar_w / vmax)
        lab = _esc(_clip(label, nclip))
        if href:
            lab = u'<a href="%s">%s</a>' % (_esc(href), lab)
        out.append(u'<text x="6" y="%d" font-size="11" fill="currentColor">%s</text>'
                   % (y + bar_h - 3, lab))
        out.append(u'<rect x="%d" y="%d" width="%.1f" height="%d" fill="%s" rx="2"/>'
                   % (label_w, y, w, bar_h, color))
        out.append(u'<text x="%.1f" y="%d" font-size="11" fill="currentColor">%s</text>'
                   % (label_w + w + 6.0, y + bar_h - 3, _num(value)))
        y += bar_h + gap
    out.append(u"</svg>")
    return u"".join(out)


def _donut_svg(rows, size=190):
    """环形图（服务端 SVG，用 stroke-dasharray 画弧）。rows = [(label, value, color)]。"""
    rows = [r for r in rows if r[1] > 0]
    total = sum(r[1] for r in rows)
    if not rows or not total:
        return u'<p class="muted">（无数据）</p>'
    r_out = size / 2.0 - 3
    r_mid = r_out * 0.78
    sw = r_out * 0.44
    circ = 2 * math.pi * r_mid
    cx = cy = size / 2.0
    parts = [u'<svg class="cs-fig" viewBox="0 0 %d %d" width="%d" height="%d" '
             u'role="img" aria-label="环形图">' % (size, size, size, size)]
    off = 0.0
    for (_label, value, color) in rows:
        dash = circ * (float(value) / total)
        parts.append(
            u'<circle cx="%.2f" cy="%.2f" r="%.2f" fill="none" stroke="%s" '
            u'stroke-width="%.2f" stroke-dasharray="%.2f %.2f" '
            u'stroke-dashoffset="%.2f" transform="rotate(-90 %.2f %.2f)"/>'
            % (cx, cy, r_mid, color, sw, dash, max(0.0, circ - dash),
               -off, cx, cy))
        off += dash
    parts.append(u'<text x="%.2f" y="%.2f" text-anchor="middle" font-size="15" '
                 u'fill="currentColor">%s</text>' % (cx, cy + 5.0, _num(total)))
    parts.append(u"</svg>")
    return u"".join(parts)


def _legend_html(rows, up=""):
    """环形图图例：色块 + 规则名 + 条数 + 占比。rows = [(kind, label, value)]。"""
    total = sum(r[2] for r in rows) or 1
    out = [u'<div class="cs-legend">']
    for (kind, label, value) in rows:
        if value <= 0:
            continue
        out.append(u'<span><i style="background:%s"></i>'
                   u'<a href="%srule/%s.html">%s</a> %s · %.1f%%</span>'
                   % (_kind_color(kind), up, _esc(kind), _esc(label),
                      _num(value), 100.0 * value / total))
    out.append(u"</div>")
    return u"".join(out)


def _head(title, up, brand=u"C 语言前端分析站点"):
    out = []
    A = out.append
    A(u'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">')
    A(u'<meta name="viewport" content="width=device-width, initial-scale=1">')
    A(u"<title>%s</title>" % _esc(title))
    A(u'<link rel="stylesheet" href="%sbrowse.css">' % up)
    A(u"</head><body>")
    A(u'<a class="skip-link" href="#main-content">跳到主内容</a>')
    A(u'<header><span class="brand">%s</span>' % _esc(brand))
    if up:
        A(u'<a href="%sindex.html">&larr; 返回索引</a>' % up)
    A(u'<a href="%sc_report.html">单页完整表 &rarr;</a></header>' % up)
    A(u'<main id="main-content">')
    return out


def _cards(pairs):
    """KPI 卡片组。pairs = [(数值, 标签)]。"""
    out = [u'<div class="cs-cards">']
    for (v, lbl) in pairs:
        out.append(u'<div class="cs-card"><span class="num">%s</span>'
                   u'<span class="lbl">%s</span></div>' % (_num(v), _esc(lbl)))
    out.append(u"</div>")
    return u"".join(out)


def _read_lines(path):
    try:
        with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read().split(u"\n")
    except Exception:
        return None


def _write_text(path, text):
    """站点页一律 LF（与仓库「生成物 = LF」口径一致），并返回字节数。"""
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, "w", encoding="utf-8", newline=u"\n") as fh:
        fh.write(text)
    return len(text.encode(u"utf-8"))


def render_c_site(c_model, root, outdir, heuristics=None, css_text=None,
                  kind_meta_fn=None, max_rule_rows=2000,
                  max_file_alerts=500, top_complexity=20):
    """生成 C 前端分页站点，返回统计 dict。

    c_model       build_c_model 的返回值（files/functions/edges/unresolved/...）
    root          被分析目录（用于把绝对 path 换算成**唯一的**站点相对路径）
    outdir        站点输出目录（不存在则创建）
    heuristics    静态检查结果（每条含 file/line/func/kind/msg/level）
    css_text      基础样式（通常是 BROWSE_CSS）；本模块再追加 CSITE_CSS
    kind_meta_fn  kind -> {"label","level","category"}，缺省用本地兜底
    """
    files = list(c_model.get("files") or [])
    edges = list(c_model.get("edges") or [])
    unresolved = list(c_model.get("unresolved") or [])
    inc_edges = list(c_model.get("include_edges") or [])
    alerts = list(heuristics or [])
    outdir = str(outdir)
    root_abs = os.path.abspath(root) if root else None

    # ---- 1) 文件条目：显示路径一律「相对 root」**自己算**，不借 rel ----
    entries = []
    seen_flat = {}
    for pf in files:
        p = pf.get("path") or u""
        rel = u""
        if p and root_abs:
            try:
                rel = os.path.relpath(os.path.abspath(p), root_abs)
            except Exception:
                rel = u""
            rel = rel.replace(os.sep, u"/")
        if not rel or rel.startswith(u".."):
            rel = pf.get("rel") or (os.path.basename(p) if p else u"?")
        flat = _flat(rel)
        if flat in seen_flat:
            seen_flat[flat] += 1
            flat = u"%s__%d" % (flat, seen_flat[flat])
        else:
            seen_flat[flat] = 0
        entries.append({"rel": rel, "path": p or None, "flat": flat, "pf": pf})

    # ---- 2) 索引 ----
    # 告警的 file 字段用的是 pf["rel"]（`_rel_of` 的口径）⇒ 按它回指到条目。
    rel_to_entry = {}
    for e in entries:
        key = e["pf"].get("rel")
        if key is not None and key not in rel_to_entry:
            rel_to_entry[key] = e
    base_to_entry = {}
    for e in entries:
        base_to_entry.setdefault(os.path.basename(e["rel"]), e)

    alerts_by_flat = {}
    alerts_by_kind = {}
    kind_level = {}
    orphan_alerts = 0
    for a in alerts:
        f = a.get("file")
        e = rel_to_entry.get(f) or base_to_entry.get(os.path.basename(f or u""))
        if e is not None:
            alerts_by_flat.setdefault(e["flat"], []).append(a)
        else:
            orphan_alerts += 1
        k = a.get("kind") or u"?"
        alerts_by_kind.setdefault(k, []).append(a)
        kind_level[k] = a.get("level") or kind_level.get(k) or u"note"

    # 函数名 -> 定义所在文件页（供函数表里的调用跳转）
    func_home = {}
    for e in entries:
        for fn in e["pf"].get("functions") or []:
            nm = (fn.get("name") or u"").lower()
            if nm and nm not in func_home:
                func_home[nm] = e["flat"]

    # 被调用索引：callee 名 -> [(caller, 文件 rel, 行)]
    callers_of = {}
    edges_by_flat = {}
    fan_out = {}
    for (ca, cb, ln, f) in edges:
        callers_of.setdefault((cb or u"").lower(), []).append((ca, f, ln))
        e = rel_to_entry.get(f) or base_to_entry.get(os.path.basename(f or u""))
        if e is not None:
            edges_by_flat.setdefault(e["flat"], []).append((ca, cb, ln))
        fan_out[ca] = fan_out.get(ca, 0) + 1
    fan_in = {}
    for (cb, lst) in callers_of.items():
        fan_in[cb] = len(lst)

    # 未解析调用的**呈现索引**：按文件归组，仅供页面展示。
    # 注意命名 —— 它不是 IR 的 unresolved 容器（判定点唯一在 frontends/ir.py），
    # 叫 `*unresolved*` 会让 tools/check_ir_attribution.py 的 I1（「往含 unresolved
    # 的容器里新增条目」）把这里误判成第二个判定点，所以刻意用 missing 命名。
    missing_by_flat = {}
    for (nm, ln, f) in unresolved:
        e = rel_to_entry.get(f) or base_to_entry.get(os.path.basename(f or u""))
        if e is not None:
            missing_by_flat.setdefault(e["flat"], []).append((nm, ln))

    inc_edges_by_flat = {}
    for (frm, inc, to) in inc_edges:
        e = rel_to_entry.get(frm) or base_to_entry.get(os.path.basename(frm or u""))
        if e is not None:
            inc_edges_by_flat.setdefault(e["flat"], []).append((inc, to))

    def _meta(kind):
        if kind_meta_fn is not None:
            try:
                m = kind_meta_fn(kind) or {}
            except Exception:
                m = {}
        else:
            m = {}
        label = m.get("label") or kind
        level = m.get("level") or kind_level.get(kind) or u"note"
        cat = m.get("category") or u""
        return (label, level, cat)

    # ---- 3) 落盘 ----
    n_bytes = 0
    n_pages = 0

    def _emit(rel_path, text):
        n = _write_text(os.path.join(outdir, rel_path.replace(u"/", os.sep)), text)
        return n

    # 3a) 规则页
    kind_rows = []
    for k in sorted(alerts_by_kind):
        kind_rows.append((k, len(alerts_by_kind[k])))
    kind_rows.sort(key=lambda x: (-x[1], x[0]))
    for (k, cnt) in kind_rows:
        label, level, cat = _meta(k)
        rows = alerts_by_kind[k]
        per_file = {}
        for a in rows:
            per_file[a.get("file") or u"?"] = per_file.get(a.get("file") or u"?", 0) + 1
        top_files = sorted(per_file.items(), key=lambda x: (-x[1], x[0]))[:50]
        out = _head(u"%s · 规则明细" % label, u"../")
        out.append(u"<h1>%s <code class=\"cs-mono\">%s</code></h1>"
                   % (_esc(label), _esc(k)))
        out.append(u'<p class="muted">严重度 <span class="cs-lvl-%s">%s</span>'
                   u"%s</p>"
                   % (_esc(level), _esc(level),
                      (u" · 类别 " + _esc(cat)) if cat else u""))
        out.append(_cards([(cnt, u"告警条数"), (len(per_file), u"涉及文件"),
                           (len(set(a.get("func") for a in rows if a.get("func"))),
                            u"涉及函数")]))
        out.append(u"<h2>按文件计数 TOP 50</h2>")
        _bars = []
        for (f, c) in top_files:
            _e = rel_to_entry.get(f) or base_to_entry.get(os.path.basename(f or u""))
            _bars.append((f, c,
                          (u"../file/%s.html" % _e["flat"]) if _e is not None else u""))
        out.append(_bar_svg(_bars, label_w=230, bar_w=380, color=_kind_color(k)))
        out.append(u"<h2>明细（最多 %s 条）</h2>" % _num(max_rule_rows))
        if cnt > max_rule_rows:
            out.append(u'<div class="cs-note">本规则共 <b>%s</b> 条，此处仅展开前 '
                       u'<b>%s</b> 条（逐条展开会退化成 GB 级单页）。完整明细请到'
                       u"各文件页查看（下方「按文件计数」可直达）。</div>"
                       % (_num(cnt), _num(max_rule_rows)))
        out.append(u'<table class="cs-t"><thead><tr><th>文件</th><th class="cs-num">行</th>'
                   u"<th>函数</th><th>级别</th><th>说明</th></tr></thead><tbody>")
        shown = rows[:max_rule_rows]
        for a in shown:
            e = rel_to_entry.get(a.get("file")) or \
                base_to_entry.get(os.path.basename(a.get("file") or u""))
            link = (u'<a href="../file/%s.html">%s</a>' % (_esc(e["flat"]), _esc(e["rel"]))
                    if e is not None else _esc(a.get("file")))
            out.append(u'<tr><td>%s</td><td class="cs-num">%s</td>'
                       u'<td class="cs-mono">%s</td><td class="cs-lvl-%s">%s</td>'
                       u"<td>%s</td></tr>"
                       % (link, _num(a.get("line") or 0), _esc(a.get("func")),
                          _esc(a.get("level") or u"note"),
                          _esc(a.get("level") or u"note"), _esc(a.get("msg"))))
        out.append(u"</tbody></table>")
        out.append(u"</main></body></html>")
        n_bytes += _emit(u"rule/%s.html" % k, u"\n".join(out))
        n_pages += 1

    # 3b) 文件页
    for e in entries:
        fns = e["pf"].get("functions") or []
        my_alerts = alerts_by_flat.get(e["flat"], [])
        out_e = edges_by_flat.get(e["flat"], [])
        my_unres = missing_by_flat.get(e["flat"], [])
        my_inc = inc_edges_by_flat.get(e["flat"], [])
        n_in = sum(len(callers_of.get((fn.get("name") or u"").lower(), [])) for fn in fns)
        out = _head(e["rel"], u"../")
        out.append(u'<h1 class="cs-mono">%s</h1>' % _esc(e["rel"]))
        out.append(_cards([
            (len(fns), u"函数"), (len(e["pf"].get("includes") or []), u"include"),
            (len(my_alerts), u"告警"), (len(out_e), u"出边"),
            (n_in, u"入边"), (len(my_unres), u"未解析调用"),
        ]))
        # 告警（带源码行上下文）
        if my_alerts:
            out.append(u"<h2>告警明细</h2>")
            if len(my_alerts) > max_file_alerts:
                out.append(u'<div class="cs-note">本文件共 <b>%s</b> 条告警，'
                           u"此处展开前 <b>%s</b> 条。</div>"
                           % (_num(len(my_alerts)), _num(max_file_alerts)))
            src = _read_lines(e["path"]) if e["path"] else None
            out.append(u'<table class="cs-t"><thead><tr><th class="cs-num">行</th>'
                       u"<th>规则</th><th>级别</th><th>函数</th><th>说明</th>"
                       u"</tr></thead><tbody>")
            for a in my_alerts[:max_file_alerts]:
                k = a.get("kind") or u"?"
                label, _lvl, _cat = _meta(k)
                snip = u""
                ln = a.get("line") or 0
                if src and 1 <= ln <= len(src):
                    snip = u'<div class="cs-snip">%s</div>' % \
                        _esc(src[ln - 1].rstrip()[:400])
                out.append(u'<tr><td class="cs-num">%s</td>'
                           u'<td><a href="../rule/%s.html">%s</a></td>'
                           u'<td class="cs-lvl-%s">%s</td><td class="cs-mono">%s</td>'
                           u"<td>%s%s</td></tr>"
                           % (_num(ln), _esc(k), _esc(label),
                              _esc(a.get("level") or u"note"),
                              _esc(a.get("level") or u"note"),
                              _esc(a.get("func")), _esc(a.get("msg")), snip))
            out.append(u"</tbody></table>")
        # 函数表
        out.append(u"<h2>函数</h2>")
        if fns:
            out.append(u'<table class="cs-t"><thead><tr><th>函数</th>'
                       u'<th class="cs-num">行</th><th>返回类型</th><th>参数</th>'
                       u'<th class="cs-num">复杂度</th><th class="cs-num">扇入</th>'
                       u"<th>调用（出边）</th></tr></thead><tbody>")
            for fn in sorted(fns, key=lambda x: (x.get("line") or 0, x.get("name") or u"")):
                nm = fn.get("name") or u"?"
                callees = []
                for c in (fn.get("calls") or []):
                    cn = c[0] if isinstance(c, (list, tuple)) and c else u"?"
                    home = func_home.get((cn or u"").lower())
                    if home:
                        callees.append(u'<a href="%s.html">%s</a>'
                                       % (_esc(home), _esc(cn)))
                    else:
                        callees.append(_esc(cn))
                out.append(u'<tr><td class="cs-mono">%s</td><td class="cs-num">%s</td>'
                           u'<td class="cs-mono">%s</td><td class="cs-mono">%s</td>'
                           u'<td class="cs-num">%s</td><td class="cs-num">%s</td>'
                           u"<td>%s</td></tr>"
                           % (_esc(nm), _num(fn.get("line") or 0),
                              _esc(fn.get("ret")), _esc(u", ".join(fn.get("params") or [])),
                              _num(fn.get("complexity") or 0),
                              _num(fan_in.get(nm.lower(), 0)),
                              u", ".join(callees) or u'<span class="muted">—</span>'))
            out.append(u"</tbody></table>")
        else:
            out.append(u'<p class="muted">本文件未解析出函数定义。</p>')
        # include
        if e["pf"].get("includes"):
            out.append(u"<h2>#include</h2><p>%s</p>"
                       % u"".join(u'<code class="inc">%s</code> ' % _esc(i)
                                  for i in e["pf"]["includes"]))
        if my_inc:
            out.append(u"<h2>#include 解析结果</h2>")
            out.append(u'<table class="cs-t"><thead><tr><th>#include</th>'
                       u"<th>解析到</th></tr></thead><tbody>")
            for (inc, to) in sorted(my_inc):
                out.append(u"<tr><td><code>%s</code></td><td>%s</td></tr>"
                           % (_esc(inc),
                              (_esc(to) if to else u'<span class="muted">未找到'
                                                   u"（系统库或项目外）</span>")))
            out.append(u"</tbody></table>")
        # 未解析
        if my_unres:
            out.append(u"<h2>未解析调用</h2>")
            out.append(u'<table class="cs-t"><thead><tr><th class="cs-num">行</th>'
                       u"<th>被调函数</th></tr></thead><tbody>")
            for (nm, ln) in sorted(my_unres, key=lambda x: (x[1], x[0]))[:max_file_alerts]:
                out.append(u'<tr><td class="cs-num">%s</td>'
                           u'<td class="cs-mono">%s</td></tr>' % (_num(ln), _esc(nm)))
            out.append(u"</tbody></table>")
        # 被调用处（入边）
        in_rows = []
        for fn in fns:
            for (ca, f, ln) in callers_of.get((fn.get("name") or u"").lower(), []):
                in_rows.append((fn.get("name"), ca, f, ln))
        if in_rows:
            in_rows.sort(key=lambda x: (x[2] or u"", x[3] or 0))
            out.append(u"<h2>被调用处</h2>")
            if len(in_rows) > max_file_alerts:
                out.append(u'<div class="cs-note">共 <b>%s</b> 处，此处展开前 '
                           u"<b>%s</b> 处。</div>"
                           % (_num(len(in_rows)), _num(max_file_alerts)))
            out.append(u'<table class="cs-t"><thead><tr><th>本文件函数</th>'
                       u"<th>调用方</th><th>所在文件</th><th class=\"cs-num\">行</th>"
                       u"</tr></thead><tbody>")
            for (mine, ca, f, ln) in in_rows[:max_file_alerts]:
                ce = rel_to_entry.get(f) or base_to_entry.get(os.path.basename(f or u""))
                link = (u'<a href="%s.html">%s</a>' % (_esc(ce["flat"]), _esc(ce["rel"]))
                        if ce is not None else _esc(f))
                out.append(u'<tr><td class="cs-mono">%s</td><td class="cs-mono">%s</td>'
                           u'<td>%s</td><td class="cs-num">%s</td></tr>'
                           % (_esc(mine), _esc(ca), link, _num(ln)))
            out.append(u"</tbody></table>")
        out.append(u"</main></body></html>")
        n_bytes += _emit(u"file/%s.html" % e["flat"], u"\n".join(out))
        n_pages += 1

    # 3c) 索引页
    total_funcs = sum(len(e["pf"].get("functions") or []) for e in entries)
    cx_vals = [fn.get("complexity") or 0 for e in entries
               for fn in (e["pf"].get("functions") or [])]
    avg_cx = round(sum(cx_vals) / float(len(cx_vals)), 1) if cx_vals else 0.0
    out = _head(u"C 语言前端分析站点", u"")
    out.append(u"<h1>C 语言前端分析站点（--lang c --browse）</h1>")
    out.append(u'<p class="muted">零 JS / 零外链：图表在服务端算成 SVG 后注入，'
               u"断网双击即可打开。分页口径见 <code>renderers/csite.py</code> 模块"
               u"说明（单页报告在语料级规模下会到 GB 级）。</p>")
    out.append(_cards([
        (len(entries), u"C 文件"), (total_funcs, u"C 函数"), (len(edges), u"调用边"),
        (len(unresolved), u"未解析调用"), (len(inc_edges), u"include 边"),
        (len(alerts), u"静态检查"), (avg_cx, u"平均复杂度"),
    ]))
    if alerts:
        kr = [(k, len(alerts_by_kind[k])) for k in sorted(alerts_by_kind)]
        kr.sort(key=lambda x: (-x[1], x[0]))
        out.append(u'<h2>告警构成</h2><div class="cs-cols">')
        out.append(_donut_svg([(k, c, _kind_color(k)) for (k, c) in kr]))
        out.append(u"<div>")
        out.append(_legend_html([(k, _meta(k)[0], c) for (k, c) in kr]))
        out.append(_bar_svg([(u"%s（%s）" % (_meta(k)[0], k), c,
                              u"rule/%s.html" % k) for (k, c) in kr],
                            label_w=250, bar_w=380))
        out.append(u"</div></div>")
        out.append(u'<p class="muted">按严重度：'
                   u'<span class="cs-lvl-error">error</span> / '
                   u'<span class="cs-lvl-warning">warning</span> / '
                   u'<span class="cs-lvl-note">note</span></p>')
    # 复杂度 TOP
    top = [(fn.get("complexity") or 0, fn.get("name") or u"?", e)
           for e in entries for fn in (e["pf"].get("functions") or [])]
    top.sort(key=lambda x: (-x[0], x[1]))
    out.append(u"<h2>复杂度 TOP %d</h2>" % top_complexity)
    out.append(_bar_svg([(u"%s · %s" % (n, e["rel"]), c,
                          u"file/%s.html" % e["flat"])
                         for (c, n, e) in top[:top_complexity]],
                        label_w=300, bar_w=340, color="#8250df"))
    # 规则表
    if alerts:
        out.append(u"<h2>规则汇总</h2>")
        out.append(u'<table class="cs-t"><thead><tr><th>规则</th><th>说明</th>'
                   u'<th class="cs-num">条数</th><th class="cs-num">占比</th>'
                   u"<th>级别</th><th>类别</th></tr></thead><tbody>")
        tot = len(alerts) or 1
        for (k, c) in kr:
            label, level, cat = _meta(k)
            out.append(u'<tr><td><a href="rule/%s.html" class="cs-mono">%s</a></td>'
                       u"<td>%s</td><td class=\"cs-num\">%s</td>"
                       u'<td class="cs-num">%.1f%%</td>'
                       u'<td class="cs-lvl-%s">%s</td><td>%s</td></tr>'
                       % (_esc(k), _esc(k), _esc(label), _num(c),
                          100.0 * c / tot, _esc(level), _esc(level), _esc(cat)))
        out.append(u"</tbody></table>")
    # 目录分组文件清单
    out.append(u"<h2>文件清单（按目录分组）</h2>")
    groups = {}
    for e in entries:
        d = os.path.dirname(e["rel"]) or u"(根目录)"
        groups.setdefault(d, []).append(e)
    for d in sorted(groups):
        lst = groups[d]
        lst.sort(key=lambda x: x["rel"])
        n_alert = sum(len(alerts_by_flat.get(x["flat"], [])) for x in lst)
        n_fn = sum(len(x["pf"].get("functions") or []) for x in lst)
        out.append(u'<details class="cs-dir"><summary>%s <span class="muted">'
                   u"（%s 文件 · %s 函数 · %s 告警）</span></summary><ul>"
                   % (_esc(d), _num(len(lst)), _num(n_fn), _num(n_alert)))
        for x in lst:
            na = len(alerts_by_flat.get(x["flat"], []))
            out.append(u'<li><a href="file/%s.html" class="cs-mono">%s</a>'
                       u'%s</li>'
                       % (_esc(x["flat"]), _esc(os.path.basename(x["rel"])),
                          (u' <span class="muted">· %s 告警</span>' % _num(na))
                          if na else u""))
        out.append(u"</ul></details>")
    out.append(u"</main></body></html>")
    n_bytes += _emit(u"index.html", u"\n".join(out))
    n_pages += 1

    # 3d) 样式：基础样式 + 本模块片段，写到根与每个含 .html 的子目录
    css = (css_text or u"") + CSITE_CSS
    n_bytes += _write_text(os.path.join(outdir, "browse.css"), css)
    for (dp, _dn, fn_) in os.walk(outdir):
        if os.path.abspath(dp) == os.path.abspath(outdir):
            continue
        if any(x.endswith(u".html") for x in fn_):
            dst = os.path.join(dp, "browse.css")
            if not os.path.exists(dst):
                n_bytes += _write_text(dst, css)

    # 3e) 确定性质量快照（无时间戳，两次运行逐字节稳定）
    q = {
        "kind": "c-site-quality",
        "files": len(entries),
        "functions": total_funcs,
        "edges": len(edges),
        "unresolved": len(unresolved),
        "include_edges": len(inc_edges),
        "alerts": len(alerts),
        "rule_kinds": len(alerts_by_kind),
        "pages": n_pages,
        "bytes": n_bytes,
        "orphan_alerts": orphan_alerts,
        "ambiguous_flat": sum(1 for v in seen_flat.values() if v),
    }
    import json as _json
    _write_text(os.path.join(outdir, "site-quality.json"),
                _json.dumps(q, ensure_ascii=False, indent=2, sort_keys=True))
    q["wrote_bytes"] = n_bytes
    return q
