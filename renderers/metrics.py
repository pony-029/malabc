# -*- coding: utf-8 -*-
"""关键函数风险度量页面渲染（从 matlabc.py 迁出）。

输入为已计算好的度量行（list[dict]），纯字符串拼装，不依赖分析逻辑。
"""
import re
import html as html_mod
from renderers._shared import _browse_page


_TAG_CLASS = {"关键": "tag-key", "上帝函数": "tag-god", "孤立": "tag-iso", "普通": ""}


def _render_metrics_table(rows, top_n=None):
    """渲染「关键函数风险度量」HTML 表格（可选只取前 top_n 行）。"""
    if top_n:
        rows = rows[:top_n]
    if not rows:
        return '<div class="muted">（无项目内函数，暂无可度量的风险指标。）</div>'
    out = ['<table class="metrics-tbl">',
           '<tr><th>#</th><th>函数</th><th>文件</th><th>行</th><th>类型</th><th>复杂度</th>'
           '<th>扇入</th><th>扇出</th><th>影响面</th><th>依赖面</th><th>风险</th><th>标签</th></tr>']
    for i, r in enumerate(rows, 1):
        # P271 R4：为每行补一个稳定的函数锚点 id，使命令面板（Ctrl+K）在报告页
        # 也能「跳转到该函数」，而不是无处可跳（报告是自包含单文件，没有详情页可去）。
        # P-rev R76：锚点并入行序号保证全局唯一——原「函数名-行号」方案在跨文件
        # 同名同行的函数（如两份重复代码样板）上会撞车，深链只认第一个。
        _anchor = "fn-%d-%s-%d" % (i, re.sub(r"[^A-Za-z0-9_.-]", "_", r["name"]),
                                   r["line"])
        out.append(
            '<tr id="%s"><td>%d</td><td><code>%s</code></td><td>%s</td><td>%d</td><td>%s</td>'
            '<td>%d</td><td>%d</td><td>%d</td><td>%d</td><td>%d</td><td>%d</td>'
            '<td><span class="%s">%s</span></td></tr>'
            % (_anchor, i, html_mod.escape(r["name"]), html_mod.escape(r["rel"]), r["line"],
               html_mod.escape(r["kind"]), r["cx"], r["fan_in"], r["fan_out"],
               r["impact"], r["dependency"], r["risk"], _TAG_CLASS.get(r["tag"], ""),
               r["tag"]))
    out.append('</table>')
    return "".join(out)


# P-rev R78：浏览站页面统一骨架。此前每个 render_* 页面都各自手工重复
# <!DOCTYPE>/<head>/<style>BROWSE_CSS/skip-link/header/<main> 一整套样板——
# 是站内最大的拷贝面之一。统一为 _browse_page 后，新页面不再逐份手抄骨架。
# 关键约束：输出与旧式逐行 A() 拼接**逐字节一致**（样板行顺序/换行不变量），
# 试点页重构前后产物 sha256 不变（见 R78 契约测试）。
def render_metrics_page(rows):
    """生成独立的「关键函数风险度量」页面（--browse 模式专用）。"""
    lines = []
    A = lines.append
    A("<h1>关键函数风险度量</h1>")
    A("<div class=\"muted\">按「风险分」降序排列项目内全部函数：<b>影响面</b>（改动本函数会波及"
      "多少函数，权重最高）、<b>扇入</b>（被多少函数调用）、<b>依赖面</b>、<b>扇出</b>、<b>圈复杂度</b>"
      "综合加权。标签：<span class=\"tag-key\">关键</span> = 影响面/被依赖度高，改动需谨慎；"
      "<span class=\"tag-god\">上帝函数</span> = 扇出过多或高复杂度，建议拆分；"
      "<span class=\"tag-iso\">孤立</span> = 无人调用也不调用他人。</div>")
    A(_render_metrics_table(rows))
    # P-rev R78：骨架统一模板 _browse_page（输出与旧样板逐字节一致）
    return _browse_page("关键函数风险度量", "关键函数风险度量", "\n".join(lines))


