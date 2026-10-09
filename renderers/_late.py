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
