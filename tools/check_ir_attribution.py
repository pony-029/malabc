# -*- coding: utf-8 -*-
"""登记制护栏：**「解析不到的调用」只有一个判定点，而且归因吃到的就是它**。

一图看懂（这个不变式守的是什么）：

    C 前端 ─┐
    Py 前端 ─┤                        ┌──▶ edges        （调用图 / 报告）
    JS 前端 ─┼─▶ frontends/ir.py ────┤
    MATLAB  ─┘   resolve_calls()      └──▶ unresolved   （唯一判定点）
    （matlab.py）                              │
                                               ├──▶ renderers/unresolved.py  「疑似漏检」页
                                               └──▶ --binary-attach 三态归因
                                                       library: / gpu_kernel: / missing

R44（C'''1）之前，这个图是**假的**：同一条规则

    被调名在本语言的 func_index 里找不到  ⇒  记入 unresolved

被抄了**五遍**（`build_c_model` 内联、`_build_ext_model` 内联、C/Py/JS 三个
`build_edges` 逐字复制），另有 MATLAB 第 6 条独立路径。五份实现会各自漂移，
而归因只挂在其中一条名字来源上 —— 于是「源码说这个名字解析不到」与
「归因说它来自某个库」讨论的**可能不是同一批名字**，而两边都不报错。

本护栏把这件事钉成七条静态判据 + 十条纯函数判据，**每条都能被反例证伪**：

  C1 **写点集合双向一致**：全仓「往一个含 unresolved 的容器里新增条目」的函数
     集合，必须恰好等于 `IR_DECIDERS ∪ IR_CONSUMERS`。未登记 → 红（有人又抄了一遍）；
     登记了却不存在 → 也红（陈旧登记读起来像有覆盖）。
  C1b **写点的形状也要对**：只查集合会漏掉「**保留了共享调用、又顺手加了一段内联
     `append`**」这种写法（写点集合一个都没变）—— 所以每个写点登记它用哪种写法
     （`append`/`extend`/…），形状漂移 → 红。这是红路径探针的变异②逼出来的。
  C2 **判定点必须在 frontends/ 包内**：判定规则跑到包外面，就又是「前端各自为政」。
  C3 **接线真实**：每个登记点必须真的调用共享函数（`resolve_calls` /
     `call_sites_of_files`），否则只是登记了一条不存在的接线。
  C4 **归因喂入点受登记且名字来源可证**：把名字交给 `--binary-attach` 的函数
     必须恰好等于 `ATTR_FEEDS`，且每个喂入点必须登记它的名字来源，而来源按
     **AST 事实**证明（`kind="calls"` 调了哪个函数 / `kind="reads"` 读了哪个键）。
     **判据不看源码文本** —— 变异③说明看文本时，函数 docstring 里一句
     「名字取自 _collect_unresolved_calls」就足以把判据骗过去。
  C5' **查表谓词登记制**：想再抄一遍判定，可以改临时变量名、可以把结果藏进别的
     容器（那样 C1/C1b 看不见），但**绕不过 `func_index.get(x.lower())` 这次查表**。
     所以「哪个函数里有这次查表」也必须登记（`FUNC_INDEX_PREDICATES`）。

  C6' **语言登记双向一致**：`matlabc.py` 里 `register_frontend("x", …)` 注册了哪些
     语言，必须恰好等于 `frontends.IR_LANG_OWNERS` 登记了哪些语言，且每个登记项
     指向的模块/函数**真实可调用**（只写字符串的登记表可以是两个拼错的名字，
     而它看起来依然「有覆盖」）。产品模块之外敢调 `register_frontend` 的文件
     必须进 `REGISTER_OUT_OF_SCOPE`（两向核对，防陈旧）—— 这条范围划分不是洁癖：
     R44 实测 `tests/test_matlabc.py` 就会注册一个假前端，全仓扫描会**误红**。
     这条判据的由来：本包 docstring 当时已写着「守这件事的是本门，并且两向核对」，
     而本门里根本没有那个标识符 —— 一句话在描述一个不存在的对手方。

纯函数判据（比集合，不比个数 —— 与 R37 的基线门同一条纪律）：
  C5 IR 形状：`build_ir` 的键集合 == `IR_KEYS`；元组长度 == `UNRESOLVED_ARITY`；
     `unresolved_symbols` 返回 **set**（不是 list）。
  C6 判定规则：命中多个同名 ⇒ 每个命中各一条边；零命中 ⇒ 一条 unresolved；
     同一名字出现两次 ⇒ 元组 2 条但**符号集合只有 1 个**；顺序不影响符号集合。
  C7 MATLAB 侧符号集合同口径（同为 set）。

用法：
    python tools/check_ir_attribution.py             # 0=干净 1=有违规 2=缺输入
    python tools/check_ir_attribution.py --selftest  # 两向自证（坏样本要红、好样本要过）
    python tools/check_ir_attribution.py --help      # 显示本帮助（立即返回）

退出码：
    0  = 七条静态判据 + 十条纯函数判据在真实仓库上全部通过
    1  = 有违规（写点未被登记 / 判定点跑到包外 / 接线缺失 / 归因自算 / 形状或规则不符）
    2  = 缺输入（找不到 frontends/ir.py 或 matlabc.py → 红；「缺输入」不许当「干净」）

为什么必须是一道**静态**门而不是只写测试：五处逐字复制的代码在 review 里
看不出问题（每一处单独看都对）；只有「全仓恰好这些写点」这种**全局集合**判据
才能让它现形，而它必须每次提交都跑、且是秒级的。
"""
import ast
import io
import os
import sys
import tempfile

# ---------------------------------------------------------------- 登记表
# 键 = (相对仓库根的路径, 函数名)。**两向核对**：未登记 → 红；登记了却不存在 → 红。
#
# R44 实测（探针 probe_writers.py，全仓 AST 扫描）：全仓「往 unresolved 写」的
# 地方恰好 3 处。这份表的数字不是估的，是量出来的 —— 列在这里是为了让下次改动
# 有一个**能说不**的对手方。
IR_DECIDERS = {
    ("frontends/ir.py", "resolve_calls"):
        "唯一判定点：决定哪些调用进 edges、哪些进 unresolved（规则只在这里一次）",
}

IR_CONSUMERS = {
    ("matlabc.py", "build_c_model"):
        "把 IR 的 edges/unresolved 搬进 C 模型容器（不再自己判定）",
    ("matlabc.py", "_build_ext_model"):
        "同上：Py/JS 共用的组装器",
}

# 每个写点**允许的写入形状**。为什么要这一层：只问「哪些函数写了 unresolved」
# 会漏掉一种最隐蔽的回归 —— 函数**保留了共享调用**、又顺手加了一段内联
# `unresolved.append(...)`。那时写点集合没变（还是同一个函数），C3 的接线
# 检查也照样通过，只有「形状」变了。
# 形状标记：append / extend / insert（方法名）与 "=" / "+="（下标赋值）。
# 未登记的写点会先被 C1 报出来；这里只管**已登记写点的形状是否还是登记的那种**。
IR_WRITE_SHAPES = {
    ("frontends/ir.py", "resolve_calls"): ("append",),
    ("matlabc.py", "build_c_model"): ("extend",),
    ("matlabc.py", "_build_ext_model"): ("extend",),
}

# 判定点必须落在这些前缀里（规则跑出 frontends/ 就等于回到「各自为政」）。
DECIDER_PREFIXES = ("frontends/",)

# 把名字交给归因的函数 → (判据种类, 标记, 理由)
#
# ⚠ 判据种类**必须是结构化的**（AST 里真实的调用 / 真读的键），不能是"源码文本里
#   有没有这个字符串"。本文件前两版就是文本搜索，被红路径探针抓出一个真盲区：
#   变异「把 _collect_unresolved_calls(files) 换成自己遍历 external_calls」**没被
#   抓到** —— 因为那个函数（准确的说是它的 docstring）里还留着一句
#   「（名字取自 `_collect_unresolved_calls`）」，恰好满足了文本判据。
#   一行与被测行为无关的文字，顶替了一次真实的来源检查。这就是「断言必须钉在
#   被测的那条输出上，而不是钉在『整个输出里有没有这个字符串』」。
#
#   kind="calls"  : 函数体里必须出现对标记函数的**调用**
#   kind="reads"  : 函数体里必须**读到**标记的字典键（`.get("k")` 或 `["k"]`）
#   kind=None     : 纯转发点，不作来源要求
ATTR_FEEDS = {
    ("matlabc.py", "_emit_binary_attach_names"):
        (None, (), "纯转发：把调用方给的名字交给 _attribute_unresolved_with_binaries"),
    ("matlabc.py", "_run_c_only"):
        ("reads", ("unresolved",),
         "C 模式的 JSON / 终端两条分支都从 IR 容器读 unresolved 键"),
    ("matlabc.py", "_emit_binary_attach"):
        ("calls", ("_collect_unresolved_calls",),
         "MATLAB 主流程：名字来自 _collect_unresolved_calls -> "
         "frontends.matlab.unresolved_tuples"),
}

# 触发「这是一个归因喂入点」的函数名（调用其中任意一个即视为喂入）。
ATTR_TARGETS = ("_attribute_unresolved_with_binaries", "_emit_binary_attach_names")

# 注册前端的那次调用：`register_frontend("c", CFrontend)`，第一个参数是字面量语言名。
#
# 为什么这里要单列一条判据（C6'）：`frontends/__init__.py` 的 docstring 当时已经写着
# 「守这件事的是本门，并且两向核对」，而本门里**根本没有** IR_LANG_OWNERS /
# register_frontend / LANGS 这三个标识符（R44 实测 grep 0 命中）。一句文档在描述
# 一个不存在的对手方 —— 本仓把这类东西统一叫做「宣称没有装置」。
REGISTER_FN = "register_frontend"

# 语言名只在**产品模块**里构成宣称。测试会注册假前端来验证注册表自身的行为
# （R44 实测 tests/test_matlabc.py:4855 有 register_frontend("dummy", ...)），
# 那是夹具不是宣称 —— 直接全仓扫描会**误红**，所以范围显式化。
REGISTER_SCOPE = ("matlabc.py",)

# 产品范围之外的注册点必须逐文件登记，且**两向核对**：
#   未登记 → 红（新的产品外注册点没有任何装置知道）；
#   登记了却已不再注册 → 也红（陈旧登记读起来像有覆盖）。
REGISTER_OUT_OF_SCOPE = {
    "tests/test_matlabc.py": "夹具：注册一个假前端，用来验证注册表自身的行为",
}

# 登记点必须真的调用共享函数（任一命中即可）。
SHARED_CALL_TOKENS = ("resolve_calls", "call_sites_of_files")

# 「拿函数索引按小写名查表」这个谓词出现在哪些函数里。**唯一事实源的关键判据**：
# 任何一次「又把判定规则抄一遍」都必须包含这次查表 —— 抄的人可以改临时变量名、
# 可以把列表藏进别的容器（那样写点判据看不见），但**绕不过这次查表**。
# 标记 = 接收者文本里出现 func_index / funcidx，或接收者恰好是 idx。
FUNC_INDEX_MARKERS = ("func_index", "funcidx")
FUNC_INDEX_EXACT = ("idx",)
FUNC_INDEX_PREDICATES = {
    ("frontends/ir.py", "resolve_calls"):
        "唯一判定点的谓词本身（命中 -> 边，未命中 -> unresolved）",
    ("matlabc.py", "_match_c_bridge"):
        "MATLAB↔C 桥接：**只取命中**（`if not hits: continue`），既不产出 unresolved "
        "也不产出边 —— 语义不同，故显式登记其存在与理由",
}

DECIDE_ATTRS = ("append", "extend", "insert")
SKIP_DIRS = (".git", "__pycache__", ".pytest_cache", "node_modules",
             ".mypy_cache", ".workbuddy")


def _str_const(node):
    """取字符串字面量的值（兼容 3.6 的 `ast.Str` 与 3.8+ 的 `ast.Constant`）。

    不直接 `isinstance(node, ast.Constant)`：3.6 的解析器**不产出** Constant
    （产出 Str/Num），3.8+ 才统一。本仓承诺 3.6.5，所以两边都要认。
    顺手也让 `avoid unparse()` 成为可能 —— `ast.unparse` / `ast.get_source_segment`
    都是 3.9/3.8 才有的，用了就等于悄悄抬高本仓的最低 Python。
    """
    v = getattr(node, "value", None)
    if isinstance(v, str):
        return v
    s = getattr(node, "s", None)
    if isinstance(s, str):
        return s
    return None


def _receiver_text(lines, attr_node, attr):
    """从源码取 `X.append(...)` 的 `X` 文本（不用 ast.unparse —— 那是 3.9+）。"""
    if attr_node.lineno - 1 >= len(lines):
        return ""
    line = lines[attr_node.lineno - 1]
    seg = line[attr_node.col_offset:]
    pos = seg.find("." + attr)
    return seg[:pos] if pos >= 0 else seg


def _func_spans(tree):
    """[(起始行, 结束行, 函数名)]；结束行缺失时（3.6）取子树最大行号。"""
    spans = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(n, "end_lineno", None)
            if end is None:
                end = max([getattr(c, "lineno", n.lineno)
                           for c in ast.walk(n)] or [n.lineno])
            spans.append((n.lineno, end, n.name))
    return spans


def _owner(spans, lineno):
    """最近覆盖该行的函数名（嵌套时取最内层）。"""
    best = None
    for lo, hi, name in spans:
        if lo <= lineno <= hi and (best is None or lo > best[0]):
            best = (lo, name)
    return best[1] if best else "<module>"


def _has_lower_call(node):
    """AST 子树上是否有 `.lower()` 调用（用于识别 `X.get(y.lower())` 这个谓词）。"""
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and \
                n.func.attr == "lower":
            return True
    return False


def scan_file(path, rel):
    """扫单文件，返回
        {"writes": {函数名: set(形状)},
         "calls":  {函数名: set(被调名)},
         "reads":  {函数名: set(读到的字面量键)},
         "preds":  {函数名: set(谓词接收者文本)},
         "regs":   {语言名: 行号}（register_frontend 的字面量首参）}

    解析失败返回 {"error": ...} —— **解析不了不许当作干净**（缺输入不能通过）。

    这里**只产出 AST 事实**，不产出任何源码文本。R44 实测过一次假通过：来源判据
    当时读的是函数源码文本，于是 `_emit_binary_attach` 的 **docstring** 里那句
    「名字取自 _collect_unresolved_calls」就把它满足了（红路径探针的变异③）。
    源码文本可以被注释和文档字符串满足 —— 它顶替了一次真实的来源检查。
    """
    try:
        text = io.open(path, "r", encoding="utf-8", errors="replace").read()
        tree = ast.parse(text.replace("\r\n", "\n"))
    except Exception as e:                          # noqa: BLE001 - 只要报出来
        return {"error": "%s: %s" % (rel, e)}
    lines = text.replace("\r\n", "\n").split("\n")
    spans = _func_spans(tree)
    writes = {}
    calls = {}
    reads = {}
    preds = {}
    regs = {}
    for n in ast.walk(tree):
        fname = _owner(spans, getattr(n, "lineno", 1))
        if isinstance(n, ast.Call):
            fn_node = n.func
            # 记名字：裸调用（Name）与方法调用（Attribute）都要收。
            # 只收 receiver（如 f_ir）会漏掉方法名（resolve_calls）——
            # 本文件首版就是这个 bug，被自己的「好样本必须放行」当场抓到。
            if isinstance(fn_node, ast.Name):
                calls.setdefault(fname, set()).add(fn_node.id)
            elif isinstance(fn_node, ast.Attribute):
                calls.setdefault(fname, set()).add(fn_node.attr)
                v = fn_node.value
                if isinstance(v, ast.Name):
                    calls.setdefault(fname, set()).add(v.id)
                elif isinstance(v, ast.Attribute):
                    calls.setdefault(fname, set()).add(v.attr)
            # C6'：注册前端。**只认字面量** —— 用变量拼出来的语言名核对不了，
            # 宁可看不见也不要猜（猜出来的"合规"比红更糟）。
            # 裸调用 register_frontend(...) 与属性式调用 ma.register_frontend(...)
            # **都要收**。首版只认裸调用，于是 tests/ 里那处属性式调用看不见，
            # 反过来让「陈旧登记」判据报了一条**假红**（R44 实测）。
            _rf = ((isinstance(fn_node, ast.Name) and fn_node.id == REGISTER_FN) or
                   (isinstance(fn_node, ast.Attribute) and fn_node.attr == REGISTER_FN))
            if _rf and n.args:
                lang = _str_const(n.args[0])
                if lang:
                    regs[lang] = n.lineno
            # 写：list.append/extend/insert(接收者含 unresolved)
            if isinstance(fn_node, ast.Attribute) and \
                    fn_node.attr in DECIDE_ATTRS:
                recv = _receiver_text(lines, fn_node, fn_node.attr)
                if "unresolved" in recv:
                    writes.setdefault(fname, set()).add(fn_node.attr)
            # 读：X.get("字面量")
            if isinstance(fn_node, ast.Attribute) and fn_node.attr == "get" and n.args:
                key = _str_const(n.args[0])
                if key:
                    reads.setdefault(fname, set()).add(key)
                # 谓词：X.get(....lower())
                if _has_lower_call(n.args[0]):
                    recv = _receiver_text(lines, fn_node, "get").strip()
                    if any(m in recv for m in FUNC_INDEX_MARKERS) or \
                            recv in FUNC_INDEX_EXACT:
                        preds.setdefault(fname, set()).add(recv)
        # 读：x["字面量"]
        if isinstance(n, ast.Subscript):
            key = _str_const(n.slice)
            if key:
                reads.setdefault(fname, set()).add(key)
        if isinstance(n, (ast.Assign, ast.AugAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in targets:
                if isinstance(t, ast.Subscript) and \
                        _str_const(t.slice) == "unresolved":
                    writes.setdefault(fname, set()).add(
                        "=" if isinstance(n, ast.Assign) else "+=")
    return {"writes": writes, "calls": calls, "reads": reads,
            "preds": preds, "regs": regs}


def scan_repo(root, on_problem):
    """扫全仓 .py → 四个「按 (rel, 函数) 索引」的表 + 扫过的文件数。"""
    writes = {}
    calls = {}
    reads = {}
    preds = {}
    regs = {}
    n_files = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            r = scan_file(p, rel)
            if "error" in r:
                on_problem("I0 %s（解析不了 -> 不能当作干净）" % r["error"])
                continue
            n_files += 1
            for f, shapes in r["writes"].items():
                writes.setdefault((rel, f), set()).update(shapes)
            for f, names in r["calls"].items():
                calls.setdefault((rel, f), set()).update(names)
            for f, keys in r["reads"].items():
                reads.setdefault((rel, f), set()).update(keys)
            for f, recvs in r["preds"].items():
                preds.setdefault((rel, f), set()).update(recvs)
            for lang, ln in r["regs"].items():
                regs[(rel, lang)] = ln
    return writes, calls, reads, preds, regs, n_files


# ---------------------------------------------------------------- 判据
def judge(writes, calls, deciders, consumers, attr_feeds, attr_targets,
          decider_prefixes=DECIDER_PREFIXES, shared_tokens=SHARED_CALL_TOKENS,
          write_shapes=None, reads=None, preds=None, pred_registry=None,
          pred_markers=FUNC_INDEX_MARKERS, pred_exact=FUNC_INDEX_EXACT):
    """把六条静态判据抽成纯函数（自证直接喂合成数据测它）。

    `writes` 收 dict{点: set(形状)} 或 set(点)（首版只收 set，自证样本传了 dict
    就 TypeError —— 那是我自己的**类型契约不一致**，不是被测对象的问题，记在案）。
    返回问题字符串列表；空 = 通过。
    """
    probs = []
    if write_shapes is None:
        write_shapes = {}
    if reads is None:
        reads = {}
    if preds is None:
        preds = {}
    if not isinstance(writes, dict):
        writes = dict((k, None) for k in writes)
    want = set(deciders) | set(consumers)
    found_w = set(writes)

    # --- C1 写点集合双向一致 ---
    for k in sorted(found_w - want):
        probs.append("I1 未登记的写点 %s::%s —— 「命不中就记 unresolved」"
                     "这条规则又被抄了一遍（回到 R44 之前的状态）" % k)
    for k in sorted(want - found_w):
        probs.append("I1 陈旧登记 %s::%s —— 登记表说这里有个写点，源码里已经没有了"
                     "（读起来像有覆盖，其实是空的）" % k)

    # --- C1b 已登记写点的**形状**必须还是登记的那种 ---
    # 补的盲区很具体：函数**保留了共享调用**、又顺手加了一段内联
    # `unresolved.append(...)`（写到别的临时容器里也照样算 —— 写点集合没变）。
    for k in sorted(found_w & want):
        want_shapes = write_shapes.get(k)
        got = writes.get(k)
        if want_shapes is None or got is None:
            continue        # 形状未登记（合成样本）⇒ 不做这一条，也不假装测过
        if set(got) != set(want_shapes):
            probs.append("I1b %s::%s 的写入形状是 %s，登记的是 %s —— "
                         "要么登记过期，要么有人在同一函数里又加了一段内联判定"
                         % (k[0], k[1], sorted(got), sorted(want_shapes)))
    for k in sorted(set(write_shapes) - want):
        probs.append("I1b 形状表登记了一个不存在的写点 %s::%s" % (k[0], k[1]))

    # --- C2 判定点必须在包内 ---
    for k in sorted(deciders):
        if not any(k[0].startswith(p) for p in decider_prefixes):
            probs.append("I2 判定点 %s::%s 不在 %s 包内 —— 规则跑回前端各自为政"
                         % (k[0], k[1], list(decider_prefixes)))
    if not deciders:
        probs.append("I2 判定点登记表为空 —— 那就等于没有唯一判定点")

    # --- C3 接线真实 ---
    for k in sorted(want):
        if any(k[0].startswith(p) for p in decider_prefixes):
            continue        # 共享函数就在包内，它本身就是实现
        if not (set(shared_tokens) & calls.get(k, set())):
            probs.append("I3 %s::%s 登记为判定/消费点，函数体里却没有调用 %s"
                         " 中的任何一个 —— 登记了一条不存在的接线"
                         % (k[0], k[1], list(shared_tokens)))

    # --- C4 归因喂入点受登记 + 来源必须**结构上**可证 ---
    found_f = set()
    for k, names in calls.items():
        if set(attr_targets) & names:
            found_f.add(k)
    want_f = set(attr_feeds)
    for k in sorted(found_f - want_f):
        probs.append("I4 未登记的归因喂入点 %s::%s —— 它把名字交给了 "
                     "--binary-attach，却没有登记「名字从哪来」" % (k[0], k[1]))
    for k in sorted(want_f - found_f):
        probs.append("I4 陈旧登记 %s::%s —— 该喂入点已不存在" % (k[0], k[1]))
    for k in sorted(want_f):
        entry = attr_feeds[k]
        kind, toks = entry[0], entry[1]
        if kind is None:
            continue        # 纯转发点：来源由它的调用方负责
        if k not in found_f:
            continue        # 陈旧登记已报过
        if kind == "calls":
            ok = bool(set(toks) & calls.get(k, set()))
        elif kind == "reads":
            ok = bool(set(toks) & reads.get(k, set()))
        else:
            probs.append("I4 %s::%s 的判据种类 %r 不认识（判不了不许算通过）"
                         % (k[0], k[1], kind))
            continue
        if not ok:
            probs.append("I4 %s::%s 是归因喂入点，但它%s里找不到已登记的"
                         "名字来源 %s —— 名字可能是自己重算的"
                         % (k[0], k[1],
                            "调用的" if kind == "calls" else "读的键",
                            list(toks)))

    # --- C5' 「拿函数索引按小写名查表」这个谓词出现在哪些函数里 ---
    # 这是唯一事实源的关键判据：抄一遍判定**绕不过**这次查表
    # （抄的人可以改临时变量名、把结果藏进别的容器，让 C1/C1b 看不见）。
    if pred_registry is None:
        # 显式「本条不适用」（合成样本没造这张表）—— 跳过，而不是偷偷当成空表：
        # 「空表 = 没有对手方」是**真跑时**必须报的红，两者不能混成一个。
        pass
    else:
        for k in sorted(set(preds) - set(pred_registry)):
            probs.append("I5 %s::%s 里有「函数索引按小写名查表」的谓词却没有登记 "
                         "—— 这几乎必然是把判定规则又抄了一遍" % (k[0], k[1]))
        for k in sorted(set(pred_registry) - set(preds)):
            probs.append("I5 陈旧登记 %s::%s —— 登记表说这里有查表谓词，"
                         "源码里已经没有了" % (k[0], k[1]))
        if not pred_registry:
            probs.append("I5 谓词登记表为空 —— 唯一判定点没有任何对手方守着")
    del pred_markers, pred_exact        # 只由 scan_file 用来识别；这里只用登记表
    return probs


def _owner_lookup(fr, owners):
    """把 `IR_LANG_OWNERS` 的 (模块名, 函数名) 兑现成**真实可调用对象**。

    登记表只写字符串是不够的：`("ir", "resolve_calls")` 完全可以是两个拼错的
    名字，而登记表本身看起来依然"有覆盖"。这里要求它真的能取到可调用对象。

    ⚠ `owners` 是**必传**的，刻意不给默认值：`judge_langs` 收一个 `declared` 参数，
    如果兑现动作却总去读模块里的那一份，传进来的表与真正被兑现的表可以不是
    同一张 —— 那样「登记项可兑现」这条判据会在**判别的表**。R44 实测踩到：
    回归测试想用一个拼错函数名的表去触发这条判据，结果触发不了 ——
    **测试写不出来，就是接口本身不自洽**。
    """

    def _f(lang):
        spec = (owners or {}).get(lang)
        if not spec or len(spec) != 2:
            return None
        mod = getattr(fr, spec[0], None)
        fn = getattr(mod, spec[1], None) if mod is not None else None
        return fn if callable(fn) else None

    return _f


def judge_langs(registered, declared, owner_lookup,
                outside=(), out_registry=None,
                scope=REGISTER_SCOPE):
    """C6'：`register_frontend` 与 `frontends.IR_LANG_OWNERS` 双向一致。

    registered : {语言: 行号}，只在 `scope`（产品模块）内采集到的注册语言
    outside    : {相对路径} —— 产品范围外**调用过** register_frontend 的文件
    返回 (问题列表, 实际跑了多少项断言)。
    """
    probs = []
    n = 0
    if out_registry is None:
        out_registry = {}
    reg = set(registered)
    dec = set(declared)

    n += 1
    for lang in sorted(reg - dec):
        probs.append("I6 注册了前端 %r 却没有在 frontends.IR_LANG_OWNERS 里登记"
                     "它的 unresolved 产出点 —— 这个语言的「解析不到的调用」无人负责"
                     % lang)
    n += 1
    for lang in sorted(dec - reg):
        probs.append("I6 陈旧登记：IR_LANG_OWNERS 里有 %r，%s 里却没有 "
                     "register_frontend(%r, ...) —— 读起来像「已支持」，其实是空的"
                     % (lang, list(scope), lang))
    for lang in sorted(reg & dec):
        n += 1
        if owner_lookup(lang) is None:
            probs.append("I6 %r 登记为 %r，但包内取不到那个可调用的模块/函数"
                         " —— 登记表只写字符串是不够的"
                         % (lang, declared.get(lang)))
    n += 1
    if not dec:
        probs.append("I6 IR_LANG_OWNERS 为空 —— 没有任何语言被登记为有产出点")
    n += 1
    for rel in sorted(set(outside) - set(out_registry)):
        probs.append("I6 %s 调用了 register_frontend 却不在 REGISTER_SCOPE 里、"
                     "也没登记 —— 产品范围外的注册点必须显式说明它是夹具还是宣称"
                     % rel)
    n += 1
    for rel in sorted(set(out_registry) - set(outside)):
        probs.append("I6 陈旧登记：REGISTER_OUT_OF_SCOPE 里有 %s，但它已经不再"
                     "调用 register_frontend" % rel)
    return probs, n


def check_shapes(fr, on_problem):
    """C5 + C6 + C7：纯函数判据（只造内存样本，不起进程、不写盘）。

    返回**实际执行的断言数**（写进成功行 —— 免得「七条判据」是一句没人重算的话）。
    """
    ir = fr.ir
    n = 0

    def _assert(cond, msg):
        if not cond:
            on_problem(msg)

    # C5-① build_ir 的键集合 == IR_KEYS
    built = ir.build_ir("t", [], {})
    n += 1
    _assert(set(built.keys()) == set(ir.IR_KEYS),
            "I5 build_ir 产出的键 %s 与 IR_KEYS %s 不一致"
            % (sorted(built.keys()), sorted(ir.IR_KEYS)))
    n += 1
    _assert("unresolved" in ir.IR_KEYS,
            "I5 IR_KEYS 里没有 unresolved —— 归因没有可对接的键")
    # C5-② 元组长度：合法的要放行、四段元组要抓
    n += 1
    _assert(not ir.unresolved_arity_problems({"unresolved": [("a", 1, "x.c")]}),
            "I5 合法的三段元组被判为形状违规")
    n += 1
    _assert(bool(ir.unresolved_arity_problems(
        {"unresolved": [("a", 1, "x.c", "多出来的第四段")]})),
        "I5 四段元组没被判为形状违规（元组长度判据失效）")
    # C5-③ 返回值必须是 set
    syms = ir.unresolved_symbols({"unresolved": [("a", 1, "x.c")]})
    n += 1
    _assert(isinstance(syms, set),
            "I5 unresolved_symbols 返回 %s 而不是 set —— "
            "比集合的判据会退化成比个数" % type(syms).__name__)

    # C6-① 命中多个同名 ⇒ 每个命中各一条边
    idx = {"foo": [{"file": None, "func": {"name": "foo"}},
                   {"file": None, "func": {"name": "Foo"}}]}
    e, u = ir.resolve_calls(idx, [("a", "foo", 1, "x")])
    n += 1
    _assert(len(e) == 2 and not u,
            "I6 同名两处命中应产 2 条边 0 条 unresolved，实测 edges=%d unresolved=%d"
            % (len(e), len(u)))
    # C6-② 零命中 ⇒ 一条 unresolved
    e, u = ir.resolve_calls({}, [("a", "nope", 1, "x")])
    n += 1
    _assert(not e and len(u) == 1,
            "I6 零命中应产 0 条边 1 条 unresolved，实测 edges=%d unresolved=%d"
            % (len(e), len(u)))
    # C6-③ 同一名字两次 ⇒ 元组 2 条、符号集合 1 个（这正是「比集合不比个数」）
    e, u = ir.resolve_calls({}, [("a", "dup", 1, "x"), ("b", "dup", 2, "y")])
    n += 1
    _assert(len(u) == 2 and
            len(ir.unresolved_symbols({"unresolved": u})) == 1,
            "I6 同名两次未解析：元组应为 2 条、符号集合应为 1 个，实测 %d / %d"
            % (len(u), len(ir.unresolved_symbols({"unresolved": u}))))
    # C6-④ 顺序不影响符号集合
    a = {"unresolved": [("p", 1, "x"), ("q", 2, "y")]}
    b = {"unresolved": [("q", 2, "y"), ("p", 1, "x")]}
    n += 1
    _assert(ir.unresolved_symbols(a) == ir.unresolved_symbols(b),
            "I6 顺序不同导致符号集合不同 —— 集合比较失效")
    # C7 MATLAB 侧同口径
    n += 1
    _assert(isinstance(fr.matlab.unresolved_symbols([]), set),
            "I7 frontends.matlab.unresolved_symbols 返回 %s 而不是 set"
            % type(fr.matlab.unresolved_symbols([])).__name__)
    return n


# ---------------------------------------------------------------- 自证
def _mk_repo(tmp, files):
    for rel, text in files.items():
        p = os.path.join(tmp, rel.replace("/", os.sep))
        d = os.path.dirname(p)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        io.open(p, "w", encoding="utf-8", newline="").write(text)
    return tmp


def _rm_tree_small(tmp):
    """只删小目录（自证样本 ≤5 个文件）。本机 safe-delete 会拦大目录，
    所以这里刻意走 os.remove/os.rmdir 而不是 shutil.rmtree。"""
    for dp, dns, fns in os.walk(tmp, topdown=False):
        for f in fns:
            try:
                os.remove(os.path.join(dp, f))
            except OSError:
                pass
        for d in dns:
            try:
                os.rmdir(os.path.join(dp, d))
            except OSError:
                pass


GOOD_REPO = {
    "frontends/__init__.py": ("from . import ir\nfrom . import matlab\n"
                              "IR_KEYS = ir.IR_KEYS\n"),
    "frontends/ir.py": ("IR_KEYS = ('unresolved',)\n"
                        "def resolve_calls(idx, sites):\n"
                        "    unresolved = []\n"
                        "    for c in sites:\n"
                        "        hits = idx.get(c.lower())\n"
                        "        if hits:\n"
                        "            continue\n"
                        "        unresolved.append(c)\n"
                        "    return [], unresolved\n"),
    "matlabc.py": ("def build_c_model(files):\n"
                   "    model = {'unresolved': []}\n"
                   "    _e, _u = f_ir.resolve_calls({}, "
                   "f_ir.call_sites_of_files(files))\n"
                   "    model['unresolved'].extend(_u)\n"
                   "    return model\n"
                   "\n"
                   "def _collect_unresolved_calls(files):\n"
                   "    return f_matlab.unresolved_tuples(files)\n"
                   "\n"
                   "def _emit_binary_attach(args, files):\n"
                   "    names = _collect_unresolved_calls(files)\n"
                   "    return _attribute_unresolved_with_binaries('', names)\n"),
}

# 坏样本①：又抄了一份判定点（这正是 R44 要防的回归）
BAD_DUP_DECIDER = dict(GOOD_REPO, **{
    "matlabc.py": ("def build_c_model(files):\n"
                   "    unresolved = []\n"
                   "    for c in files:\n"
                   "        unresolved.append(c)\n"
                   "    return unresolved\n"),
})
# 坏样本②：登记的点没接共享函数
BAD_NO_WIRE = dict(GOOD_REPO, **{
    "matlabc.py": ("def build_c_model(files):\n"
                   "    model = {'unresolved': []}\n"
                   "    model['unresolved'].extend([])\n"
                   "    return model\n"
                   "\n"
                   "def _collect_unresolved_calls(files):\n"
                   "    return f_matlab.unresolved_tuples(files)\n"
                   "\n"
                   "def _emit_binary_attach(args, files):\n"
                   "    names = _collect_unresolved_calls(files)\n"
                   "    return _attribute_unresolved_with_binaries('', names)\n"),
})
# 坏样本③：归因自己重算名字（不登记、也不从 IR 取）
BAD_SELF_COMPUTED = dict(GOOD_REPO, **{
    "matlabc.py": ("def build_c_model(files):\n"
                   "    model = {'unresolved': []}\n"
                   "    _e, _u = f_ir.resolve_calls({}, "
                   "f_ir.call_sites_of_files(files))\n"
                   "    model['unresolved'].extend(_u)\n"
                   "    return model\n"
                   "\n"
                   "def _emit_binary_attach(args, files):\n"
                   "    names = [f.name for f in files]\n"
                   "    return _attribute_unresolved_with_binaries('', names)\n"),
})
# 坏样本④：陈旧登记（登记了一个源码里不存在的消费点）
BAD_STALE = dict(GOOD_REPO, **{
    "matlabc.py": ("def build_c_model(files):\n"
                   "    return {'unresolved': []}\n"
                   "\n"
                   "def _collect_unresolved_calls(files):\n"
                   "    return f_matlab.unresolved_tuples(files)\n"
                   "\n"
                   "def _emit_binary_attach(args, files):\n"
                   "    names = _collect_unresolved_calls(files)\n"
                   "    return _attribute_unresolved_with_binaries('', names)\n"),
})
# 坏样本⑤：判定点跑到 frontends/ 包外
BAD_OUTSIDE = dict(GOOD_REPO, **{
    "xxx.py": ("def g(idx, sites):\n"
               "    unresolved = []\n"
               "    unresolved.append(1)\n"
               "    return [], unresolved\n"),
})
# 坏样本⑥：**新增一个前端又自带一份判定**（R44 之前 C/Py/JS 三个 build_edges 就是这个形状）
BAD_NEW_FRONTEND = dict(GOOD_REPO, **{
    "matlabc.py": (GOOD_REPO["matlabc.py"] +
                   "\nclass NewFrontend(object):\n"
                   "    def build_edges(self, model):\n"
                   "        unresolved = []\n"
                   "        for f in model['files']:\n"
                   "            unresolved.append(f)\n"
                   "        return [], unresolved\n"),
})

# 自证样本共用的形状表
SHAPES_MAIN = {
    ("frontends/ir.py", "resolve_calls"): ("append",),
    ("matlabc.py", "build_c_model"): ("extend",),
}

# 自证样本共用的谓词表（好样本的 frontends/ir.py 里真有 idx.get(c.lower())）。
# 之所以要把样本也造出这个谓词：否则 I5 这条判据在自证里**一次都不执行**，
# 而「没测过」看起来与「测过了」一模一样。
PREDS_MAIN = {
    ("frontends/ir.py", "resolve_calls"): "样本侧的「函数索引按小写名查表」",
}


def _selftest():
    """两向自证：坏样本必须被抓到、好样本必须放行。计数由实际执行统计。"""
    bad = good = 0
    dec = {("frontends/ir.py", "resolve_calls"): "唯一判定点"}
    con = {("matlabc.py", "build_c_model"): "消费"}
    feeds = {("matlabc.py", "_emit_binary_attach"):
             ("calls", ("_collect_unresolved_calls",), "MATLAB 主流程")}

    def _sample(name, files, deciders, consumers, want_problem, feeds_map=feeds,
                shapes=SHAPES_MAIN, preds_map=PREDS_MAIN):
        tmp = tempfile.mkdtemp(prefix="ir_attr_selftest_")
        try:
            _mk_repo(tmp, files)
            probs = []
            writes, calls, reads, preds, _regs, n = scan_repo(tmp, probs.append)
            if n == 0:
                probs.append("I0 一个 .py 都没扫到")
            probs.extend(judge(writes, calls, deciders, consumers, feeds_map,
                               ATTR_TARGETS, write_shapes=shapes,
                               reads=reads, preds=preds,
                               pred_registry=preds_map))
            got = bool(probs)
            if got == want_problem:
                return True, (probs[0] if probs else "")
            return False, ("期望 %s 实际 %s%s"
                           % ("红" if want_problem else "绿",
                              "红" if got else "绿",
                              ("；" + probs[0]) if probs else ""))
        finally:
            _rm_tree_small(tmp)

    for name, files, want in (
        ("好样本：唯一判定点 + 归因取自 IR", GOOD_REPO, False),
        ("坏样本①：消费点里又混进一段内联判定（形状变了）", BAD_DUP_DECIDER, True),
        ("坏样本②：登记的点没接共享函数", BAD_NO_WIRE, True),
        ("坏样本③：归因自己重算名字", BAD_SELF_COMPUTED, True),
        ("坏样本④：陈旧登记（消费点已不存在）", BAD_STALE, True),
        ("坏样本⑤：额外判定点跑到 frontends/ 包外", BAD_OUTSIDE, True),
        ("坏样本⑥：新增前端又自带一份判定", BAD_NEW_FRONTEND, True),
    ):
        ok, why = _sample(name, files, dec, con, want)
        if ok:
            good += 1
            print("  [selftest] %s" % name)
        else:
            bad += 1
            print("  [selftest] **未达预期** %s：%s" % (name, why))

    # ---- 纯函数层：坏样本必须报、好样本必须不报 ----
    p1 = judge({("x.py", "f"): {"append"}}, {}, dec, con, feeds, ATTR_TARGETS)
    if p1:
        good += 1
    else:
        bad += 1
        print("  [selftest] **未达预期** 纯函数：未登记写点未被抓到")
    p2 = judge({("frontends/ir.py", "resolve_calls"): {"append"},
                ("matlabc.py", "build_c_model"): {"extend"}},
               {("matlabc.py", "build_c_model"):
                {"resolve_calls", "call_sites_of_files"}},
               dec, con, {}, ATTR_TARGETS,
               write_shapes={("frontends/ir.py", "resolve_calls"): ("append",),
                             ("matlabc.py", "build_c_model"): ("extend",)},
               preds=PREDS_MAIN, pred_registry=PREDS_MAIN)
    if not p2:
        good += 1
    else:
        bad += 1
        print("  [selftest] **未达预期** 纯函数：合法集合被误伤 %s" % p2)
    # C1 是**集合**判据：两个额外写点必须各报一条（不是「个数变了就报一条」）
    p3 = judge({("frontends/ir.py", "resolve_calls"): {"append"},
                ("a.py", "g"): {"append"}, ("b.py", "h"): {"append"}},
               {}, dec, con, {}, ATTR_TARGETS)
    if len([x for x in p3 if x.startswith("I1 未登记")]) == 2:
        good += 1
    else:
        bad += 1
        print("  [selftest] **未达预期** 纯函数：两个额外写点应各报一条，实测 %s" % p3)
    # C2：判定点登记在包外必须报
    p4 = judge({("xxx.py", "g"): {"append"}}, {},
               {("xxx.py", "g"): "跑到包外"}, {}, {}, ATTR_TARGETS)
    if any(x.startswith("I2") for x in p4):
        good += 1
    else:
        bad += 1
        print("  [selftest] **未达预期** 纯函数：包外判定点未被抓到 %s" % p4)
    # C1b：写点集合没变、只有**形状**变了（保留接线 + 又加一段内联 append）必须报
    p5 = judge({("frontends/ir.py", "resolve_calls"): {"append"},
                ("matlabc.py", "build_c_model"): {"extend", "append"}},
               {("matlabc.py", "build_c_model"): {"resolve_calls"}},
               dec, con, {}, ATTR_TARGETS,
               write_shapes={("frontends/ir.py", "resolve_calls"): ("append",),
                             ("matlabc.py", "build_c_model"): ("extend",)})
    if any(x.startswith("I1b") for x in p5):
        good += 1
    else:
        bad += 1
        print("  [selftest] **未达预期** 纯函数：形状漂移未被抓到 %s" % p5)
    # I5：谓词表**传了但是空的** ⇒ 红。「没有对手方」不许当干净；这与
    # pred_registry=None（本条不适用）是两件事，所以必须单独测一次。
    p6 = judge({("frontends/ir.py", "resolve_calls"): {"append"},
                ("matlabc.py", "build_c_model"): {"extend"}},
               {("matlabc.py", "build_c_model"): {"resolve_calls"}},
               dec, con, {}, ATTR_TARGETS,
               preds=PREDS_MAIN, pred_registry={})
    if any(x.startswith("I5") for x in p6):
        good += 1
    else:
        bad += 1
        print("  [selftest] **未达预期** 纯函数：空谓词登记表未被抓到 %s" % p6)
    # I5：多出一个没登记的查表谓词 ⇒ 红（这正是「又抄一遍判定」的指纹：
    # 抄的人绕不过这次查表，所以这次查表出现在哪个函数里就是证据）
    p7 = judge({("frontends/ir.py", "resolve_calls"): {"append"},
                ("matlabc.py", "build_c_model"): {"extend"}},
               {("matlabc.py", "build_c_model"): {"resolve_calls"}},
               dec, con, {}, ATTR_TARGETS,
               preds={("frontends/ir.py", "resolve_calls"): {"idx"},
                      ("matlabc.py", "another_copy"): {"idx"}},
               pred_registry=PREDS_MAIN)
    if any(x.startswith("I5") for x in p7):
        good += 1
    else:
        bad += 1
        print("  [selftest] **未达预期** 纯函数：多出的查表谓词未被抓到 %s" % p7)

    # ---- C6'：语言登记双向一致（四向：多注册 / 陈旧登记 / 取不到函数 / 范围外）----
    def _ok(_lang):
        """冒充一个「能取到可调用对象」的登记表。"""
        return lambda: None

    l0, _n0 = judge_langs({"c": 1, "py": 2}, {"c": ("ir", "f"),
                                             "py": ("ir", "f")}, _ok, (), {})
    if not l0:
        good += 1
    else:
        bad += 1
        print("  [selftest] **未达预期** C6'：合法语言集合被误伤 %s" % l0)
    l1, _n1 = judge_langs({"c": 1, "zz": 9}, {"c": ("ir", "f")}, _ok, (), {})
    if any(x.startswith("I6 注册了前端") for x in l1):
        good += 1
    else:
        bad += 1
        print("  [selftest] **未达预期** C6'：多注册的语言未被抓到 %s" % l1)
    l2, _n2 = judge_langs({"c": 1}, {"c": ("ir", "f"),
                                        "go": ("ir", "f")}, _ok, (), {})
    if any(x.startswith("I6 陈旧登记") for x in l2):
        good += 1
    else:
        bad += 1
        print("  [selftest] **未达预期** C6'：陈旧语言登记未被抓到 %s" % l2)
    l3, _n3 = judge_langs({"c": 1}, {"c": ("ir", "typo")},
                          lambda _l: None, (), {})
    if any("取不到" in x for x in l3):
        good += 1
    else:
        bad += 1
        print("  [selftest] **未达预期** C6'：指向不存在函数的登记未被抓到 %s" % l3)
    l4, _n4 = judge_langs({"c": 1}, {"c": ("ir", "f")}, _ok,
                          ("tests/x.py",), {})
    l5, _n5 = judge_langs({"c": 1}, {"c": ("ir", "f")}, _ok,
                          (), {"tests/gone.py": "夹具"})
    if any("产品范围外" in x for x in l4) and any("不再" in x for x in l5):
        good += 1
    else:
        bad += 1
        print("  [selftest] **未达预期** C6'：范围外注册点两向核对失效 %s / %s"
              % (l4, l5))
    return bad, good


# ---------------------------------------------------------------- main
def _write_help(text):
    for s in (sys.stdout, sys.stderr):
        if s is not None and hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    sys.stdout.write(text)
    sys.stdout.flush()


def _load_frontends(root):
    if root not in sys.path:
        sys.path.insert(0, root)
    import frontends
    return frontends


def main(argv):
    if "--help" in argv or "-h" in argv:
        _write_help(__doc__)
        return 0
    if "--selftest" in argv:
        b, g = _selftest()
        print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (b, g))
        # 下界断言：新增自证样本不许把它变红；覆盖数只许增。
        # 今天实测 18（7 个仓库样本 + 7 条纯函数 + 4 条语言登记相关），
        # 下界留一点重构余量，但不能低到「删掉一半样本也看不出来」。
        return 0 if (b == 0 and g >= 16) else 1

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.isfile(os.path.join(root, "matlabc.py")):
        print("check_ir_attribution: 找不到 matlabc.py（缺输入 -> 红）：%s" % root)
        return 2
    if not os.path.isfile(os.path.join(root, "frontends", "ir.py")):
        print("check_ir_attribution: 找不到 frontends/ir.py（缺输入 -> 红）")
        return 2

    probs = []
    writes, calls, reads, preds, regs, n_files = scan_repo(root, probs.append)
    if n_files == 0:
        print("check_ir_attribution: 一个 .py 都没扫到（缺输入 -> 红）")
        return 2
    probs.extend(judge(writes, calls, IR_DECIDERS, IR_CONSUMERS, ATTR_FEEDS,
                       ATTR_TARGETS, write_shapes=IR_WRITE_SHAPES,
                       reads=reads, preds=preds,
                       pred_registry=FUNC_INDEX_PREDICATES))
    try:
        fr = _load_frontends(root)
    except Exception as e:                      # noqa: BLE001
        print("check_ir_attribution: 导不进 frontends 包（缺输入 -> 红）：%s" % e)
        return 2
    n_shape = check_shapes(fr, probs.append)
    # C6'：语言登记双向一致。产品范围内的注册语言看 matlabc.py，
    # 范围外的注册文件进 REGISTER_OUT_OF_SCOPE 两向核对。
    in_scope = dict((lang, ln) for (rel, lang), ln in regs.items()
                    if rel in REGISTER_SCOPE)
    outside = set(rel for (rel, _lang) in regs if rel not in REGISTER_SCOPE)
    lprobs, n_lang = judge_langs(in_scope, fr.IR_LANG_OWNERS,
                                 _owner_lookup(fr, fr.IR_LANG_OWNERS), outside,
                                 REGISTER_OUT_OF_SCOPE)
    probs.extend(lprobs)

    if probs:
        print("check_ir_attribution: %d 项不合规" % len(probs))
        for p in probs:
            print("  - " + p)
        return 1
    print("check_ir_attribution: OK（扫描 %d 个 .py；写点 %d 处 = 判定点 %d + "
          "消费点 %d，归因喂入点 %d 处，语言登记 %d 个，与登记表双向一致；"
          "另跑了 %d 项纯函数形状/规则判据 + %d 项语言登记判据）"
          % (n_files, len(IR_DECIDERS) + len(IR_CONSUMERS), len(IR_DECIDERS),
             len(IR_CONSUMERS), len(ATTR_FEEDS), len(in_scope), n_shape, n_lang))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
