# -*- coding: utf-8 -*-
"""frontends —— 跨语言前端**统一 IR** 包（R44 / C'''1）。

    ir.py      : 统一 IR 形状 + 「解析到的边 / 解析不到的调用」的**唯一判定点**
    matlab.py  : MATLAB 侧 unresolved 的**唯一产出点**（形状与 C/Py/JS 不同，见其 docstring）

对外只暴露这一层。`matlabc.py` 是**单向依赖**本包（本包绝不 import matlabc）。

IR_LANG_OWNERS 是本包最重要的一张表
===================================
它回答的问题是：**「这个语言的 unresolved 由谁负责产出？」**

在此之前，这个问题没有答案，只有四处**逐字复制**的实现和一处内联实现；
现在它是数据：每个已注册的语言前端都必须在这里**点名**它的产出点。
守这件事的是 `tools/check_ir_attribution.py`，并且**两向核对**：

  * `matlabc.py` 里 `register_frontend("x", ...)` 注册了、这里却没登记 → 红
    （新前端悄悄自带一份 unresolved 实现，而没有任何装置知道）；
  * 这里登记了、`matlabc.py` 却没注册 → 红
    （陈旧登记：说的是已经不存在的语言，读起来像有覆盖）。

注意「**文件扩展名不在这里**」：C 的 8 类扩展名有它自己的唯一事实源
（`matlabc.py::_C_SOURCE_EXTS`）；`collect_c_files` 与 `CFrontend.exts`
都**引用**它（`CFrontend.exts is _C_SOURCE_EXTS` —— 同一个对象，不是副本）。
本包只负责 **IR / unresolved 规则**，不重复登记「如何收集文件」——
否则就会为了「外挂化」而**新造一个第二事实源**，那正是本包要消灭的东西。

R50/C''''4 实测：上面这句「共用」在写下时**并不成立** ——
`CFrontend.exts` 曾写死 `(".c", ".h")`，只有 `collect_c_files` 真认的
8 类里的 2 类（独立装置 `_r50/probe_ext_truth.py`：事实源 8 / 行为 8 /
前端声明 2，`is` 判定为 False）。守这句话的是 `tools/check_ir_attribution.py`
的 C7'（登记类必须把 `exts` 绑到登记的事实源名上；未登记的复制品也红）。
"""

from . import ir
from . import matlab

# 对外 API（唯一入口）。按字母序，避免读者以为顺序有意义。
IR_KEYS = ir.IR_KEYS
IR_VERSION = ir.IR_VERSION
UNRESOLVED_ARITY = ir.UNRESOLVED_ARITY
build_ir = ir.build_ir
call_sites_of_files = ir.call_sites_of_files
resolve_calls = ir.resolve_calls
unresolved_arity_problems = ir.unresolved_arity_problems
unresolved_symbols = ir.unresolved_symbols

# 语言 → (包内模块名, 该语言 unresolved 的产出函数名)。**唯一登记处。**
IR_LANG_OWNERS = {
    "c": ("ir", "resolve_calls"),
    "py": ("ir", "resolve_calls"),
    "js": ("ir", "resolve_calls"),
    "matlab": ("matlab", "unresolved_tuples"),
}

# 所有「已注册前端」的期望集合（供门做两向核对）。由 IR_LANG_OWNERS 派生，
# **不另写一份** —— 两份手写清单一定会漂移。
LANGS = tuple(sorted(IR_LANG_OWNERS))
