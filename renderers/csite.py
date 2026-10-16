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
    file/<扁平名>.html   每个源文件一页：函数表（**出边 + 入边**）/ 依赖 / 告警 / 未解析 / 被调用处
    funcs.html          **全局函数索引**：扇入 TOP + 扇出 TOP + 未解析名 TOP（有机上界）
    src/<扁平名>.html   **源码页**：带 `#L<行>` 锚点，供函数表 / 告警 / 入边跳转
    rule/<kind>.html    每条检查规则一页：按文件聚合计数的 TOP + 有界明细
    binaries.html       **动态链接库页**（给了二进制读数时）：容器 / 依赖 / 导出 / 缓解措施 / 归因
    dynlibs.html        **源码级动态库引用页**（R100，四语言总生成）：「代码想用谁」—— 与 binaries.html 互补
    browse.css          站点样式（调用方传入的基础样式 + 本模块自有片段）
    site-quality.json   站点读数快照（无时间戳 ⇒ 两次运行逐字节稳定）

R92：**本模块的名字是历史**（它最初只服务 `--lang c`），行为已泛化为
「**语言无关的交叉引用站点**」：`lang` / `display` / `dep_key` 三个形参把
C 的 `includes` 与 Py/JS 的 `imports` 走同一条渲染路径，于是
**c / py / js / asm 四种前端的 `--browse` 站点形态完全一致**。

为什么必须泛化：`_run_ext_only` 此前明写「**不生成 HTML 站点**」，于是
Python/JS 用户拿不到任何可浏览的调用关系 —— 而 MATLAB 侧从 P63 起就有
`src/` + `dirs/` 分页站点。同一条能力按语言分裂成「有」和「没有」，
正是 R83 记下的那类**能力被砍成一半**。

为什么不新开一个 `xref.py`：那会把 `_flat()` 的路径口径（R76/R78 的 C-2
踩过同名覆盖）、零 JS 纪律（R75 的 CDN 教训）、离线自足（`browse.css`
悬空）三条判据各复制一份 —— 正是本仓最贵的那类「第二事实源」。

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
import zlib

from . import dynlibs as _dynlibs

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
.cs-src{border:1px solid #d0d7de;border-radius:6px;margin:10px 0;overflow-x:auto;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12.5px;line-height:1.5}
.cs-l{display:flex;white-space:pre}
.cs-l:target{background:#fff8c5}
.cs-ln{flex:0 0 auto;width:64px;text-align:right;padding-right:10px;color:#6e7781;background:#f6f8fa;border-right:1px solid #d0d7de;user-select:none}
.cs-lc{padding-left:8px}

/* ---- 调用关系图（R93）---- */
.cs-graph{display:block;margin:0.6em 0 0.2em;border:1px solid #d0d7de;
  border-radius:6px;background:#ffffff;max-width:100%;height:auto}
.cs-graph .cs-gself{fill:#0969da;stroke:#0a4c97;stroke-width:0.8}
.cs-graph .cs-gext{fill:#e6a23c;stroke:#a0651a;stroke-width:0.8}
.cs-graph .cs-gedge line{stroke:#b6bfc9;stroke-width:0.7}
.cs-graph .cs-gedge line.cs-gdash{stroke:#d0a35a;stroke-dasharray:3 2}
.cs-graph .cs-glbl{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;
  font-size:11px;fill:#1f2328;text-anchor:middle}
.cs-graph a{cursor:pointer}
.cs-graph a:hover circle{stroke-width:2.2}
:root[data-theme="dark"] .cs-graph{border-color:#30363d;background:#0d1117}
:root[data-theme="dark"] .cs-graph .cs-glbl{fill:#e6edf3}
:root[data-theme="dark"] .cs-graph .cs-gedge line{stroke:#30363d}
:root[data-theme="dark"] .cs-graph .cs-gedge line.cs-gdash{stroke:#6b4f22}
:root[data-theme="dark"] .cs-card,:root[data-theme="dark"] details.cs-dir{border-color:#30363d}
:root[data-theme="dark"] table.cs-t th,:root[data-theme="dark"] table.cs-t td{border-color:#30363d}
:root[data-theme="dark"] table.cs-t thead th{background:#161b22}
:root[data-theme="dark"] .cs-note{background:#2d2a1b;border-color:#9e6a03}
:root[data-theme="dark"] .cs-snip{background:#0d1117;border-left-color:#30363d}
:root[data-theme="dark"] .cs-ln{background:#161b22;border-right-color:#30363d}
:root[data-theme="dark"] .cs-src{border-color:#30363d}
:root[data-theme="dark"] .cs-l:target{background:#2d2a1b}
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

# R92：旧单页 `c_report.html` 的**文件数阈值**。超过它就不写单页，改在索引上明说。
# 为什么是这个数：两处实测 —— `fs` 子树 2,085 文件单页 30.6 MB（归档在
# `tests/test_matlabc.py::test_r76_c_site_is_paginated_and_styled` 的 docstring），
# `kernel/sched` 45 文件单页 1,290,995 B（R92 实测，带 2,800 条告警）；
# 即 14.7–28.7 KB/文件 ⇒ 内核 62,704 文件外推约 0.9–1.7 GB。5,000 落在两者之间
# （单页约 70–140 MB，浏览器仍能打开）。
# ⚠ 两组读数差 ≈2×，差异来自**告警明细量**而非文件数 ⇒ 体积基数只能是**区间**，
#   写成单值会得到一个「看似精确、实则依赖语料」的数（R92 踩过）。
# 它是一道**成本闸**，不是正确性判据 —— 所以越界时页面必须自己讲清楚「没写」。
# R93：调用关系图的节点上限与迭代次数。**两个都是架构约束，不是调参** ——
# FR 力导向是 O(n^2 * 迭代)，而 `kernel/sched` 的最大文件页有 461 节点。
# 实测 105.14 us/节点/迭代（`_r92/probe_force_layout.py`）：K=40 => 20.19 ms/页
# => 内核 6.3 万文件约 0.4 h；不设限则 fair.c 单页 5.82 s、整树 0.6 h。
GRAPH_MAX_NODES = 40
GRAPH_ITERS = 120
LEGACY_SINGLE_PAGE_MAX_FILES = 5000

# R92：旧单页体积的**实测基数区间**（字节 / 文件）。两处实测各一端：
#   低端 14,676 ≈ 30.6e6 / 2085  —— `fs` 子树 2,085 文件 → 30.6 MB（R76 归档）
#   高端 28,689 ≈ 1,290,995 / 45  —— `kernel/sched` 45 文件 → 1.29 MB（R92 实测，
#                                   同一棵语料带 2,800 条告警明细）
# 为什么必须是区间而不是一个数：两处差 ≈2×，且差异来自**告警明细量**（同文件数
# 下告警多的语料单页大得多）。写单值会得到一个「看似精确、实则依赖语料」的数 ——
# 之前那个写死的「约 1.8 GB」就是高端值被当成唯一值时算出来的。
LEGACY_BYTES_PER_FILE_LOW = 14676
LEGACY_BYTES_PER_FILE_HIGH = 28689

# R92：语言 → 显示名。**只影响标题文案**，不参与任何判据。
DISPLAY_NAMES = {
    "c": u"C", "cpp": u"C++", "py": u"Python", "js": u"JavaScript",
    "asm": u"汇编", "matlab": u"MATLAB",
}


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
    if not kind:
        return "#6e7781"
    # ⚠ 绝不能用内置 `hash()`：`str` 的哈希受 **PYTHONHASHSEED 随机化**影响，
    #   跨进程**不稳定** ⇒ 同一个 kind 两次运行分到不同颜色，站点产物因此
    #   **不可逐字节复现**（与本模块 docstring 的「两次运行逐字节稳定」直接
    #   冲突）。R99 实测：同一份代码连跑两次，`index.html` 与 `rule/*.html`
    #   的配色全变、内容一字不差。改用 `zlib.crc32` —— 标准库、跨进程稳定、
    #   与 PYTHONHASHSEED 无关。
    # ⚠ `%` 的优先级低于属性取值：`u"%s" % kind.encode(...)` 会**先**对
    #   `kind` 取 `.encode` ⇒ 非 `str` 的 kind 直接 AttributeError，
    #   整站 try/except 兜住后**一个页面都不落盘**（R99 实测：门夹具上
    #   py/js 的 browse_site 由 yes 变假）。先 `%s` 归一成字符串再 encode。
    _h = zlib.crc32((u"%s" % kind).encode("utf-8"))
    return _KIND_COLOR_FALLBACK[_h % len(_KIND_COLOR_FALLBACK)]


def _clip(s, n):
    """裁剪过长标签：保留尾部（路径的辨识度在尾部），前缀用省略号。"""
    s = u"%s" % (s if s is not None else u"")
    if len(s) <= n:
        return s
    return u"\u2026" + s[-(n - 1):]


def _force_layout(nodes, edges, width, height, iters=120):
    """确定性 Fruchterman-Reingold 布局。**不用 random**。

    初值 = 黄金角螺旋 + 名字的整数哈希抖动。同输入两次结果逐位相同
    （`_r92/probe_force_layout.py` 实测），否则同一份语料两次跑出会得到两份
    不同的 HTML，而本仓把「同输入逐位相等」当身份式判据。

    完全重合的点给一个由 `(i, j)` 决定的微扰而不是随机位移：重合在真实
    调用图里很常见（同名函数的两处定义），随机会让布局每次都不一样。
    """
    n = len(nodes)
    if n == 0:
        return []
    if n == 1:
        return [(width / 2.0, height / 2.0)]
    _ga = math.pi * (3.0 - math.sqrt(5.0))
    xs = [0.0] * n
    ys = [0.0] * n
    _rad = min(width, height) * 0.42
    for i in range(n):
        _h = 0
        # ⚠ 哈希源是 **label**（永远是字符串），不是 `id`：调用方给的
        # `id` 可以是任意结构（本项目传的是 `("d", name)` 元组），
        # 拿它 `for ch in id` 会让 ord() 收到非单字符对象。
        for _ch in u"%s" % (nodes[i].get("label") or u""):
            _h = (_h * 131 + ord(_ch)) & 0xFFFFFFFF
        _ang = _ga * i + (_h % 1000) / 1000.0 * 0.6
        xs[i] = width / 2.0 + _rad * math.cos(_ang)
        ys[i] = height / 2.0 + _rad * math.sin(_ang)
    _area = float(width) * float(height)
    _k = math.sqrt(_area / float(n)) * 0.85
    _temp = width * 0.10
    for _ in range(iters):
        dx = [0.0] * n
        dy = [0.0] * n
        for i in range(n):
            xi = xs[i]
            yi = ys[i]
            for j in range(n):
                if i == j:
                    continue
                ddx = xi - xs[j]
                ddy = yi - ys[j]
                d2 = ddx * ddx + ddy * ddy
                if d2 < 1e-9:
                    ddx = 1e-3 * ((i - j) % 3 + 1)
                    ddy = 1e-3 * ((i + j) % 3 + 1)
                    d2 = ddx * ddx + ddy * ddy
                d = math.sqrt(d2)
                f = (_k * _k) / d
                dx[i] += ddx / d * f
                dy[i] += ddy / d * f
        for (a, b) in edges:
            ddx = xs[a] - xs[b]
            ddy = ys[a] - ys[b]
            d = math.sqrt(ddx * ddx + ddy * ddy) or 1e-6
            f = d * d / _k
            fx = ddx / d * f
            fy = ddy / d * f
            dx[a] -= fx
            dy[a] -= fy
            dx[b] += fx
            dy[b] += fy
        step = _temp / 5.0
        for i in range(n):
            d = math.sqrt(dx[i] * dx[i] + dy[i] * dy[i])
            if d > 1e-9:
                xs[i] += dx[i] / d * min(step, d)
                ys[i] += dy[i] / d * min(step, d)
        _temp *= 0.965
    return list(zip(xs, ys))


def _graph_svg(nodes, links, width=880, height=520):
    """把节点/边画成**内联 SVG**（u"" 表示画不了）。

    为什么内联而不是 `<img src="x.svg">`：`<img>` 里的 SVG **不能点** ——
    这正是 doxygen 的 callgraph 不可跳转的原因（clang-uml 文档明写：
    「Doxygen adds images to HTML documentation as `<img src=""/>`,
    which disables interactive links in SVG diagrams」）。内联 + `<a href>`
    是零脚本实现可跳转的唯一办法。

    零 JS：只用 `<a>` / `<line>` / `<circle>` / `<text>`。
    """
    n = len(nodes)
    if n == 0:
        return u""
    pos = _force_layout(nodes, links, width, height)
    _xs = [p[0] for p in pos]
    _ys = [p[1] for p in pos]
    _x0, _x1 = min(_xs), max(_xs)
    _y0, _y1 = min(_ys), max(_ys)
    _sc = min((width - 52.0) / ((_x1 - _x0) or 1.0),
              (height - 52.0) / ((_y1 - _y0) or 1.0))
    _cx = (_x0 + _x1) / 2.0
    _cy = (_y0 + _y1) / 2.0
    xy = [(width / 2.0 + (px - _cx) * _sc, height / 2.0 + (py - _cy) * _sc)
          for (px, py) in pos]
    deg = {}
    for (a, b) in links:
        deg[a] = deg.get(a, 0) + 1
        deg[b] = deg.get(b, 0) + 1
    out = [u'<svg class="cs-graph" viewBox="0 0 %d %d" width="100%%" '
           u'role="img" xmlns="http://www.w3.org/2000/svg">'
           % (width, height)]
    out.append(u"<title>%s</title>" % _esc(u"调用关系图"))
    out.append(u"<desc>%s</desc>"
               % _esc(u"确定性力导向布局；节点可点击跳到源码行。"
                      u"实线为已解析的调用边，虚线连向未解析的外部名字。"))
    out.append(u'<g class="cs-gedge">')
    for (a, b) in links:
        x1, y1 = xy[a]
        x2, y2 = xy[b]
        cls = u"cs-gdash" if (nodes[a].get("ext") or nodes[b].get("ext")) else u""
        out.append(u'<line class="%s" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>'
                   % (cls, x1, y1, x2, y2))
    out.append(u"</g>")
    for i, nd in enumerate(nodes):
        x, y = xy[i]
        d = deg.get(i, 0)
        r = 5.0 + min(9.0, (d ** 0.5) * 1.7)
        cls = u"cs-gext" if nd.get("ext") else u"cs-gself"
        lbl = nd.get("label") or u""
        maxch = int(max(8, (r + 4) * 0.62))
        if len(lbl) > maxch:
            lbl = lbl[:maxch - 1] + u"…"
        href = nd.get("href")
        if href:
            out.append(u'<a href="%s">' % _esc(href))
        out.append(u'<circle class="%s" cx="%.1f" cy="%.1f" r="%.1f"/>'
                   % (cls, x, y, r))
        out.append(u'<text class="cs-glbl" x="%.1f" y="%.1f">%s</text>'
                   % (x, y + r + 12.0, _esc(lbl)))
        if href:
            out.append(u"</a>")
    out.append(u"</svg>")
    return u"\n".join(out)

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


def _head(title, up, brand=u"C 语言前端分析站点", nav=(), legacy=None):
    """页头。`nav` = [(href, label)] 站内导航（相对 `up`）；`legacy` = 旧单页地址或 None。

    R92：旧单页链接**必须**可关 —— Python/JS 站点没有 `c_report.html`，
    写死它就是一个**悬空链接**（R76 记的正是同一类缺陷：`browse.css` 只写
    页面不写文件 ⇒ 整站无样式）。所以这里由调用方决定它存不存在。
    """
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
    for (_h, _l) in nav:
        A(u'<a href="%s%s">%s</a>' % (up, _h, _esc(_l)))
    if legacy:
        A(u'<a href="%s%s">单页完整表 &rarr;</a>' % (up, legacy))
    A(u"</header>")
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


def _table3(h1, h2, h3, rows):
    """三列表格（R92：缓解措施用）。**单元格按值直接写入**，调用方负责转义。"""
    out = [u'<table class="cs-t"><thead><tr><th>%s</th><th>%s</th><th>%s</th>'
           u"</tr></thead><tbody>" % (_esc(h1), _esc(h2), _esc(h3))]
    for (a, b, c) in rows:
        out.append(u'<tr><td class="cs-mono">%s</td><td>%s</td><td>%s</td></tr>'
                   % (_esc(a), _esc(b), _esc(c)))
    out.append(u"</tbody></table>")
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
                  max_file_alerts=500, top_complexity=20,
                  lang="c", display=None, dep_key="includes",
                  dep_edges=None,
                  binaries=None, attribution=None,
                  src_budget=48 * 1024 * 1024, src_max_file=256 * 1024,
                  legacy_max_files=LEGACY_SINGLE_PAGE_MAX_FILES, top_index=200,
                  graph_max_nodes=GRAPH_MAX_NODES, graph_iters=GRAPH_ITERS,
                  skip_index=False, src_subdir=u"src", finalize_page=None):
    """生成**语言无关的交叉引用站点**，返回统计 dict。

    c_model       `build_c_model` / `_build_ext_model` 的返回值
                  （files/functions/edges/unresolved/…）。两种前端的模型形状
                  在同一层上是相同的：`files[].functions[].calls` 是调用点，
                  `edges` 是解析后的边，`unresolved` 是解析不到的调用。
    root          被分析目录（用于把绝对 path 换算成**唯一的**站点相对路径）
    outdir        站点输出目录（不存在则创建）
    heuristics    静态检查结果（每条含 file/line/func/kind/msg/level）
    css_text      基础样式（通常是 BROWSE_CSS）；本模块再追加 CSITE_CSS
    kind_meta_fn  kind -> {"label","level","category"}，缺省用本地兜底
    lang          R92：语言标签（`c` / `py` / `js` / `asm`），只影响**标题**与
                  `site-quality.json`，**不影响任何一条判据** —— 站点形态必须
                  四语言一致，否则「像 MATLAB 那样」这句话按语言分裂。
    display       R92：显示名（默认由 `lang` 映射）。
    dep_key       R92：文件级依赖的键名。C 是 `includes`，Py/JS 是 `imports`；
                  两者都渲染成「依赖 → 解析到谁」两张表，取不到的键就是空表
                  （**不报错、不假装有**）。
    dep_edges     R92：文件级依赖**边**（三元组 `(from, dep, to)`）的**显式**来源。
                  给了就用它，完全不看模型里的 `include_edges` —— Py/JS 的 import
                  图是调用方**现算**的，而模型里的 `include_edges` 还被
                  `--callgraph` 的 rung-2 消歧读着（那是 C 专属口径，让 import 边
                  混进去会改变既有产物）。None = 沿用模型里的 C `#include` 图。
    binaries      R92：动态链接库读数（`binfmt.parse` 的摘要字典列表），给了就
                  生成 `binaries.html`。**只有明说出来的二进制**才在这里。
    attribution   R92：`--binary-attach` 的归因行（name/attribution/origins/detail），
                  给了就在 `binaries.html` 里加一张「未解析调用 → 归到了谁」表。
    src_budget    R92：源码页**总输出预算**（字节）。用尽即停止再写源码页，
                  并把「有多少文件因此没内联」写进索引 —— 内核级语料（6.3 万
                  文件 / 1.3 GB 源码）无条件内联会把站点推到 GB 级。
    src_max_file  R92：单文件源码页上限；超过的文件**只给一行说明**，不静默跳过。
    legacy_max_files  R92：旧单页 `c_report.html` 的体积闸 —— 文件数超过它就不写
                  单页（内核级外推 0.9–1.7 GB 的无用单页，见
                  `LEGACY_BYTES_PER_FILE_LOW/HIGH`），改在索引里说明。
    top_index     funcs.html 三张榜各自的**有界**行数（扇入 / 扇出 / 未解析名）。
    skip_index    R99：True 时**不写** `index.html` 与 `site-quality.json`。
                  这两件是「站点汇总产物」；本模块被 MATLAB 站点路径复用时，
                  站点根已有 `render_browse_site` 的富页入口与自己的质检快照，
                  基础层不覆盖它们，其余页面照常落盘 ⇒ 四语言**页面名同形**。
    src_subdir    R99：源码页子目录名（默认 `src`）。MATLAB 的源码页目录
                  也叫 `src/` 但命名规则不同（`<rel>.m.html`），两者写进
                  同一个目录会互相污染 ⇒ MATLAB 那次调用传 `xref_src`。
    finalize_page R108：页面**写盘前**的逐页收尾钩子 `fn(html) -> html`。
                  `matlabc.py` 的 `_emit_lang_site` 用它补「横切元信息」
                  （viewport / description / Open Graph / 表头 scope）——
                  那是它自己那份 `_finalize_html_str`，本模块**不 import 它**
                  （避免反向依赖）。不给 ⇒ 逐字节等于 R107 的产物。
    graph_max_nodes  R93：单张调用关系图的**节点上限**（默认
                  `GRAPH_MAX_NODES`）。力导向是 O(n^2 * 迭代)，`kernel/sched`
                  实测最大文件页 461 节点 => 5.82 s/页，整棵内核外推 0.6 h。
                  超出时按 `(扇入+扇出)` 降序取前 K 个，并在图下**写明**
                  「另有 N 个节点未画」—— 截断必须可见，否则「图 = 全貌」
                  这个误解会在页面上一直存在（与 R91 的边上限同一条纪律）。
    graph_iters      R93：布局迭代次数（默认 `GRAPH_ITERS`）。它决定的是产物
                  的**确定性**，不是画质：同输入必须逐位可复现。

    """
    files = list(c_model.get("files") or [])
    edges = list(c_model.get("edges") or [])
    unresolved = list(c_model.get("unresolved") or [])
    # R92：依赖边的来源**显式传入优先**。C 的 `#include` 图本来就在模型里
    # （P90 的 `include_edges`），Py/JS 的 import 图由调用方经 `dep_edges` 传进来。
    # 两种来源、一个渲染器 —— 站点形态不许按语言分叉。
    inc_edges = (list(dep_edges) if dep_edges is not None
                 else list(c_model.get("include_edges") or []))
    alerts = list(heuristics or [])
    outdir = str(outdir)
    root_abs = os.path.abspath(root) if root else None
    # R92：标题与旧单页链接由语言决定；页内导航在所有页上一致。
    # ⚠ `brand` 里**不预先转义** —— `_head()` 会转义一次；转两次会让 `&`
    #   变成 `&amp;amp;`（显示名里只要出现一次 & 就会静默坏掉）。
    if display is None:
        display = DISPLAY_NAMES.get(lang, lang)
    brand = u"%s 语言前端分析站点" % display
    # `DISPLAY_NAMES["c"] == u"C"` ⇒ C 的品牌串与 R76 时的字面量保持一致
    # （既有测试与文档按它核对）；这不是巧合，是刻意把它钉在映射表里。
    # R92：旧单页的**两个不写理由必须分开** —— 合成一个布尔会撒谎：
    #   (a) 本语言根本没有 `c_report.html` 这件产物（只有 C 有）；
    #   (b) 有，但文件数超阈值，刻意跳过。
    # 之前两件事共用一个 `write_legacy=False`，于是 Python 站点上印出
    # 「3 个文件在线性外推下约需 1.8 GB 单页」—— 既算错，又把一个不存在的
    # 文件名写进索引（悬空引用）。
    legacy_too_many = len(files) > legacy_max_files
    write_legacy = (lang == "c" and not legacy_too_many)
    legacy_href = u"c_report.html" if write_legacy else None
    nav = [(u"funcs.html", u"函数索引"), (u"deps.html", u"文件依赖"),
           (u"dynlibs.html", u"动态链接库引用")]
    if binaries:
        nav.append((u"binaries.html", u"动态链接库"))
    dep_label = u"#include" if dep_key == "includes" else u"import"

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

    # R102：目录分组**提前**建好。`file/` 页要挂「所在目录」回链 —— 否则
    #   基础层的 `dir/*.html` 只在基础层自己的 `index.html` 里有入口，而
    #   MATLAB 站点传 `skip_index=True`（保住宿主索引）⇒ 那批目录页在整站里
    #   **没有任何页面链到**（fe_audit S7 实测判为孤儿页）。
    #   分组只依赖 `entries`，而 `entries` 建好后全程只读 ⇒ 提前无副作用。
    groups = {}
    for e in entries:
        d = os.path.dirname(e["rel"]) or u"(根目录)"
        groups.setdefault(d, []).append(e)
    dir_flat = {}
    for d in sorted(groups):
        dir_flat[d] = (u"_root" if d == u"(根目录)" else _flat(d))

    # ---- 1b·R100：源码级动态库引用（四语言共用一页 dynlibs.html）----
    # 与 `binaries` 形参（**容器解析**，需要文件递过来）是两路：这一路
    # 只读源码字面量 ⇒ 语料里一个库文件都没有也能出结果。读失败**不静默**
    # （`dynlib_read_fail` 计数并上页面）。
    dynlib_refs = []
    dynlib_read_fail = 0
    if lang in _dynlibs.SUPPORTED_LANGS:
        for e in entries:
            _p = e["path"]
            if not _p:
                continue
            try:
                _txt = io.open(_p, "r", encoding="utf-8",
                               errors="replace").read()
            except Exception:
                dynlib_read_fail += 1
                continue
            for _r in _dynlibs.extract_dynlib_refs(e["rel"], _txt, lang):
                _r["flat"] = e["flat"]
                dynlib_refs.append(_r)
        dynlib_refs.sort(key=lambda r: (r["file"], r["line"], r["api"],
                                        r["lib"] or u""))
    _agg = (_dynlibs.summarize(dynlib_refs)
            if lang in _dynlibs.SUPPORTED_LANGS else None)

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
    # R92：**全部**同名定义（不止第一次命中）。`func_home` 回答「跳到哪」，
    # 这份回答「一共有几处」—— 两者必须都在场：只给前者，读者会把
    # 「多个同名定义」当成「一个定义」（本项目在 MATLAB 侧的 P80 就是为
    # 这件事做的歧义可视化）。
    func_defs = {}
    # R92：小写键 → 展示用**原样**名字。没有它，扇入/扇出榜会把 `memcpy`
    # 印成 `memcpy`（巧合），却把 `kmalloc_array` 印成小写 —— 名字的大小写
    # 是符号的一部分，榜单上印错就是印错。
    name_disp = {}
    for e in entries:
        for fn in e["pf"].get("functions") or []:
            nm = (fn.get("name") or u"").lower()
            if not nm:
                continue
            func_defs.setdefault(nm, []).append((e["flat"], fn.get("line") or 0))
            name_disp.setdefault(nm, fn.get("name") or nm)
            if nm not in func_home:
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
    # R92：未解析调用**按名字聚合**（funcs.html 的第三张榜）。口径与 MATLAB 侧的
    # `unresolved.html` 同源：一个名字解析不到，先问「项目里到底有没有同名定义」——
    # 有 ⇒ `in_project`（**疑似漏检**：定义在，匹配没命中）；没有 ⇒ 真·外部。
    # 两档在页面上**分列**，绝不合并成一句「未解析」。
    missing_by_name = {}
    for (nm, ln, f) in unresolved:
        e = rel_to_entry.get(f) or base_to_entry.get(os.path.basename(f or u""))
        if e is not None:
            missing_by_flat.setdefault(e["flat"], []).append((nm, ln))
        key = (nm or u"").lower()
        rec = missing_by_name.get(key)
        if rec is None:
            rec = {"name": nm or u"", "count": 0, "files": set(), "in_project": False}
            missing_by_name[key] = rec
        rec["count"] += 1
        if e is not None:
            rec["files"].add(e["flat"])
        if key in func_home:
            rec["in_project"] = True

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

    # ---- 2·规划（R92）：源码页名单**先算后写** ----
    # 为什么不能边写边省：文件页要**链回自己的源码页**，所以「哪些文件会有源码页」
    # 必须在写文件页之前就定下来。否则要么链接全部悬空（按 `os.path.exists` 现查
    # 会永远为假 —— 源码页在文件页之后才写），要么把顺序写死成隐式契约。
    # 预算按**源文件字节**计（不是输出字节）：它可预先算出、可复现，且不依赖
    # 转义后的大小；`src_skipped_budget` 会如实报出因此没内联的文件数。
    src_plan = []
    src_flat = set()
    src_skip_size = 0
    src_skip_budget = 0
    _src_used = 0
    for e in entries:
        if not e["path"]:
            src_skip_size += 1
            continue
        try:
            _sz = os.path.getsize(e["path"])
        except Exception:
            src_skip_size += 1
            continue
        if _sz > src_max_file:
            src_skip_size += 1
            continue
        if _src_used >= src_budget:
            src_skip_budget += 1
            continue
        _src_used += _sz
        src_plan.append(e)
        src_flat.add(e["flat"])

    # ---- 3) 落盘 ----
    n_bytes = 0
    n_pages = 0
    # R93：图的读数计数器（进 `site-quality.json`，无时间戳 ⇒ 可复现）
    n_graph = 0
    n_graph_nodes = 0
    n_graph_dropped = 0

    def _emit(rel_path, text):
        # R108：横切元信息在**写盘前**逐页补 —— 而不是等整个站点写完再回头扫目录。
        #   下面的 `n_bytes += _emit(...)` 就是本模块对外报「站点多大」的那个数；
        #   事后补会让它少算收尾加进去的几百字节/页，而没有任何判据看得见。
        if finalize_page is not None:
            text = finalize_page(text)
        n = _write_text(os.path.join(outdir, rel_path.replace(u"/", os.sep)), text)
        return n

    # ---- 3·原语（R92）----
    # ⚠ **前缀必须显式传**：站点里有两类页面 —— 根页（`index/funcs/deps/
    #   binaries`，链接是 `file/X.html`）与 `file/` 原页（链接是 `X.html`）。
    #   同一个原语在两类页面上写出的 href 不同，写死任何一边都会造出
    #   `file/file/X.html` 这种**看起来完全正常**的死链。
    #   这不是假想：本仓 R92 的独立审计器（`_r92/verify_site_links.py`）
    #   第一次跑就抓到 30 条 —— 页面能打开、函数名能点，点下去 404。
    # 函数名 → 文件页链接。同名多定义时只链第一处，并在 `title` 里写出**共有几处**
    # —— 零 JS 的前提下，Hover 是唯一不引入脚本的告知方式；不写它，读者会把
    # 「多个同名定义」当成「一个定义」。
    def _fn_link(name, pre=u"file/"):
        nm = u"%s" % (name or u"")
        key = nm.lower()
        home = func_home.get(key)
        if not home:
            return u'<span class="cs-mono">%s</span>' % _esc(nm)
        n_def = len(func_defs.get(key) or ())
        title = (u' title="%d 处同名定义"' % n_def) if n_def > 1 else u""
        return u'<a href="%s%s.html"%s>%s</a>' % (pre, _esc(home), title, _esc(nm))

    # 调用方列表 → 去重后的行（(caller, 条目, 行)）。**先全量去重再截断**：
    # 边是按「同名定义数」扇出的（`frontends/ir.py::resolve_calls` 的契约），
    # 同一条调用点会重复多次；不去重就截断，会把「14 条不同调用方」显示成
    # 「14 条同一条」。
    def _caller_rows(callers):
        seen = set()
        rows = []
        for (ca, f, ln) in callers:
            ce = rel_to_entry.get(f) or base_to_entry.get(os.path.basename(f or u""))
            key = (ca, ce["flat"] if ce is not None else f, ln)
            if key in seen:
                continue
            seen.add(key)
            rows.append((ca, ce, ln))
        return rows

    def _caller_links(rows, limit=24, pre=u"file/"):
        out = []
        for (ca, ce, ln) in rows[:limit]:
            if ce is not None:
                out.append(u'<a href="%s%s.html">%s</a>'
                           u'<span class="muted">:%s</span>'
                           % (pre, _esc(ce["flat"]), _esc(ca or u"?"),
                              _num(ln or 0)))
            else:
                out.append(u'<span class="cs-mono">%s</span>'
                           % _esc(ca or u"?"))
        s = u" · ".join(out) if out else u'<span class="muted">—</span>'
        rest = len(rows) - len(out)
        if rest > 0:
            s += u' <span class="muted">… 另有 %s 处</span>' % _num(rest)
        return s

    # 出边（本函数调用了谁）：按**名字**给链接，链到第一处定义。
    def _callee_names(fn):
        names = []
        seen = set()
        for c in (fn.get("calls") or []):
            cn = c[0] if isinstance(c, (list, tuple)) and c else u"?"
            k = (cn or u"").lower()
            if k in seen:
                continue
            seen.add(k)
            names.append(cn)
        return names

    def _callee_links(fn, limit=24, pre=u"file/"):
        names = _callee_names(fn)
        out = [_fn_link(n, pre) for n in names[:limit]]
        s = u" · ".join(out) if out else u'<span class="muted">—</span>'
        rest = len(names) - len(out)
        if rest > 0:
            s += u' <span class="muted">… 另有 %s 个</span>' % _num(rest)
        return s

    # 行号 → **源码页锚点**。没有源码页（超限 / 超预算）就只印数字，
    # **绝不**造一个指不到东西的链接（R76 的 `browse.css` 悬空链接是同一类）。
    # ⚠ 锚点里的行号必须是**裸整数**：`_num()` 会插千分位逗号，`#L1,234`
    #   永远匹配不到 `id="L1234"`，而页面上看起来完全正常。
    def _src_link(flat, line):
        n = int(line or 0)
        if flat and flat in src_flat:
            return (u'<a href="../%s/%s.html#L%d">%d</a>' % (src_subdir, _esc(flat), n, n))
        return u'<span class="muted">%d</span>' % n

    def _file_graph(entry, pre=u""):
        """组装**本文件**的调用关系图。返回 (svg_html, note_html)。

        出边来自 `edges_by_flat`、入边来自 `callers_of` —— 与函数表的
        两列是**同一份数据**。所以「图里有条边」=>「表里必有同一行」。

        `pre` 是给图内 `<a href>` 的路径前缀：图被放在 `file/` 原页里，
        源码页是 `../src/X.html`；放在根页则要 `src/X.html`。写死任何一边
        都会造出「页面能开、节点能点、点下去 404」的死链（R92 的审计器
        在 `_fn_link` 上抓到过 30 条那样的死链）。
        """
        _pf = entry["pf"]
        _fns = _pf.get("functions") or []
        if not _fns:
            return (u"", u"")
        _key2node = {}
        _nodes = []

        def _node(key, label, ext=False):
            nd = _key2node.get(key)
            if nd is not None:
                return nd
            nd = {"id": key, "label": label, "ext": ext, "href": None}
            _key2node[key] = nd
            _nodes.append(nd)
            return nd

        def _def_href(flat, line):
            """指向某个定义的源码行。**先查 `src_flat`**：源码页有双闸
            （单文件上限 + 总预算），不是每个文件都有源码页（实测
            `kernel/sched` 44/45 —— `core.c` 超单文件上限被跳过）。
            表里的链接走 `_src_link`（它查 `src_flat`），图里的链接必须
            查同一张表 —— 否则图会造出表里不存在的死链，而独立审计器
            抓到的是 144 条（全是 `#L` 指向没写的源码页）。
            没有源码页时退到**文件页**（那个页面一定在）。
            """
            if not flat:
                return None
            if flat in src_flat:
                return (u"%s%s/%s.html#L%d" % (pre, src_subdir, flat, int(line or 0)))
            return u"%sfile/%s.html" % (pre, flat)

        # 本文件的定义先全部建节点（即使它没有任何调用点也要有）。
        # ⚠ 这一段曾经被 `_def_href` 的 `def` **劈成两半**：后半落在
        #   `return` 之后成了不可达代码 —— `ast.parse` 不报、门禁全绿、
        #   页面照样能开，但凡是「只靠自身定义建节点」的函数（如没有
        #   调用点的 `big_top`）在图里**没有链接**，点不动。
        #   发现它靠的是「注入缺陷5 必须让测试变红」这条反向验证：
        #   小夹具全有源码页 ⇒ 回退分支永不执行 ⇒ 判据形同虚设。
        #   **教训：补丁锚点必须比「要插入的位置」更窄**，否则会插进
        #   循环体中间把代码劈开（R90 的「补丁会悄悄吃掉东西」同族）。
        for fn in _fns:
            nm = fn.get("name") or u""
            if not nm:
                continue
            _home = func_home.get(nm.lower())
            _href = _def_href(_home, fn.get("line")) if _home else None
            nd = _node(("d", nm.lower()), nm, False)
            nd["href"] = _href

        # 出边：**从 `calls` 流出发**（不是从 `edges`）。理由：函数表的
        # 「调用（它调用了谁）」列读的就是 `calls`，所以图也读它 —— 这样
        # 图与表是同一份数据的两种投影。若改从 `edges` 出发，未解析调用
        # 就会**整体消失**（`edges` 里只有解析成功的），图会显得比真实
        # 干净：实测 main.c 有 5 条未解析（malloc/memcpy/printf/free），
        # 而只画 edges 时页面上写的是「外部/未解析 0」。
        _edge_pairs = []
        for fn in _fns:
            _an = (fn.get("name") or u"").lower()
            if not _an:
                continue
            _a = _node(("d", _an), fn.get("name") or u"?", False)
            for _call in (fn.get("calls") or []):
                _cb = _call[0] if isinstance(_call, (tuple, list)) else _call
                _bn = (u"%s" % (_cb or u"")).lower()
                if not _bn:
                    continue
                if _bn in func_home:
                    _b = _node(("d", _bn),
                               name_disp.get(_bn, u"%s" % _cb), False)
                    _b["href"] = _def_href(
                        func_home[_bn],
                        (func_defs.get(_bn) or [(u"", 0)])[0][1])
                else:
                    _b = _node(("x", _bn), u"%s" % _cb, True)
                _edge_pairs.append((_a["id"], _b["id"]))

        # 入边：谁调用了本文件的函数（`callers_of` 就是函数表那一列的来源）
        for fn in _fns:
            _bn = (fn.get("name") or u"").lower()
            if not _bn:
                continue
            for (ca, cf, cln) in callers_of.get(_bn, []):
                _an = (ca or u"").lower()
                if not _an:
                    continue
                _a = _node(("d", _an), ca or u"?", False)
                if _an in func_home:
                    _a["href"] = _def_href(
                        func_home[_an],
                        (func_defs.get(_an) or [(u"", 0)])[0][1])
                else:
                    _a = _node(("x", _an), ca or u"?", True)
                _b = _node(("d", _bn), fn.get("name") or u"?", False)
                _edge_pairs.append((_a["id"], _b["id"]))

        # 去重边（同一对可能因「同名多定义扇出」重复出现）
        _seen = set()
        _links = []
        for (a, b) in _edge_pairs:
            if a == b:
                continue
            k = (a, b)
            if k in _seen:
                continue
            _seen.add(k)
            _links.append((a, b))

        # ---- 节点上限：按度数降序，名字稳定排序兜底（确定性）----
        # ⚠ `_graph_svg` / `_force_layout` 的 links 是**下标对**（它们在节点
        #   列表里按下标取坐标），所以这里必须先把节点**排好序**、再把边
        #   翻译成下标。第一版让两者都带元组键，于是 `_graph_svg` 里
        #   `deg[a]` 拿元组当下标 => `list indices must be integers`。
        #   契约写在**调用侧**，不是靠给渲染器加特判兜住。
        _idx = {}
        for _i, _nd in enumerate(_nodes):
            _idx[_nd["id"]] = _i
        _deg = {}
        for (a, b) in _links:
            _deg[a] = _deg.get(a, 0) + 1
            _deg[b] = _deg.get(b, 0) + 1

        total = len(_nodes)
        dropped = 0
        order = list(range(total))
        if total > graph_max_nodes:
            order = sorted(order,
                           key=lambda i: (-_deg.get(_nodes[i]["id"], 0),
                                          _nodes[i]["label"],
                                          u"%s" % (_nodes[i]["id"],)))[:graph_max_nodes]
            dropped = total - graph_max_nodes
        keep = [_nodes[i] for i in order]
        # ⚠ 过滤边时要用**节点 id 集合**，不是下标集合：`order` 里是下标，
        #   而 `_links` 里是 id。两者混用会让过滤**静默丢掉全部边**
        #   （实测：`pairs=3` 而 `links=0`，页面看起来仍然「正常」——
        #   有节点、无连线，正是最容易骗过人的那种坏）。
        #
        # ⚠ 第二个坑：截断后 `_idx` 就**过期**了（它记的是截断**前**的
        #   下标）。直接用它翻译边，下标会越界 =>
        #   `list index out of range`。正解是**按 keep 的新顺序重建**映射。
        #   这个坑只在**真的发生截断**时才触发，所以 3 文件夹具永远测不到
        #   —— 必须拿「超过 40 节点」的真实语料（`kernel/sched` 的 fair.c
        #   有 461 节点）才暴露。**小夹具通过不等于路径正确。**
        _keep_ids = set(nd["id"] for nd in keep)
        _newidx = {}
        for _i, _nd in enumerate(keep):
            _newidx[_nd["id"]] = _i
        _kept_links = [(_newidx[a], _newidx[b]) for (a, b) in _links
                       if a in _keep_ids and b in _keep_ids]

        svg = _graph_svg(keep, _kept_links)
        if not svg:
            return (u"", u"")

        n_def = sum(1 for nd in keep if not nd.get("ext"))
        n_ext = sum(1 for nd in keep if nd.get("ext"))
        note = [u'<div class="cs-note">调用关系图：'
                u"<b>%d</b> 个节点（本文件定义 %d · 外部/未解析 %d）· "
                u"<b>%d</b> 条边（已去重）。"
                % (len(keep), n_def, n_ext, len(_kept_links))]
        if dropped:
            note.append(u"另有 <b>%d</b> 个节点未画（图有节点上限，"
                        u"按扇入+扇出取前 %d 个）—— 见下方表格的完整清单。"
                        % (dropped, graph_max_nodes))
        note.append(u"点节点跳到源码行；橙色为未解析/外部名字。</div>")
        return (svg, u"".join(note))

    # ---- 3a) 规则页
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
        out = _head(u"%s · 规则明细" % label, u"../", brand=brand, nav=nav,
                    legacy=legacy_href)
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
        _deps = e["pf"].get(dep_key) or []
        # R102：标题必须与**宿主站点的源码页**分得开 —— MATLAB 的
        #   `src/a.m.html` 标题就是 `a.m`，而本页原先也是 `a.m`，同一份文件
        #   的两张页在标签栏里一模一样（fe_audit S19 逐条报「重复 <title>」）。
        #   不加宽判据，而是把「文件页」这个身份写进标题。
        #   同时挂「所在目录」回链：目录页本来就链着它列出的每个文件页，
        #   反方向此前是空的 ⇒ MATLAB 站点（skip_index=True）里 `dir/` 成孤儿。
        _df = dir_flat.get(os.path.dirname(e["rel"]) or u"(根目录)")
        _fnav = list(nav)
        if _df:
            _fnav.append((u"dir/%s.html" % _df, u"所在目录"))
        out = _head(u"%s · 文件" % e["rel"], u"../", brand=brand, nav=_fnav,
                    legacy=legacy_href)
        out.append(u'<h1 class="cs-mono">%s</h1>' % _esc(e["rel"]))
        if e["flat"] in src_flat:
            out.append(u'<p><a href="../%s/%s.html">查看本文件源码页（带行锚点）'
                       u"&rarr;</a></p>" % (src_subdir, _esc(e["flat"])))
        out.append(_cards([
            (len(fns), u"函数"), (len(_deps), dep_label.lstrip(u"#")),
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
                           % (_src_link(e["flat"], ln), _esc(k), _esc(label),
                              _esc(a.get("level") or u"note"),
                              _esc(a.get("level") or u"note"),
                              _esc(a.get("func")), _esc(a.get("msg")), snip))
            out.append(u"</tbody></table>")
        # 函数表 —— R92：**出边与入边同表**。这是「每一个函数和其他函数之间的
        # 调用关系」真正落地的地方：以前只有出边（我调了谁），入边要滚到页面
        # 底部那张「被调用处」才看得到，而且不区分是本文件哪个函数被调。
        out.append(u"<h2>函数</h2>")
        if fns:
            out.append(u'<table class="cs-t"><thead><tr><th>函数</th>'
                       u'<th class="cs-num">行</th><th>返回类型</th><th>参数</th>'
                       u'<th class="cs-num">复杂度</th><th class="cs-num">出边</th>'
                       u'<th class="cs-num">入边</th>'
                       u"<th>调用（它调用了谁）</th>"
                       u"<th>被调用（谁调用了它）</th></tr></thead><tbody>")
            for fn in sorted(fns, key=lambda x: (x.get("line") or 0, x.get("name") or u"")):
                nm = fn.get("name") or u"?"
                _key = nm.lower()
                _callers = _caller_rows(callers_of.get(_key, []))
                out.append(u'<tr><td class="cs-mono">%s</td><td class="cs-num">%s</td>'
                           u'<td class="cs-mono">%s</td><td class="cs-mono">%s</td>'
                           u'<td class="cs-num">%s</td><td class="cs-num">%s</td>'
                           u'<td class="cs-num">%s</td><td>%s</td><td>%s</td></tr>'
                           % (_esc(nm), _src_link(e["flat"], fn.get("line")),
                              _esc(fn.get("ret")), _esc(u", ".join(fn.get("params") or [])),
                              _num(fn.get("complexity") or 0),
                              _num(len(_callee_names(fn))),
                              _num(len(_callers)),
                              _callee_links(fn, pre=u""),
                              _caller_links(_callers, pre=u"")))
            out.append(u"</tbody></table>")
            out.append(u'<p class="muted">入边按<b>被调名字</b>聚合（C 的定义落点由'
                       u"翻译单元决定，同名多定义在链接期才定；本项目拒绝按"
                       u"「同名同文件」猜，见 <code>--callgraph-identity</code>）。"
                       u"所以同一名字在不同文件里的定义会**共享**这份入边 —— "
                       u"这是如实标注的口径，不是漏算。</p>")
        else:
            out.append(u'<p class="muted">本文件未解析出函数定义。</p>')
        # R93：调用关系图。**放在函数表之后** —— 图里的节点链接指向源码页，
        # 而源码页名单（`src_flat`）在规划阶段就定了，所以顺序不影响可达性；
        # 但放在表后，读者先看到精确数据（可排序可搜索的表格），再看概览。
        _g_svg, _g_note = _file_graph(e, pre=u"../")
        if _g_svg:
            out.append(u"<h2>调用关系图</h2>")
            out.append(_g_note)
            out.append(_g_svg)
            n_graph += 1
            n_graph_nodes += _g_svg.count(u"<circle")
            if _g_note.find(u"未画") >= 0:
                n_graph_dropped += 1
        # 依赖（R92：C 是 #include，Py/JS 是 import —— 同一条渲染路径）
        if _deps:
            out.append(u"<h2>%s</h2><p>%s</p>"
                       % (_esc(dep_label),
                          u"".join(u'<code class="inc">%s</code> ' % _esc(i)
                                   if not isinstance(i, (list, tuple)) else
                                   u'<code class="inc">%s</code> ' % _esc(i[0])
                                   for i in _deps)))
        if my_inc:
            out.append(u"<h2>%s 解析结果</h2>" % _esc(dep_label))
            out.append(u'<table class="cs-t"><thead><tr><th>%s</th>'
                       u"<th>解析到</th></tr></thead><tbody>" % _esc(dep_label))
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
                       u"<th>被调函数</th><th>项目内有同名定义</th>"
                       u"</tr></thead><tbody>")
            for (nm, ln) in sorted(my_unres, key=lambda x: (x[1], x[0]))[:max_file_alerts]:
                _k2 = (nm or u"").lower()
                out.append(u'<tr><td class="cs-num">%s</td>'
                           u'<td class="cs-mono">%s</td><td>%s</td></tr>'
                           % (_src_link(e["flat"], ln), _esc(nm),
                              (u'<b class="cs-lvl-warning">是</b>'
                               u'<span class="muted">（疑似漏检）</span>')
                              if _k2 in func_home else
                              u'<span class="muted">否（外部）</span>'))
            out.append(u"</tbody></table>")
        # 被调用处（入边）—— 保留独立小节：函数表里的入边是**有界**的，
        # 这里给出完整（至多 max_file_alerts）明细，并按调用方文件排序。
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
                # 行号链到**调用方所在文件**的源码页锚点：从「谁调用了它」
                # 一跳就到调用现场，这是交叉引用文档的关键一跳。
                _ln = (u'<a href="../%s/%s.html#L%d">%d</a>'
                       % (src_subdir, _esc(ce["flat"]),
                          int(ln or 0), int(ln or 0))
                       if (ce is not None and ce["flat"] in src_flat)
                       else _num(ln))
                out.append(u'<tr><td class="cs-mono">%s</td><td class="cs-mono">%s</td>'
                           u'<td>%s</td><td class="cs-num">%s</td></tr>'
                           % (_esc(mine), _esc(ca), link, _ln))
            out.append(u"</tbody></table>")
        out.append(u"</main></body></html>")
        n_bytes += _emit(u"file/%s.html" % e["flat"], u"\n".join(out))
        n_pages += 1

    # 3b·R92：源码页（单文件上限 + 总预算**双闸**）
    #   ⚠ 为什么必须有预算：整棵内核的 C 源码是 1,315.8 MiB，无条件内联会把
    #     站点从 KB/页推到 GB 级；而「只内联了一部分」**必须写在索引上**
    #     （不静默：`src_skipped_size` / `src_skipped_budget` 两个计数 + 一句为什么）。
    n_src_pages = 0
    n_src_bytes = 0
    n_src_skip_size = src_skip_size
    n_src_skip_budget = src_skip_budget
    for e in src_plan:
        _lines = _read_lines(e["path"])
        if _lines is None:
            # 读取失败（权限 / 已被删除 / 编码异常）**降级为「没写这一页」并计入
            # `src_skipped_size`** —— 它不可能是静默的，计数会进质量快照。
            n_src_skip_size += 1
            continue
        out = _head(u"%s · 源码" % e["rel"], u"../", brand=brand, nav=nav,
                    legacy=legacy_href)
        out.append(u'<h1 class="cs-mono">%s</h1>' % _esc(e["rel"]))
        out.append(u'<p class="muted">共 %s 行 · 本页供 <code>#L&lt;行&gt;</code> '
                   u"锚点跳转（函数表 / 告警 / 入边共用同一套锚点）</p>"
                   % _num(len(_lines)))
        out.append(u'<div class="cs-src">')
        for i, ln in enumerate(_lines):
            out.append(u'<div class="cs-l" id="L%d"><span class="cs-ln">%d</span>'
                       u'<span class="cs-lc">%s</span></div>'
                       % (i + 1, i + 1, _esc(ln.replace(u"\t", u"    "))))
        out.append(u"</div></main></body></html>")
        _n = _emit(u"%s/%s.html" % (src_subdir, e["flat"]), u"\n".join(out))
        n_bytes += _n
        n_src_bytes += _n
        n_pages += 1
        n_src_pages += 1

    # 3b·R92：全局函数索引 funcs.html（三张**有上界**的榜）
    fanin_rows = sorted(((v, k) for (k, v) in fan_in.items()),
                        key=lambda x: (-x[0], x[1]))[:top_index]
    fanout_rows = sorted(((v, k) for (k, v) in fan_out.items()),
                         key=lambda x: (-x[0], x[1]))[:top_index]
    miss_rows = sorted(missing_by_name.values(),
                       key=lambda r: (-r["count"], (r["name"] or u"").lower()))[:top_index]

    def _nd(name):
        """名字（小写键）→ 展示用原样名字；取不到就原样返回。"""
        return name_disp.get(name, name)

    out = _head(u"函数索引", u"", brand=brand, nav=nav, legacy=legacy_href)
    out.append(u"<h1>全局函数索引</h1>")
    out.append(u'<p class="muted">三张榜各有 <b>%s</b> 行上界：全量索引在语料级规模下'
               u"会退化成几十 MB 的单页，而浏览器解析不了那么大的表。"
               u"<b>截断在这里是明说的</b>（行尾写「另有 N 项」），不是静默丢弃，"
               u"完整明细请到各文件页。</p>" % _num(top_index))
    out.append(_cards([
        (len(fan_in), u"出现过调用点的名字"),
        (len(func_defs), u"有定义的名字"),
        (len(unresolved), u"未解析调用点"),
        (len(missing_by_name), u"未解析的不同名字"),
        (sum(1 for r in missing_by_name.values() if r["in_project"]), u"其中项目内有同名定义"),
    ]))
    out.append(u"<h2>扇入 TOP %s（谁被调用得最多）</h2>" % _num(top_index))
    out.append(u'<p class="muted">扇入按<b>名字</b>聚合：同名多定义在 C 里是常见形态'
               u"（`memcpy`），链接期才知道指向哪一份。定义列给出「跳到哪」，"
               u"Hover 给出「一共有几处」。</p>")
    out.append(u'<table class="cs-t"><thead><tr><th>函数</th>'
               u'<th class="cs-num">扇入</th><th>定义</th></tr></thead><tbody>')
    for (v, k) in fanin_rows:
        nd = func_defs.get(k) or []
        loc = (u' · '.join(u'<a href="file/%s.html">%s</a>'
                           % (_esc(f), _esc(f)) for (f, _l) in nd[:3])
               if nd else u'<span class="muted">项目内无定义</span>')
        out.append(u'<tr><td class="cs-mono">%s</td><td class="cs-num">%s</td>'
                   u"<td>%s%s</td></tr>"
                   % (_esc(_nd(k)), _num(v), loc,
                      (u' <span class="muted">（共 %s 处）</span>' % _num(len(nd)))
                      if len(nd) > 3 else u""))
    out.append(u"</tbody></table>")
    out.append(u"<h2>扇出 TOP %s（谁调用得最多）</h2>" % _num(top_index))
    out.append(u'<p class="muted">扇出是<b>出边条数</b>（按调用方名字聚合）。'
               u"它不是「不同的被调函数个数」—— 名字级聚合下这两者会在"
               u"「同一个函数被调用两次」时分开。</p>")
    out.append(u'<table class="cs-t"><thead><tr><th>调用方</th>'
               u'<th class="cs-num">出边条数</th><th>定义</th></tr></thead><tbody>')
    for (v, k) in fanout_rows:
        nd = func_defs.get(k) or []
        loc = (u' · '.join(u'<a href="file/%s.html">%s</a>'
                           % (_esc(f), _esc(f)) for (f, _l) in nd[:3])
               if nd else u'<span class="muted">项目内无定义</span>')
        out.append(u'<tr><td class="cs-mono">%s</td><td class="cs-num">%s</td>'
                   u"<td>%s</td></tr>"
                   % (_esc(_nd(k)), _num(v), loc))
    out.append(u"</tbody></table>")
    out.append(u"<h2>未解析名 TOP %s</h2>" % _num(top_index))
    out.append(u'<p class="muted">一个调用点解析不到定义时有<b>两种</b>含义，'
               u"这里**分列**、不合并：<b>项目内有同名定义</b> ⇒ 匹配没命中，"
               u"属「疑似漏检」；<b>项目内无同名定义</b> ⇒ 真的来自外部"
               u"（系统库 / 另一个编译单元未在语料里）。</p>")
    out.append(u'<table class="cs-t"><thead><tr><th>被调名</th>'
               u'<th class="cs-num">调用点</th><th class="cs-num">涉及文件</th>'
               u'<th>项目内有同名定义</th></tr></thead><tbody>')
    for r in miss_rows:
        out.append(u'<tr><td class="cs-mono">%s</td><td class="cs-num">%s</td>'
                   u'<td class="cs-num">%s</td><td>%s</td></tr>'
                   % (_esc(r["name"]), _num(r["count"]), _num(len(r["files"])),
                      (u'<b class="cs-lvl-warning">是</b>'
                       u'<span class="muted">（疑似漏检）</span>')
                      if r["in_project"] else
                      u'<span class="muted">否（外部）</span>'))
    out.append(u"</tbody></table>")
    out.append(u"</main></body></html>")
    n_bytes += _emit(u"funcs.html", u"\n".join(out))
    n_pages += 1

    # 3b·R92：文件依赖 deps.html（有界明细 + 目录聚合）
    out = _head(u"文件依赖", u"", brand=brand, nav=nav, legacy=legacy_href)
    out.append(u"<h1>文件依赖（%s 解析结果）</h1>" % _esc(dep_label))
    _dir_pairs = {}
    for (_frm, _inc, _to) in inc_edges:
        if not _to:
            continue
        _df = os.path.dirname((_frm or u"").replace(u"\\", u"/")) or u"(根目录)"
        _dt = os.path.dirname((_to or u"").replace(u"\\", u"/")) or u"(根目录)"
        if _df == _dt:
            continue
        _dir_pairs[(_df, _dt)] = _dir_pairs.get((_df, _dt), 0) + 1
    out.append(_cards([
        (len(inc_edges), u"%s 行" % dep_label),
        (sum(1 for e2 in inc_edges if e2[2]), u"解析到项目内文件"),
        (sum(1 for e2 in inc_edges if not e2[2]), u"未解析（系统库或项目外）"),
        (len(_dir_pairs), u"跨目录依赖对"),
    ]))
    out.append(u'<div class="cs-note">未解析**不是**失败：`%s &lt;stdio.h&gt;` 本来'
               u"就指系统头。这里只如实分列两档，不把「项目外」算成缺陷。</div>"
               % _esc(dep_label))
    if _dir_pairs:
        _top_dirs = sorted(_dir_pairs.items(), key=lambda kv: (-kv[1], kv[0]))[:60]
        out.append(u"<h2>跨目录依赖 TOP 60</h2>")
        out.append(_bar_svg([(u"%s → %s" % (a, b), c, u"")
                             for ((a, b), c) in _top_dirs],
                            label_w=300, bar_w=330, color="#0969da"))
    out.append(u"<h2>依赖明细（有界 %s 行）</h2>" % _num(max_rule_rows))
    if len(inc_edges) > max_rule_rows:
        out.append(u'<div class="cs-note">共 <b>%s</b> 条，此处展开前 <b>%s</b> 条。'
                   u"</div>" % (_num(len(inc_edges)), _num(max_rule_rows)))
    out.append(u'<table class="cs-t"><thead><tr><th>文件</th><th>依赖</th>'
               u"<th>解析到</th></tr></thead><tbody>")
    for (_frm, _inc, _to) in inc_edges[:max_rule_rows]:
        _fe = rel_to_entry.get(_frm) or base_to_entry.get(os.path.basename(_frm or u""))
        _te = rel_to_entry.get(_to) or base_to_entry.get(os.path.basename(_to or u""))
        out.append(u'<tr><td>%s</td><td class="cs-mono">%s</td><td>%s</td></tr>'
                   % ((u'<a href="file/%s.html" class="cs-mono">%s</a>'
                       % (_esc(_fe["flat"]), _esc(_fe["rel"])))
                      if _fe is not None else _esc(_frm),
                      _esc(_inc),
                      (u'<a href="file/%s.html" class="cs-mono">%s</a>'
                       % (_esc(_te["flat"]), _esc(_te["rel"])))
                      if _te is not None else
                      u'<span class="muted">未找到（系统库或项目外）</span>'))
    out.append(u"</tbody></table></main></body></html>")
    n_bytes += _emit(u"deps.html", u"\n".join(out))
    n_pages += 1

    # 3b·R92：动态链接库页 binaries.html（只有**明说出来的二进制**才在这里）
    if binaries:
        out = _head(u"动态链接库", u"", brand=brand, nav=nav, legacy=legacy_href)
        out.append(u"<h1>动态链接库（%s 个）</h1>" % _num(len(binaries)))
        out.append(u'<div class="cs-note">本页只显示**显式给出**的二进制'
                   u"（`--binary` / `--binary-attach`）。"
                   u"「没显示」与「没有依赖」是两件事 —— 没给出就是没给证据。</div>")
        _n_dep = sum(len(b.get("deps") or []) for b in binaries)
        _n_exp = sum(len(b.get("exports") or []) for b in binaries)
        _n_imp = sum(int(b.get("n_imports") or 0) for b in binaries)
        out.append(_cards([(len(binaries), u"二进制"),
                           (_n_exp, u"导出符号"),
                           (_n_imp, u"导入符号"),
                           (_n_dep, u"依赖项")]))
        for b in binaries:
            out.append(u'<h2 class="cs-mono">%s</h2>' % _esc(b.get("name")))
            out.append(_cards([(b.get("container") or u"?", u"容器"),
                               (b.get("arch") or u"?", u"架构"),
                               (b.get("bits") or u"?", u"位数"),
                               (b.get("flavour") or u"?", u"形态")]))
            if b.get("note"):
                out.append(u'<div class="cs-note">%s</div>' % _esc(b["note"]))
            deps = b.get("deps") or []
            out.append(u"<h3>依赖（%s）</h3>" % _num(len(deps)))
            if deps:
                out.append(u'<table class="cs-t"><thead><tr><th>类型</th>'
                           u"<th>名字</th></tr></thead><tbody>")
                for (dk, dn) in deps[:200]:
                    out.append(u'<tr><td>%s</td><td class="cs-mono">%s</td></tr>'
                               % (_esc(dk), _esc(dn)))
                out.append(u"</tbody></table>")
                if len(deps) > 200:
                    out.append(u'<p class="muted">… 另有 %s 条未显示</p>'
                               % _num(len(deps) - 200))
            else:
                out.append(u'<p class="muted">无依赖项记录（静态库 / 目标文件常见）。</p>')
            exp = b.get("exports") or []
            out.append(u"<h3>导出（%s）</h3>" % _num(len(exp)))
            if exp:
                out.append(u"<p>%s</p>"
                           % u" ".join(u'<code class="cs-mono">%s</code>'
                                       % _esc(x) for x in exp[:120]))
                if len(exp) > 120:
                    out.append(u'<p class="muted">… 另有 %s 个未显示</p>'
                               % _num(len(exp) - 120))
            else:
                out.append(u'<p class="muted">无导出符号。</p>')
            mit = b.get("mitigations") or {}
            if mit:
                out.append(u"<h3>缓解措施（evidence_kind=%s）</h3>"
                           % _esc(mit.get("evidence_kind") or u"?"))
                _rows = []
                for _k in sorted(mit):
                    if _k in ("evidence_kind", "basis", "limitations"):
                        continue
                    _v = mit.get(_k)
                    _rows.append((_k, u"unknown" if _v is None
                                  else (u"yes" if _v else u"NO"),
                                  (mit.get("basis") or {}).get(_k) or u""))
                out.append(_table3(u"键", u"值", u"依据", _rows))
                for _lm in (mit.get("limitations") or []):
                    out.append(u'<div class="cs-note">%s</div>' % _esc(_lm))
        if attribution:
            out.append(u"<h2>未解析调用 → 归到了谁</h2>")
            out.append(u'<p class="muted">三态：<b>library</b>（在某库里找到导出）'
                       u" / <b>source</b>（语料内其实有定义）/ "
                       u"<b>missing</b>（哪儿都没有 —— 这才是缺陷）。</p>")
            out.append(u'<table class="cs-t"><thead><tr><th>名字</th><th>归因</th>'
                       u"<th>来自</th></tr></thead><tbody>")
            for r in attribution[:max_rule_rows]:
                out.append(u'<tr><td class="cs-mono">%s</td><td>%s</td>'
                           u"<td>%s</td></tr>"
                           % (_esc(r.get("name")), _esc(r.get("attribution")),
                              _esc(u", ".join(r.get("origins") or [])
                                   or r.get("detail") or u"")))
            out.append(u"</tbody></table>")
        out.append(u"</main></body></html>")
        n_bytes += _emit(u"binaries.html", u"\n".join(out))
        n_pages += 1

    # 3c·R100：源码级动态库引用页 dynlibs.html（**四语言总生成**）
    # 与 3b 的 binaries.html 是两路：那一页回答「递过来的二进制里有什么」
    # （`binfmt.parse` 的容器读数，需要文件真的存在），本页回答「源码里想用谁」
    # —— 只读字面量，所以语料里一个库文件都没有也能出结果。两者互补：
    # 只有前者会漏掉「写了但没递文件」，只有后者会漏掉「递了文件但没写」。
    # 页面**总生成**（含 0 条、以及本语言不支持两种情形）：页面名四语言同形，
    # 而「没有这条能力」与「恰好没有引用」在页面上被分开写出来。
    out = _head(u"动态链接库引用", u"", brand=brand, nav=nav, legacy=legacy_href)
    out.append(u"<h1>动态链接库引用</h1>")
    out.append(u'<div class="cs-note">本页是**源码静态可见**的库引用：字面量实参'
               u"被提取；运行期才拼出来的名字（<code>dlopen(buf)</code>）"
               u"只记调用点、库名留空 —— 引擎**不跟踪运行期绑定**。"
               u"「容器里到底有什么」（导出 / 依赖 / 缓解措施）在另一页："
               u"<code>binaries.html</code>（那条路需要把文件递过来）。</div>")
    if _agg is None:
        out.append(u'<p class="muted">本语言（<code>%s</code>）目前**没有**源码级'
                   u"动态库引用提取 —— 已支持：%s。</p>"
                   % (_esc(lang),
                      _esc(u" / ".join(sorted(_dynlibs.SUPPORTED_LANGS)))))
    else:
        out.append(_cards([(_agg["total"], u"引用条数"),
                           (_agg["n_libs"], u"涉及库"),
                           (_agg["n_files"], u"涉及文件"),
                           (_agg["n_unknown"], u"运行期才知道")]))
        if dynlib_read_fail:
            out.append(u'<div class="cs-note">有 <b>%s</b> 个文件**读不到**'
                       u"（未纳入统计）—— 静默跳过会让「这文件没有引用」与"
                       u"「没读到」长得一样。</div>" % _num(dynlib_read_fail))
        libs = _agg["libs"]
        out.append(u"<h2>按库聚合（%s 个）</h2>" % _num(len(libs)))
        if libs:
            out.append(u'<table class="cs-t"><thead><tr><th>库名</th>'
                       u'<th class="cs-num">引用</th><th class="cs-num">文件</th>'
                       u"<th>API</th><th>语义</th></tr></thead><tbody>")
            for x in libs:
                out.append(u'<tr><td class="cs-mono">%s</td>'
                           u'<td class="cs-num">%s</td><td class="cs-num">%s</td>'
                           u"<td>%s</td><td>%s</td></tr>"
                           % (_esc(x["lib"]), _num(x["count"]),
                              _num(x["n_files"]),
                              _esc(u", ".join(x["apis"])),
                              _esc(u", ".join(x["kinds"]))))
            out.append(u"</tbody></table>")
        else:
            out.append(u'<p class="muted">本语料没有出现任何库名字面量。</p>')
        # 明细表只列**首实参本该是库名**的调用；**本来就不带库名**的
        # （句柄 / FFI 类型）在下节单列。两件事不合并不重复：
        #   * 合并会让人把条数加两遍；
        #   * 不分口径会让 `libpointer('int32Ptr')` 看起来像
        #     「运行期才知道」（R98b ⑰ 混口径）。
        _detail = [r for r in dynlib_refs if r.get("lib_is_arg", True)]
        shown = _detail[:max_rule_rows]
        out.append(u"<h2>逐条明细（%s 条%s）</h2>"
                   % (_num(len(_detail)),
                      u"，此处展开前 %s" % _num(max_rule_rows)
                      if len(_detail) > max_rule_rows else u""))
        if shown:
            out.append(u'<table class="cs-t"><thead><tr><th>文件</th>'
                       u'<th class="cs-num">行</th><th>API</th><th>库名</th>'
                       u"<th>代码</th></tr></thead><tbody>")
            for r in shown:
                out.append(u'<tr><td><a href="file/%s.html" class="cs-mono">%s</a></td>'
                           u'<td class="cs-num">%s</td><td class="cs-mono">%s</td>'
                           u'<td class="cs-mono">%s</td><td class="cs-mono">%s</td></tr>'
                           % (_esc(r.get("flat") or u""), _esc(r.get("file")),
                              _num(r.get("line") or 0), _esc(r.get("api")),
                              _esc(r.get("lib") or u"(运行期才知道)"),
                              _esc(r.get("text") or u"")))
            out.append(u"</tbody></table>")
        else:
            out.append(u'<p class="muted">零条。</p>')
        if _agg["n_no_lib_arg"]:
            out.append(u"<h2>本来就不带库名的调用（%s 条）</h2>"
                       % _num(_agg["n_no_lib_arg"]))
            out.append(u'<p class="muted">这些 API 的首实参不是库名'
                       u"（句柄 / FFI 类型），**不是**「没解析出来」。</p>")
            out.append(u'<table class="cs-t"><thead><tr><th>文件</th>'
                       u'<th class="cs-num">行</th><th>API</th>'
                       u"<th>代码</th></tr></thead><tbody>")
            for r in _agg["no_lib_arg"][:max_rule_rows]:
                out.append(u'<tr><td><a href="file/%s.html" class="cs-mono">%s</a></td>'
                           u'<td class="cs-num">%s</td><td class="cs-mono">%s</td>'
                           u'<td class="cs-mono">%s</td></tr>'
                           % (_esc(r.get("flat") or u""), _esc(r.get("file")),
                              _num(r.get("line") or 0), _esc(r.get("api")),
                              _esc(r.get("text") or u"")))
            out.append(u"</tbody></table>")
    out.append(u"</main></body></html>")
    n_bytes += _emit(u"dynlibs.html", u"\n".join(out))
    n_pages += 1

    # 3c) 索引页
    total_funcs = sum(len(e["pf"].get("functions") or []) for e in entries)
    cx_vals = [fn.get("complexity") or 0 for e in entries
               for fn in (e["pf"].get("functions") or [])]
    avg_cx = round(sum(cx_vals) / float(len(cx_vals)), 1) if cx_vals else 0.0
    out = _head(u"%s（索引）" % brand, u"", brand=brand, nav=nav,
                legacy=legacy_href)
    out.append(u"<h1>%s（--lang %s --browse）</h1>" % (_esc(brand), _esc(lang)))
    out.append(u'<p class="muted">零 JS / 零外链：图表在服务端算成 SVG 后注入，'
               u"断网双击即可打开。分页口径见 <code>renderers/csite.py</code> 模块"
               u"说明（单页报告在语料级规模下会到 GB 级）。</p>")
    out.append(u'<div class="cs-note"><b>站点地图</b>：'
               u'<a href="funcs.html">函数索引</a>（扇入 / 扇出 / 未解析名三张榜）· '
               u'<a href="deps.html">文件依赖</a>（%s 解析结果）· '
               u'<a href="dynlibs.html">动态链接库引用</a>%s · '
               u'本页 = 文件清单与目录下钻'
               u"</div>"
               % (_esc(dep_label),
                  (u' · <a href="binaries.html">动态链接库</a>') if binaries else u""))
    out.append(_cards([
        (len(entries), u"%s 文件" % _esc(display)),
        (total_funcs, u"%s 函数" % _esc(display)),
        (len(edges), u"调用边"),
        (len(unresolved), u"未解析调用"),
        (len(inc_edges), u"%s 边" % _esc(dep_label.lstrip(u"#"))),
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
    # 目录分组文件清单 —— R92 改为**每目录一页**（`dir/`）。
    # 为什么：内核级语料有 6.3 万个文件、约 2 千个目录，把它们全摊在索引页上
    # 会得到一个几 MB 的单页（正是 R76 判定的那种「不可用」形态）。每目录一页
    # 后索引页只列目录（约两千行），下钻一层才见文件。
    # R102：分组与 `dir_flat` 已在**文件条目之后**提前建好（那时 `entries`
    #   刚定型），此处直接复用，不再重复算一遍。
    for d in sorted(groups):
        lst = sorted(groups[d], key=lambda x: x["rel"])
        n_alert = sum(len(alerts_by_flat.get(x["flat"], [])) for x in lst)
        n_fn = sum(len(x["pf"].get("functions") or []) for x in lst)
        dout = _head(u"%s · 目录" % d, u"../", brand=brand, nav=nav,
                     legacy=legacy_href)
        dout.append(u'<h1 class="cs-mono">%s/</h1>' % _esc(d))
        dout.append(u'<p class="muted">%s下的 %s 个文件（本页是<b>目录页</b>，'
                    u"索引页只列目录以保持可打开）</p>" % (_esc(d), _num(len(lst))))
        dout.append(_cards([(len(lst), u"文件"), (n_fn, u"函数"),
                            (n_alert, u"告警"),
                            (sum(len(edges_by_flat.get(x["flat"], [])) for x in lst),
                             u"出边")]))
        dout.append(u'<table class="cs-t"><thead><tr><th>文件</th>'
                    u'<th class="cs-num">函数</th><th class="cs-num">告警</th>'
                    u'<th class="cs-num">出边</th><th class="cs-num">未解析</th>'
                    u"</tr></thead><tbody>")
        for x in lst:
            dout.append(
                u'<tr><td><a href="../file/%s.html" class="cs-mono">%s</a></td>'
                u'<td class="cs-num">%s</td><td class="cs-num">%s</td>'
                u'<td class="cs-num">%s</td><td class="cs-num">%s</td></tr>'
                % (_esc(x["flat"]), _esc(os.path.basename(x["rel"])),
                   _num(len(x["pf"].get("functions") or [])),
                   _num(len(alerts_by_flat.get(x["flat"], []))),
                   _num(len(edges_by_flat.get(x["flat"], []))),
                   _num(len(missing_by_flat.get(x["flat"], [])))))
        dout.append(u"</tbody></table></main></body></html>")
        n_bytes += _emit(u"dir/%s.html" % dir_flat[d], u"\n".join(dout))
        n_pages += 1
    out.append(u"<h2>目录清单（%s 个）</h2>" % _num(len(groups)))
    out.append(u'<table class="cs-t"><thead><tr><th>目录</th>'
               u'<th class="cs-num">文件</th><th class="cs-num">函数</th>'
               u'<th class="cs-num">告警</th></tr></thead><tbody>')
    for d in sorted(groups):
        lst = groups[d]
        out.append(u'<tr><td><a href="dir/%s.html" class="cs-mono">%s/</a></td>'
                   u'<td class="cs-num">%s</td><td class="cs-num">%s</td>'
                   u'<td class="cs-num">%s</td></tr>'
                   % (_esc(dir_flat[d]), _esc(d), _num(len(lst)),
                      _num(sum(len(x["pf"].get("functions") or []) for x in lst)),
                      _num(sum(len(alerts_by_flat.get(x["flat"], [])) for x in lst))))
    out.append(u"</tbody></table>")
    # 站点读数 / **没有内联的部分**（R92：不静默）
    out.append(u"<h2>站点读数与坦诚说明</h2>")
    out.append(_cards([
        (n_src_pages, u"源码页"),
        (round(n_src_bytes / 1048576.0, 1), u"源码页 MB"),
        (n_src_skip_size, u"源码页跳过（超大 / 读不到）"),
        (n_src_skip_budget, u"源码页跳过（超总预算）"),
    ]))
    out.append(u'<div class="cs-note">源码页有**两道闸**：单文件超过 %s KB 不内联，'
               u"总量超过 %s MB 不再内联。它们是**明说的**（上面两个计数），"
               u"因为「内联了一部分」与「全都内联了」在页面上长得一样 —— "
               u"而后者会让内核级站点从 KB/页涨到 GB 级。"
               u"完整的源码始终在你本机的原始文件里。</div>"
               % (_num(int(src_max_file / 1024)),
                  _num(int(src_budget / 1048576))))
    if lang == "c" and legacy_too_many:
        # 只有「C 且超阈值」才说这句话。别的语言没有这件产物，提它等于悬空引用。
        _n = len(entries)
        _lo = _n * LEGACY_BYTES_PER_FILE_LOW / 1073741824.0
        _hi = _n * LEGACY_BYTES_PER_FILE_HIGH / 1073741824.0
        out.append(u'<div class="cs-note">本次<b>没有</b>生成旧单页 '
                   u'<code>c_report.html</code>：%s 个文件超过阈值 %s。'
                   u"单页体积随文件数**与告警明细量**增长，实测基数 "
                   u"%s–%s B/文件 ⇒ 本次外推约 %.1f–%.1f GB —— 浏览器打不开，"
                   u"且与分页站点完全重复。要看完整表请用各文件页 / 目录页。</div>"
                   % (_num(_n), _num(legacy_max_files),
                      _num(LEGACY_BYTES_PER_FILE_LOW),
                      _num(LEGACY_BYTES_PER_FILE_HIGH), _lo, _hi))
    out.append(u"</main></body></html>")
    if skip_index:
        # R99：MATLAB 路径**不覆盖**站点根的 index.html —— 那里已有
        # `render_browse_site` 的富页入口（40+ 个语言专属页）。基础层的
        # 其余页面（funcs / file / dir / deps / rule / binaries）照常落盘，
        # 于是四语言的站点**页面名同形** —— 这正是登记表里
        # `site_same_page_names` 那一格从 `no` 变 `yes` 的实现。
        pass
    else:
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
        # R92：`kind` 保留历史字面量（既有消费方按它判类型），**另加** `lang`
        # 让它自报语言 —— 改掉 `kind` 会静默打断下游，只是加字段则不会。
        "lang": lang,
        "files": len(entries),
        "functions": total_funcs,
        "edges": len(edges),
        "unresolved": len(unresolved),
        "unresolved_names": len(missing_by_name),
        "unresolved_names_in_project": sum(
            1 for r in missing_by_name.values() if r["in_project"]),
        "include_edges": len(inc_edges),
        "alerts": len(alerts),
        "rule_kinds": len(alerts_by_kind),
        "dir_pages": len(groups),
        "src_pages": n_src_pages,
        "src_bytes": n_src_bytes,
        "src_skipped_size": n_src_skip_size,
        "src_skipped_budget": n_src_skip_budget,
        "binaries": len(binaries or []),
        "dynlib_refs": len(dynlib_refs),
        "dynlib_libs": (_agg["n_libs"] if _agg else 0),
        "dynlib_files": (_agg["n_files"] if _agg else 0),
        "dynlib_read_fail": dynlib_read_fail,
        "legacy_single_page": bool(write_legacy),
        "pages": n_pages,
        "bytes": n_bytes,
        "orphan_alerts": orphan_alerts,
        "ambiguous_flat": sum(1 for v in seen_flat.values() if v),
        "graph_max_nodes": graph_max_nodes,
        "graph_iters": graph_iters,
        "graph_pages": n_graph,
        "graph_nodes_drawn": n_graph_nodes,
        "graph_nodes_dropped": n_graph_dropped,
    }
    import json as _json
    if not skip_index:
        # R99：`site-quality.json` 与 `index.html` 同属**站点汇总产物** ——
        # MATLAB 路径下这两件都已有自己的版本，基础层不覆盖它们。
        _write_text(os.path.join(outdir, "site-quality.json"),
                    _json.dumps(q, ensure_ascii=False, indent=2,
                               sort_keys=True))
    q["wrote_bytes"] = n_bytes
    return q
