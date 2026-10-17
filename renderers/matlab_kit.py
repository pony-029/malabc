# -*- coding: utf-8 -*-
"""渲染工具：九个**不依赖 matlabc 模块级符号**的纯函数。

批次一（3 个，deps=0）：`render_tree` / `render_call_chain` / `render_call_detail`。
批次二（6 个，只依赖 `html_kit`）：`render_mermaid` / `render_dot` /
`render_operator_impact_page` / `render_ai_prompts_page` / `render_checks_page` /
`render_compliance_page`。

从 `matlabc.py` 搬出（R156，P2 第一批）。判据：

- `--json`：`tools/json_diff.py before after --ignore generated_at` → rc=0
- `--browse`：`tools/tree_diff.py A B --ignore-line "generated_at|生成时间"
  --ignore-file "manifest\\.json"` → rc=0

为什么先搬这三个：依赖分析（`globs ∩ Load`）实测它们 **deps=0**，且各自只有
1 处调用（都在 `render_markdown_report` 里）。它们不 import `matlabc`，
所以 `renderers/` 不会反向依赖产品文件（`check_import_graph` 的 G1）。
"""
import html as html_mod
import os

from renderers.html_kit import (_compliance_score, _dot_label,
                                   _html_esc, _mermaid_label,
                                   _src_href_from_rel)



def render_tree(files, root, rel):
    """生成目录树文本。files: [(rel, kind)]"""
    lines_out = []
    tree = {}
    for r, _ in files:
        parts = r.split("/")
        node = tree
        for p in parts:
            node = node.setdefault(p, {})
    # 递归绘制
    def walk(node, prefix, is_last, is_root=False):
        items = list(node.items())
        for i, (name, sub) in enumerate(items):
            if is_root:
                lines_out.append(f"📁 {name}/")
            else:
                conn = "└── " if i == len(items) - 1 else "├── "
                lines_out.append(prefix + conn + name)
            nxt_prefix = prefix + ("    " if i == len(items) - 1 else "│   ")
            walk(sub, nxt_prefix, i == len(items) - 1)
    lines_out.append(f"{root}/")
    walk(tree, "", True, False)
    return "\n".join(lines_out)


def render_call_chain(outgoing, incoming, nodes, max_entries=50):
    """生成「从入口到末端」的调用树文本行列表（树形缩进，标注调用层级）。

    入口 = 项目内没有被任何函数调用的函数（通常是主函数/脚本/回调入口）。
    自顶向下展示「谁先执行、再调用了谁」，直观反映从头到尾的执行路径；
    每行标注调用深度（距入口的层级），便于快速判断执行先后顺序。
    """
    lines = []
    if not nodes:
        return lines
    entries = sorted(n for n in nodes if not incoming.get(n))
    if not entries:
        entries = sorted(nodes)[:1]  # 全是环，任取其一作为入口
    for entry in entries[:max_entries]:
        lines.append("【入口】" + entry)
        visited = set()

        def walk(node, depth, stack):
            for callee in sorted(outgoing.get(node, ())):
                indent = "    " * (depth + 1)
                lines.append(indent + "└── [%d] %s" % (depth + 1, callee))
                if callee in stack:
                    lines.append(indent + "    (循环调用，已截断)")
                    continue
                if callee in visited:
                    lines.append(indent + "    (已在当前链路出现，已截断)")
                    continue
                visited.add(callee)
                walk(callee, depth + 1, stack + (callee,))

        visited.add(entry)
        walk(entry, 0, (entry,))
        lines.append("")
    if len(entries) > max_entries:
        lines.append("（入口函数过多，仅展示前 %d 个；完整关系见 Mermaid / DOT 图）" % max_entries)
    return lines


def render_call_detail(outgoing, incoming, nodes, max_nodes=300,
                       label_to_func=None, ambiguous=None):
    """逐函数列出：它调用了谁、被谁调用（双向关系）。

    label_to_func: 节点标签 -> MatlabFunction，用于显示类型 / 文件；
    ambiguous: 集合，元素为 "调用方标签:被调短名"，命中则提示该调用存在同名歧义。
    """
    lines = []
    shown = 0
    for node in sorted(nodes):
        lines.append("#### `" + node + "`")
        func = label_to_func.get(node) if label_to_func else None
        if func is not None:
            kind = getattr(func, "kind", "")
            src = func.mfile.rel if func.mfile else "?"
            lines.append("- 类型：%s · 文件：`%s`" % (kind, src))
        outs = sorted(outgoing.get(node, ()))
        ins = sorted(incoming.get(node, ()))
        if outs:
            lines.append("- 调用了（%d）：" % len(outs) + "、".join("`%s`" % c for c in outs))
        else:
            lines.append("- 调用了：无（末端 / 叶子函数）")
        if ins:
            lines.append("- 被调用（%d）：" % len(ins) + "、".join("`%s`" % c for c in ins))
        else:
            lines.append("- 被调用：无（入口函数）")
        if ambiguous and node in ambiguous:
            lines.append("- ⚠ 该函数存在**同名函数歧义**：部分被调名在多处定义，"
                         "链接已尽量就近解析，可能并非你期望的目标。")
        lines.append("")
        shown += 1
        if shown >= max_nodes:
            lines.append("（参与调用的函数过多，仅展示前 %d 个）" % max_nodes)
            break
    return lines


def render_mermaid(files, edges, file_graph, title="MATLAB 调用图", folder_graph=False):
    """生成 Mermaid flowchart。file_graph=文件级聚合；folder_graph=文件夹级聚合（P57）。"""
    lines = [f"flowchart LR"]
    node_ids = {}
    if folder_graph:
        # P57：文件夹级——节点为目录，边为跨目录调用
        dirs = sorted({os.path.dirname(mf.rel) or "(root)" for mf in files})
        for i, d in enumerate(dirs):
            node_ids[d] = f"D{i}"
            lines.append(f'  D{i}["{_mermaid_label(d)}"]')
    elif file_graph:
        # 文件级
        for i, mf in enumerate(files):
            node_ids[mf.rel] = f"F{i}"
            lines.append(f'  F{i}["{_mermaid_label(mf.rel)}"]')
    else:
        # 函数级
        idx = 0
        for mf in files:
            for f in mf.functions:
                node_ids[f"{(mf.rel)}:{f.name}"] = f"n{idx}"
                label = f"{os.path.basename(mf.rel)}:{f.name}"
                if f.kind == "method":
                    label += "()"
                lines.append(f'  n{idx}["{_mermaid_label(label)}"]')
                idx += 1
    lines.append("")
    seen = set()
    for caller, callee, cross in edges:
        if folder_graph:
            a = os.path.dirname(caller.split(":")[0]) or "(root)"
            b = os.path.dirname(callee.split(":")[0]) or "(root)"
            if a == b:
                continue
        elif file_graph:
            if not cross:
                continue
            a, b = caller.split(":")[0], callee.split(":")[0]
        else:
            a, b = caller, callee
        if a not in node_ids or b not in node_ids:
            continue
        key = (node_ids[a], node_ids[b])
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"  {node_ids[a]} --> {node_ids[b]}")
    return "\n".join(lines)


def render_dot(files, edges, file_graph, folder_graph=False):
    """生成 Graphviz DOT 文件。file_graph=文件级聚合；folder_graph=文件夹级聚合（P57）。"""
    lines = ["digraph matlab {"]
    if folder_graph:
        # P57：文件夹级
        dirs = sorted({os.path.dirname(mf.rel) or "(root)" for mf in files})
        for d in dirs:
            lines.append(f'  "D-{_dot_label(d)}" [label="{_dot_label(d)}"];')
        for caller, callee, _ in edges:
            a = os.path.dirname(caller.split(":")[0]) or "(root)"
            b = os.path.dirname(callee.split(":")[0]) or "(root)"
            if a == b:
                continue
            lines.append(f'  "D-{_dot_label(a)}" -> "D-{_dot_label(b)}";')
    elif file_graph:
        for mf in files:
            label = mf.rel.replace("\\", "/")
            lines.append(f'  "F-{_dot_label(mf.rel)}" [label="{_dot_label(label)}"];')
        for caller, callee, cross in edges:
            if not cross:
                continue
            a, b = caller.split(":")[0], callee.split(":")[0]
            lines.append(f'  "F-{_dot_label(a)}" -> "F-{_dot_label(b)}";')
    else:
        for mf in files:
            for f in mf.functions:
                label = f"{os.path.basename(mf.rel)}:{f.name}"
                nid = f"{mf.rel}:{f.name}"
                lines.append(f'  "{_dot_label(nid)}" [label="{_dot_label(label)}"];')
        for caller, callee, _ in edges:
            lines.append(f'  "{_dot_label(caller)}" -> "{_dot_label(callee)}";')
    lines.append("}")
    return "\n".join(lines)


def render_operator_impact_page(oi):
    """生成「算子工程影响分析」浏览页（operator_impact.html）：复用站点外部样式，
    不使用内联 <style>（满足 fe_audit S22），并含 skip-link / <main> / 条形图。
    P221-A：额外渲染「算子目录覆盖」——目录全量算子（每一个都被统计）命中/零命中。"""
    _ops = oi.get("operators", [])
    _max = max((r["impact"] for r in _ops), default=0.0) or 1.0
    _rows = []
    for _r in _ops:
        _w = min(100.0, _r["impact"] / _max * 100.0)
        _color = {"error": "#dc2626", "warning": "#d97706", "note": "#2563eb"}.get(
            _r["level"], "#2563eb")
        _rows.append(
            '<tr><td title="%s">%s</td><td>%.2f</td>'
            '<td><div style="width:%.1f%%;background:%s;height:14px;border-radius:3px">'
            '</div></td><td>%s</td></tr>'
            % (_r["rule"], _html_esc(_r["label"]), _r["impact"], _w, _color,
               _html_esc(_r["category"])))
    _bars = "".join(_rows)
    _meta = oi.get("_meta") or {}
    _gen = _meta.get("generated_at", "")

    # P221-A：目录全量算子（每一个都被统计）——命中/零命中/仅元数据
    _cat = oi.get("catalog_operators") or []
    _total = oi.get("catalog_total", len(_cat))
    _fired_n = oi.get("catalog_fired",
                      sum(1 for _c in _cat if _c["fired"]))
    _unmapped = oi.get("catalog_unmapped", max(0, _total - len(_cat)))
    _zerohit = sum(1 for _c in _cat if not _c["fired"])
    _level_badge = {"error": "#dc2626", "warning": "#d97706", "note": "#2563eb"}
    _cat_rows = []
    for _c in sorted(_cat, key=lambda c: (not c["fired"], -c["impact"])):
        _lc = _level_badge.get(_c["level"], "#2563eb")
        _state = ("✅ 命中 %d" % _c["count"]) if _c["fired"] else "⚪ 零命中"
        _cat_rows.append(
            '<tr class="%s"><td title="%s">%s</td>'
            '<td><span style="color:%s;font-weight:600">%s</span></td>'
            '<td>%s</td><td>%s</td></tr>'
            % ("op-fired" if _c["fired"] else "op-zero",
               _html_esc(_c["rule"]), _html_esc(_c["label"]), _lc,
               _html_esc(_c["level"]), _html_esc(_c["category"]), _state))
    _cat_table = "".join(_cat_rows)
    _coverage_box = (
        "<p class=\"muted\">算子目录覆盖：已纳入统计 <b>%d</b> / 目录 <b>%d</b> ｜ "
        "本次命中 <b>%d</b> ｜ 零命中盲区 <b>%d</b> ｜ 仅元数据/未纳管 <b>%d</b></p>"
        % (len(_cat), _total, _fired_n, _zerohit, _unmapped))

    return (
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>检测算子工程影响分析</title>"
        "<link rel=\"stylesheet\" href=\"src/styles.css\"></head><body>"
        "<a class=\"skip-link\" href=\"#main-content\">跳到主内容</a>"
        "<main id=\"main-content\" class=\"container\">"
        "<h1>检测算子工程影响分析（R62）</h1>"
        "<p class=\"muted\">触发算子 <b>%d</b> 个 ｜ 总检出 <b>%d</b> 条 ｜ 总影响分 <b>%.2f</b>%s</p>"
        "<h2>算子目录覆盖（每一个算子都被统计）</h2>"
        "%s"
        "<table class=\"data-table\"><thead><tr><th>算子</th><th>级别</th>"
        "<th>类别</th><th>状态</th></tr></thead><tbody>%s</tbody></table>"
        "<h2>命中算子（影响排名）</h2>"
        "<table class=\"data-table\"><thead><tr><th>算子</th><th>影响分</th>"
        "<th>占比</th><th>类别</th></tr></thead><tbody>%s</tbody></table>"
        "</main></body></html>"
        % (oi.get("fired_count", 0), oi.get("total_findings", 0),
           oi.get("total_impact", 0.0),
           (" ｜ 生成于 %s" % _gen) if _gen else "",
           _coverage_box, _cat_table, _bars))


def render_ai_prompts_page(title, body):
    """AI 分析页（ai_prompts.html）：清晰标注「静态分析 ↔ 动态 AI 分析」边界，
    并渲染离线/在线两条接入路径。P221-D：AI 随时可接入，不改变静态事实。"""
    _body_html = "<pre class=\"ai-prompt\">%s</pre>" % _html_esc(body or "")
    _boundary = (
        "<section class=\"ai-boundary\">"
        "<h2>静态分析 ↔ 动态 AI 分析（边界说明）</h2>"
        "<ul>"
        "<li><b>静态分析（本站点全部页面）</b>：由 matlabc 确定性算出的事实"
        "——结构 / 调用图 / 维度 / 算子影响 / SARIF。可复现、可审计、零外部依赖。</li>"
        "<li><b>动态 AI 分析（本页）</b>：可选的解释层，消费上述静态事实，对代码做"
        "评审 / 修复 / 补测试 / 重构建议。AI 随时可接入：</li>"
        "<ul>"
        "<li><b>离线（默认）</b>：下方提示词可直接复制粘贴至任意 LLM；无密钥、不联网。</li>"
        "<li><b>在线（多模型，含国产）</b>：配置对应密钥（如 <code>OPENAI_API_KEY</code> / "
        "<code>ANTHROPIC_API_KEY</code> / <code>DASHSCOPE_API_KEY</code>(通义千问) / "
        "<code>ZHIPU_API_KEY</code>(智谱) / <code>DEEPSEEK_API_KEY</code> / "
        "<code>MOONSHOT_API_KEY</code>(Kimi) / <code>ERNIE_API_KEY</code>+<code>ERNIE_SECRET_KEY</code>(文心) 等）后，"
        "用 <code>ai_cli.py --provider qwen --prompt-file ai_prompts.json --task review</code> 一键调用"
        "（<code>--provider</code> 支持 deepseek/qwen/ernie/zhipu/moonshot/baichuan/doubao/yi/stepfun/iflytek，"
        "亦可用中文别名如 通义千问/文心一言；参数见 ai_config.schema.json）。</li>"
        "</ul></ul>"
        "<p class=\"muted\">边界原则：AI 不改变静态事实，只在其上叠加解释与建议；"
        "所有结论需回到静态分析自证（如生成的补丁须通过 re-run 分析校验）。</p>"
        "</section>")
    return (
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>AI 分析（静态↔动态边界）</title>"
        "<link rel=\"stylesheet\" href=\"src/styles.css\"></head><body>"
        "<a class=\"skip-link\" href=\"#main-content\">跳到主内容</a>"
        "<main id=\"main-content\" class=\"container\">"
        "<h1>AI 分析：%s</h1>"
        % _html_esc(title or "AI 评审提示")
        + _boundary
        + "<h2>AI 评审提示词（离线可用）</h2>"
        + _body_html
        + "</main></body></html>")


def render_checks_page(checks):
    """C3：生成「静态检查」汇总页（checks.html，--browse 模式专用）。

    聚合未初始化（高）/ 类型不一致（中）/ 死代码（低）三类告警，按严重度分级、
    可点击跳转源码行，把 JSON 里的检查结果变成 review 可直接使用的清单。"""
    lines = []
    A = lines.append
    A("<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
      "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">")
    A("<script>(function(){try{var t=localStorage.getItem('gs-theme');"
      "if(!t){t=(window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches)?'dark':'light';}"
      "if(t==='dark'){document.documentElement.setAttribute('data-theme','dark');}}catch(e){}})();</script>")
    A("<title>静态检查（未初始化 / 类型不一致 / 死代码）</title>")
    A('<link rel="stylesheet" href="src/styles.css">')
    A("</head><body>")
    A('<a class="skip-link" href="#main-content">跳到主内容</a>')
    A("<header><span class=\"brand\">静态检查</span>"
      "<a href=\"index.html\">&larr; 返回索引</a></header>")
    A("<main id=\"main-content\">")
    A("<h1>静态检查汇总</h1>")
    uninit = checks["uninitialized"]
    mismatch = checks["type_mismatch"]
    dead = checks["dead_code"]
    total = len(uninit) + len(mismatch) + len(dead)
    hi_uninit = sum(1 for r in uninit if r.get("confidence") == "high")
    # R94：合并而非整体替换 —— 调用方给的 suppressed 可能字段不齐（历史上快照回放侧
    # 就漏过 blocks 键）。渲染层不该因数据残缺而让整站生成失败，缺省一律按 0 计。
    suppressed = {"names": 0, "all": 0, "lines": 0, "blocks": 0}
    suppressed.update(checks.get("suppressed") or {})
    supp_total = suppressed["names"] + suppressed["all"] + suppressed["lines"] + suppressed["blocks"]
    A("<div class=\"muted\">聚合未初始化变量（高）、类型不一致（中）、死代码（低）三类静态检查告警，"
      "共 <b>%d</b> 条（其中未初始化高置信 <b>%d</b> 条）。点击跳转到对应源码行。</div>" % (total, hi_uninit))
    if supp_total > 0:
        A("<div class=\"muted\">另有 <b>%d</b> 条告警被抑制注释忽略"
          "（名称级 %d · 文件级 %d · 行级 %d · 区间级 %d，见 <code>%% analyzer:ignore</code> / <code>%% analyzer:disable</code>）。</div>"
          % (supp_total, suppressed["names"], suppressed["all"], suppressed["lines"], suppressed["blocks"]))
        # 抑制原因汇总（可审计明细，定期复审防止抑制疲劳）
        details = suppressed.get("details", [])
        if details:
            shown = details[:200]
            A("<details class=\"supp-details\"><summary>查看抑制明细（%d 条，点击展开）</summary>"
              "<ul class=\"supp-list\">" % len(details))
            for d in shown:
                A("<li>%s</li>" % html_mod.escape(d))
            if len(details) > len(shown):
                A("<li class=\"muted\">…另有 %d 条未显示（可在源码注释中核对）。</li>"
                  % (len(details) - len(shown)))
            A("</ul></details>")
    if total == 0:
        A("<div class=\"muted\">未发现静态检查告警——代码健康。</div>")
        A("</main></body></html>")
        return "\n".join(lines)

    # 高：未初始化变量
    A("<h2 style=\"border-left:4px solid #cf222e;padding-left:10px;\">未初始化变量 "
      "<span class=\"muted\">（高 · %d 条）</span></h2>" % len(uninit))
    if uninit:
        A("<table><tr><th>变量</th><th>函数</th><th>文件</th><th>行</th></tr>")
        for r in uninit:
            href = "%s#L%d" % (_src_href_from_rel(r["file"]), r["line"])
            A("<tr><td><code>%s</code></td><td>%s</td>"
              "<td><a href=\"%s\">%s</a></td><td class=\"num\">%d</td></tr>"
              % (html_mod.escape(r["name"]), html_mod.escape(r["func"]),
                 href, html_mod.escape(r["file"]), r["line"]))
        A("</table>")

    # 中：类型不一致
    A("<h2 style=\"border-left:4px solid #bc4c00;padding-left:10px;\">类型不一致 "
      "<span class=\"muted\">（中 · %d 条）</span></h2>" % len(mismatch))
    if mismatch:
        A("<table><tr><th>变量</th><th>函数</th><th>类型变化</th><th>文件</th><th>行</th></tr>")
        for r in mismatch:
            href = "%s#L%d" % (_src_href_from_rel(r["file"]), r["line"])
            A("<tr><td><code>%s</code></td><td>%s</td>"
              "<td><code>%s &rarr; %s</code></td>"
              "<td><a href=\"%s\">%s</a></td><td class=\"num\">%d</td></tr>"
              % (html_mod.escape(r["name"]), html_mod.escape(r["func"]),
                 html_mod.escape(r["from_type"]), html_mod.escape(r["to_type"]),
                 href, html_mod.escape(r["file"]), r["line"]))
        A("</table>")

    # 低：死代码
    A("<h2 style=\"border-left:4px solid #6e7781;padding-left:10px;\">死代码 "
      "<span class=\"muted\">（低 · %d 条）</span></h2>" % len(dead))
    if dead:
        A("<table><tr><th>函数</th><th>原因</th><th>文件</th><th>行</th></tr>")
        for r in dead:
            href = "%s#L%d" % (_src_href_from_rel(r["file"]), r["line"])
            A("<tr><td>%s</td><td>%s</td>"
              "<td><a href=\"%s\">%s</a></td><td class=\"num\">%d</td></tr>"
              % (html_mod.escape(r["func"]), html_mod.escape(r["reason"]),
                 href, html_mod.escape(r["file"]), r["line"]))
        A("</table>")
    A("</main></body></html>")
    return "\n".join(lines)


def render_compliance_page(files, findings, per_file, summary, fan_in=None, fan_trans=None):
    """P271 R6-2：生成「代码审查工作台」总览页 compliance.html。

    把静态浏览站点升级为审查工作台的第一入口：给出工程合规得分、
    按官方严重度（error > warning > suggestion）分组的发现，
    以及按文件下钻的清单——让人一眼知道「先改哪里」。
    """
    score = _compliance_score(summary)
    if score >= 90:
        grade, gcls = "良好", "ok"
    elif score >= 70:
        grade, gcls = "待改进", "warn"
    else:
        grade, gcls = "需重点整改", "bad"

    lines = []
    A = lines.append
    A("<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">")
    A("<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">")
    A("<title>代码审查工作台</title>")
    A('<link rel="stylesheet" href="src/styles.css">')
    A("</head><body>")
    A('<a class="skip-link" href="#main">跳到主内容</a>')
    A('<header><span class="brand">代码审查工作台</span>'
      '<a href="index.html">← 返回索引</a></header>')
    A('<main id="main">')
    A("<h1>代码审查工作台</h1>")
    A("<div class=\"muted\">依据 MathWorks 官方审查标准"
      "（matlab-agentic-toolkit 的 matlab-review-code / matlab-modernize-code）："
      "命名约定、函数质量、代码模式、高危项。严重度沿用官方三级："
      "<b>error（必须改）</b> &gt; <b>warning（应该改）</b> &gt; <b>suggestion（可改）</b>。</div>")

    # 得分卡
    A("<div class=\"cmp-score cmp-%s\">" % gcls)
    A("<div class=\"cmp-score-num\">%d</div>" % score)
    A("<div class=\"cmp-score-meta\"><div class=\"cmp-grade\">%s</div>" % grade)
    A("<div class=\"muted\">合规得分（满分 100）</div></div>")
    A("</div>")

    # 严重度统计
    A("<div class=\"cmp-cards\">")
    for sev, label in (("error", "必须改"), ("warning", "应该改"),
                       ("suggestion", "可改")):
        A("<div class=\"cmp-card cmp-%s\"><div class=\"cmp-card-n\">%d</div>"
          "<div class=\"cmp-card-l\">%s</div></div>"
          % (sev, summary.get(sev, 0), label))
    A("</div>")

    # P-rev S6：智能引导——「下一步该改什么」。基于官方严重度与（能拿到的）影响面，
    # 给出可点击优先顺序；每条展开「为什么」即为官方标准依据，让审查结论可溯源。
    SEV_W = {"error": 100, "warning": 40, "suggestion": 10}
    # 官方标准依据（matlab-agentic-toolkit 审查清单的可读摘录）
    RULE_REF = {
        "命名约定": "官方命名要求：函数名应为小写、用下划线分隔（snake_case），变量名应描述用途、避免泛化命名。",
        "函数质量": "官方要求函数「单一职责、可测试、参数少、无副作用」；长函数应拆分，避免嵌套过深。",
        "代码模式": "官方推荐向量化、预分配、用函数句柄/table/tiledlayout 等现代写法，避免低效/过时模式。",
        "高危": "官方将「清除变量/关闭图窗/硬编码路径/clear all」列为高危，要求限定作用域、显式管理资源。",
        "需人工复核": "官方明确 checkcode 查不出，必须人工确认（如 subplot 是否该替换、containers.Map 是否该改 dictionary）。",
    }
    def _prio(f):
        return SEV_W.get(f["severity"], 0)
    # P-rev R8/R14：按「行号 → 影响面」构建映射。R14 升级为传递闭包——若改 X，
    # 其全部下游（传递被依赖者）都会被影响，用传递规模作为主导权重。
    if fan_in is None:
        fan_in = {}
    if fan_trans is None:
        fan_trans = {}
    _line_fan = {}
    _line_trans = {}
    for _mf in files:
        for _f in _mf.functions:
            _k = "%s::%s" % (_mf.rel, _f.name)
            _line_fan[(_mf.rel, _f.line)] = fan_in.get(_k, 0)
            _line_trans[(_mf.rel, _f.line)] = fan_trans.get(_k, 0)
    def _impact(f):
        return _line_trans.get((f["file"], f.get("line", 0)),
                               _line_fan.get((f["file"], f.get("line", 0)), 0))
    def _prio2(f):
        _base = SEV_W.get(f["severity"], 0)
        _imp = _impact(f)
        return _base + _imp * 8   # 每多一处传递受影响，权重 +8，突出「改动波及广」项
    if findings:
        ordered = sorted(findings, key=lambda f: (-_prio2(f), f["cat"]))
        top = ordered[: min(8, len(ordered))]
        A("<h2>下一步建议（按影响优先）</h2>")
        A("<div class=\"cmp-note\">按「官方严重度 + 传递影响面（改了会波及多少下游函数）」"
          "综合排序，先处理「必须改且改动波及广」的项。点击任意项直达源码。</div>")
        A("<ol class=\"guide-ol\">")
        for i, f in enumerate(top, 1):
            href = f["file"].replace("\\", "/")
            if not href.endswith(".html"):
                href = "src/%s.html" % href
            ref = RULE_REF.get(f["cat"], RULE_REF.get("代码模式"))
            A("<li class=\"guide-li\">"
              "<a class=\"guide-go\" href=\"%s#L%d\">%s · %s:%d</a>"
              "<span class=\"guide-sev guide-%s\">%s</span>"
              "<span class=\"guide-imp\" title=\"改了此函数会波及的下游函数数\">波及 %d 处</span>"
              "<details class=\"guide-why\"><summary>为什么？</summary>"
              "<div class=\"guide-ref\">%s</div>"
              "</details>"
              "</li>"
              % (html_mod.escape(href), f.get("line", 0),
                 html_mod.escape(f["cat"]), html_mod.escape(f["file"]), f.get("line", 0),
                 f["severity"], f["severity"], _impact(f), html_mod.escape(ref)))
        A("</ol>")

    # 发现清单（按严重度分组）
    A("<h2>发现清单</h2>")
    if not findings:
        A("<div class=\"cmp-empty\">未发现违反官方审查标准的问题。</div>")
    else:
        for sev, label in (("error", "必须改（error）"),
                           ("warning", "应该改（warning）"),
                           ("suggestion", "可改（suggestion）")):
            group = [f for f in findings if f["severity"] == sev]
            if not group:
                continue
            A("<h3 class=\"cmp-h cmp-%s\">%s · %d</h3>" % (sev, label, len(group)))
            A("<table class=\"cmp-tbl\"><thead><tr>"
              "<th>类别</th><th>文件</th><th>行</th><th>问题</th><th>怎么改</th>"
              "</tr></thead><tbody>")
            for f in group:
                href = f["file"].replace("\\", "/")
                if not href.endswith(".html"):
                    # 源码页保留 .m：src/foo.m.html
                    href = "src/%s.html" % href
                A("<tr><td>%s</td>"
                  "<td><a href=\"%s#L%d\">%s</a></td>"
                  "<td>%d</td><td>%s</td><td class=\"cmp-how\">%s</td></tr>"
                  % (html_mod.escape(f["cat"]),
                     html_mod.escape(href), f.get("line", 0),
                     html_mod.escape(f["file"]), f.get("line", 0),
                     html_mod.escape(f["msg"]), html_mod.escape(f.get("how", ""))))
            A("</tbody></table>")

    # P271 R6-4：「静态分析查不出」的项目 —— 官方明确要求人工复核
    human = [f for f in findings if f["cat"] == "需人工复核"]
    A("<h2>需要人工复核</h2>")
    A("<div class=\"cmp-note\">以下项目 <b>MATLAB 的 checkcode / Code Analyzer"
      " 不会报</b>，官方审查清单明确要求人工确认。本工具已尽力自动检出，"
      "但仍建议逐条核对——不要因为「自动检查没报」就认为没问题。</div>")
    if not human:
        A("<div class=\"cmp-empty\">未自动检出需要人工复核的项目。</div>")
    else:
        A("<table class=\"cmp-tbl\"><thead><tr>"
          "<th>文件</th><th>行</th><th>项目</th><th>说明</th>"
          "</tr></thead><tbody>")
        for f in human:
            A("<tr><td><a href=\"src/%s.html#L%d\">%s</a></td><td>%d</td>"
              "<td>%s</td><td>%s</td></tr>"
              % (html_mod.escape(f["file"]), f.get("line", 0),
                 html_mod.escape(f["file"]), f.get("line", 0),
                 html_mod.escape(f.get("symbol", "")),
                 html_mod.escape(f["msg"])))
        A("</tbody></table>")
    A("<div class=\"cmp-note\">官方列出的「checkcode 查不出」还包括："
      "<code>subplot</code> 用法（官方说明它<b>并未废弃</b>，只是新代码推荐 "
      "tiledlayout/nexttile，不要盲目替换）、<code>containers.Map</code>"
      "（建议改 dictionary，但 checkcode 完全不报）。</div>")

    # 按文件下钻
    A("<h2>按文件分布</h2>")
    A("<table class=\"cmp-tbl\"><thead><tr>"
      "<th>文件</th><th>必须改</th><th>应该改</th><th>可改</th><th>合计</th>"
      "</tr></thead><tbody>")
    rows = []
    for mf in files:
        fs = per_file.get(mf.rel, [])
        if not fs:
            continue
        c = {"error": 0, "warning": 0, "suggestion": 0}
        for f in fs:
            c[f["severity"]] = c.get(f["severity"], 0) + 1
        rows.append((mf.rel, c, len(fs)))
    rows.sort(key=lambda r: (-r[1]["error"], -r[1]["warning"], -r[2]))
    for rel, c, tot in rows:
        A("<tr><td><a href=\"src/%s.html\">%s</a></td><td>%d</td><td>%d</td>"
          "<td>%d</td><td><b>%d</b></td></tr>"
          % (html_mod.escape(rel), html_mod.escape(rel),
             c["error"], c["warning"], c["suggestion"], tot))
    A("</tbody></table>")
    # P-rev S2/S4/R22：审查页也接入跨页联动 + 个人工作台 + 符号层
    A('<script defer src="src/_symbols.js"></script>')
    A('<script defer src="src/_ctxlink.js"></script>')
    A('<script defer src="src/_workbench.js"></script>')
    A('<script>document.addEventListener("DOMContentLoaded",function(){'
      'if(window.WB){WB.ensure();WB.recent();'
      'var h=document.querySelector("header");'
      'if(h){var b=document.createElement("button");b.className="ug-btn";'
      'b.textContent="⭐ 收藏本页";b.onclick=function(){WB.favor(location.pathname);'
      'WB.render();alert("已加入收藏（见右下角🧰工作台）");};h.appendChild(b);}}});</script>')
    A("</main></body></html>")
    return "\n".join(lines)
