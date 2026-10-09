# -*- coding: utf-8 -*-
"""frontends/matlab.py —— MATLAB 侧 unresolved 的**唯一产出点**（R44 / C'''1）。

MATLAB 前端与 C/Py/JS 三者的 IR 形状**不同**，这一点必须说清而不是抹平：

  * C / Py / JS ：「调用点」是 `fn["calls"]` 里的 `(名, 行)`，判定规则是
    `func_index` 命中与否 —— 这条规则在 `frontends/ir.py::resolve_calls`（**一份**）。
  * MATLAB：`Function` 对象上带的是 `external_calls`（**dict：名字 → 次数**，
    由解析器在**不知道项目里有哪些函数**的时候就填好了），并且这个诊断是**按名字聚合**的
    （`unresolved.html` 关心的是「哪些名字解析不到、出现几次、项目里有没有同名」），
    而不是按调用点。所以它产出的是「(名字, 行, rel) 流」，行是该函数**定义行**
    （老实现即如此，`_collect_unresolved_calls` 的 rows 只暴露名字与计数，
    行号仅用于 `matches`）。

抹平这两种形状（比如硬把 external_calls 塞进 func_index 判定）会遇到一个真问题：
`external_calls` 的含义是「**解析期**未知的外部调用」，而 `func_index` 判定要求
「**汇总期**有全项目函数表」。前者是后者的**超集**（外部名里可能混入项目内同名，
那正是 `in_project=True` 的「疑似漏检」档）。所以两件事、两个函数，各有**唯一**产出点。

纪律：本模块零依赖、3.6.5 兼容、纯数据进出；只处理**属性访问**，不 import matlabc
（`matlabc.py` → `frontends` 是单向依赖，反向 import 会造出与本仓
`renderers ↔ matlabc` 同款的循环依赖）。
"""

LANG = "matlab"


def unresolved_tuples(files):
    """产出 `(名字, 行, rel)` 流 —— MATLAB 侧 unresolved 的**唯一**产出点。

    老实现（`matlabc.py::_collect_unresolved_calls`）直接写
    `cnt.update(f.external_calls)`，名字集合**只在那一个函数里存在**；
    于是「归因用的名字」与「诊断页用的名字」是**两条各自独立的读取**，
    谁都不知道对方读的是不是同一批（R44 之前，没有任何装置守着这件事）。

    迭代顺序与老实现**逐字节一致**：files → functions（解析器给的顺序）→
    `external_calls` 的键顺序；下游用 `Counter.most_common()`，
    其并列项的先后完全由**首次插入顺序**决定 ⇒ 顺序必须在这里也固定住。
    """
    for mf in files or []:
        rel = getattr(mf, "rel", None)
        for fn in getattr(mf, "functions", None) or []:
            ext = getattr(fn, "external_calls", None) or {}
            for name in ext:
                yield (name, getattr(fn, "line", None), rel)


def unresolved_symbols(files):
    """MATLAB 侧 unresolved 的符号**集合**（与 `ir.py::unresolved_symbols` 同一口径）。"""
    out = set()
    for name, _line, _rel in unresolved_tuples(files):
        if name:
            out.add(name)
    return out
