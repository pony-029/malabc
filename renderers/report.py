# -*- coding: utf-8 -*-
"""Markdown -> HTML 文本渲染 + 自包含 HTML 报告装配（从 matlabc.py 迁出）。"""
import re
import html as html_mod
from renderers.assets import (
    CORE_JS, GLOBAL_SEARCH_JS, KBD_JS, DEEPLINK_JS, LOCALCG_INIT_JS, HTML_CG_CSS, P271_A11Y_CSS)


def _inline_md(s):
    """行内 Markdown → HTML：`code`、**bold**，其余字符先做 HTML 转义（防注入）。"""
    s = html_mod.escape(s)
    s = re.sub(r"`([^`]+)`", lambda m: f"<code>{m.group(1)}</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    return s


def build_report_css():
    """FE-18：把报告页原本内联的 <style> 抽成外部 report.css（S22 门禁：内联样式
    会阻断样式缓存、膨胀 HTML）。静态样式 + HTML_CG_CSS + P271_A11Y_CSS 合并输出。"""
    return (
        "body { font-family: \"Microsoft YaHei\", \"Segoe UI\", sans-serif; "
        "max-width: 1100px; margin: 24px auto; padding: 0 20px; color: #222; }\n"
        "h1 { border-bottom: 3px solid #0072c6; padding-bottom: 8px; }\n"
        "h2 { border-left: 5px solid #0072c6; padding-left: 10px; margin-top: 32px; }\n"
        "h3 { margin-top: 24px; }\n"
        "table { border-collapse: collapse; margin: 12px 0; width: 100%; }\n"
        "th, td { border: 1px solid #ccc; padding: 6px 10px; font-size: 14px; }\n"
        "th { background: #f0f6fa; }\n"
        "code { background: #f4f4f4; padding: 1px 5px; border-radius: 3px; }\n"
        "pre { background: #f8f8f8; padding: 12px; border-radius: 6px; overflow-x: auto; }\n"
        ".mermaid { text-align: center; background: #fafafa; padding: 12px; "
        "border-radius: 8px; margin: 16px 0; }\n"
        + HTML_CG_CSS + "\n" + P271_A11Y_CSS + "\n"
    )


def write_report_css(outdir):
    """FE-18：把报告页 CSS 落盘为外部 report.css，供报告页 <link> 引用。"""
    try:
        from pathlib import Path
        Path(outdir).mkdir(parents=True, exist_ok=True)
        (Path(outdir) / "report.css").write_text(build_report_css(), encoding="utf-8")
        return True
    except Exception:
        return False


def md_to_html(md):
    """轻量级 Markdown → HTML：标题 / 表格 / 代码块 / 引用 / 列表 / 段落，统一安全转义。"""
    lines = md.split("\n")
    out = []
    i, n = 0, len(lines)
    while i < n:
        ln = lines[i]
        # 代码块 ``` ... ```
        if ln.strip().startswith("```"):
            buf = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1  # 跳过结束标记
            out.append("<pre><code>" + html_mod.escape("\n".join(buf)) + "</code></pre>")
            continue
        # 空行
        if not ln.strip():
            i += 1
            continue
        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m:
            level = len(m.group(1))
            out.append(f"<h{level}>{_inline_md(m.group(2))}</h{level}>")
            i += 1
            continue
        # 引用
        if ln.startswith(">"):
            out.append(f"<blockquote>{_inline_md(ln.lstrip('> '))}</blockquote>")
            i += 1
            continue
        # 表格（表头 | 分隔行 | 数据行）
        if ln.startswith("|") and i + 1 < n and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            headers = [c.strip() for c in ln.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            t = ["<table><thead><tr>"]
            t += [f"<th>{_inline_md(h)}</th>" for h in headers]
            t.append("</tr></thead><tbody>")
            for row in rows:
                t.append("<tr>")
                t += [f"<td>{_inline_md(c)}</td>" for c in row]
                t.append("</tr>")
            t.append("</tbody></table>")
            out.append("".join(t))
            continue
        # 列表
        if re.match(r"^\s*[-*]\s+", ln):
            items = []
            while i < n and re.match(r"^\s*[-*]\s+", lines[i]):
                # 注意：Python 3.6 的 f-string 表达式部分不允许反斜杠，
                # 这里先把正则结果存到变量，再拼接 f-string（避免 SyntaxError）。
                item_text = re.sub(r"^\s*[-*]\s+", "", lines[i])
                items.append(f"<li>{_inline_md(item_text)}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        # 普通段落
        out.append(f"<p>{_inline_md(ln)}</p>")
        i += 1
    return "\n".join(out)

def render_html(markdown_body, mermaid_txt, title="MATLAB 代码结构分析报告",
                model=None, max_nodes=None, offline=False, mermaid_cdn=False):
    """生成自包含 HTML（含 Mermaid 图 + 热点函数离线 SVG 调用图）。

    model：统一分析数据层（build_analysis_model 返回值）。若提供，则在 Mermaid 图后
    补充「热点函数调用图」区块——完全复用 --browse 浏览站点的全局邻接表
    （window.__CG__）+ 前端 initLocalCG「按需下钻」渲染与交互（点击高亮上下游、
    点击 +/- 增量展开子树），使两种输出在核心可视化上保持一致、且全部受回归测试覆盖。
    """
    mmd = html_mod.escape(mermaid_txt) if mermaid_txt else ""
    # P270：共享内核（主题统一，与 --browse / --global-state 同源单一实现）
    core_js = CORE_JS
    # P271 R4：报告页挂载命令面板（Ctrl+K）——复用与浏览站点完全相同的实现，
    # 数据取自本页已注入的 window.__CG__.meta（函数名索引），不额外增加体积。
    search_js = GLOBAL_SEARCH_JS
    # P270 R4/R3：键盘导航/无障碍层 + 可分享深链层（与 browse/global-state 同源）
    kbd_js = KBD_JS
    dl_js = DEEPLINK_JS
    # 5轮收尾改进 R3（S3 外部 CDN 白名单）：默认离线优先——**不注入** mermaid CDN，
    # 自动把 Mermaid 源码以 <pre> 展示（仍可人工阅读/复制），保证零外网请求，
    # 适配纯内网/离线环境（本工具的主要使用场景）。仅当显式 --mermaid-cdn 时才注入。
    if offline or not mermaid_cdn:
        mermaid_boot = ("<!-- 离线优先：未注入 mermaid CDN（"
                        "--mermaid-cdn 可开启在线实时流程图），"
                        "自动回退为静态 Mermaid 源码展示 -->")
    else:
        mermaid_boot = """<script>
  (function(){{
    var hasMermaid = (typeof window !== 'undefined' && window.mermaid);
    if(!hasMermaid){{
      try{{
        var s=document.createElement('script');
        s.src='https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js';
        s.onerror=function(){{ var m=document.getElementById('mermaid-fallback'); if(m) m.style.display='block'; }};
        document.head.appendChild(s);
      }}catch(e){{}}
    }}
  }})();
</script>"""
    body = md_to_html(markdown_body)
    builtin_section = ""
    if model is not None and getattr(model, "files", None):
        builtin_section = render_matlab_builtin_section(
            collect_used_builtins(model.files))
    hotspot_html = ""
    if model is not None:
        hotspot_html = render_html_hotspot_callgraphs(model, max_nodes=max_nodes)
    cg_script = ("<script>%s\nif(window.initLocalCG){window.initLocalCG();}</script>"
                 % LOCALCG_INIT_JS) if hotspot_html else ""
    metrics_html = ""
    unresolved_html = ""
    if model is not None and getattr(model, "files", None):
        # P23：关键函数风险度量（扇入/扇出 + 影响面/依赖面 + 圈复杂度排名）
        _metrics = _compute_function_metrics(
            model.files, model.callers_of, model.calls_of)
        metrics_html = ('<h2>关键函数风险度量</h2>'
                        '<div class="muted">按风险分降序排列（影响面权重最高，'
                        '兼顾扇入/依赖面/扇出/圈复杂度）。标签：'
                        '<span class="tag-key">关键</span>（影响面/被依赖度高）、'
                        '<span class="tag-god">上帝函数</span>（扇出过多或高复杂度，建议拆分）、'
                        '<span class="tag-iso">孤立</span>（无人调用也不调用他人）。</div>'
                        + _render_metrics_table(_metrics, top_n=40))
        # P25：疑似漏检调用诊断（未解析到项目/内置的调用名 + 项目内同名交叉核对）
        _unresolved = _collect_unresolved_calls(model.files)
        unresolved_html = ('<h2>疑似漏检调用诊断</h2>'
                           '<div class="muted">列出未匹配到项目函数或 MATLAB 内置函数的调用名。'
                           '<span class="tag-god">疑似漏检</span> = 项目内存在同名函数/脚本'
                           '（可能为脚本调用、限定名或解析遗漏）；'
                           '<span class="tag-iso">外部</span> = 工具箱/外部依赖。</div>'
                           + _render_unresolved_table_html(_unresolved))
    # 统一补全横切元信息（description/OG/viewport/表头 scope）：报告页不走
    # --browse 的目录收口，故在此就地接入，保证任何落盘路径都合规。
    return _finalize_html_str(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="MATLAB 代码结构分析报告：调用图 / 圈复杂度 / 目录影响面 / 跨文件耦合分析（离线优先）">
<meta name="theme-color" content="#0072c6">
<meta property="og:type" content="website">
<meta property="og:title" content="{title}">
<meta property="og:description" content="MATLAB 代码结构分析报告：调用图 / 圈复杂度 / 目录影响面 / 跨文件耦合分析">
<!-- P270：共享内核（主题统一，与 --browse / --global-state 同源） -->
<script src="app.js" defer></script>
<!-- P270 R4：键盘导航/无障碍层（? 帮助 / Esc 关闭 / t 主题 / 跳转） -->

<!-- P270 R3：可分享深链层（视图状态同步到 URL hash） -->

<!-- P147 离线优先；P269：--offline 时连 CDN 注入也一并省略，零外网请求 -->
{mermaid_boot}
<link rel="stylesheet" href="report.css">
</head>
<body>
<!-- P271 R5：无障碍基线——跳转到主内容的 skip link + <main> 语义地标 -->
<a class="skip-link" href="#main-content">跳到主内容</a>
<main id="main-content">
{body}
{builtin_section}
<h2>调用关系图</h2>
<div class="mermaid" id="mermaid-box">
{mmd}
</div>
<pre class="mermaid-fallback" id="mermaid-fallback" style="display:none;">{mmd}</pre>
<script>
  if (typeof mermaid !== 'undefined') {{
    mermaid.initialize({{ startOnLoad: true, securityLevel: 'loose' }});
  }} else {{
    // P147：离线回退——CDN 未加载时直接展示 Mermaid 源码（仍可人工阅读/复制）
    var fb = document.getElementById('mermaid-fallback');
    var box = document.getElementById('mermaid-box');
    if (fb && box) {{ fb.style.display = 'block'; }}
  }}
</script>
{metrics_html}
{unresolved_html}
{hotspot_html}
{cg_script}
<!-- P271 R4：报告页挂载命令面板（Ctrl+K）——自包含单文件没有详情/源码页可跳，
     故用自定义解析器把函数映射到**页内锚点**（热点图 hs-fn-<gid> 或度量表 fn-<名>-<行>）；
     解析不到就返回 null，该项不显示，绝不产出死链。 -->
<script>{search_js}</script>
<script>
/* P271 R3：报告是自包含单文件，站点内其它页面（index/unified/metrics/dup/
   func_detail/global_state）**并不存在**。必须显式声明，否则命令面板会列出
   这些导航命令，点了却跳到不存在的页面（「幽灵命令」——比没有更糟）。 */
window.__GS_PAGES__ = {{
  'index.html': false, 'unified.html': false, 'metrics.html': false,
  'dup.html': false, 'func_detail.html': false, 'global_state.html': false
}};
window.__GS_FN_HREF__ = function(it){{
  var n = it && it.n;
  if(!n) return null;
  if(it.g != null && document.getElementById('hs-fn-' + it.g)) return '#hs-fn-' + it.g;
  var m = (window.__CG__ && window.__CG__.meta) ? window.__CG__.meta[it.g] : null;
  var line = (m && m.l) || 0;
  var cand = 'fn-' + String(n).replace(/[^A-Za-z0-9_.-]/g, '_') + '-' + line;
  if(document.getElementById(cand)) return '#' + cand;
  // 退而求其次：按名字前缀匹配度量表锚点
  var rows = document.querySelectorAll('tr[id^="fn-"]');
  var pre = 'fn-' + String(n).replace(/[^A-Za-z0-9_.-]/g, '_') + '-';
  for(var i=0;i<rows.length;i++){{
    if(rows[i].id.indexOf(pre) === 0) return '#' + rows[i].id;
  }}
  return null;
}};
</script>
</main>
</body>
</html>
""")

# 以下分析数据层辅助函数由 matlabc 持有（被 browse/snapshot/metrics 等多处复用），
# 此处仅「借用」，保持单向依赖 renderers -> matlabc。必须放到本模块底部再导入，
# 与 matlabc 的「底部再导出 renderers.report」错开，避免部分初始化循环导入。
from matlabc import (
    render_matlab_builtin_section,
    collect_used_builtins,
    _compute_function_metrics,
    _collect_unresolved_calls,
    _finalize_html_str)
# 度量表已迁至 renderers.metrics；未解析调用表已迁至 renderers.unresolved；
# 热点调用图已迁至 renderers.hotspot。render_html 在报告中内嵌这些片段，故从此处借用。
from renderers.metrics import _render_metrics_table
from renderers.unresolved import _render_unresolved_table_html
from renderers.hotspot import render_html_hotspot_callgraphs
