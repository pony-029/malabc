# -*- coding: utf-8 -*-
"""import 图门（R52）：**模块级** import 必须无环；借用的回边只能走登记的惰性通道。

一图看懂：

    python tools/check_import_graph.py
        │
        ├─ 扫仓库 .py（跳过 .git / .workbuddy / __pycache__），用 ast 建图
        │
        ├─ 边 = Import / ImportFrom，并分两档：
        │     · 模块级边（tree.body 的直接子节点）→ **import 期图**（G1 判它）
        │     · 函数级边（嵌套在 def 里）        → 惰性边，import 期不发生
        │
        ├─ G1 模块级图必须**无环**（SCC 大小 > 1 → 红）
        ├─ G2 惰性环必须登记（LAZY_CYCLES，两向：未登记红 / 陈旧红）
        ├─ G3 指向**本仓模块**的动态 import 必须登记（DYNAMIC_IMPORTS，两向）
        ├─ G4 自环（模块 import 自己）→ 红，**不可登记**
        ├─ G5 理由少于 8 字符 → 该登记**不生效**
        ├─ G6 `CONTRIBUTING.md` 双向标记 `<!-- import-cycle: <id> -->`
        └─ G7 借用清单两向核对（`_mL.X` 使用点 ↔ `renderers/_late.py::BORROWED`）
        │
        ▼
    0 = 全绿   1 = 有违规   2 = 缺输入

为什么需要它（R52 实测，装置在仓库外 `_r52/probe_cycle_kind.py`）：
`renderers.{callgraph,hotspot,report,sarif,snapshot,unresolved}` 原先在模块**底部**
`from matlabc import (...)`，而 `matlabc.py` 底部又 `from renderers.X import (...)` ——
两个方向互相指认，**import 期成环**。它能跑，靠的是一份**隐式时序契约**：
`matlabc` 被部分初始化时，被借用的名字必须已经定义在再导出点**之前**。
契约没有被任何东西钉住，而 `git status` / `git diff` / 任何一个测试都看不见它。

R52 把这条回边搬进 `renderers/_late.py`（**惰性**属性访问 + 一条登记过的动态 import），
import 期图于是无环；这道门就是**不让它再长回来**的对手方。

R53/C''''2 又补上这条通道**内容侧**的对手方：`_mL.X` 的 `X` 原先只由**使用点**定义，
门与测试只能验「X 存在于 matlabc」，**多一个借用、少一个使用点都没有东西要求同步**。
现在 `renderers/_late.py::BORROWED` 是借用清单的**静态单一事实源**，G7 两向核对：
用了没登记 → 红；登记了没人用、或登记了 matlabc 模块层里不存在的名字 → 也红。
⚠ 树里没有 `renderers/_late.py`（合成样本）时 G7 **不适用**；有这条通道而
登记表**缺失或为空** ⇒ **真红**（与 check_ir_attribution 的 `pred_registry=None` 同口径）。

四条判据「各自独立作证」（本仓纪律：被别的判据抓走 ⇒ 该判据没有独立证人）：
  * 加一条**模块级**回边        → 只 G1 红（G2 抓的是嵌套环，G3 抓的是动态 import）；
  * 加一条**未登记的嵌套**环    → 只 G2 红；
  * 加一条**未登记的动态** import → 只 G3 红；
  * 动一处**借用**（用多一个 / 少登记一个 / 登记一个 matlabc 里没有的名字）→ 只 G7 红。

用法：
    python tools/check_import_graph.py            # 0=全绿 1=有违规 2=缺输入
    python tools/check_import_graph.py --selftest # 两向自证
    python tools/check_import_graph.py --help     # 显示本帮助（立即返回）

退出码：
    0 = 全绿（模块级无环、登记两向一致、文档标记对称、借用清单两向一致）
    1 = 有违规（未登记环 / 陈旧登记 / 未登记动态 import / 未登记借用 / 陈旧借用登记 / 悬空借用 / 理由过短 / 文档标记不对称）
    2 = 缺输入（找不到仓库根、扫不到任何 .py、或缺 CONTRIBUTING.md）
"""
import ast
import io
import os
import re
import sys

# ---------------------------------------------------------------------------
# 登记表（单一事实源）。每项必须有 id / reason（>=8 字符），
# 且必须在 CONTRIBUTING.md 里出现一次 `<!-- import-cycle: <id> -->` 标记（G6，双向）。
# ---------------------------------------------------------------------------
LAZY_CYCLES = (
    {
        "id": "agent-loop-matlabc-flow",
        "modules": ("agent_loop", "matlabc_flow"),
        "reason": ("两条边都写在**函数体**里（惰性 import）：agent_loop 只在 run_* 里 "
                   "import matlabc_flow，matlabc_flow 只在 --auto-apply-loop 分支里 "
                   "import agent_loop。import 期不发生，所以它不是 import 期环；"
                   "登记它的意义是：谁把它改成**模块级**边，G1 立刻红。"),
    },
)

DYNAMIC_IMPORTS = (
    {
        "id": "late-matlabc",
        "file": "renderers/_late.py",
        "target": "matlabc",
        "reason": ("R52：renderers 借用 matlabc 的 20 个符号，改成**首次属性访问**时才取"
                   "（importlib.import_module，不是 import 语句）。这是全仓唯一一条"
                   "指向本仓模块的动态 import —— 登记它，是为了让「把这条通道删了、"
                   "却把注释/文档留在原地」也变红。"),
    },
    {
        "id": "tests-frontends",
        "file": "tests/test_matlabc.py",
        "target": "frontends",
        "reason": ("测试**故意**按 ROOT 动态导入 frontends 包，导入后立刻把 ROOT 从 "
                   "sys.path 撤掉（静态写法会要求测试运行目录恰好是仓库根，"
                   "在别处跑就静默变成另一个包）。登记它，是为了让「改回静态、"
                   "或把 sys.path 清理那段删掉」时有人看得见。"),
    },
)

MIN_REASON = 8
SKIP_DIRS = (".git", ".workbuddy", "__pycache__", "node_modules")
# ⚠ id 的字符集必须**收紧**：文档里会写示例形态 `<!-- import-cycle: <id> -->`，
# 若用 `[^\s>]+` 兜底，那个 `<id` 会被当成一个**陈旧标记**（G6 假红）。
MARKER_RE = r"<!--\s*import-cycle\s*:\s*([A-Za-z0-9_.\-]+)\s*-->"


# ---------------------------------------------------------------------------
# 纯函数（自证直接测它们，不建文件）
# ---------------------------------------------------------------------------
def _str_const(node):
    """取字符串字面量的值（兼容 3.6 的 `ast.Str` 与 3.8+ 的 `ast.Constant`）。"""
    v = getattr(node, "value", None)
    if isinstance(v, str):
        return v
    s = getattr(node, "s", None)
    if isinstance(s, str):
        return s
    return None


def _literal_dict(node):
    """把 ast 节点还原成纯字面量 dict；失败返回 None。

    **不做任何"尽力而为"**：`BORROWED` 读不出来就是「登记表缺失」，由 G7 判红，
    而不是静默当成空表 —— 后者会让整张表悄悄失效而 rc 依然是 0。
    """
    try:
        return ast.literal_eval(node)
    except Exception:                       # noqa: BLE001 - 故意兜住
        return None


def _toplevel_names(tree):
    """模块层的绑定名（def / class / 赋值目标 / import asname）。

    只看 `tree.body` 的**直接子节点** —— 与 G1 判「模块级」同一条口径：
    嵌在模块层 `if/try` 里的定义**不算**模块层绑定（那类名字在 import 期是否
    存在取决于分支，借用它们本就不安全）。
    """
    out = set()
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                for x in ast.walk(t):
                    if isinstance(x, ast.Name):
                        out.add(x.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                out.add(a.asname or a.name.split(".")[0])
    return out


def _mod_name(rel):
    """`renderers/report.py` -> `renderers.report`；`x/__init__.py` -> `x`。"""
    m = rel[:-3] if rel.endswith(".py") else rel
    parts = m.replace("\\", "/").split("/")
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _resolve(level, module, src):
    """把 (level, module) 解析成绝对模块名（相对 import 用包的层级）。"""
    if not level:
        return module or ""
    pkg = src.rsplit(".", 1)[0] if "." in src else ""
    parts = pkg.split(".") if pkg else []
    up = level - 1
    if up:
        parts = parts[:len(parts) - up] if up <= len(parts) else []
    if module:
        parts = parts + [module]
    return ".".join([p for p in parts if p])


def scan(files):
    """files: {rel_path: source_text} -> built dict。

    键：
      known      : set(模块名)
      edges_mod  : {src: set(dst)}  —— **模块级**边（import 期图）
      edges_all  : {src: set(dst)}  —— 含嵌套边
      self_mod   : [(src, lineno)]  —— 模块级自环
      dyn        : [(rel, target, lineno)] —— 指向本仓模块的动态 import
      parse_err  : [(rel, msg)]
      n_mod, n_nested : 边计数
    """
    known = {}
    for rel in files:
        known[_mod_name(rel)] = rel
    kset = set(known)
    edges_mod = {}
    edges_all = {}
    self_mod = []
    dyn = []
    parse_err = []
    n_mod = n_nested = 0

    for rel, text in sorted(files.items()):
        src = _mod_name(rel)
        try:
            tree = ast.parse(text)
        except SyntaxError as e:
            parse_err.append((rel, "%s" % e))
            continue
        top = set(id(n) for n in tree.body)

        def add(nm, lineno, is_top):
            tgt = None
            if nm in kset:
                tgt = nm
            elif nm and nm.split(".")[0] in kset:
                tgt = nm.split(".")[0]
            if tgt is None:
                return
            edges_all.setdefault(src, set()).add(tgt)
            if is_top:
                if tgt == src:
                    self_mod.append((src, lineno))
                else:
                    edges_mod.setdefault(src, set()).add(tgt)

        # 模块级边：只看 tree.body 的直接子节点
        # （⚠ 不能用「行号落在顶层语句范围内」来判顶层 —— 嵌套节点的行号天然落在其中，
        #   本轮装置首版就是这么把 agent_loop<->matlabc_flow 误判成模块级环的。）
        for node in tree.body:
            if isinstance(node, ast.Import):
                for a in node.names:
                    add(a.name, node.lineno, True)
                    n_mod += 1
            elif isinstance(node, ast.ImportFrom):
                base = _resolve(node.level, node.module, src)
                if base:
                    add(base, node.lineno, True)
                    n_mod += 1
                for a in node.names:
                    if a.name != "*":
                        add((base + "." + a.name) if base else a.name,
                            node.lineno, True)
                        n_mod += 1

        # 嵌套边 + 动态 import
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)) and id(node) not in top:
                if isinstance(node, ast.Import):
                    for a in node.names:
                        add(a.name, node.lineno, False)
                        n_nested += 1
                else:
                    base = _resolve(node.level, node.module, src)
                    if base:
                        add(base, node.lineno, False)
                        n_nested += 1
                    for a in node.names:
                        if a.name != "*":
                            add((base + "." + a.name) if base else a.name,
                                node.lineno, False)
                            n_nested += 1
            elif isinstance(node, ast.Call):
                fn = node.func
                is_dyn = ((isinstance(fn, ast.Name) and fn.id == "__import__") or
                          (isinstance(fn, ast.Attribute) and
                           fn.attr == "import_module"))
                if is_dyn and node.args:
                    t = _str_const(node.args[0])
                    if t in kset:
                        dyn.append((rel, t, node.lineno))

    # ---- R53/C''''2：借用清单一族（使用点 / 登记表 / 目标模块的模块层名字） ----
    # 只看 `renderers/` 子树，且只认字面别名 `_mL`（R52 起全仓唯一写法）。
    # 用 (模块, 属性) 而不是属性名 —— 同一个名字被两个模块借用时，
    # 登记表必须**两边都写**，否则「谁借了什么」这件事就模糊了。
    borrow_sites = {}
    for rel, text in sorted(files.items()):
        r = rel.replace("\\", "/")
        if not r.startswith("renderers/"):
            continue
        try:
            btree = ast.parse(text)
        except SyntaxError:
            continue
        src = _mod_name(rel)
        for node in ast.walk(btree):
            if (isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "_mL"):
                key = (src, node.attr)
                borrow_sites[key] = borrow_sites.get(key, 0) + 1

    late_key = "renderers/_late.py"
    has_late = late_key in files
    borrowed_reg = None
    if has_late:
        try:
            for node in ast.parse(files[late_key]).body:
                if (isinstance(node, ast.Assign) and len(node.targets) == 1
                        and isinstance(node.targets[0], ast.Name)
                        and node.targets[0].id == "BORROWED"):
                    borrowed_reg = _literal_dict(node.value)
        except SyntaxError:
            borrowed_reg = None

    mc_names = None
    if "matlabc.py" in files:
        try:
            mc_names = _toplevel_names(ast.parse(files["matlabc.py"]))
        except SyntaxError:
            mc_names = None

    return {"known": kset, "edges_mod": edges_mod, "edges_all": edges_all,
            "self_mod": self_mod, "dyn": dyn, "parse_err": parse_err,
            "n_mod": n_mod, "n_nested": n_nested,
            "has_late": has_late, "borrow_sites": borrow_sites,
            "borrowed_reg": borrowed_reg, "mc_names": mc_names}


def scc(nodes, graph):
    """Tarjan（迭代版，避免深图递归爆栈）。返回 [comp, ...]，comp 已排序。"""
    index, low, on, stack, out, c = {}, {}, {}, [], [], [0]
    for root in sorted(nodes):
        if root in index:
            continue
        work = [(root, 0)]
        while work:
            v, pi = work[-1]
            if pi == 0:
                index[v] = low[v] = c[0]
                c[0] += 1
                stack.append(v)
                on[v] = True
            rec = False
            succ = sorted(graph.get(v, ()))
            while pi < len(succ):
                w = succ[pi]
                if w not in index:
                    work[-1] = (v, pi + 1)
                    work.append((w, 0))
                    rec = True
                    break
                if on.get(w):
                    low[v] = min(low[v], index[w])
                pi += 1
            if rec:
                continue
            if low[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop()
                    on[w] = False
                    comp.append(w)
                    if w == v:
                        break
                out.append(sorted(comp))
            work.pop()
            if work:
                p = work[-1][0]
                low[p] = min(low[p], low[v])
    return out


def judge(built, lazy_cycles, dyn_imports, doc_text):
    """核心判定。返回问题字符串列表（空 = 全绿）。纯函数，自证直接喂合成 built。"""
    probs = []

    # G4 自环：先报（自环一定会让 G1 也红，但两种病因要分开说）
    for (src, ln) in built["self_mod"]:
        probs.append("G4 %s:%s 模块级 import 了自己（自环不可登记）" % (src, ln))

    # G1 模块级无环
    mod_cycles = [c for c in scc(built["known"], built["edges_mod"]) if len(c) > 1]
    for c in mod_cycles:
        probs.append("G1 import 期成环：%s —— 模块级 import 必须无环"
                     "（借用请走惰性通道，见 renderers/_late.py）" % " <-> ".join(c))

    # G2 惰性环登记（双向）。
    # 口径：只看**依赖至少一条嵌套边**的环 —— 纯模块级环由 G1 负责（两条判据各管一段，
    # 不许一条判据把另一条的病也抓走，否则「独立证人」就没了）。
    # 只走模块级边的环在 import 期真实存在（G1）；含嵌套边的环 import 期**不发生**，
    # 所以它是「已知的、被允许的架构事实」，登记即可，但必须写清理由。
    all_cycles = [c for c in scc(built["known"], built["edges_all"]) if len(c) > 1]
    mod_keys = set(frozenset(c) for c in mod_cycles)
    actual = {}
    for c in all_cycles:
        if frozenset(c) in mod_keys:
            continue
        actual[frozenset(c)] = c
    registered = {}
    for item in lazy_cycles:
        key = frozenset(item.get("modules") or ())
        registered[key] = item
        if len("".join(item.get("reason") or "").strip()) < MIN_REASON:
            probs.append("G5 惰性环登记 %s 的理由少于 %d 字符 ⇒ 该登记不生效"
                         % (item.get("id"), MIN_REASON))
    for key, c in sorted(actual.items(), key=lambda kv: sorted(kv[1])):
        if key not in registered:
            probs.append("G2 未登记的惰性环：%s —— 要么去掉这条嵌套 import，"
                         "要么在 LAZY_CYCLES 登记并说明理由" % " <-> ".join(c))
    for key, item in sorted(registered.items(),
                            key=lambda kv: kv[1].get("id") or ""):
        if key not in actual:
            probs.append("G2 陈旧登记 %s：%s 之间已不成环"
                         % (item.get("id"), " / ".join(sorted(key))))

    # G3 指向本仓模块的动态 import 登记（双向）
    actual_dyn = set((rel, tgt) for (rel, tgt, _ln) in built["dyn"])
    reg_dyn = set()
    for item in dyn_imports:
        reg_dyn.add((item.get("file"), item.get("target")))
        if len("".join(item.get("reason") or "").strip()) < MIN_REASON:
            probs.append("G5 动态 import 登记 %s 的理由少于 %d 字符 ⇒ 该登记不生效"
                         % (item.get("id"), MIN_REASON))
    for pair in sorted(actual_dyn - reg_dyn):
        probs.append("G3 未登记的动态 import：%s 里 %s —— "
                     "动态取本仓模块会绕开 import 图，必须登记" % pair)
    for pair in sorted(reg_dyn - actual_dyn):
        probs.append("G3 陈旧登记：已找不到 %s 里的动态 import %s" % pair)

    # G6 CONTRIBUTING.md 双向标记
    marks = set(re.findall(MARKER_RE, doc_text or ""))
    want = set([i.get("id") for i in lazy_cycles] +
               [i.get("id") for i in dyn_imports])
    for i in sorted(want - marks):
        probs.append("G6 CONTRIBUTING.md 缺标记 `<!-- import-cycle: %s -->`" % i)
    for i in sorted(marks - want):
        probs.append("G6 CONTRIBUTING.md 有陈旧标记 `<!-- import-cycle: %s -->`"
                     "：登记表里没有这个 id" % i)

    # G7 借用清单（R53/C''''2）：`_mL.X` 的使用点必须与
    # `renderers/_late.py::BORROWED` **互为对手方**。
    # 口径：树里没有 `renderers/_late.py` ⇒ 该树不涉及借用通道 ⇒ G7 **不适用**
    # （合成样本因此不受影响）；有通道而登记表缺失/为空 ⇒ **真红**。
    if built.get("has_late"):
        reg = built.get("borrowed_reg")
        sites = built.get("borrow_sites") or {}
        mc = built.get("mc_names")
        if not isinstance(reg, dict) or not reg:
            probs.append("G7 renderers/_late.py 里找不到非空的 BORROWED 登记表 —— "
                         "借用必须有静态单一事实源（空表也是真红）")
        else:
            reg_names = {}
            for mod in sorted(reg):
                entry = reg.get(mod) or {}
                names = tuple(entry.get("names") or ())
                reg_names[mod] = names
                if not names:
                    probs.append("G7 借用登记 %s 的 names 为空 —— 空登记不成立" % mod)
                if len("".join(entry.get("reason") or "").strip()) < MIN_REASON:
                    probs.append("G7 借用登记 %s 的理由少于 %d 字符 ⇒ 该登记不生效"
                                 % (mod, MIN_REASON))
                if mod not in built["known"]:
                    probs.append("G7 借用登记 %s：仓库里根本没有这个模块（陈旧登记）"
                                 % mod)
                for nm in names:
                    if (mod, nm) not in sites:
                        probs.append("G7 陈旧登记 %s：登记借用了 %s，"
                                     "但仓库里再没有 `_mL.%s` 使用点"
                                     % (mod, nm, nm))
                    if mc is not None and nm not in mc:
                        probs.append("G7 悬空借用 %s：登记借用的 %s 在 matlabc 的"
                                     "模块层没有定义（借用目标不存在）" % (mod, nm))
            for (mod, nm) in sorted(sites):
                if nm not in reg_names.get(mod, ()):
                    probs.append("G7 未登记借用：%s 用了 `_mL.%s`，"
                                 "但 BORROWED 里没有登记" % (mod, nm))
    return probs


# ---------------------------------------------------------------------------
# 真实仓库
# ---------------------------------------------------------------------------
def root_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_repo(root):
    files = {}
    for dp, dn, fns in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for fn in fns:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            files[rel] = io.open(p, "r", encoding="utf-8",
                                 errors="replace").read()
    return files


def _write_help(text):
    for _s in (sys.stdout, sys.stderr):
        if _s is not None and hasattr(_s, "reconfigure"):
            try:
                _s.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    sys.stdout.write(text)
    sys.stdout.flush()


def main(argv):
    if "--help" in argv or "-h" in argv:
        _write_help(__doc__)
        return 0
    if "--selftest" in argv:
        bad, good = _selftest()
        print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
        return 0 if bad == 0 else 1

    root = root_dir()
    files = read_repo(root)
    if not files:
        print("check_import_graph: 仓库根下扫不到任何 .py（缺输入 → 红）：%s" % root)
        return 2
    contrib = os.path.join(root, "CONTRIBUTING.md")
    if not os.path.exists(contrib):
        print("check_import_graph: 找不到 CONTRIBUTING.md（G6 的单据在它里面 → 缺输入）")
        return 2
    doc = io.open(contrib, "r", encoding="utf-8", errors="replace").read()

    built = scan(files)
    if built["parse_err"]:
        for rel, msg in built["parse_err"]:
            print("check_import_graph: %s 解析失败：%s" % (rel, msg))
        return 2
    probs = judge(built, LAZY_CYCLES, DYNAMIC_IMPORTS, doc)
    if probs:
        for p in probs:
            print("check_import_graph: " + p)
        print("check_import_graph: %d 项违规" % len(probs))
        return 1
    n_mod = sum(len(v) for v in built["edges_mod"].values())
    n_all = sum(len(v) for v in built["edges_all"].values())
    _bs = built.get("borrow_sites") or {}
    _reg = built.get("borrowed_reg") or {}
    print("check_import_graph: OK（%d 个模块 / 模块级仓库内边 %d 条 / 全图仓库内边 %d 条；"
          "模块级环 0、惰性环 %d（已登记）、动态 import %d（已登记）；"
          "借用登记 %d 个模块 / %d 个符号 / %d 处使用点；G1–G7 全绿）"
          % (len(built["known"]), n_mod, n_all,
             len(LAZY_CYCLES), len(DYNAMIC_IMPORTS),
             len(_reg), len(set(nm for (_m, nm) in _bs)), sum(_bs.values())))
    return 0


# ---------------------------------------------------------------------------
# 两向自证：坏样本必须红、好样本必须绿
# ---------------------------------------------------------------------------
def _mk(mapping):
    """把 {name: [行...]} 变成 {name: text}。"""
    out = {}
    for k, v in mapping.items():
        out[k] = "\n".join(v) + "\n"
    return out


def _selftest():
    """两向自证。`bad` 数的是**本装置自己的失误**（坏样本没红 / 好样本被误伤）。"""
    bad = [0]
    good = [0]

    def red(tag, files, lazy, dyn, doc, want):
        """坏样本必须红，且必须红在**指定**判据上（被别的判据抓走不算）。"""
        probs = judge(scan(files), lazy, dyn, doc)
        hit = [p for p in probs if p.startswith(want)]
        if hit:
            good[0] += 1
        else:
            bad[0] += 1
            print("  [selftest] %s 未被 %s 抓到（实得 %r）" % (tag, want, probs))

    def green(tag, files, lazy, dyn, doc):
        probs = judge(scan(files), lazy, dyn, doc)
        if not probs:
            good[0] += 1
        else:
            bad[0] += 1
            print("  [selftest] %s 被误伤：%r" % (tag, probs))

    DOC_L = "<!-- import-cycle: L1 -->\n"
    DOC_D = "<!-- import-cycle: D1 -->\n"
    L1 = ({"id": "L1", "modules": ("a", "b"),
           "reason": "a 与 b 只在函数体内互相 import（惰性）"},)
    D1 = ({"id": "D1", "file": "a.py", "target": "b",
           "reason": "a.py 里用 importlib 取 b，属于动态通道"},)

    # -------- 坏样本（各自必须红在**自己那条**判据上） --------
    red("B1 纯模块级环", _mk({"a.py": ["import b", "def fa():", "    return 1"],
                            "b.py": ["import a", "def fb():", "    return 1"]}),
        (), (), "", "G1")
    red("B2 模块级自环", _mk({"a.py": ["import a"]}), (), (), "", "G4")
    red("B3 未登记的惰性环",
        _mk({"a.py": ["def fa():", "    import b", "    return b"],
             "b.py": ["def fb():", "    import a", "    return a"]}),
        (), (), "", "G2 未登记")
    red("B4 理由过短",
        _mk({"a.py": ["def fa():", "    import b", "    return b"],
             "b.py": ["def fb():", "    import a", "    return a"]}),
        ({"id": "L1", "modules": ("a", "b"), "reason": "短"},), (), "", "G5")
    red("B5 陈旧惰性登记",
        _mk({"a.py": ["def fa():", "    import b", "    return b"],
             "b.py": ["def fb():", "    return 1"]}), L1, (), DOC_L, "G2 陈旧")
    red("B6 未登记动态 import",
        _mk({"a.py": ["import importlib", "def fa():",
                      "    return importlib.import_module('b')"],
             "b.py": ["def fb():", "    return 1"]}), (), (), "", "G3 未登记")
    red("B7 陈旧动态登记",
        _mk({"a.py": ["def fa():", "    return 1"],
             "b.py": ["def fb():", "    return 1"]}), (), D1, DOC_D, "G3 陈旧")
    red("B8 缺文档标记",
        _mk({"a.py": ["def fa():", "    import b", "    return b"],
             "b.py": ["def fb():", "    import a", "    return a"]}),
        L1, (), "", "G6")
    red("B9 陈旧文档标记", _mk({"a.py": ["def fa():", "    return 1"]}),
        (), (), DOC_L, "G6")

    # -------- 好样本 --------
    green("G1 干净图", _mk({"a.py": ["import b", "def fa():", "    return 1"],
                          "b.py": ["def fb():", "    return 1"]}), (), (), "")
    green("G2 惰性环已登记",
          _mk({"a.py": ["def fa():", "    import b", "    return b"],
               "b.py": ["def fb():", "    import a", "    return a"]}),
          L1, (), DOC_L)
    green("G3 动态 import 已登记",
          _mk({"a.py": ["import importlib", "def fa():",
                        "    return importlib.import_module('b')"],
               "b.py": ["def fb():", "    return 1"]}), (), D1, DOC_D)
    green("G4 相对 import 解析正确",
          _mk({"pkg/__init__.py": [""],
               "pkg/a.py": ["from . import b", "def fa():", "    return 1"],
               "pkg/b.py": ["def fb():", "    return 1"]}), (), (), "")
    green("G5 文档示例形态不算标记",
          _mk({"a.py": ["def fa():", "    return 1"]}),
          (), (), "示例：<!-- import-cycle: <id> -->\n")

    # -------- R53/C''''2：G7 借用清单（使用点 ↔ BORROWED 两向） --------
    # 合成树必须**自带** `renderers/_late.py`（G7 的适用开关）与 `matlabc.py`
    # （悬空借用的对手方）；否则 G7 不适用，坏样本也红不起来。
    _late_ok = ("BORROWED = {\n"
                "    'renderers.m': {'names': ('foo',),\n"
                "                     'reason': 'm 只借一个纯函数 foo，用于合成自证'},\n"
                "}\n")
    _mc_ok = "def foo():\n    return 1"
    _use_foo = ["from renderers._late import late as _mL", "def f():",
                "    return _mL.foo()"]

    def _btree(late=None, use=None, mc=None):
        return _mk({"renderers/_late.py": [late or _late_ok],
                    "renderers/m.py": use if use is not None else _use_foo,
                    "matlabc.py": [mc or _mc_ok]})

    red("B10 未登记借用",
        _btree(use=["from renderers._late import late as _mL", "def f():",
                    "    return _mL.bar()"]), (), (), "", "G7 未登记")
    red("B11 陈旧借用登记",
        _btree(late="BORROWED = {\n"
                    "    'renderers.m': {'names': ('foo', 'baz'),\n"
                    "                     'reason': '登记了 baz 但其实没人用'},\n"
                    "}\n"), (), (), "", "G7 陈旧")
    red("B12 悬空借用",
        _btree(late="BORROWED = {\n"
                    "    'renderers.m': {'names': ('foo', 'nope'),\n"
                    "                     'reason': 'nope 在 matlabc 里没有定义'},\n"
                    "}\n",
               use=["from renderers._late import late as _mL", "def f():",
                    "    return _mL.foo() + _mL.nope()"]),
        (), (), "", "G7 悬空")
    red("B13 借用登记理由过短",
        _btree(late="BORROWED = {\n"
                    "    'renderers.m': {'names': ('foo',), 'reason': '短'},\n"
                    "}\n"), (), (), "", "G7 借用登记")
    green("G7 借用清单两向一致", _btree(), (), (), "")

    return bad[0], good[0]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
