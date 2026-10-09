# -*- coding: utf-8 -*-
"""调用图静态 SVG 渲染（从 matlabc.py 迁出）。

承载全项目调用图与按目录聚类的函数调用图 SVG 生成；输入为文件列表与调用关系字典，
纯字符串拼装，不依赖分析逻辑。路径辅助函数由 matlabc 持有，放底部再导入。
"""
import os
import html as html_mod


def render_static_callgraph_svg(files, calls_of, callers_of, max_nodes=300, link_prefix=""):
    """P30：生成整个项目调用图的**静态 SVG**（左→右分层布局：入口/孤立函数在左，被调函数
    逐层向右）。纯文本、零依赖、无需浏览器，可直接用浏览器打开或嵌入文档 / 评审 / PPT。
    节点过多时按「扇入*2 + 扇出」降序取前 max_nodes（优先保留关键/被依赖高的函数）。
    P68：link_prefix 控制函数节点链接前缀（站点根为 ""，目录页内嵌为 "../"），点击节点
    可跳转源码页对应行。"""
    all_nodes = []
    fn_rel = {}
    for mf in files:
        for f in mf.functions:
            if f.kind != "script":
                all_nodes.append(f)
                fn_rel[id(f)] = mf.rel
    if not all_nodes:
        return ""
    if len(all_nodes) > max_nodes:
        def _score(f):
            return len(callers_of.get(id(f), [])) * 2 + len(calls_of.get(id(f), []))
        all_nodes.sort(key=lambda f: (-_score(f), fn_rel.get(id(f), "").lower(), f.line))
        all_nodes = all_nodes[:max_nodes]
    gid = {}
    for i, f in enumerate(all_nodes):
        gid[id(f)] = i
    n = len(all_nodes)
    down = [set() for _ in range(n)]
    up = [set() for _ in range(n)]
    for f in all_nodes:
        u = gid[id(f)]
        for cf, _dmf in calls_of.get(id(f), []):
            v = gid.get(id(cf))
            if v is not None:
                down[u].add(v)
                up[v].add(u)
    # BFS 分层：入口（无调用方）为第 0 层
    layer = [-1] * n
    queue = []
    for i in range(n):
        if not up[i]:
            layer[i] = 0
            queue.append(i)
    head = 0
    while head < len(queue):
        u = queue[head]
        head += 1
        for v in down[u]:
            if layer[v] == -1:
                layer[v] = layer[u] + 1
                queue.append(v)
    for i in range(n):
        if layer[i] == -1:
            layer[i] = 0
    maxlayer = max(layer) if layer else 0
    by_layer = {}
    for i in range(n):
        by_layer.setdefault(layer[i], []).append(i)
    X_GAP = 190
    Y_GAP = 30
    MARGIN = 40
    R = 6
    pos = {}
    y_cursor = MARGIN
    for L in range(maxlayer + 1):
        ids = sorted(by_layer.get(L, []), key=lambda i: (fn_rel.get(id(all_nodes[i]), "").lower(), all_nodes[i].line))
        for i in ids:
            pos[i] = (MARGIN + L * X_GAP, y_cursor)
            y_cursor += Y_GAP
    H = y_cursor + MARGIN
    W = MARGIN + (maxlayer + 1) * X_GAP + 220
    colors = {"main": "#0969da", "local": "#1a7f37", "method": "#8250df",
              "constructor": "#bf5700", "script": "#57606a"}
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
           'viewBox="0 0 %d %d" font-family="Consolas,Microsoft YaHei,sans-serif">'
           % (W, H, W, H)]
    svg.append('<rect width="100%" height="100%" fill="#ffffff"/>')
    for i in range(n):
        if i not in pos:
            continue
        x1, y1 = pos[i]
        for v in down[i]:
            if v not in pos:
                continue
            x2, y2 = pos[v]
            mx = (x1 + x2) / 2
            svg.append('<path d="M %d,%d C %d,%d %d,%d %d,%d" fill="none" '
                       'stroke="#9aa4b0" stroke-width="1"/>'
                       % (x1, y1, mx, y1, mx, y2, x2, y2))
    for i in range(n):
        if i not in pos:
            continue
        x, y = pos[i]
        f = all_nodes[i]
        color = colors.get(f.kind, "#0969da")
        rel = fn_rel.get(id(f), "")
        href = link_prefix + "src/" + _mL._page_rel(rel) + "#L%d" % f.line
        svg.append('<a href="%s">' % html_mod.escape(href, quote=True))
        svg.append('<circle cx="%d" cy="%d" r="%d" fill="%s"/>' % (x, y, R, color))
        svg.append('<text x="%d" y="%d" font-size="12" fill="#1f2328">%s</text>'
                   % (x + R + 4, y + 4, html_mod.escape(f.name)))
        svg.append('</a>')
    svg.append('</svg>')
    return "\n".join(svg)


def render_folder_function_graph_svg(files, calls_of):
    """P62：生成「目录-函数」分层调用图 SVG（doxygen 风格）——目录作为簇（圆角容器），
    函数作为簇内节点；目录内调用为浅灰边，跨目录调用为红色边（即目录依赖）。纯文本、
    零依赖，可直接用浏览器打开或嵌入文档 / 评审。"""
    from collections import defaultdict as dd
    dir_funcs = dd(list)
    fn_dir = {}
    for mf in files:
        d = os.path.dirname(mf.rel) or "(root)"
        for f in mf.functions:
            if f.kind != "script":
                dir_funcs[d].append((mf, f))
                fn_dir[id(f)] = d
    if not dir_funcs:
        return ""
    dirs = sorted(dir_funcs.keys())

    # P64：每个目录的跨目录扇出/扇入（目录级耦合度）
    fan_out = dd(int)
    fan_in = dd(int)
    for mf in files:
        sd = os.path.dirname(mf.rel) or "(root)"
        for f in mf.functions:
            for cf, cmf in calls_of.get(id(f), []):
                if cmf is None:
                    continue
                td = os.path.dirname(cmf.rel) or "(root)"
                if sd != td:
                    fan_out[sd] += 1
                    fan_in[td] += 1

    def _coupling(d):
        """返回 (边框颜色, 边框粗细)：耦合度（扇入+扇出）越高越醒目。"""
        c = fan_out.get(d, 0) + fan_in.get(d, 0)
        if c >= 4:
            return "#e5484d", 2.0      # 高耦合：红色加粗
        if c >= 2:
            return "#d4a72c", 1.6      # 中耦合：橙色
        if c >= 1:
            return "#0969da", 1.2      # 低耦合：蓝色
        return "#d0d7de", 1.0          # 无耦合：默认灰色

    Y_GAP = 26          # 函数节点垂直间距
    X_PAD = 24          # 节点距簇左边距
    Y_HEAD = 34         # 目录名标签高度
    Y_FOOT = 16         # 簇底部留白
    TOP = 30            # 所有簇顶部对齐的 Y
    R = 5

    # 计算每个目录簇的尺寸（P64：宽度兼顾目录名 + 扇入/扇出标注）
    dir_geom = {}
    for d in dirs:
        pairs = dir_funcs[d]
        max_name = max((len(f.name) for _, f in pairs), default=4)
        dir_label_len = len(d) + (8 if (fan_out.get(d, 0) or fan_in.get(d, 0)) else 0)
        w = max(max_name, dir_label_len) * 7 + 40
        if w < 110:
            w = 110
        h = len(pairs) * Y_GAP + Y_HEAD + Y_FOOT
        dir_geom[d] = {"w": w, "h": h, "pairs": pairs}

    # 水平排布簇
    X_GAP = 30
    x_cursor = 30
    for d in dirs:
        dir_geom[d]["x"] = x_cursor
        x_cursor += dir_geom[d]["w"] + X_GAP
    W = x_cursor + 10
    H = max((g["h"] for g in dir_geom.values()), default=200) + TOP + 20

    # 函数节点坐标
    fn_pos = {}
    for d in dirs:
        g = dir_geom[d]
        for idx, (_mf, f) in enumerate(g["pairs"]):
            fn_pos[id(f)] = (g["x"] + X_PAD, TOP + Y_HEAD + idx * Y_GAP)

    kind_colors = {"main": "#0969da", "local": "#1a7f37", "method": "#8250df",
                   "constructor": "#bf5700", "script": "#57606a"}

    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
           'viewBox="0 0 %d %d" font-family="Consolas,Microsoft YaHei,sans-serif">'
           % (W, H, W, H)]
    svg.append('<rect width="100%" height="100%" fill="#ffffff"/>')

    # 边：目录内浅灰，跨目录红色
    for mf in files:
        for f in mf.functions:
            if f.kind == "script" or id(f) not in fn_pos:
                continue
            x1, y1 = fn_pos[id(f)]
            for cf, _cmf in calls_of.get(id(f), []):
                if id(cf) not in fn_pos:
                    continue
                x2, y2 = fn_pos[id(cf)]
                cross = fn_dir.get(id(f)) != fn_dir.get(id(cf))
                stroke = "#e5484d" if cross else "#d0d7de"
                width = "1.4" if cross else "1"
                mx = (x1 + x2) / 2
                svg.append('<path d="M %d,%d C %d,%d %d,%d %d,%d" fill="none" '
                           'stroke="%s" stroke-width="%s"/>'
                           % (x1, y1, mx, y1, mx, y2, x2, y2, stroke, width))

    # 目录簇（容器）——P63：目录名可点击跳转站点首页；P64：按耦合度着色边框 + 标注扇入/扇出
    for d in dirs:
        g = dir_geom[d]
        bcol, bwidth = _coupling(d)
        fo = fan_out.get(d, 0)
        fi = fan_in.get(d, 0)
        label = "%s (出%d/入%d)" % (html_mod.escape(d), fo, fi) if (fo or fi) else html_mod.escape(d)
        svg.append('<rect x="%d" y="%d" width="%d" height="%d" rx="10" fill="#f6f8fa" '
                   'stroke="%s" stroke-width="%s"/>' % (g["x"], TOP, g["w"], g["h"], bcol, bwidth))
        svg.append('<a href="dirs/%s"><text x="%d" y="%d" font-size="13" '
                   'font-weight="bold" fill="%s">%s</text></a>'
                   % (_mL._dir_page_name(d), g["x"] + 12, TOP + 22, bcol, label))

    # 函数节点——P63：可点击跳转源码页对应行
    for mf in files:
        for f in mf.functions:
            if f.kind == "script" or id(f) not in fn_pos:
                continue
            x, y = fn_pos[id(f)]
            color = kind_colors.get(f.kind, "#0969da")
            href = _mL._src_href_from_rel(mf.rel) + "#L%d" % f.line
            svg.append('<a href="%s">' % html_mod.escape(href, quote=True))
            svg.append('<circle cx="%d" cy="%d" r="%d" fill="%s"/>' % (x, y, R, color))
            svg.append('<text x="%d" y="%d" font-size="12" fill="#1f2328">%s</text>'
                       % (x + R + 4, y + 4, html_mod.escape(f.name)))
            svg.append('</a>')

    svg.append('</svg>')
    return "\n".join(svg)



# R52：以下路径辅助函数仍由 matlabc 持有，但**不再**在模块底部 `from matlabc import`
# —— 那是一条 import 期回边（matlabc 底部又再导出 renderers.callgraph），两个方向
# 都依赖「对方恰好已经定义好这几个名字」这一**隐式时序契约**。现改为惰性代理：
# 首次属性访问时才取 matlabc，本模块在 import 期不再依赖 matlabc。
from renderers._late import late as _mL
