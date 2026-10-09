# -*- coding: utf-8 -*-
"""frontends/ir.py —— 跨语言**统一 IR** 与「解析不到的调用」的**唯一判定点**（R44 / C'''1）。

为什么需要这个包
================
在本包出现之前，同一条规则

    被调名在**本语言**的 func_index 里找不到  ⇒  记入 unresolved

在 `matlabc.py` 里被**抄了五遍**（数字是 R44 实测数出来的，不是估的）：

    matlabc.py::build_c_model            （内联，for 循环直接 append）
    matlabc.py::_build_ext_model         （内联，Py/JS 共用同一份组装器）
    matlabc.py::CFrontend.build_edges    （逐字复制）
    matlabc.py::PyFrontend.build_edges   （逐字复制）
    matlabc.py::JsFrontend.build_edges   （逐字复制）

另有第 6 条路径形状**不同**：MATLAB 侧 `_collect_unresolved_calls`（名字来自
`Function.external_calls`，按名字聚合）—— 它归 `frontends/matlab.py`。

抄五遍的代价不是「多写了几十行」，而是**五条路径会各自漂移**：改了其中一处，
另外四处静默保持旧语义。而 `--binary-attach` 的三态归因只挂在其中**一条**名字来源上 ——
于是「源码说这个名字解析不到」与「归因说它来自某个库」讨论的**可能不是同一批名字**，
而两边都不会报错。

⚠ 不要把 `_match_c_bridge` 也算进来：它是**只取命中**的桥接规则
（`if not hits: continue`），既不产出 unresolved 也不产出边，语义不同。

修法不是「把四份改成一样」，而是**让第二份不存在**：规则只在这里实现一次，
四条路径都调它。守这件事的是 `tools/check_ir_attribution.py`（登记制 + 两向自证）。

IR 形状（唯一登记处 = IR_KEYS）
==============================

    {
      "ir_version": 1,              # 形状变更必须 +1，否则下游读到的键会静默缺失
      "lang":       "c",            # 语言标识
      "files":      [...],          # 各语言自己的解析结果（本模块不解释其内部）
      "func_index": {小写名: [{"file": pf, "func": fn}, ...]},
      "edges":      [(caller, callee, line, rel), ...],
      "unresolved": [(callee, line, rel), ...],
    }

纪律
====
* **零依赖**：只 import 标准库的东西一个不用（本文件甚至不需要 import）；
* **3.6.5 兼容**：不用 dataclass / walrus / `list[str]` / `match`；
* **纯数据进出**：没有全局可变状态（否则 `check_shared_state` 那一族会咬人）；
* **比集合不比个数**：`unresolved_symbols()` 返回 **set** —— 与 R37 的基线门同一条纪律，
  个数相等可能是巧合。
"""

# 形状版本：任何键的增删改都必须 +1。下游（归因 / JSON 序列化）按它判断兼容性。
IR_VERSION = 1

# IR 的键集合**唯一登记处**。`build_ir` 产出、门核对、测试断言，三处都读它。
IR_KEYS = ("ir_version", "lang", "files", "func_index", "edges", "unresolved")

# `unresolved` 元组的三段结构（callee, line, rel）。写成常量是为了让
# 「有没有人偷偷往里塞第四个元素」可被判据看见（长度必须是 3）。
UNRESOLVED_ARITY = 3


def resolve_calls(func_index, call_sites):
    """**唯一判定点**：把调用点分成「解析到的边」与「解析不到的调用」。

    func_index : {小写名: [{"file": pf, "func": fn}, ...]}（各语言共用同一形状；
                 大小写不敏感 —— 小写键是调用方灌进来时的约定）
    call_sites : 可迭代的 (caller_name, callee_name, line, rel)

    返回 (edges, unresolved)：
        edges      = [(caller_name, 命中的函数名, line, rel), ...]
                     命中多个同名单例时**每个命中各产一条边**（扇出，不是覆盖）
        unresolved = [(callee_name, line, rel), ...]

    注意 ①：`hits` 里的函数名取 `h["func"]["name"]`（**定义处的原始大小写**），
    不是调用处的大小写 —— 老实现就是这个语义，本函数保持逐字节一致。
    注意 ②：返回顺序 = call_sites 的产出顺序，**不做排序**（排序会破坏
    「按源码顺序打印」的下游渲染）。
    """
    edges = []
    unresolved = []
    for caller, callee, line, rel in call_sites:
        hits = func_index.get(callee.lower()) if callee else None
        if hits:
            for h in hits:
                edges.append((caller, h["func"]["name"], line, rel))
        else:
            unresolved.append((callee, line, rel))
    return edges, unresolved


def call_sites_of_files(files):
    """按**统一顺序**展开「每个函数里的每个调用点」。

    顺序被显式固定在这里，是因为四份旧实现都依赖同一个嵌套循环顺序
    （files → functions → calls）；顺序一旦分叉，`edges` 的打印顺序就分叉，
    而这类差异**不会让任何断言变红**（集合相同）。
    """
    for pf in files or []:
        rel = pf.get("rel")
        for fn in pf.get("functions", []) or []:
            for cname, ln in fn.get("calls", []) or []:
                yield (fn.get("name"), cname, ln, rel)


def build_ir(lang, files, func_index):
    """产出统一 IR。**这是 unresolved 被写出来的唯一地方**（门守这条）。"""
    edges, unresolved = resolve_calls(func_index,
                                      call_sites_of_files(files))
    return {"ir_version": IR_VERSION,
            "lang": lang,
            "files": files,
            "func_index": func_index,
            "edges": edges,
            "unresolved": unresolved}


def unresolved_symbols(ir):
    """IR → 符号**集合**。

    归因路径与 IR 必须比集合（R37 的纪律：个数相等可能是巧合，
    「一好一坏」能顶替总数）。返回 set 而不是 list，是为了让
    `==` 直接表达「同一批名字」，而不是「同样多的名字」。
    """
    out = set()
    for row in (ir.get("unresolved") or []):
        if row and row[0]:
            out.add(row[0])
    return out


def unresolved_arity_problems(ir):
    """返回形状违规列表（空 = 合规）。给门与测试共用，避免两处各写一份判据。"""
    bad = []
    for i, row in enumerate(ir.get("unresolved") or []):
        if not isinstance(row, (tuple, list)) or len(row) != UNRESOLVED_ARITY:
            bad.append((i, row))
    return bad
