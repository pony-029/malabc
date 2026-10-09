# -*- coding: utf-8 -*-
"""R52：`renderers -> matlabc` 的**惰性**借用通道（打断 import 期的回边）。

背景（R52 独立装置实测，仓库外 `_r52/probe_cycle_kind.py`）：
`renderers.{callgraph,hotspot,report,sarif,snapshot,unresolved}` 原先在模块**底部**
`from matlabc import (...)`，而 `matlabc.py` 底部又 `from renderers.X import (...)`，
两边互相指认 ⇒ **import 期有环**。它能跑，靠的是一份**隐式时序契约**：
`matlabc` 被部分初始化时，被借用的那几个名字必须**已经被定义在再导出点之前**。
契约没有被任何东西钉住 —— 谁把某个名字挪到再导出点之后，两个方向都不会报错。

现在改成：本模块**不**在 import 期触碰 matlabc（静态 import 图里没有这条边），
只在**首次属性访问**时用 `importlib` 取一次并缓存。于是：

  * import 期图无环（`tools/check_import_graph.py` 的 G1 断言的就是它）；
  * 「部分初始化的对方」这件事**不再存在**：访问一定发生在 matlabc 加载完毕之后；
  * 这条**动态 import** 被 G3 登记为单一事实源并双向核对（登记了却已无该字符串 → 红）。

注意：这是**借用**，不是依赖倒置。matlabc 仍是这些名字的定义者；本模块只是把
「什么时候去取」从 import 期推迟到调用期。

R53（C''''2）：下面那张 `BORROWED` 表是这条通道的**静态单一事实源**。
此前 `_mL.X` 的 `X` **只由使用点定义** —— 门与测试只能验「X 存在于 matlabc」，
于是「多用一个借用」与「拿掉一个使用点」**都没有一张表要求同步**。
现在 `tools/check_import_graph.py` 的 **G7** 断言「使用点集合 == 登记表」（两向）：

  * 用了却没登记        → 红；
  * 登记了却再没人用    → 也红（陈旧登记）；
  * 登记的符号在 matlabc 的模块层没有定义 → 也红（悬空借用）；
  * 某条登记的理由少于 8 字符 ⇒ 该登记**不生效**。

⚠ 它**不**改变任何运行时行为：`BORROWED` 只被门读，产品代码从不读它 ——
换句话说，这张表是**宣称**，而 G7 是它的对手方。
"""

import importlib

_MC = None


def mc():
    """返回 matlabc 模块（首次调用时导入并缓存）。"""
    global _MC
    if _MC is None:
        _MC = importlib.import_module("matlabc")
    return _MC


class _Late(object):
    """属性访问即转发到 matlabc 的代理。

    **不缓存值** —— `VERSION` 之类在 matlabc 里被改写时，这里立刻拿到新的。
    """

    __slots__ = ()

    def __getattr__(self, name):
        return getattr(mc(), name)


late = _Late()

# ---------------------------------------------------------------------------
# 借用清单（R53/C''''2）：**静态单一事实源**，由 tools/check_import_graph.py 的 G7
# 两向核对。键 = 借用方模块名（与 import 图里的模块名同口径）；
# 每项必须写清 reason（< 8 字符则整条登记不生效）。
# ⚠ 本表**只被门读**，产品代码从不读它；改 `_mL.X` 的使用点就必须同步这里。
# ---------------------------------------------------------------------------
BORROWED = {
    "renderers.callgraph": {
        "names": ("_dir_page_name", "_page_rel", "_src_href_from_rel"),
        "reason": "只借三个纯路径辅助，把源码路径映射成浏览站 URL；无其它模块级依赖",
    },
    "renderers.hotspot": {
        "names": ("_build_global_cg", "_cg_impact_panel_html",
                  "_cg_path_panel_html"),
        "reason": "只借调用图构建与两个面板 HTML 生成器，均为不读全局状态的纯函数",
    },
    "renderers.report": {
        "names": ("_collect_unresolved_calls", "_compute_function_metrics",
                  "_finalize_html_str", "collect_used_builtins",
                  "render_matlab_builtin_section"),
        "reason": "借报告汇总入口与指标、内置函数章节渲染；均为纯函数，不写全局状态",
    },
    "renderers.sarif": {
        "names": ("VERSION", "_SARIF_RULES", "_sarif_fp_detail",
                  "_sarif_result_fp"),
        "reason": "借版本号与 SARIF 规则表及两个假阳性明细辅助；VERSION 不做缓存",
    },
    "renderers.snapshot": {
        "names": ("_json_default", "_page_rel", "_src_href_from_rel",
                  "_up_to_index", "_write_output", "render_checks_page",
                  "render_matlab_lib_page", "render_taint_page",
                  "render_todo_page"),
        "reason": "借快照/浏览站主渲染入口与四个路径、JSON 辅助；借用面最大的一处",
    },
    "renderers.unresolved": {
        "names": ("_src_href_from_rel",),
        "reason": "只借一个路径辅助，把源码相对路径映射成浏览站 URL",
    },
}
