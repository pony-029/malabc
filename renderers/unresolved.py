# -*- coding: utf-8 -*-
"""「疑似漏检调用诊断」页面渲染（从 matlabc.py 迁出）。

输入为已收集好的诊断行（list[dict]），纯字符串拼装，不依赖分析逻辑。
"""
import html as html_mod
from renderers._shared import _browse_page


def _render_unresolved_table_html(rows, link_fn=None):
    """渲染「疑似漏检调用诊断」HTML 表格。link_fn(rel, line)->href（可选，browse 用）。"""
    if not rows:
        return ('<div class="muted">未发现未解析调用——所有调用均已匹配到项目函数或 '
                'MATLAB 内置函数。</div>')
    out = ['<table class="metrics-tbl"><tr><th>调用名</th><th>次数</th>'
           '<th>项目内同名</th><th>说明</th></tr>']
    for r in rows:
        if r["in_project"]:
            loc = "、".join(
                ('<a href="%s#L%d">%s:%s</a>' % (link_fn(rel, line), line, rel, name)
                 if link_fn else '%s:%s' % (rel, name))
                for (rel, name, line, kind) in r["matches"])
            out.append('<tr><td><code>%s</code></td><td>%d</td>'
                       '<td><span class="tag-god">疑似漏检</span></td>'
                       '<td>项目内存在同名函数/脚本：%s（可能为脚本调用、限定名或解析遗漏，请核对）</td></tr>'
                       % (html_mod.escape(r["name"]), r["count"], loc))
        else:
            out.append('<tr><td><code>%s</code></td><td>%d</td>'
                       '<td><span class="tag-iso">外部</span></td>'
                       '<td>未匹配到项目内同名函数，可能为工具箱 / 外部依赖</td></tr>'
                       % (html_mod.escape(r["name"]), r["count"]))
    out.append('</table>')
    return "".join(out)


def render_unresolved_page(rows, orphaned=None, dynamic=None, indirect=None, index_like=None):
    """生成独立的「疑似漏检调用诊断」页面（--browse 模式专用）。
    orphaned: 无法溯源到根的函数列表 [(mf, fn), ...]；dynamic: 动态执行调用汇总列表；
    indirect: P225-L 间接调用汇总列表（cell 元素/索引后/动态字段方法）；
    index_like: P225-M 索引样式调用汇总列表（A(:)/A(end)/A(1) 等疑似数组索引）。"""
    lines = []
    A = lines.append
    A("<h1>疑似漏检调用诊断</h1>")
    A("<div class=\"muted\">列出每个函数体中「未匹配到项目函数或 MATLAB 内置函数」的调用名，"
      "按调用次数降序。若某名在项目内存在同名函数/脚本（<span class=\"tag-god\">疑似漏检</span>），"
      "说明可能存在脚本调用、限定名或解析遗漏，请核对；否则为工具箱/外部依赖（"
      "<span class=\"tag-iso\">外部</span>）。</div>")
    A(_render_unresolved_table_html(rows, link_fn=lambda rel, line: _mL._src_href_from_rel(rel)))

    # P43：溯源完整性——无法溯源到根的函数（处于调用循环、缺外部入口）
    A("<h2>溯源完整性（无法溯源到根的函数）</h2>")
    A("<div class=\"muted\">下列函数「有调用方，但沿调用方上溯无法到达无调用方入口」，"
      "通常意味着处于调用循环、或上层调用仍未解析（可结合上方疑似漏检与动态调用排查）。</div>")
    if orphaned:
        A("<ul class=\"call-order-list\">")
        for mf, f in orphaned:
            A("<li><a href=\"%s#L%d\">%s</a><span class=\"muted\"> · %s</span></li>"
              % (_mL._src_href_from_rel(mf.rel), f.line, html_mod.escape(f.name),
                 html_mod.escape(mf.rel)))
        A("</ul>")
    else:
        A("<div class=\"muted\">无——所有函数均可上溯到入口，或本身即为入口函数。</div>")

    # P43：动态执行调用（eval/run/evalin/evalc 等，需人工确认调用关系）
    A("<h2>动态执行调用（需人工确认调用关系）</h2>")
    A("<div class=\"muted\">下列函数存在 <code>eval</code>/<code>run</code>/<code>evalin</code>/"
      "<code>evalc</code> 等无法可靠静态解析的动态调用，可能遗漏上层调用方，请人工核对。</div>")
    if dynamic:
        A("<ul class=\"call-order-list\">")
        for d in dynamic:
            cnts = ", ".join("%s × %d" % (k, v) for k, v in sorted(d["counts"].items()))
            A("<li><a href=\"%s#L%d\">%s</a><span class=\"muted\"> · %s · %s</span></li>"
              % (_mL._src_href_from_rel(d["rel"]), d["line"], html_mod.escape(d["name"]),
                 html_mod.escape(d["rel"]), cnts))
        A("</ul>")
    else:
        A("<div class=\"muted\">无动态执行调用。</div>")

    # P225-L：间接调用（cell 元素 C{1}(x) / 索引后 A(i)(x) / 动态字段 .(v)(x)）
    A("<h2>间接调用（cell/索引/动态字段修饰后调用，目标运行期确定）</h2>")
    A("<div class=\"muted\">下列调用被元胞索引、数组索引或动态字段修饰（如 <code>C{1}(x)</code>、"
      "<code>A(i)(x)</code>、<code>obj.(v)(x)</code>），调用目标运行期才确定，无法静态解析为项目内"
      "具体函数。此前调用图会完全遗漏这类调用，此处提示性列出，供人工核对潜在调用方。</div>")
    if indirect:
        A("<ul class=\"call-order-list\">")
        for d in indirect:
            cnts = ", ".join("%s × %d" % (k, v) for k, v in sorted(d["counts"].items()))
            A("<li><a href=\"%s#L%d\">%s</a><span class=\"muted\"> · %s · %s</span></li>"
              % (_mL._src_href_from_rel(d["rel"]), d["line"], html_mod.escape(d["name"]),
                 html_mod.escape(d["rel"]), cnts))
        A("</ul>")
    else:
        A("<div class=\"muted\">无间接调用。</div>")

    # P225-M：索引样式调用（A(:)/A(end)/A(1)/A(2,3) 等疑似数组索引，非函数调用）
    A("<h2>索引样式调用（疑似数组索引，已从「疑似漏检」剥离）</h2>")
    A("<div class=\"muted\">下列被调名以 <code>A(:)</code>/<code>A(end)</code>/<code>A(1)</code>/"
      "<code>A(2,3)</code> 等强索引信号出现，MATLAB 同源语法下几乎必然是数组索引而非函数调用。"
      "已从「疑似漏检调用」诊断中剥离，避免把变量索引误报为缺失调用；此处仅作标注性列出。</div>")
    if index_like:
        A("<ul class=\"call-order-list\">")
        for d in index_like:
            cnts = ", ".join("%s × %d" % (k, v) for k, v in sorted(d["counts"].items()))
            A("<li><a href=\"%s#L%d\">%s</a><span class=\"muted\"> · %s · %s</span></li>"
              % (_mL._src_href_from_rel(d["rel"]), d["line"], html_mod.escape(d["name"]),
                 html_mod.escape(d["rel"]), cnts))
        A("</ul>")
    else:
        A("<div class=\"muted\">无索引样式调用。</div>")

    # P-rev R78：骨架统一模板 _browse_page（输出与旧样板逐字节一致）
    return _browse_page("疑似漏检调用诊断", "疑似漏检调用诊断", "\n".join(lines))



# R52：_src_href_from_rel 仍由 matlabc 持有（被多个渲染模块复用），但不再
# `from matlabc import` —— 那是 import 期回边。改为惰性代理，见 renderers/_late.py。
from renderers._late import late as _mL
