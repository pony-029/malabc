# -*- coding: utf-8 -*-
"""pyast_frontend.py —— Python 前端的 **ast 层**（R101 / 槽 25 `py_ast_frontend`）。

为什么这层存在
==============
`matlabc.py` 的 Python 前端一直是**行锚定词法扫描器**（`_parse_py_source`
+ `_scan_py_defs`）：按行匹配 `def` 头、按括号配平取形参、用字符串 / 注释
状态机避开假定义。对「函数」它够用，但有三件事**从原理上做不到**：

  1. **限定调用看不见** —— 扫描器显式跳过前一个字符是 `.` 的调用点，
     于是 `obj.m()` / `self.f()` 一条边都不产；
  2. **单行函数体的调用点在定义行上** —— 定义行自身被跳过，
     `def f(v): return g(v)` 里的 `g` 收不到；
  3. **没有结构** —— 没有类、没有字段、没有装饰器、没有注解，
     于是实体层（`entity_model.py` 要的 `classes` / 字段）**没有数据源**。

本模块把这三种补上：用 `ast` 解析，产出与词法层**同形**的 `functions` /
`imports`，另加 `classes` / `globals`。

双层调度（槽 25 的核心形状）
============================
`ast` **优先**；语法失败（`SyntaxError` / `ValueError` …）**降级**到词法
扫描器，而降级**必须写进 `limitations`**。这不是口味，是一条纪律：

    「我没读到」与「确实没有」必须长得不一样。

一份 3.7+ 新语法（或被 3.13 语法拒掉的 Python 2 风格）文件被 `ast` 拒了，
它仍然有词法读数，但那份读数里**没有** class / 字段 / 装饰器 / 注解。
只静默降级的话，下游会把「词法读不出类」当成「这个文件没有类」。所以
每次降级都留一条 >= `MIN_LIMITATION` 字符的说明，`parser` 键从 `ast`
变成 `lexical`。

同形契约（本模块即唯一事实源）
==============================
每文件页面 = 词法层的四个键 + 四个新键：

    rel / path / functions / imports          # 与词法层逐键同形
    classes / globals / parser / limitations  # 本层新增

`functions[]` 的键集：

* **两层的公共部分** `LEGACY_FUNCTION_FIELDS`（9 键，词法层就有的那 9 个）；
* **仅 ast 页面额外有的** `AST_FUNCTION_FIELDS`（`decorators` /
  `annotations` / `is_async`）。

⚠ 后 3 个键在 `parser == "lexical"` 的页面上**不出现**（而不是给一个空
值的假哨兵）—— 「这层读不到」与「确实没有」必须长得不一样，同一条纪律。
判断「确实没有装饰器」要看 `parser == "ast"` 的页面。

`classes[]` 的键集是 `CLASS_FIELDS`，类成员（属性）的键集是
`ATTRIBUTE_FIELDS`。这是**原生形态**，不是 `entity_model.py` 的实体契约 ——
归一化由 `entity_model.py_entities` 做（适配器只读，不改这里的键）。

与词法层**有意不同**的两处（都写在这里，不留给别人去猜）
--------------------------------------------------------
  * `complexity`：本层按 **AST 结构**计数（`If` / `For` / `AsyncFor` /
    `While` / `Try` / `ExceptHandler` 各 1，`BoolOp` 记它的运算符个数，
    基 1）；词法层按**行内关键字**数（`COMPLEXITY_KEYWORDS`）。
    **两者不是同一个量** —— 换一份语料，数字就可能不同。降级那一路走的是
    词法口径，这正是它要进 `limitations` 的原因之一。
  * `ret`：本层写**真实返回注解**（`-> bool` 得到 `"bool"`）；**没有注解时
    沿用词法层的哨兵 `"None"`**，因为改哨兵会动既有读数。于是哨兵与
    「真的写了 `-> None`」在载荷上**不可区分** —— 这是如实交代的已知歧义。

边界（本模块**不做**的事）
==========================
* **不 import 产品**：只 import `ast` 与 `sys`。词法扫描器由 `matlabc.py`
  通过 `lexical` 形参**注入**，而不是本模块反向依赖它 —— 于是本模块可以
  单独 `--selftest`，也可以在 `_r101/` 的装置里裸跑（不需要引擎）；
* **不碰文件系统**：输入是 `(text, rel, path)`，输出是纯 dict；
* **不判定调用边**：调用点只**收集**，`edges` / `unresolved` 仍然只由
  `frontends/ir.py::resolve_calls` 决定（R44 / C'''1 的唯一判定点）；
* **不解析注解的全部语法**：`_expr_src` 只覆盖注解里真实会出现的形态
  （名字 / 属性 / 下标 / 元组 / 列表 / 位或 / 字面量），读不出来就返回
  空串（哨兵），**不猜**。

用法
====
    import pyast_frontend as pa
    page = pa.parse_file(text, rel, path, keywords, lexical=lexical_scanner)

命令行（用于自证，不依赖引擎）：
    python pyast_frontend.py --selftest    # 两向自证；0=通过 1=有反例失败
    python pyast_frontend.py --help        # 本帮助
"""
import ast
import sys

# 判据族（`--selftest` 打的那一行）。
ROW_SIGNATURE = "P1–P5"

# 层名：同时是每文件 `parser` 键的值域。
PARSER_AST = "ast"
PARSER_LEXICAL = "lexical"
PARSERS = (PARSER_AST, PARSER_LEXICAL)

# 降级理由的下限（字符）。与 `entity_model._MIN_REASON` /
# `check_parity_registry.MIN_REASON` 同一下限（8）—— 空理由等于没登记。
MIN_LIMITATION = 8

# 每文件页面的键集**唯一登记处**。两层的页面都必须恰好是这 8 个键。
PAGE_FIELDS = ("rel", "path", "functions", "imports", "classes", "globals",
               "parser", "limitations")

# 两层公共的函数键（词法层就有的那 9 个）。
LEGACY_FUNCTION_FIELDS = ("name", "line", "params", "ret", "complexity",
                          "calls", "body_start", "body_end", "indent")

# 仅 `parser == "ast"` 的页面额外提供的 3 个键（词法层读不到，于是**不出现**）。
AST_FUNCTION_FIELDS = ("decorators", "annotations", "is_async")

CLASS_FIELDS = ("name", "line", "bases", "decorators", "methods", "attributes")

ATTRIBUTE_FIELDS = ("name", "line", "annotation", "scope")

ATTR_SCOPE_CLASS = "class"
ATTR_SCOPE_INSTANCE = "instance"
ATTR_SCOPES = (ATTR_SCOPE_CLASS, ATTR_SCOPE_INSTANCE)

# 词法层复杂度关键字。**唯一事实源**：`matlabc.py::_parse_py_source_lexical`
# 引用它，不再内联字面量（R101 之前那句话在这两个文件里各写了一遍）。
COMPLEXITY_KEYWORDS = (u"if ", u"elif ", u"for ", u"while ", u" and ", u" or ",
                       u"try", u"except ")

# AST 结构计数用的节点族：与 `COMPLEXITY_KEYWORDS` **一一对应**
#   `if `/`elif ` → If（elif 的 orelse 里也是 If）
#   `for `        → For / AsyncFor
#   `while `      → While
#   `try`         → Try
#   `except `     → ExceptHandler
#   ` and `/` or ` → BoolOp 的运算符个数（len(values) - 1）
_BRANCH_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try,
                 ast.ExceptHandler)

# 「自成一份函数」的节点：收集调用点 / 复杂度时**不下穿**它们 ——
# 嵌套函数与类里的调用点归它们自己，这是词法层的栈式语义，保持它。
_DEF_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

U_SELF = u"self"


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
def _is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def _is_str(x):
    return isinstance(x, str)


def _expr_src(node):
    """把**注解表达式**渲染成源码文本（Py3.6 兼容，不依赖 3.8+ 的 `ast.unparse`）。

    为什么不用 `ast.unparse` / `ast.get_source_segment`：本仓承诺 Python 3.6.5
    可运行，而这两个 API 分别是 3.9 / 3.8 才有的。自己渲染这十几个形态更稳。

    只覆盖注解里真实会出现的形态；**读不出来返回空串**（哨兵），不猜。
    用 `type(node).__name__` 而不是 `isinstance(node, ast.Str)` 来判
    3.6/3.7 的 `Str` / `Num` / `NameConstant`：那几个类在 3.8+ 是**废弃别名**，
    `isinstance` 会发 DeprecationWarning，而本仓有「不许有警告噪声」的纪律。
    """
    if node is None:
        return u""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _expr_src(node.value)
        return (base + u"." + node.attr) if base else u""
    if isinstance(node, ast.Subscript):
        sl = node.slice
        if type(sl).__name__ == "Index":          # Py<3.9：下标包一层 Index
            sl = sl.value
        base, idx = _expr_src(node.value), _expr_src(sl)
        return (base + u"[" + idx + u"]") if base else u""
    if isinstance(node, ast.Tuple):
        return u", ".join(_expr_src(e) for e in node.elts)
    if isinstance(node, ast.List):
        return u"[" + u", ".join(_expr_src(e) for e in node.elts) + u"]"
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _expr_src(node.left) + u" | " + _expr_src(node.right)
    tn = type(node).__name__
    if tn == "Constant":                          # 3.8+
        return repr(node.value)
    if tn == "Str":                               # 3.6 / 3.7
        return repr(node.s)
    if tn == "Num":                               # 3.6 / 3.7
        return repr(node.n)
    if tn == "NameConstant":                      # 3.6 / 3.7
        return repr(node.value)
    return u""


def _arg_objs(a):
    """按**形参书写顺序**列出 `ast.arguments` 里的 `ast.arg`（不含星号）。"""
    out = list(getattr(a, "posonlyargs", None) or [])   # 3.8+；3.6/3.7 没有这个属性
    out += list(a.args or [])
    if a.vararg is not None:
        out.append(a.vararg)
    out += list(a.kwonlyargs or [])
    if a.kwarg is not None:
        out.append(a.kwarg)
    return out


def _star_prefix(a, obj):
    """`ast.arg` 在形参表里的星号前缀（`""` / `"*"` / `"**"`）。"""
    if a.vararg is obj:
        return u"*"
    if a.kwarg is obj:
        return u"**"
    return u""


def _arg_names(a):
    """形参名列表。

    `*args` / `**kw` 保留星号、`/`（positional-only）与裸 `*`（keyword-only）
    记号**丢弃** —— 与词法层的 `_py_split_params` 逐项同值
    （守这件事的是 `tools/check_py_js_frontend_shapes.py` 的 **G3**）。
    """
    return [_star_prefix(a, o) + o.arg for o in _arg_objs(a)]


def _param_annotations(a):
    """注解形参 → 注解文本（只列**有注解**的那些；`*args` 带星号）。"""
    out = {}
    for o in _arg_objs(a):
        if getattr(o, "annotation", None) is None:
            continue
        out[_star_prefix(a, o) + o.arg] = _expr_src(o.annotation)
    return out


def _callee_name(node):
    """调用节点的被调名。

    `ast.Name` → 它的名字；`ast.Attribute` → **属性名**（这正是词法层看不见的
    那一类：`obj.m()` → `m`）；其余形态（下标 / 调用结果 / lambda）返回空串，
    即「这不是一个具名调用」，**不猜**。
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return u""


def _iter_calls(node, keywords, own, out):
    """按**源码顺序**收集 `node` 子树里的调用点；**不下穿**嵌套函数 / 类定义。

    与词法层的两点差别（都是有意的）：

    * 词法层跳过前一个字符是 `.` 的调用点（`obj.m()` 一条都不产），本层产
      （这就是槽 25 要解锁的那一格）；
    * 词法层的调用收集只看**行**，于是 `def f(v): return g(v)` 这种单行体
      收不到（定义行自身被跳过），本层按语句收，收得到。

    被调名仍按 `keywords`（调用方从 `matlabc.py` 注入的 `_PY_KEYWORDS`）
    过滤、并排除**自己调自己** —— 与词法层同一个口径，免得 `func_index` 里
    凭空多出一堆自环。
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _DEF_NODES):
            continue
        if isinstance(child, ast.Call):
            nm = _callee_name(child.func)
            if nm and nm not in keywords and nm != own:
                out.append((nm, child.lineno))
        _iter_calls(child, keywords, own, out)


def _complexity(stmts):
    """AST 结构复杂度（基 1 + 分支节点数 + `BoolOp` 运算符数）。

    与 `COMPLEXITY_KEYWORDS` 一一对应（见该常量上的注释）。**不下穿**嵌套
    函数 / 类定义 —— 那些分支归它们自己的读数。
    """
    c = 1
    # 起始集合要先滤掉「自成一份函数」的语句 —— 否则嵌套函数里的分支会被
    # 记到**外层**头上（`def outer(): def inner(): if x: ...`）。
    stack = [s for s in (stmts or []) if not isinstance(s, _DEF_NODES)]
    while stack:
        cur = stack.pop()
        # 判定**cur 自己**（而不是只判它的孩子）：`If` 就是 `node.body` 的
        # 直接子节点，只判孩子会把它整条漏掉 —— 自证里 `if a and b:` 的
        # 正例当场抓出过这个错。
        if isinstance(cur, _BRANCH_NODES):
            c += 1
        elif isinstance(cur, ast.BoolOp):
            c += max(0, len(cur.values) - 1)
        for ch in ast.iter_child_nodes(cur):
            if isinstance(ch, _DEF_NODES):
                continue
            stack.append(ch)
    return c


def _body_end(lines, def_idx0, def_indent):
    """函数体最后一行（1-based）。

    为什么按**缩进**扫而不是用 `node.end_lineno`：那个属性是 3.8 才有的，
    而本仓承诺 3.6.5 可运行。缩进扫描的语义与词法层的栈式 `body_end` 一致
    （栈在「缩进 <= 定义行缩进」时弹出），所以两条路径给出同一段区间 ——
    `_scan_ext_first`（`py_eval_usage` 的载体）读的正是它。
    """
    last = def_idx0 + 1
    for i in range(def_idx0 + 1, len(lines)):
        raw = lines[i]
        if not raw.strip():
            continue
        ind = len(raw) - len(raw.lstrip())
        if ind <= def_indent:
            break
        last = i + 1
    return last


def _iter_defs(tree):
    """全部函数定义，按**行号**排序（含嵌套函数与类内方法）。"""
    out = [n for n in ast.walk(tree)
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    out.sort(key=lambda n: n.lineno)
    return out


def _collect_imports(tree):
    """`(模块, 引入名, 行号)` 三元组列表，按行号排序。

    与词法层的 `_RE_PY_FROM` / `_RE_PY_IMPORT` 两点不同（都是**修正**）：

    * **相对导入**：词法层的正则要求模块名以字母开头，`from . import x`
      / `from .mod import y` 整条看不见；本层认，并把前导点写进模块名
      （`"." * level + (module or "")`）。解析这些点该落到哪个文件是**下一层**
      的事（`_ext_dep_edges` 目前只解析绝对导入，未解析的边在载荷里
      `to=None` —— 看得见，不是静默丢了）；
    * **括号里的多名字**：词法层把 `from x import (a, b)` 切成 `"(a"` 与
      `"b)"`；本层按 AST 名字表给 `"a"` / `"b"`。

    `import *` 与词法层一致地记为名字 `"*"`（不改既有读数）。
    """
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = u"." * (getattr(node, "level", 0) or 0) + (node.module or u"")
            for al in node.names:
                out.append((mod, al.asname or al.name, node.lineno))
        elif isinstance(node, ast.Import):
            for al in node.names:
                nm = al.asname or al.name.split(u".")[-1]
                out.append((al.name, nm, node.lineno))
    out.sort(key=lambda t: t[2])
    return out


def _module_globals(tree):
    """模块级赋值绑定的名字（按首次出现顺序、去重）。

    只认**模块顶层**的 `Name` 目标（`Assign` 的每个目标 / `AnnAssign` 的
    单个目标）。解包（`a, b = ...`）会因目标是 Tuple 而整体跳过 —— 那是
    「这层不读」，不是「没有」，与降级同一条纪律（如实交代在 docstring 里）。
    """
    out, seen = [], set()
    for st in tree.body:
        targets = []
        if isinstance(st, ast.Assign):
            targets = list(st.targets or [])
        elif isinstance(st, ast.AnnAssign):
            targets = [st.target]
        for tg in targets:
            if isinstance(tg, ast.Name) and tg.id not in seen:
                seen.add(tg.id)
                out.append(tg.id)
    return out


def _is_self_attr(tg):
    """`self.x` 形态的目标（只认 `self` 本身，不认 `a.b.c`）。"""
    return (isinstance(tg, ast.Attribute)
            and isinstance(tg.value, ast.Name)
            and tg.value.id == U_SELF)


def _self_attrs(fn):
    """`self.x = ...` / `self.x: T = ...` 形态的**实例属性** → 四元组列表。

    **不下穿**嵌套函数与嵌套类：`def f(self): def g(): self.y = 1` 里的 `y`
    不属于外层类的实例属性（它属于一个闭包），归零比归错好。
    """
    out = []

    def rec(node):
        # 同样先判**自己**：`self.v = v` 这条语句本身就是 `Assign`，
        # 只判孩子会一条属性都收不到（自证的正例抓过）。
        if isinstance(node, ast.Assign):
            for tg in (node.targets or []):
                if _is_self_attr(tg):
                    out.append((tg.attr, node.lineno, u"",
                                ATTR_SCOPE_INSTANCE))
        elif isinstance(node, ast.AnnAssign) and _is_self_attr(node.target):
            out.append((node.target.attr, node.lineno,
                        _expr_src(node.annotation), ATTR_SCOPE_INSTANCE))
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, _DEF_NODES):
                continue
            rec(ch)

    for st in (fn.body or []):
        if isinstance(st, _DEF_NODES):
            continue
        rec(st)
    return out


def _class_page(node):
    """一个 `ClassDef` → `CLASS_FIELDS` 形状的 dict（**原生**形态）。"""
    bases = []
    for b in (getattr(node, "bases", None) or []):
        s = _expr_src(b)
        if s:
            bases.append(s)
    # `class C(metaclass=M)` / `class C(**kw)`：星号实参不是基类，但也不能
    # 静默丢掉 —— 写成 `metaclass=M` / `**kw` 这样的原样文本。
    for kw in (getattr(node, "keywords", None) or []):
        s = _expr_src(kw.value)
        if not s:
            continue
        bases.append((u"**" + s) if kw.arg is None else (u"metaclass=" + s))
    decorators = [s for s in (_expr_src(d) for d in (node.decorator_list or []))
                  if s]
    methods, attrs = [], []
    for st in (node.body or []):
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods.append(st.name)
            attrs.extend(_self_attrs(st))
        elif isinstance(st, ast.AnnAssign):
            if isinstance(st.target, ast.Name):
                attrs.append((st.target.id, st.lineno,
                              _expr_src(st.annotation), ATTR_SCOPE_CLASS))
        elif isinstance(st, ast.Assign):
            for tg in (st.targets or []):
                if isinstance(tg, ast.Name):
                    attrs.append((tg.id, st.lineno, u"", ATTR_SCOPE_CLASS))
    attrs.sort(key=lambda t: t[1])
    members, seen = [], set()
    for nm, ln, an, sc in attrs:
        if nm in seen:
            continue
        seen.add(nm)
        members.append({"name": nm, "line": ln, "annotation": an, "scope": sc})
    return {"name": node.name, "line": node.lineno, "bases": bases,
            "decorators": decorators, "methods": methods,
            "attributes": members}


def _function_page(node, lines, keywords):
    """一个函数定义 → `LEGACY_FUNCTION_FIELDS` + `AST_FUNCTION_FIELDS` 形状。"""
    a = node.args
    name = node.name
    indent = node.col_offset
    calls = []
    for st in (node.body or []):
        _iter_calls(st, keywords, name, calls)
    ret = _expr_src(node.returns) if getattr(node, "returns", None) is not None \
        else u""
    return {
        "name": name,
        "line": node.lineno,
        "params": _arg_names(a),
        "ret": ret or u"None",           # 沿用语法层的哨兵（见模块 docstring）
        "complexity": _complexity(node.body),
        "calls": calls,
        "body_start": node.lineno,       # 与词法层一致：**定义行**，不是首条语句
        "body_end": _body_end(lines, node.lineno - 1, indent),
        "indent": indent,
        "decorators": [s for s in (_expr_src(d)
                                   for d in (node.decorator_list or [])) if s],
        "annotations": _param_annotations(a),
        "is_async": isinstance(node, ast.AsyncFunctionDef),
    }


def parse_ast(text, rel, path, keywords):
    """用 `ast` 解析一份 Python 源码 → 页面 dict（**不含** parser / limitations）。

    语法错误**不吞**：`ast.parse` 抛什么就让它抛什么，由 `parse_file` 决定
    降级（本函数不 import 产品、也不碰文件系统，于是可以在装置里裸跑）。
    """
    if text.startswith(u"\ufeff"):
        text = text[1:]
    tree = ast.parse(text, filename=path or rel or u"<py>")
    lines = text.split(u"\n")
    return {
        "rel": rel,
        "path": path,
        "functions": [_function_page(n, lines, keywords)
                      for n in _iter_defs(tree)],
        "imports": _collect_imports(tree),
        "classes": [_class_page(n)
                    for n in sorted((x for x in ast.walk(tree)
                                     if isinstance(x, ast.ClassDef)),
                                    key=lambda x: x.lineno)],
        "globals": _module_globals(tree),
    }


# 降级时要捕的异常：`SyntaxError` 是正主；`ValueError`（源码里有 NUL 字节）
# 与 `RecursionError` / `MemoryError`（畸形深嵌套）在真实语料上都见过。
# 一个文件把整棵树的运行掀掉，比降级成词法读数**差得多** —— 这正是要捕它
# 们的理由。**不捕 `BaseException`**：`KeyboardInterrupt` 之类必须照常穿出去。
_FALLBACK_ERRORS = (SyntaxError, ValueError, RecursionError, MemoryError)


def parse_file(text, rel, path, keywords, lexical=None):
    """**双层调度器**：`ast` 优先，语法失败降级到 `lexical`（注入进来的）。

    返回的页面**恒有** `PAGE_FIELDS` 的 8 个键；`parser` 说明这一页是哪层
    产出的，`limitations` 在降级时**非空**（>= `MIN_LIMITATION` 字符）。
    """
    try:
        page = parse_ast(text, rel, path, keywords)
    except _FALLBACK_ERRORS as exc:
        lineno = getattr(exc, "lineno", None)
        why = (u"ast 解析失败（%s%s）⇒ 本文件退化为词法扫描："
               u"class / 字段 / 装饰器 / 注解 / 相对导入 未识别"
               % (type(exc).__name__,
                  u"，第 %s 行" % lineno if lineno else u""))
        if lexical is None:
            page = {"rel": rel, "path": path, "functions": [], "imports": [],
                    "classes": [], "globals": []}
        else:
            page = dict(lexical(text, rel, path))
            page.setdefault("classes", [])
            page.setdefault("globals", [])
        page["parser"] = PARSER_LEXICAL
        page["limitations"] = [why]
        return page
    page["parser"] = PARSER_AST
    page["limitations"] = []
    return page


# ---------------------------------------------------------------------------
# 判据（`--selftest` 的载体）：都是**纯函数**，自证直接喂合成页面，
# 不另写一份「自证专用」的判定逻辑。
# ---------------------------------------------------------------------------
def param_problems(fn, where=u"函数"):
    """P2：形参**值域** —— 名字里不许有注解 / 默认值 / 空白，星号只许在开头。"""
    probs = []
    params = fn.get("params")
    if not isinstance(params, list):
        return [u"%s 的 `params` 必须是 list，拿到 %s"
                % (where, type(params).__name__)]
    for i, p in enumerate(params):
        tag = u"%s 的第 %d 个形参" % (where, i)
        if not _is_str(p) or not p:
            probs.append(u"%s 不是非空字符串：%r" % (tag, p))
            continue
        body = p.lstrip(u"*")
        if not body:
            probs.append(u"%s 只有星号没有名字：%r" % (tag, p))
        if u":" in p or u"=" in p:
            probs.append(u"%s 带着注解 / 默认值（应已剥掉）：%r" % (tag, p))
        if body != body.strip() or any(c.isspace() for c in body):
            probs.append(u"%s 含空白：%r" % (tag, p))
        if p.startswith(u"**"):
            pass
        elif p.startswith(u"*") and body.startswith(u"*"):
            probs.append(u"%s 星号过多：%r" % (tag, p))
    return probs


def function_problems(fn, where=u"函数", strict=True):
    """P1（函数半边）：键集 + 值域。`strict=True` 时要求 ast 的 12 个键全在。"""
    probs = []
    if not isinstance(fn, dict):
        return [u"%s 不是 dict，而是 %s" % (where, type(fn).__name__)]
    want = LEGACY_FUNCTION_FIELDS + (AST_FUNCTION_FIELDS if strict else ())
    missing = [k for k in LEGACY_FUNCTION_FIELDS if k not in fn]
    if missing:
        probs.append(u"%s 缺公共键 %s" % (where, missing))
    if strict:
        missing_ast = [k for k in AST_FUNCTION_FIELDS if k not in fn]
        if missing_ast:
            probs.append(u"%s 是 ast 页面却缺 %s" % (where, missing_ast))
    extra = sorted(set(fn) - set(want))
    if extra:
        probs.append(u"%s 有契约外键 %s" % (where, extra))
    if not _is_str(fn.get("name")) or not fn.get("name"):
        probs.append(u"%s 的 `name` 必须是非空字符串，拿到 %r"
                     % (where, fn.get("name")))
    if not _is_int(fn.get("line")) or fn.get("line") < 1:
        probs.append(u"%s 的 `line` 必须是 >=1 的整数，拿到 %r"
                     % (where, fn.get("line")))
    probs.extend(param_problems(fn, where))
    if not _is_str(fn.get("ret")):
        probs.append(u"%s 的 `ret` 必须是字符串，拿到 %r" % (where, fn.get("ret")))
    if not _is_int(fn.get("complexity")) or fn.get("complexity") < 1:
        probs.append(u"%s 的 `complexity` 必须是 >=1 的整数，拿到 %r"
                     % (where, fn.get("complexity")))
    for i, c in enumerate(fn.get("calls") or []):
        if not (isinstance(c, (list, tuple)) and len(c) == 2
                and _is_str(c[0]) and _is_int(c[1])):
            probs.append(u"%s 的第 %d 个调用点不是 (名字, 行号)：%r"
                         % (where, i, c))
    for k in ("body_start", "body_end", "indent"):
        if not _is_int(fn.get(k)) or fn.get(k) < 0:
            probs.append(u"%s 的 `%s` 必须是非负整数，拿到 %r"
                         % (where, k, fn.get(k)))
    if strict:
        deco = fn.get("decorators")
        if not isinstance(deco, list) or any(not _is_str(d) for d in deco):
            probs.append(u"%s 的 `decorators` 必须是字符串 list，拿到 %r"
                         % (where, deco))
        ann = fn.get("annotations")
        if not isinstance(ann, dict) or \
                any(not _is_str(k) or not _is_str(v) for k, v in ann.items()):
            probs.append(u"%s 的 `annotations` 必须是 str->str 的 dict，拿到 %r"
                         % (where, ann))
        if not isinstance(fn.get("is_async"), bool):
            probs.append(u"%s 的 `is_async` 必须是 bool，拿到 %r"
                         % (where, fn.get("is_async")))
    return probs


def attribute_problems(a, where=u"类成员"):
    """P5（成员半边）：键集 + 值域。"""
    probs = []
    if not isinstance(a, dict):
        return [u"%s 不是 dict，而是 %s" % (where, type(a).__name__)]
    missing = [k for k in ATTRIBUTE_FIELDS if k not in a]
    if missing:
        probs.append(u"%s 缺字段 %s" % (where, missing))
    extra = sorted(set(a) - set(ATTRIBUTE_FIELDS))
    if extra:
        probs.append(u"%s 有契约外字段 %s" % (where, extra))
    if not _is_str(a.get("name")) or not a.get("name"):
        probs.append(u"%s 的 `name` 必须是非空字符串，拿到 %r"
                     % (where, a.get("name")))
    if not _is_int(a.get("line")) or a.get("line") < 0:
        probs.append(u"%s 的 `line` 必须是非负整数，拿到 %r"
                     % (where, a.get("line")))
    if not _is_str(a.get("annotation")):
        probs.append(u"%s 的 `annotation` 必须是字符串（未知写空串），拿到 %r"
                     % (where, a.get("annotation")))
    if a.get("scope") not in ATTR_SCOPES:
        probs.append(u"%s 的 `scope`=%r 不在 %s"
                     % (where, a.get("scope"), list(ATTR_SCOPES)))
    return probs


def class_problems(c, where=u"类"):
    """P5（类半边）：键集 + 值域。"""
    probs = []
    if not isinstance(c, dict):
        return [u"%s 不是 dict，而是 %s" % (where, type(c).__name__)]
    missing = [k for k in CLASS_FIELDS if k not in c]
    if missing:
        probs.append(u"%s 缺字段 %s" % (where, missing))
    extra = sorted(set(c) - set(CLASS_FIELDS))
    if extra:
        probs.append(u"%s 有契约外字段 %s" % (where, extra))
    if not _is_str(c.get("name")) or not c.get("name"):
        probs.append(u"%s 的 `name` 必须是非空字符串，拿到 %r"
                     % (where, c.get("name")))
    if not _is_int(c.get("line")) or c.get("line") < 1:
        probs.append(u"%s 的 `line` 必须是 >=1 的整数，拿到 %r"
                     % (where, c.get("line")))
    for k in ("bases", "decorators", "methods"):
        v = c.get(k)
        if not isinstance(v, list) or any(not _is_str(x) for x in v):
            probs.append(u"%s 的 `%s` 必须是字符串 list，拿到 %r" % (where, k, v))
    attrs = c.get("attributes")
    if not isinstance(attrs, list):
        probs.append(u"%s 的 `attributes` 必须是 list，拿到 %s"
                     % (where, type(attrs).__name__))
    else:
        for i, a in enumerate(attrs):
            probs.extend(attribute_problems(
                a, u"%s 的第 %d 个成员" % (where, i)))
    return probs


def page_problems(page, where=u"页面"):
    """P1：页面**形状** —— 8 个键恰好齐全，且逐层委派到函数 / 类的判据。

    `strict` 按页面自己声明的 `parser` 决定：ast 页面必须带那 3 个额外键，
    lexical 页面**必须不带**（带了就是这一层在读它读不到的东西）。
    """
    probs = []
    if not isinstance(page, dict):
        return [u"%s 不是 dict，而是 %s" % (where, type(page).__name__)]
    missing = [k for k in PAGE_FIELDS if k not in page]
    if missing:
        probs.append(u"%s 缺键 %s" % (where, missing))
    extra = sorted(set(page) - set(PAGE_FIELDS))
    if extra:
        probs.append(u"%s 有契约外键 %s" % (where, extra))
    parser = page.get("parser")
    if parser not in PARSERS:
        probs.append(u"%s 的 `parser`=%r 不在 %s"
                     % (where, parser, list(PARSERS)))
    strict = (parser == PARSER_AST)
    for i, fn in enumerate(page.get("functions") or []):
        probs.extend(function_problems(
            fn, u"%s 的第 %d 个函数" % (where, i), strict=strict))
    for i, c in enumerate(page.get("classes") or []):
        probs.extend(class_problems(c, u"%s 的第 %d 个类" % (where, i)))
    for i, g in enumerate(page.get("globals") or []):
        if not _is_str(g) or not g:
            probs.append(u"%s 的第 %d 个全局名不是非空字符串：%r"
                         % (where, i, g))
    for i, imp in enumerate(page.get("imports") or []):
        if not (isinstance(imp, (list, tuple)) and len(imp) == 3
                and _is_str(imp[0]) and _is_str(imp[1]) and _is_int(imp[2])):
            probs.append(u"%s 的第 %d 条 import 不是 (模块, 名字, 行号)：%r"
                         % (where, i, imp))
    return probs


def fallback_problems(page, where=u"页面"):
    """P3：**降级必须说出来** —— lexical 页面 `limitations` 非空且 parser 对得上。"""
    probs = []
    if not isinstance(page, dict):
        return [u"%s 不是 dict" % where]
    parser = page.get("parser")
    lims = page.get("limitations")
    if not isinstance(lims, list):
        return [u"%s 的 `limitations` 必须是 list，拿到 %s"
                % (where, type(lims).__name__)]
    if parser == PARSER_LEXICAL and not lims:
        probs.append(u"%s 声明走词法层却没有任何 `limitations` —— "
                     u"「我没读到」被当成「确实没有」了" % where)
    if parser == PARSER_AST and lims:
        probs.append(u"%s 声明走 ast 层却带着 limitations（陈旧说明）：%r"
                     % (where, lims))
    return probs


def limitation_problems(page, where=u"页面"):
    """P4：每条降级理由都必须是**说得清**的（>= `MIN_LIMITATION` 字符）。"""
    probs = []
    for i, s in enumerate((page or {}).get("limitations") or []):
        if not _is_str(s) or len(s.strip()) < MIN_LIMITATION:
            probs.append(u"%s 的第 %d 条 limitations 只有 %d 个字符"
                         u"（下限 %d）：%r"
                         % (where, i, len((s or u"").strip()),
                            MIN_LIMITATION, s))
    return probs


# ---------------------------------------------------------------------------
# 自证：每个判据都要有**反例**（只跑正例等于没测），而且正例要用**真解析**。
# ---------------------------------------------------------------------------
_SAMPLE = (u"import os\n"
           u"from a.b import c as d\n"
           u"\n"
           u"class K(object):\n"
           u"    x = 1\n"
           u"\n"
           u"    def __init__(self, v):\n"
           u"        self.v = v\n"
           u"\n"
           u"    @property\n"
           u"    def get(self):\n"
           u"        return self.v\n"
           u"\n"
           u"\n"
           u"def top(a, b=2, *rest, **kw):\n"
           u"    h = K(a)\n"
           u"    if a and b:\n"
           u"        return h.get()\n"
           u"    return None\n")

_BROKEN = u"def broken(:\n    pass\n"


def _lexical_stub(text, rel, path):
    """自证用的**最小**词法替身：只证明「形参注入」这条接线通。

    它刻意不与 `matlabc.py` 的词法实现同构 —— 自证要证的是本模块对
    `lexical` 这个**接口**的处理（页面被补齐 8 键、parser 改成 lexical、
    limitations 非空），不是替身本身有多像。
    """
    return {"rel": rel, "path": path, "functions": [], "imports": []}


def _expect(state, name, probs, want_red):
    ok = bool(probs) if want_red else (not probs)
    if ok:
        state["bad" if want_red else "good"] += 1
    else:
        state["fail"].append(name)


def _selftest():
    state = {"good": 0, "bad": 0, "fail": []}

    # ---- 正例：真解析一份带类 / 属性 / 装饰器 / 注解 / 星号形参的源码 ----
    kw = set(u"if and or return object property".split())
    page = parse_file(_SAMPLE, u"sample.py", u"sample.py", kw,
                      lexical=_lexical_stub)
    _expect(state, "clean page", page_problems(page), False)
    _expect(state, "clean page fallback", fallback_problems(page), False)
    _expect(state, "clean page limitation", limitation_problems(page), False)

    fns = dict((f["name"], f) for f in page["functions"])
    _expect(state, "3 functions", None if len(page["functions"]) == 3
            else ["n"], False)
    _expect(state, "get line=11", None if fns.get("get", {}).get("line") == 11
            else ["n"], False)
    _expect(state, "decorator read", None
            if fns.get("get", {}).get("decorators") == ["property"] else ["n"],
            False)
    _expect(state, "star params", None
            if fns.get("top", {}).get("params") == ["a", "b", "*rest", "**kw"]
            else ["n"], False)
    _expect(state, "qualified call produced", None
            if ("get", 18) in (fns.get("top", {}).get("calls") or [])
            else ["n"], False)
    _expect(state, "boolop complexity", None
            if fns.get("top", {}).get("complexity") == 3 else ["n"], False)
    _expect(state, "one class", None if len(page["classes"]) == 1 else ["n"],
            False)
    cls = (page["classes"] or [{}])[0]
    _expect(state, "class bases", None if cls.get("bases") == ["object"]
            else ["n"], False)
    _expect(state, "class members", None
            if [(m["name"], m["scope"]) for m in cls.get("attributes") or []]
            == [("x", ATTR_SCOPE_CLASS), ("v", ATTR_SCOPE_INSTANCE)]
            else ["n"], False)
    _expect(state, "relative-ready imports", None
            if page["imports"] == [("os", "os", 1), ("a.b", "d", 2)] else ["n"],
            False)
    _expect(state, "globals empty", None if page["globals"] == [] else ["n"],
            False)

    # ---- 降级正例：语法坏了 ⇒ 必须走词法层且理由够长 ----
    bad_page = parse_file(_BROKEN, u"broken.py", u"broken.py", kw,
                          lexical=_lexical_stub)
    _expect(state, "degrade page shape", page_problems(bad_page), False)
    _expect(state, "degrade fallback", fallback_problems(bad_page), False)
    _expect(state, "degrade limitation", limitation_problems(bad_page), False)
    _expect(state, "degrade declares lexical", None
            if bad_page["parser"] == PARSER_LEXICAL else ["n"], False)

    # ---- 无 lexical 注入时也必须给一个 8 键的（空）页面 ----
    lone = parse_file(_BROKEN, u"b2.py", u"b2.py", kw, lexical=None)
    _expect(state, "degrade without lexical", page_problems(lone), False)

    # ---- P1 坏例 ----
    p1 = dict(page)
    del p1["classes"]
    _expect(state, "P1 missing page key", page_problems(p1), True)
    p1 = dict(page)
    p1["surprise"] = 1
    _expect(state, "P1 extra page key", page_problems(p1), True)
    p1 = dict(page)
    p1["functions"] = [dict(fns["top"])]
    del p1["functions"][0]["decorators"]
    _expect(state, "P1 ast page missing decorators", page_problems(p1), True)
    p1 = dict(page)
    p1["parser"] = "mebbe"
    _expect(state, "P1 bad parser", page_problems(p1), True)
    # lexical 页面**不许**带 ast 的 3 个键
    p1 = dict(bad_page)
    p1["functions"] = [dict(fns["top"])]
    _expect(state, "P1 lexical page leaking ast keys",
            page_problems(p1), True)

    # ---- P2 坏例 ----
    p2 = dict(page)
    fn2 = dict(fns["typed"] if "typed" in fns else fns["top"])
    fn2["params"] = ["a: int"]
    p2["functions"] = [fn2]
    _expect(state, "P2 annotation left in params", page_problems(p2), True)
    fn2 = dict(fns["top"])
    fn2["params"] = ["a=b"]
    p2["functions"] = [fn2]
    _expect(state, "P2 default left in params", page_problems(p2), True)

    # ---- P3 坏例 ----
    p3 = dict(bad_page)
    p3["limitations"] = []
    _expect(state, "P3 silent degrade", fallback_problems(p3), True)
    p3 = dict(page)
    p3["limitations"] = [u"陈旧说明，本该没有"]
    _expect(state, "P3 stale limitation on ast page",
            fallback_problems(p3), True)

    # ---- P4 坏例 ----
    p4 = dict(bad_page)
    p4["limitations"] = [u"短"]
    _expect(state, "P4 short limitation", limitation_problems(p4), True)

    # ---- P5 坏例 ----
    p5 = dict(page)
    c5 = dict(cls)
    c5["attributes"] = [{"name": "x", "line": 5, "annotation": "",
                         "scope": "banana"}]
    p5["classes"] = [c5]
    _expect(state, "P5 bad attr scope", page_problems(p5), True)
    p5 = dict(page)
    c5 = dict(cls)
    del c5["bases"]
    p5["classes"] = [c5]
    _expect(state, "P5 class missing key", page_problems(p5), True)
    _expect(state, "P5 bad member directly",
            attribute_problems({"name": "x", "line": 1, "annotation": ""},
                               u"成员"), True)

    print("SELFTEST COUNTS {\"bad\": %d, \"good\": %d}"
          % (state["bad"], state["good"]))
    if state["fail"]:
        print("FAILED: %s" % ", ".join(state["fail"]))
        return 1
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    if "--selftest" in argv:
        return _selftest()
    print("usage: python pyast_frontend.py [--selftest | --help]")
    return 2


if __name__ == "__main__":
    sys.exit(main())
