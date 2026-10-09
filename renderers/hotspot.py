# -*- coding: utf-8 -*-
"""热点调用图 HTML 渲染（从 matlabc.py 迁出）。
输入为调用关系字典，纯字符串拼装；分析辅助与资产常量分别从 matlabc / renderers.assets 导入。
"""
import html as html_mod

def render_html_hotspot_callgraphs(model, top_n=12, max_nodes=None):
    """为 --html 合并报告内嵌「热点函数调用图」：取圈复杂度 Top N 的函数，
    复用与 --browse 完全相同的全局邻接表（window.__CG__）+ 前端 initLocalCG
    「按需下钻」渲染，实现两处输出核心可视化一致。HTML 报告无独立源码页，故
    SITE_REL 置空、Shift 点击跳转源码不可用，但点击高亮上下游调用链与 +/- 展开
    子树等交互均保留。
    """
    ranked = model.ranked[:top_n]
    if not ranked:
        return ""
    callers_of = model.callers_of
    calls_of = model.calls_of
    fn_to_file = model.fn_to_file
    files = getattr(model, "files", []) or []
    cg_json, gid_of = _mL._build_global_cg(files, fn_to_file, calls_of, callers_of, model,
                                       max_nodes=max_nodes)
    parts = []
    P = parts.append
    P('<h2>热点函数调用图（Call / Caller Graph）</h2>')
    P('<div class="muted">选取圈复杂度最高的前 %d 个函数，内嵌其局部调用 / 被调用 '
      'SVG 图（与「交互式源码浏览站点」完全一致，离线可用）。<b>点击节点</b>高亮其全部'
      '上下游调用链并淡化其余；「%s」表示循环调用；圆形颜色代表函数类型。该单文件报告'
      '无独立源码页，<b>按住 Shift 点击</b>跳转源码请改用 <code>--browse</code> 站点。</div>'
      % (top_n, chr(0x21ba)))
    P('<script>window.__CG__=%s;window.__CG_SITE_REL__="";</script>' % cg_json)
    P('<div class="cg-legend2">'
      '<span><i style="background:#1a7f37"></i>main</span>'
      '<span><i style="background:#9a6700"></i>local</span>'
      '<span><i style="background:#8250df"></i>method</span>'
      '<span><i style="background:#cf222e"></i>constructor</span>'
      '<span><i style="background:#57606a"></i>script</span>'
      '<span><i style="background:#0969da"></i>其他</span></div>')
    P('<div class="muted"><input type="text" class="cg-search" '
      'placeholder="🔍 搜索函数名 → 自动展开路径并脉冲定位（如 helper）" '
      'aria-label="搜索并聚焦调用图函数">'
      '<button type="button" class="cg-share-btn" '
      'data-cg-act="cgExpandAllScoped" title="一键展开当前卡片全部调用链（callee 图全下游 / caller 图溯源到入口）">'
      '&#127757; 溯源（展开全部）</button>'
      '<button type="button" class="cg-share-btn" '
      'data-cg-act="cgCollapseAllScoped" title="复位当前卡片为默认浅层（根 + 直接子一层）">收缩</button>'
      '<button type="button" class="cg-share-btn" '
      'data-cg-act="cgCopyShareLink">'
      '&#128279; 复制可分享链接</button></div>')
    # P20：调用路径查找面板（最短可达路径 BFS），位于搜索 / 分享控件下方。
    P(_mL._cg_path_panel_html())
    # P22：影响面 / 依赖面（传递闭包）交互面板。
    P(_mL._cg_impact_panel_html())
    cguid = [0]
    for mf, f in ranked:
        if f.kind == "script":
            continue
        n_out = len(calls_of.get(id(f), []))
        n_in = len(callers_of.get(id(f), []))
        if n_out == 0 and n_in == 0:
            continue  # 孤立函数无图可画，跳过以精简报告
        # P-rev R86：热点卡锚点 = hs-fn-<gid>（全局唯一）。此前误用 _anchor_id
        # （fn-<行号>）：跨文件同行的函数会撞出重复 id（S13），且命令面板
        # getElementById('hs-fn-'+gid) 映射不到卡片（P271 R3 锚点协议失配）。
        _gid = gid_of.get(id(f))
        if _gid is None:
            _gid = f.line  # 兜底（孤立函数已在上方跳过，正常路径总有 gid）
        P('<div class="func-card" id="hs-fn-%d">' % _gid)
        P('<h4><span class="kind %s">%s</span> <code>%s</code> '
          '<span class="muted">%s 第 %d 行</span>'
          '<span class="badge">复杂度 %d</span>'
          '<span class="badge">调用 %d</span>'
          '<span class="badge">被调用 %d</span></h4>'
          % (f.kind, f.kind, html_mod.escape(f.name),
             html_mod.escape(mf.rel), f.line, f.complexity, n_out, n_in))
        # 前端「按需下钻」调用图：仅生成一个占位容器，真实 SVG 由 initLocalCG
        # 依据 window.__CG__ 全局邻接表渲染（默认浅层，点击 +/- 增量展开子树，
        # 彻底消除深度截断）。HTML 报告无独立源码页，故 Shift 点击跳转源码不可用。
        callee_svg = _render_callgraph_host(f, "callee", gid_of)
        caller_svg = _render_callgraph_host(f, "caller", gid_of)
        if callee_svg:
            P('<div class="cg-title">调用图 (Call Graph)：本函数调用的函数（点击节点 +/− 展开 / 折叠子树）</div>')
            P('<div class="cg-local">%s</div>' % callee_svg)
        if caller_svg:
            P('<div class="cg-title">被调用图 (Caller Graph)：调用本函数的函数（点击节点 +/− 展开 / 折叠子树）</div>')
            P('<div class="cg-local">%s</div>' % caller_svg)
        P('</div>')
    return "".join(parts)


# ---------------------------------------------------------------------------
# 交互式浏览站点（源码跳转）
# ---------------------------------------------------------------------------
def _render_callgraph_host(f, direction, gid_of):
    """生成单个函数的「按需下钻」调用图容器（占位 div）；真实 SVG 由前端
    initLocalCG 依据 window.__CG__ 全局邻接表渲染，支持点击节点上的 +/- 徽标
    展开 / 折叠其被调（callee）或被调用（caller）子树，彻底消除旧实现的深度截断。"""
    gid = gid_of.get(id(f))
    if gid is None:
        return ""
    return ('<div class="cg-host" data-dir="%s" data-root="%d"></div>'
            % (direction, gid))


def _cg_site_rel(from_rel):
    """返回从某源码页目录到「站点根」的相对路径前缀（用于拼接节点 href）。

    关键：源码页一律位于站点根下的 src/ 子目录（src/<rel>.html），因此到站点根
    需要的层数 = rel 的路径段数（含 src/ 这一层）。例如：
      from_rel='a/b.m' → 页面在 src/a/b.m.html（目录 src/a/），到站点根需上 2 级
                         → '../../'；
      from_rel='main.m' → 页面在 src/main.m.html（目录 src/），到站点根需上 1 级
                         → '../'。
    此前实现少算 src/ 这一层（用 len(parts)-1），导致跨文件跳转 href 变成
    src/src/... 而找不到文件，本次修正为 len(parts)。"""
    parts = from_rel.split("/") if from_rel else []
    depth = len(parts)
    return "../" * depth


def _rel_to_src_asset(from_rel, asset):
    """源码页内指向 src/ 目录下共享资源（如 _cgdata.js）的相对链接。"""
    parts = from_rel.split("/") if from_rel else []
    depth = max(0, len(parts) - 1)
    return ("../" * depth) + asset





# P270 R4：可访问性 / 键盘导航层（全站注入）。
#   提供：① ? 帮助浮层（列出全部快捷键）；② Esc 关闭任意浮层；
#   ③ 全局快捷键：t 主题 / g 跳概览 / h 跳首页 / d 跳重复代码 / / 命令面板；
#   ④ 浮层打开时焦点锁定 + 关闭后焦点归还；⑤ 跳转到主内容（skip link 由模板提供）。
# 与 GLOBAL_SEARCH_JS 的 Ctrl+K 互不冲突（搜索浮层优先消费按键）。

# P271 R3：源码行深链（代码可分享视图）。
# ① 解析 URL 的 #Lx 或 #Lx-y，高亮对应源码行并滚动入视；② 点击行号单元格即可复制
# 「当前文件 URL#Lx」分享链接（navigator.clipboard 不可用时回退到临时 textarea）。
# P271 R3（步骤3）：通用视图状态深链 —— 把页面控件状态同步到 URL hash。
# 与 DEEPLINK_JS（全局状态页专用）不同，这里是**声明式、可复用**的：
# 页面只需在 window.__VIEWSTATE_SPEC__ 里声明「控件 id → hash 键 → 默认值 → 变更回调」，
# 本脚本统一负责「URL → 控件」还原与「控件 → URL」同步，任何页面都能低成本接入。
# 例：index.html#cgmin=2&cglbl=1 分享出去，对方打开即为「只看高扇入 + 显示全部标签」的视图。

# R52：分析层辅助仍由 matlabc 持有，但改为**惰性代理** —— 原写法
# `from matlabc import ...` 是一条 import 期回边（matlabc 底部又再导出
# renderers.hotspot）。见 renderers/_late.py 顶部说明。
from renderers._late import late as _mL
