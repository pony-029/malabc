# -*- coding: utf-8 -*-
"""C 语言前端分析报告渲染（从 matlabc.py 迁出）。

承载 --lang c 的报告页与索引页；输入为语言无关 C 模型（dict），纯字符串拼装。
"""
import html as html_mod


def render_c_report(c_model, bridge, root):
    """P87：生成 C 语言前端分析报告（c_report.html）。

    展示 C 函数表、内部调用边、include 依赖、未解析调用，
    以及（混合模式下）MATLAB ↔ C MEX 桥接调用。"""
    c_files = c_model.get("files", []) or []
    edges = c_model.get("edges", []) or []
    unresolved = c_model.get("unresolved", []) or []
    bridge = bridge or []
    n_funcs = sum(len(pf["functions"]) for pf in c_files)
    n_incs = sum(len(pf["includes"]) for pf in c_files)
    cx_vals = [fn["complexity"] for pf in c_files for fn in pf["functions"]]
    avg_cx = round(sum(cx_vals) / len(cx_vals), 1) if cx_vals else 0
    # (fn, pf) 元组化，避免把 file 引用写进函数 dict（JSON 序列化会递归）
    fn_items = [(fn, pf) for pf in c_files for fn in pf["functions"]]
    top_cx = sorted(fn_items, key=lambda x: -x[0]["complexity"])[:5]
    # 扇入/扇出
    fan_in = {}
    fan_out = {}
    for (ca, cb, _ln, _f) in edges:
        fan_in[cb] = fan_in.get(cb, 0) + 1
        fan_out[ca] = fan_out.get(ca, 0) + 1
    lines = []
    A = lines.append
    A("<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
      "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">")
    A("<title>C 语言前端分析</title>")
    A('<link rel="stylesheet" href="browse.css">')
    A("</head><body>")
    A('<a class="skip-link" href="#main-content">跳到主内容</a>')
    A("<header><span class=\"brand\">C 语言前端分析</span>"
      "<a href=\"index.html\">&larr; 返回索引</a></header>")
    A("<main id=\"main-content\">")
    A("<h1>C 语言前端分析（多语言后端）</h1>")
    A("<p class=\"muted\">轻量 C 前端把「函数定义 → 调用 → 复杂度 → include 依赖」"
      "解析为与 MATLAB 前端一致的语言无关模型，验证解析层可抽象、可按语言扩展。</p>")
    A("<div class=\"stats-cards\">")
    A("<div class=\"stat-card\"><div class=\"num\">%d</div>C 文件</div>" % len(c_files))
    A("<div class=\"stat-card\"><div class=\"num\">%d</div>C 函数</div>" % n_funcs)
    A("<div class=\"stat-card\"><div class=\"num\">%d</div>内部调用边</div>" % len(edges))
    A("<div class=\"stat-card\"><div class=\"num\">%d</div>未解析调用</div>" % len(unresolved))
    A("<div class=\"stat-card\"><div class=\"num\">%d</div>include 依赖</div>" % n_incs)
    A("<div class=\"stat-card\"><div class=\"num\">%s</div>平均复杂度</div>" % avg_cx)
    A("<div class=\"stat-card\"><div class=\"num\">%d</div>MATLAB↔C 桥接</div>"
      % len(bridge))
    A("</div>")
    if not c_files:
        A("<div class=\"muted\">未发现 C/C++ 源码文件（--lang c 或 --mixed 时扫描 .c/.h）。</div>")
        A("</main></body></html>")
        return "\n".join(lines)
    A("<h2>复杂度 TOP5</h2><table id=\"c-table\"><thead><tr>"
      "<th>函数</th><th>文件</th><th>复杂度</th><th>行</th></tr></thead><tbody>")
    for (fn, pf) in top_cx:
        A("<tr><td class=\"mono\">%s</td><td>%s</td>"
          "<td class=\"cx\">%d</td><td>%d</td></tr>"
          % (html_mod.escape(fn["name"]), html_mod.escape(pf["rel"]),
             fn["complexity"], fn["line"]))
    A("</tbody></table>")
    A("<h2>C 函数总览</h2><table id=\"c-table\"><thead><tr>"
      "<th>函数</th><th>文件</th><th>返回类型</th><th>参数</th><th>行</th>"
      "<th>复杂度</th><th>扇入</th><th>扇出</th></tr></thead><tbody>")
    all_fns = sorted(fn_items, key=lambda x: (x[1]["rel"], x[0]["line"]))
    for (fn, pf) in all_fns:
        A("<tr><td class=\"mono\">%s</td><td>%s</td>"
          "<td class=\"mono\">%s</td><td class=\"mono\">%s</td>"
          "<td>%d</td><td class=\"cx\">%d</td><td>%d</td><td>%d</td></tr>"
          % (html_mod.escape(fn["name"]), html_mod.escape(pf["rel"]),
             html_mod.escape(fn.get("ret", "") or ""),
             html_mod.escape(", ".join(fn["params"])),
             fn["line"], fn["complexity"],
             fan_in.get(fn["name"], 0), fan_out.get(fn["name"], 0)))
    A("</tbody></table>")
    if n_incs:
        A("<h2>include 依赖</h2><table id=\"c-table\"><thead><tr>"
          "<th>文件</th><th>头文件</th></tr></thead><tbody>")
        for pf in c_files:
            if not pf["includes"]:
                continue
            inc_html = "".join("<code class=\"inc\">%s</code> "
                               % html_mod.escape(i) for i in pf["includes"])
            A("<tr><td>%s</td><td>%s</td></tr>"
              % (html_mod.escape(pf["rel"]), inc_html))
        A("</tbody></table>")
    # P90：#include 跨文件依赖边（解析到项目内文件 → 跨文件结构边）
    inc_edges = c_model.get("include_edges", []) or []
    if inc_edges:
        n_ok = sum(1 for e in inc_edges if e[2])
        A("<h2>#include 跨文件依赖边 "
          "<span class=\"muted\">（%d 条 · 解析 %d · 未解析 %d）</span></h2>"
          % (len(inc_edges), n_ok, len(inc_edges) - n_ok))
        A("<table id=\"c-table\"><thead><tr><th>源文件</th><th>#include</th>"
          "<th>解析到项目内文件</th></tr></thead><tbody>")
        for (frm, inc, to) in sorted(inc_edges):
            if to:
                A("<tr><td>%s</td><td><code>%s</code></td><td>%s</td></tr>"
                  % (html_mod.escape(frm), html_mod.escape(inc),
                     html_mod.escape(to)))
            else:
                A("<tr><td>%s</td><td><code>%s</code></td>"
                  "<td class=\"miss\">未找到（系统库或项目外）</td></tr>"
                  % (html_mod.escape(frm), html_mod.escape(inc)))
        A("</tbody></table>")
    if edges:
        A("<h2>内部调用图（文本）</h2><pre class=\"mono\">")
        for (ca, cb, ln, f) in sorted(edges):
            A("%s:%d  %s → %s" % (html_mod.escape(f), ln,
                                  html_mod.escape(ca), html_mod.escape(cb)))
        A("</pre>")
    else:
        A("<h2>内部调用图</h2><div class=\"muted\">C 函数间未发现内部调用。</div>")
    if unresolved:
        A("<h2>未解析调用</h2><table id=\"c-table\"><thead><tr>"
          "<th>被调函数</th><th>行</th><th>文件</th></tr></thead><tbody>")
        for (name, ln, f) in sorted(unresolved):
            A("<tr><td class=\"mono\">%s</td><td>%d</td><td>%s</td></tr>"
              % (html_mod.escape(name), ln, html_mod.escape(f)))
        A("</tbody></table>")
    if bridge:
        A("<h2>MATLAB ↔ C MEX 桥接</h2><table id=\"c-table\"><thead><tr>"
          "<th>MATLAB 函数</th><th>文件</th><th>桥接 C 函数</th><th>C 文件</th>"
          "<th>调用次数</th></tr></thead><tbody>")
        for b in bridge:
            A("<tr><td class=\"mono\">%s</td><td>%s</td>"
              "<td class=\"mono\">%s</td><td>%s</td><td>%d</td></tr>"
              % (html_mod.escape(b["matlab"]), html_mod.escape(b["mfile"]),
                 html_mod.escape(b["c_func"]), html_mod.escape(b["c_file"]),
                 b["count"]))
        A("</tbody></table>")
    A("</main></body></html>")
    return "\n".join(lines)


def render_c_index_html(c_model, root, rel="c_report.html"):
    """P87：纯 C 模式（--lang c）的简易索引页，导航到 C 分析报告。"""
    stats = {
        "files": len(c_model.get("files", []) or []),
        "functions": sum(len(pf["functions"]) for pf in c_model.get("files", [])),
        "edges": len(c_model.get("edges", []) or []),
        "unresolved": len(c_model.get("unresolved", []) or []),
    }
    lines = []
    A = lines.append
    A("<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
      "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">")
    A("<title>C 语言前端分析索引</title>")
    A('<link rel="stylesheet" href="browse.css">')
    A("</head><body>")
    A('<a class="skip-link" href="#main-content">跳到主内容</a>')
    A("<header><span class=\"brand\">C 语言前端分析</span>"
      "<a href=\"c_report.html\">C 分析报告 &rarr;</a></header>")
    A("<main id=\"main-content\">")
    A("<h1>C 语言前端分析索引（--lang c）</h1>")
    A("<p class=\"muted\">多语言后端扩展（P87）：轻量 C 前端把 .c/.h 解析为"
      "与 MATLAB 前端一致的语言无关模型。</p>")
    A("<div class=\"stats-cards\">"
      "<div class=\"stat-card\"><div class=\"num\">%d</div>C 文件</div>"
      "<div class=\"stat-card\"><div class=\"num\">%d</div>C 函数</div>"
      "<div class=\"stat-card\"><div class=\"num\">%d</div>调用边</div>"
      "<div class=\"stat-card\"><div class=\"num\">%d</div>未解析调用</div>"
      "</div>" % (stats["files"], stats["functions"], stats["edges"],
                  stats["unresolved"]))
    A("<ul><li><a href=\"c_report.html\">C 语言前端分析报告</a>"
      "（函数表 / 调用图 / include 依赖 / 复杂度 TOP）</li></ul>")
    A("</main></body></html>")
    return "\n".join(lines)


