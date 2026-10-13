# -*- coding: utf-8 -*-
"""callrel.py —— 调用关系（call relations）的**有界投影**。

为什么这个模块存在
==================
分析器**早就算出了**调用边。实测（Linux 内核整树）：C 函数 743,509 个、
调用边 **7,060,966** 条、未解析调用 1,295,143 条。可是**交付出去的结果里
一条关系都没有**，根因是产物环节而不是分析环节：

  * `--json-level summary` 的载荷**结构上不含 `edges`**（`matlabc.py` 的
    摘要支路只写 `summary.edges` 这个**计数**，非摘要支路才写
    `"edges": [{"caller","callee","line","file"}, ...]`）；
  * 全量 `edges` 在内核规模下是 GB 级（7.06M 条 × ~130 B ≈ 918 MB，加上
    每文件明细，实测外推 ~2.6 GB）——**把 GB 级 JSON 丢给用户不是解法**。

于是本模块给出第三条路：**有界投影**。规模再大，顶层输出恒为 KB 级；
被丢掉的那部分**必须如实上报**（``truncated`` 里给 ``*_total`` / ``*_shown``
两对数）。这一条与 R86-2 的 ``skipped ≠ not_found`` 同源 ——
**「我没展开」不等于「没有关系」。**

节点身份：**两种口径并列，不许同化**（R88 起）
==============================================
R86/R87 只有一种：``callee-name``（把函数名小写后当节点身份）。
代价写在 README 与 ``limitations`` 里：**跨文件的同名函数被合并成一个节点**
⇒ 内核上 ``cross_file.ambiguous`` 占到 **5,149,101 / 7,060,966 = 72.9%**，
而最大的「调用环」有 **37,775 个成员** —— 那**不是**一个真环，
是名字级合并造出来的**假阳性**。

R88 加了第二种：``definition-site``，并把它设为**默认**。它把节点拆成
「定义落点」，规则逐条如下（**每一条都要能说出它属于哪种「判得出来」**）：

  * **源（调用者）**：调用点所在文件 + 调用者名字。函数的**体**在哪个文件，
    它的定义就在哪个文件 —— 所以「调用点所在文件」**通常就是**它的定义文件；
    这一条会在 ``func_index`` 里**核对**，核不上的一律标成 ``K_SITE``
    （调用点文件已知、但不是定义落点），**不冒充定义落点**。
  * **目标（被调者）**：``func_index[名字]`` 有**恰好一份**定义 ⇒ 用那份的
    落点；**一份都没有** ⇒ ``K_EXT``；**多于一份** ⇒ ``K_AMB``，
    **保持名字级并显式标记** —— 「不猜」。

⚠ **为什么「多于一份」不给它挑一份**：`frontends/ir.py::resolve_calls` 对
同名多定义是**扇出**（每个定义各产一条边），而边里**只带函数名、不带命中的
那份定义的落点**（它取的是 ``h["func"]["name"]``，**没有取** ``h["file"]["rel"]``）。
⇒ 在边这一层，**哪一份定义的信息已经丢了**。要恢复它必须改边元组，而
``EDGE_ARITY`` **不存在**（本仓只有 ``UNRESOLVED_ARITY = 3``）——
即「边的形状」是一个**没有对手方**的契约。R88 **刻意不动它**（见复盘）。

⚠ **顺带补上一个从未被写下的口径**：因为扇出，``edges_total`` **不是**
「调用点条数」，而是「(调用点 × 命中定义) 对」的条数。这条以前没写在任何地方。

三条口径必须并列陈述（不许同化）
================================
1. **节点身份**：``identity`` 字段给出**用的是哪一种**（写成字面量常量，
   不许静默换掉 ⇒ 见 ``IDENTITY_NAME`` / ``IDENTITY_DEFSITE``）。
2. **未解析调用不在图里** —— 它们没有 callee 节点。它们**不是**「没有关系」，
   而是「这条关系没解析出来」。计数并列给出（``unresolved_total``）。
3. **截断显式** —— 见上。

顺带修掉的一个真缺陷（R88）
==========================
``hub_of`` 是「不给 ``--callgraph-focus`` 时的默认根」。旧实现（在 ``matlabc.py``
里叫 ``_callrel_hub``）取「枢纽分数 2×扇入 + 扇出」的 argmax —— 扇入权重是扇出的
**两倍**，于是一个**只被调、不调人**的节点会稳赢，而默认子图按 ``callee`` 方向
展开 ⇒ 输出 ``1 节点 / 0 边``，读起来像「这里没有关系」。
实测（``linux-6.19.14/init``）：旧口径选 ``error``（扇入 26 / 出边 **0**）⇒ `1/0`；
收窄到「候选必须是**有出边**的节点」后选 ``unpack_to_rootfs``（扇入 10 / 扇出 12）
⇒ 真子图。⇒ 判据不是「看着更顺眼」，是**默认输出非空**这条可实测的性质。

R89：节点身份口径再进一步 —— `definition-site-local`（**默认**）
====================================================================
R88 把身份从「名字」换到「定义落点」，代价是**同名多定义的被调者一律落 K_AMB
汇点**（内核 5,149,101 条 = 72.9%），并把「经过它的环会漏报」写进 limitations。
R89 要做的是**把其中判得出来的那部分收回来**，判不出来的照样留汇点。

判据是 C 的**翻译单元可见性**，两级（都不是新发明的规则，是 C 本来就有的）：

    rung 1  **同文件优先**：被调名多份定义里**恰一份**落在调用者文件里 ⇒ 用它。
            理由：定义就在这个文件里，谁包含这个文件都成立（`static` 更是不
            可能从别的 TU 可见）。
    rung 2  **包含闭包**：调用者文件的 `#include` 闭包里**恰一份**候选 ⇒ 用它。
            理由：头文件被包含进来就是 TU 的一部分。

rung 2 必须做成**三明治**（这是量具逼出来的，不是设计洁癖）
--------------------------------------------------------
include 解析是**按 basename** 做的（P90 既有口径）⇒ 闭包有两个版本：
`closure_under`（只走 basename 唯一的 include）⊆ 真 TU ⊆ `closure_over`
（多命中全部并入）。只用 `over` 判「恰好一个可见」**不成立**：假包含能把计数从
0 抬到 1。所以判据是

    vis_under == vis_over == {同一份候选}

真 TU 的可见集合夹在两者之间 ⇒ 只能是那一份。**纯集合论，与语料无关。**
另有作用域判据：调用点落在**头文件**里时，TU 由包含者决定 ⇒ rung 2
**只对 TU 根**（`.c/.cc/.cpp/.cxx`）成立（rung 1 没有这个问题）。

实测（`_r89/measure_sandwich.py`，`linux-6.19.14` 的 8 区域 / 3,927 文件 /
68,030 边）：歧义 23,957 条 ⇒ rung1 2,370（9.9%）+ rung2 2,034（8.5%）
⇒ **救回 18.4%**，残余 19,553 条（81.6%，其中调用点在头文件里的 3,558 条）。

⚠ **R88 §7① 的预期（「`ambiguous` 会塌下去」）被这三支量具当场否证** ——
松判据（只用 over 闭包）读到 31.2%，三明治之后只剩 18.4%，而残余的 81.6% 不是
「还没修」，是**这一层判不出来**：同名宏（实测 CROSS 89 条边）、函数指针、
条件编译、语料子集外的定义。**不许靠猜把这部分刷小。**

零第三方依赖 / Python 3.6.5 兼容 / 无全局可变状态。
"""

# 形状版本：键的增删改都要 +1（下游按它判断兼容性）。
#
# R88：1 → 2。理由**不是内容变了**（键集合没动），而是焦点子图**多了一个键**
# ``focus_candidates``，而它是**有意义的**：名字级口径下一个名字恒等于一个
# 节点 ⇒ 候选恒为 1；定义落点口径下一个名字可以映到多个节点 ⇒ 它必须被报出来
# （否则 ``--callgraph-focus memcpy`` 会在若干个 memcpy 里**静默挑一个**）。
# R91：3 → 4。`focus_subgraph.truncated` 新增三个键（`max_edges` /
# `hit_edge_cap` / `edges_total`）。它们是**条件键**（只在设了边上限的子图上
# 出现），但「条件出现」正是下游最需要被提前告知的形态 —— 同一个版本号下键集
# 随调用参数变，恰恰是版本号要防的歧义。
# ⚠ 代价写清楚：这一行让**默认产物**（不给任何新开关）与 R90 **不再逐字节
# 相同** —— 差恰好是这一个字符（`3` → `4`）。所以 R91 的红线就地换成更强的
# 那条：「差必须**逐字节定位**在 version 字段上，其余一个字节都不许动」
# （装置 `_r91/verify_default_byteeq.py` 两向钉住）。
CALLREL_VERSION = 4

# 节点身份口径。写成常量是为了让「口径被默默换掉」可被判据看见。
IDENTITY_NAME = "callee-name"
IDENTITY_DEFSITE = "definition-site"

# R88：默认改成定义落点。老口径**保留且可复现**（``--callgraph-identity callee-name``）。
# R89：默认再进一步 —— 定义落点 **+ 翻译单元可见性优先**。两个老口径都保留。
IDENTITY_LOCAL = "definition-site-local"

# 默认口径。`definition-site-local` 在**没有同名多定义**的语料上与
# `definition-site` 逐位相同（判据 F10d 钉的就是这条：不许无中生有）。
DEFAULT_IDENTITY = IDENTITY_LOCAL
IDENTITIES = (IDENTITY_NAME, IDENTITY_DEFSITE, IDENTITY_LOCAL)

# 证据档：本模块的读数全部来自**已经解析出的边**，是读出来的不是推出来的。
EVIDENCE_OBSERVED = "observed"

# 顶层有界投影的默认上限。与 MATLAB 侧首页力导向图（max_nodes=1200）**不同**
# 是刻意的：那边是交互式 SVG，这边是给人读的文本/结构化产物。
DEFAULT_TOP_N = 30
DEFAULT_MAX_CYCLES = 20
DEFAULT_MAX_NODES = 300
DEFAULT_DEPTH = 2

# ── 节点键 ──────────────────────────────────────────────────────────────────
# 分隔符用 U+001F（Unit Separator）：它在文本里可见、在文件名里**不合法**，
# 所以「键 → (种类, 落点, 名字)」的切分不会因为文件名里带分隔符而错位。
SEP = "\x1f"

K_DEF = "d"    # 定义落点已知
K_AMB = "a"    # 同名多定义 —— 不猜
K_EXT = "x"    # 找不到定义
K_SITE = "s"   # 调用点文件已知，但它**不是**该名字的定义文件

AMBIG_MARK = "<同名多定义>"
EXTERN_MARK = "<无定义>"
# K_SITE 的**可见标记**。为什么必须有：节点的身份是 `(kind, rel, name)`，
# 但 `name @ file` 这种显示名对 K_DEF 与 K_SITE **是同一个串** ⇒ `kind` 这一维
# 在产物上**看不见**，而「看不见的区别 = 迟早分叉」（DOT 的节点 id 也会撞）。
# ⚠ 实测（`_r88/probe_defsite_real.py`，7 份语料 / 68,030+ 条边）：K_SITE
#   **当前 C 前端上取不到** —— `call_sites_of_files` 取「被解析文件里的包围函数」，
#   而它必然已用同一个 `rel` 注册进 `func_index` ⇒ 源侧恒满足 `rel ∈ defset`。
#   所以这个标记今天改不动任何读数；它的作用是让**万一**出现的 K_SITE 能被看见。
SITE_MARK = "<非定义落点>"

# ── R89：解析阶梯 ───────────────────────────────────────────────────────────
# 这五个名字是**产物里的键**（`resolution` 块），不是内部枚举 —— 改名字就是改
# 产物形状（CALLREL_VERSION 要跟着涨）。
R_UNIQ = "unique"        # 名字只有一份定义（观测）
R_SAME = "same_file"     # 多份定义、恰一份在调用者文件里（**推导**：TU 作用域）
R_INC = "include"        # 多份定义、恰一份在调用者 include 闭包里（**推导**）
R_AMB = "ambiguous"      # 多份定义、判不出是哪一份（**不猜**）
R_EXT = "external"       # 一份定义都没有

# 阶梯只在**这些语言**上启用。为什么必须按语言分：
# C 的可见性规则是「TU = 文件 + 其 include」，句法与语义都给得出结论；
# Python / JS 的模块绑定可以被 import / 重赋值在**运行时**改掉，
# 「同名就在同文件」只是**近似** —— 近似一旦冒充结论就会造出**假环**，
# 那正是 R88 要修的东西。⇒ 宁可少报（回落 K_AMB），不猜。
LOCAL_SCOPE_LANGS = ("c",)

# 只有翻译单元的**根**才谈得上「它的 include 闭包就是它的 TU」。
TU_ROOT_EXTS = (".c", ".cc", ".cpp", ".cxx")

# 闭包 BFS 的节点上限。**超限即判不出**（回落 K_AMB 并计数），
# 绝不用截断后的集合下结论 —— 截断把「可见」判成「不可见」是**错报**的方向。
# 实测（`_r89/` 量具，CROSS 3,927 文件）：闭包 p50=684 / p90=701 / max=784，
# 上限 65536 有 ~80 倍余量。
CLOSURE_CAP = 65536
# 闭包缓存条数。边表是**按文件产出**的（`call_sites_of_files` 的顺序）⇒
# 相邻的边几乎总在同一个调用者文件里，小缓存命中率极高而内存有界。
#
# ⚠ **满了必须淘汰**（R89j 修）：写 `if len(cache) < CLOSURE_CACHE:` 就是
# 「只记最早 8 个起点、之后再也不写」—— 缓存**永远**停在头部那 8 个文件上，
# 第 9 个起点的闭包**每条边都重算**。R89 实测代价：内核整树 `--callgraph`
# 一步 **61.4 分钟未跑完**（基础分析只用 535 s），而**所有读数一个都没变**
# ⇒ 没有任何正确性判据会红。现在满则**整体清空**：同一文件的下一条边立刻
# 把它填回来 ⇒ 每个文件只算两次（under + over），内存仍有界。
# 这条不变量由 `local_scope.closure_computed == 2 × rung2_files` 守着。
CLOSURE_CACHE = 8

# `under` 图的**唯一性口径**（R89k）：按「这个 basename 解析到**几个**目标文件」
# 判，而不是按「有几条 include 行指过来」。前者是 include 解析本身的**分辨力**，
# 后者会把「被很多地方包含的头」（内核里**最常见**的形状，如 `kernel.h`）误判成
# 不确定 ⇒ `under` 几乎空掉 ⇒ 三明治恒失败。口径名进 `local_scope.under_basis`。
UNDER_BASIS = "unique-basename-target"


def _defsite_family(identity):
    '''口径是否属于**落点族**（键 = ``kind + SEP + rel + SEP + name``）。

    **唯一判据，只此一份。** 为什么必须抽出来：R88 时期四处写的是
    ``identity != IDENTITY_DEFSITE`` —— 那是**二元**判断，加入第三种口径
    （`definition-site-local`）时新口径会**静静**落进「名字级」分支：
    节点名印成**内部键**（带 U+001F）、``_name_of`` 拿不到函数名 ⇒
    ``--callgraph-focus`` 匹配不上任何节点 ⇒ 默认子图退化。
    R89 实测代价：一条补丁让门里 **F7b/F7c/F7d/F9e 四条同时红**
    （这正是「口径类缺陷所有读数一起错且都自洽」的现场）。
    '''
    return identity in (IDENTITY_DEFSITE, IDENTITY_LOCAL)


KIND_LABEL = {
    K_DEF: "定义落点",
    K_SITE: "调用点文件（非定义落点）",
    K_AMB: "同名多定义（不猜）",
    K_EXT: "无定义",
}


def _norm(name):
    """名字的归一：小写。空名归一到空串（不是 None，避免 dict 键类型漂移）。"""
    return (name or "").lower()


def _home(func_index, name):
    """函数的定义落点。返回 ``(rel, line, n_defs)``。

    ``n_defs`` 是**定义条数** —— >1 表示同名多份定义，此时 ``rel`` / ``line``
    取**第一条**但调用方必须知道它是有歧义的（沿用 R86-2 的「不猜」纪律：
    能判就判、判不了就并列陈述，绝不把第一份当成唯一份）。
    """
    if not func_index:
        return (None, None, 0)
    hits = func_index.get(_norm(name))
    if not hits:
        return (None, None, 0)
    h = hits[0]
    pf = h.get("file") or {}
    fn = h.get("func") or {}
    return (pf.get("rel"), fn.get("line"), len(hits))


def _ext_of(rel):
    """rel 的扩展名（小写，带点）。rel 一律是正斜杠形状（`_rel_of` 归一过）。"""
    if not rel:
        return ""
    i = rel.rfind("/")
    name = rel[i + 1:] if i >= 0 else rel
    j = name.rfind(".")
    return name[j:].lower() if j > 0 else ""


def _base_of(rel):
    """rel 的文件名（不含目录）。"""
    if not rel:
        return ""
    i = rel.rfind("/")
    return rel[i + 1:] if i >= 0 else rel


def _sym(func_index, name):
    """名字 → ``(kind, rel, line, ndef)``。**一个量一份实现**。

    R89：本函数现在只是 `_resolve` 的**无作用域视图**（`scope=None`）——
    保留它是为了让「名字级视图」有一个名字，而不是第二份判据。
    """
    k, rel, ln, nd = _resolve(func_index, name, None, None)[:4]
    return (k, rel, ln, nd)


def _resolve(func_index, name, rel, scope=None):
    """名字 → ``(kind, drel, line, ndef, rung)``。**R89 的判据本体，只此一份。**

    ``scope is None`` ⇒ 纯名字级视图（= R88 的 `definition-site` 行为，逐位可复现）；
    给了 scope 且 `scope["applied"]` ⇒ 走两级阶梯（见模块 docstring）。

    ⚠ 返回的 `rung` 同时给「节点映射」与「cross_file 分桶」用 ——
    两处若各判一次，同一个量必然分叉（R87 的教训）。
    """
    hits = (func_index or {}).get(_norm(name))
    if not hits:
        return (K_EXT, None, None, 0, R_EXT)
    n = len(hits)
    h0 = hits[0]
    pf0 = h0.get("file") or {}
    fn0 = h0.get("func") or {}
    if n == 1:
        return (K_DEF, pf0.get("rel"), fn0.get("line"), 1, R_UNIQ)
    if scope is not None and scope.get("applied") and rel:
        # ---- rung 1：同文件优先 ----
        # 「恰一份」而不是「至少一份」：同文件里同名定义 ≥2 份（`#ifdef` 双分支）
        # 时同样判不出来 —— 判据不许因为「反正在同文件」就松口。
        same = [h for h in hits if ((h.get("file") or {}).get("rel")) == rel]
        if len(same) == 1:
            f = same[0].get("func") or {}
            return (K_DEF, rel, f.get("line"), n, R_SAME)
        # ---- rung 2：包含闭包（**只对 TU 根成立**）----
        if _ext_of(rel) not in TU_ROOT_EXTS:
            scope["header"] = scope.get("header", 0) + 1
        elif scope.get("under") is not None:
            where = [((h.get("file") or {}).get("rel")) for h in hits]
            # 第二级的**代价**也要可观测：算过多少个不同调用者文件（R89j）。
            scope["r2"].add(rel)
            cu, c1 = _closure(rel, scope["under"], scope["cu"], scope["cap"],
                              scope)
            co, c2 = _closure(rel, scope["over"], scope["co"], scope["cap"],
                              scope)
            if c1 or c2:
                scope["capped"] = scope.get("capped", 0) + 1
            elif cu is not None and co is not None:
                vu = [w for w in where if w and w in cu]
                vo = [w for w in where if w and w in co]
                if len(vu) == 1 and len(vo) == 1 and vu == vo:
                    for h in hits:
                        if ((h.get("file") or {}).get("rel")) == vu[0]:
                            f = h.get("func") or {}
                            return (K_DEF, vu[0], f.get("line"), n, R_INC)
    return (K_AMB, pf0.get("rel"), fn0.get("line"), n, R_AMB)


def _closure(start, graph, cache, cap, stats=None):
    """从 ``start`` 出发在 include 图上可达的文件集合（含 start）。

    返回 ``(集合_or_None, 是否超限)``。**超限返回 None** —— 调用方必须把它当成
    「判不出」，不许拿截断集合当结论（截断的方向是**错报**）。

    缓存是**小容量**的（`CLOSURE_CACHE`）：边表按文件产出 ⇒ 相邻边几乎同一个
    调用者文件，小缓存就够；闭包本身在语料上可达数百项，无上限缓存会白吃
    几百 MB（内核那本账峰值已经 13 GB，这份内存是**可以不要**的）。
    """
    got = cache.get(start)
    if got is not None:
        return (got, False)
    seen = set()
    stack = [start]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        if len(seen) > cap:
            return (None, True)
        for nxt in graph.get(cur, ()):
            if nxt not in seen:
                stack.append(nxt)
    # ⚠ **满则清空**，不许「满了就不写」—— 后者会让缓存永远停在最早那 8 个
    # 起点上，第 9 个起点的闭包每条边都重算（R89j 内核实测 61.4 分钟未跑完）。
    if len(cache) >= CLOSURE_CACHE:
        cache.clear()
    cache[start] = seen
    if stats is not None:
        stats["computed"] = int(stats.get("computed") or 0) + 1
        stats["visits"] = int(stats.get("visits") or 0) + len(seen)
    return (seen, False)


def include_graphs(include_edges):
    """``model["include_edges"]`` → **两级** include 图 ``(under, over)``。

    `include_edges` 的形状是 ``[(include_方_rel, 头名, 解析到的_rel 或 None)]``
    （P90）。解析是**按 basename** 的 ⇒ 同名的头文件可能命中多份：

    * ``over``  所有能解析到文件的 include（多命中**全部**并入）—— 过近似；
    * ``under`` 只保留「basename 只解析到**一个**目标文件」的那些 —— 欠近似。

    真 TU 夹在两者之间，这正是三明治判据成立的理由。

    ⚠ **唯一性判据是「解析目标有几个」，不是「include 行有几条」**（R89k 修）。
    原实现按行计数 ⇒ 只要某个头被 ≥2 处包含（`kernel.h` / `list.h` 这类
    **最常见**的形状）就整条被丢出 `under` ⇒ 三明治在主战场上**恒失败**。
    CROSS 档实测：按行计数只留 **606 / 28,333** 条 include 边进 `under`，
    按目标数是 **7,823** 条；后果是第二级在那个语料上**一条也判不出来**
    （引擎 `resolution.include = 0`，独立量具测出的潜力是 **2,034**）。
    """
    rows = []
    # basename → **解析到的文件集合**（不是「有几条 include 行指过来」）。
    targets = {}
    for row in (include_edges or []):
        if not row or len(row) < 3 or not row[2]:
            continue
        src, dst = row[0], row[2]
        rows.append((src, dst))
        targets.setdefault(_base_of(dst).lower(), set()).add(dst)
    under = {}
    over = {}
    for src, dst in rows:
        over.setdefault(src, set()).add(dst)
        if len(targets.get(_base_of(dst).lower()) or ()) == 1:
            under.setdefault(src, set()).add(dst)
    return (under, over)


def scope_of(identity, lang, include_edges):
    """R89：**作用域对象**（`None` 表示不走阶梯 ⇒ 纯名字级视图）。

    启用条件只有两条，都写在这里（**一处实现**，不许在调用点各判一次）：
      * 口径是 `definition-site-local`；
      * 语言在 `LOCAL_SCOPE_LANGS` 里。

    ``include_edges`` 不给 ⇒ **只剩 rung 1**（这件事会**如实报在**
    `local_scope.rungs` / `include_map` 里 —— 静默少一级是「没听懂却假装听懂」）。
    ⚠ 「给了但是空的 list」与「没给（None）」**必须分得开**：前者是「这份语料
    真的没有 include」（C 模型恒提供该键，可能为空），后者才是「调用方没传」。
    """
    lg = (lang or "").lower()
    applied = (identity == IDENTITY_LOCAL and lg in LOCAL_SCOPE_LANGS)
    sc = {"applied": bool(applied), "lang": lg, "under": None, "over": None,
          "cu": {}, "co": {}, "cap": CLOSURE_CAP, "capped": 0,
          "header": 0, "r2": set(), "computed": 0, "visits": 0}
    if applied and include_edges is not None:
        under, over = include_graphs(include_edges)
        sc["under"] = under
        sc["over"] = over
    return sc


def scope_report(sc):
    """作用域 → 产物里那块**自称参数**（口径、语言、用到哪几级、上限、诊断计数）。"""
    if sc is None:
        sc = {"applied": False, "lang": "", "under": None, "capped": 0,
              "header": 0, "cap": CLOSURE_CAP, "r2": set(), "computed": 0,
              "visits": 0}
    rungs = []
    if sc.get("applied"):
        rungs.append("same-file")
        if sc.get("under") is not None:
            rungs.append("include-closure")
    return {
        "applied": bool(sc.get("applied")),
        "lang": sc.get("lang") or "",
        "allowed_langs": list(LOCAL_SCOPE_LANGS),
        "include_map": sc.get("under") is not None,
        # R89k：`under` 的**唯一性口径**（产物自称，不靠读代码猜）
        "under_basis": UNDER_BASIS,
        "rungs": rungs,
        "closure_cap": sc.get("cap"),
        "closure_capped": int(sc.get("capped") or 0),
        "header_callers": int(sc.get("header") or 0),
        # R89j：第二级的**代价**（产物自称）。`closure_computed` 是**算了几次**
        # 闭包（不是几条边）⇒ 缓存一退化它就涨，「每个文件只算两次」当场破功。
        "rung2_files": len(sc.get("r2") or ()),
        "closure_computed": int(sc.get("computed") or 0),
        "closure_visits": int(sc.get("visits") or 0),
    }


def _def_at(func_index, name, rel):
    """名字在**指定文件**里的那一份定义：``(line, ndef, matched)``。

    ``ndef`` = 该名字的定义**总数**（读者由此看出这是同名多定义中的一份）。
    ⚠ 不许用 ``_sym`` 代劳 —— 它只取 ``hits[0]``，会把两个不同落点的节点
    都指向第一份定义（R88 探针 A3 抓的就是这个）。
    """
    hits = (func_index or {}).get(_norm(name)) or []
    ndef = len(hits)
    if not rel:
        return (None, ndef, False)
    for h in hits:
        pf = h.get("file") or {}
        if pf.get("rel") == rel:
            fn = h.get("func") or {}
            return (fn.get("line"), ndef, True)
    return (None, ndef, False)


def _defset(func_index, name, cache):
    """名字的全部定义文件（集合）。带缓存 —— 内核上这条会被问 7M 次。"""
    k = _norm(name)
    s = cache.get(k)
    if s is None:
        s = set()
        for h in (func_index or {}).get(k) or []:
            pf = h.get("file") or {}
            r = pf.get("rel")
            if r:
                s.add(r)
        cache[k] = s
    return s


def _key(kind, rel, name):
    return "%s%s%s%s%s" % (kind, SEP, rel or "", SEP, _norm(name))


def _key_parts(key):
    kind, _, rest = key.partition(SEP)
    rel, _, nm = rest.partition(SEP)
    return (kind, rel or None, nm)


def _edge_res(e, func_index, identity, caches=None, scope=None):
    """边 → ``(源键, 目标键, rung, 目标落点)``。``identity`` 决定**节点身份口径**。

    这是**唯一**的「边的两端各是谁」判定点 —— 顶层投影与焦点子图都从这里取，
    不许各写一份（R87 的教训：同一个量两份实现必然分叉）。

    R89 让它**多返回两个量**（`rung`、目标落点），理由是同一个：`cross_file` 分桶
    必须与节点映射用**同一次**判定结果。若分桶自己再判一次名字歧义，
    就会出现「节点已经拆到某文件、桶里却还算歧义」这种自相矛盾的产物。
    """
    caller = e[0]
    callee = e[1]
    rel = e[3]
    kind, drel, _ln, _nd, rung = _resolve(func_index, callee, rel, scope)
    if identity == IDENTITY_NAME:
        # 老口径：名字即身份。逐字节复现 R86/R87 的读数（rung 照给，供分桶）。
        return (_norm(caller), _norm(callee), rung, drel)

    dcache = caches[0] if caches is not None else {}
    # 源：调用者。调用点所在文件**通常就是**它的定义文件；核不上就标 K_SITE。
    # （走到这里只剩两个落点口径 —— 名字级那支在上面已经返回了。）
    if rel and rel in _defset(func_index, caller, dcache):
        src = _key(K_DEF, rel, caller)
    else:
        src = _key(K_SITE, rel, caller)
    # 目标：被调者。
    if kind == K_DEF:
        dst = _key(K_DEF, drel, callee)
    elif kind == K_AMB:
        dst = _key(K_AMB, None, callee)
    else:
        dst = _key(K_EXT, None, callee)
    return (src, dst, rung, drel)


def _edge_nodes(e, func_index, identity, caches=None, scope=None):
    """``(源键, 目标键)`` —— `_edge_res` 的两元投影（老调用点的兼容面）。"""
    a, b, _rung, _drel = _edge_res(e, func_index, identity, caches, scope)
    return (a, b)


def _display(key, identity):
    """节点键 → **可读且唯一的**节点名。名字级口径下就是键本身（老行为）。"""
    if not _defsite_family(identity):
        return key
    kind, rel, nm = _key_parts(key)
    if kind == K_DEF:
        return ("%s @ %s" % (nm, rel)) if rel else nm
    if kind == K_SITE:
        return ("%s @ %s %s" % (nm, rel, SITE_MARK)) if rel else nm
    if kind == K_AMB:
        return "%s @ %s" % (nm, AMBIG_MARK)
    return "%s @ %s" % (nm, EXTERN_MARK)


def _name_of(key, identity):
    if not _defsite_family(identity):
        return key
    return _key_parts(key)[2]


def _focus_label(s, identity):
    """``focus`` 这一栏的显示名。

    ``s`` 可能是**节点键**（内部分隔符 U+001F 在，来自 ``hub_of`` / 内部消歧），
    也可能是**用户敲的名字**（没有分隔符）。前者要转成可读形状，后者**原样回显**
    —— 名字不在图里时更应该让用户看到他敲的是什么，而不是把内部键形状漏出去。
    名字级口径下两种情形都返回 ``s`` 本身 ⇒ 老读数逐字节不变。
    """
    if not _defsite_family(identity):
        return s
    return _display(s, identity) if isinstance(s, str) and SEP in s else s


def _nodeinfo(key, identity, func_index):
    """节点键 → ``{"name","file","line","defs"}``（**字段集合与老口径一致**）。"""
    if not _defsite_family(identity):
        rel, line, ndef = _home(func_index, key)
        return {"name": key, "file": rel, "line": line, "defs": ndef}
    kind, rel, nm = _key_parts(key)
    if kind == K_AMB:
        # 汇点：**不猜是哪一份定义** ⇒ file/line 一律 None，只报定义**条数**。
        _k, _r, _line, ndef = _sym(func_index, nm)
        return {"name": _display(key, identity), "file": None, "line": None,
                "defs": ndef}
    if kind == K_DEF:
        # ``file`` 取自**键**（键就是这个节点的身份，不是反查来的）；
        # ``line`` 取该名字在**这个文件**里的那一份定义；``defs`` 是该名字的定义总数。
        line, ndef, _matched = _def_at(func_index, nm, rel)
        return {"name": _display(key, identity), "file": rel, "line": line,
                "defs": ndef}
    if kind == K_SITE:
        return {"name": _display(key, identity), "file": rel, "line": None,
                "defs": len(_defset(func_index, nm, {}))}
    return {"name": _display(key, identity), "file": None, "line": None,
            "defs": 0}


def _dir_of(rel):
    if not rel:
        return None
    i = rel.rfind("/")
    if i < 0:
        i = rel.rfind("\\")
    return rel[:i] if i >= 0 else ""


# ── 邻接表（CSR）────────────────────────────────────────────────────────────
def build_csr(pairs):
    """把 ``[(源键, 目标键)]`` 压成 CSR。

    为什么不用 ``dict[str, list]``：内核规模下 7.06M 条边，Python 的
    ``list`` 每个元素一个指针 + int 对象，实测要多占数百 MB；而 ``array('i')``
    是裸 4 字节。分析本身峰值就到过 13,135.4 MB，这里**不再加一份 O(E) 的
    Python 对象层**是硬要求。

    返回 ``(ids, names, head, adj)``：
        ids    : 键 -> 节点号
        names  : 节点号 -> 键（取首次出现的那份）
        head   : 长度 n+1 的偏移表（CSR 标准形状）
        adj    : 长度 E 的扁平后继表（**含重边** —— 重复调用是事实，不去重）
    """
    from array import array

    ids = {}
    names = []
    src = array("i")
    dst = array("i")
    for a, b in pairs:
        ka = ids.get(a)
        if ka is None:
            ka = len(names)
            ids[a] = ka
            names.append(a)
        kb = ids.get(b)
        if kb is None:
            kb = len(names)
            ids[b] = kb
            names.append(b)
        src.append(ka)
        dst.append(kb)
    n = len(names)
    deg = array("i", bytes(4 * n))
    for k in src:
        deg[k] += 1
    head = array("i", bytes(4 * (n + 1)))
    acc = 0
    for i in range(n):
        head[i] = acc
        acc += deg[i]
    head[n] = acc
    fill = array("i", head[:n])
    adj = array("i", bytes(4 * len(src)))
    for i in range(len(src)):
        k = src[i]
        adj[fill[k]] = dst[i]
        fill[k] += 1
    return (ids, names, head, adj)


# ── 强连通分量（迭代 Tarjan）────────────────────────────────────────────────
def strongly_connected(names, head, adj, max_cycles=DEFAULT_MAX_CYCLES,
                       label=None):
    """节点级 SCC（size > 1 才算环）。**迭代**实现，不用递归。

    为什么必须迭代：内核语料 645,111 个节点，递归 Tarjan 的深度会跟最长简单
    路径走 —— 那是个不受控的量，Python 默认递归上限 1000，一撞就是
    ``RecursionError``（而 `parse()` 那一层的 except 接不住它）。

    ``label`` 把节点键映成**可读名**（定义落点口径下键里带着 U+001F）。
    不给则原样输出 —— 名字级口径因此逐字节复现老读数。

    返回 ``(cycles, stats)``：
        cycles —— ``[{"size": k, "members": [名字, ...]}]``，按 (size, 名字) 降序
        stats  —— ``{"components": 全部环数, "nodes_in_cycles": 环内节点总数,
                     "biggest": 最大环大小}``
    """
    from array import array

    n = len(names)
    index = array("i", [-1]) * n if n else array("i")
    low = array("i", bytes(4 * n))
    onstk = bytearray(n)
    stk = []
    idx = 0
    comps = []
    for root in range(n):
        if index[root] != -1:
            continue
        work = [(root, head[root])]
        while work:
            v, pi = work[-1]
            if pi == head[v]:
                index[v] = idx
                low[v] = idx
                idx += 1
                stk.append(v)
                onstk[v] = 1
            moved = False
            p = pi
            end = head[v + 1]
            while p < end:
                w = adj[p]
                if index[w] == -1:
                    work[-1] = (v, p + 1)
                    work.append((w, head[w]))
                    moved = True
                    break
                if onstk[w] and index[w] < low[v]:
                    low[v] = index[w]
                p += 1
            if moved:
                continue
            if low[v] == index[v]:
                comp = []
                while True:
                    w = stk.pop()
                    onstk[w] = 0
                    comp.append(w)
                    if w == v:
                        break
                if len(comp) > 1:
                    comps.append(comp)
            work.pop()
            if work:
                u = work[-1][0]
                if low[v] < low[u]:
                    low[u] = low[v]

    _lab = label if label is not None else (lambda s: s)
    cycles = []
    nodes_in = 0
    biggest = 0
    for comp in comps:
        members = sorted(_lab(names[k]) for k in comp)
        cycles.append({"size": len(members), "members": members})
        nodes_in += len(members)
        if len(members) > biggest:
            biggest = len(members)
    cycles.sort(key=lambda c: (-c["size"], c["members"][0]))
    stats = {"components": len(cycles), "nodes_in_cycles": nodes_in,
             "biggest": biggest}
    return (cycles[:max_cycles], stats)


# ── 顶层有界投影 ────────────────────────────────────────────────────────────
def call_relations(edges, func_index=None, top_n=DEFAULT_TOP_N,
                   max_cycles=DEFAULT_MAX_CYCLES, with_cycles=True,
                   unresolved_total=0, identity=DEFAULT_IDENTITY, lang=None,
                   include_edges=None):
    """产出**有界**调用关系投影。规模无关，输出恒为 KB 级。

    ``edges``            ``[(caller, callee, line, rel)]``（与统一 IR 同源）
    ``func_index``       ``{小写名: [{"file": pf, "func": fn}]}``，用于回指文件/行
    ``unresolved_total`` 未解析调用条数（**不进图**，但要并列报出来）
    ``identity``         ``callee-name`` | ``definition-site`` |
                         ``definition-site-local``（默认第三个，R89）
    ``lang``             语料语言。阶梯只在 `LOCAL_SCOPE_LANGS` 上启用 ——
                         **语言是启用条件的一部分**，不许默认「都是 C」。
    ``include_edges``    ``model["include_edges"]``（P90）。不给 ⇒ 阶梯只剩
                         rung 1，且这件事会**如实报在** `local_scope` 里。
    """
    n_edges = len(edges)
    dfcache = {}
    scope = scope_of(identity, lang, include_edges)

    fan_out = {}
    fan_in = {}
    cross = {"internal": 0, "cross": 0, "ambiguous": 0, "unknown": 0}
    dir_cross = {"internal": 0, "cross": 0, "unknown": 0}
    resolution = {R_UNIQ: 0, R_SAME: 0, R_INC: 0, R_AMB: 0, R_EXT: 0}
    pairs = []
    for e in edges:
        a, b, rung, drel = _edge_res(e, func_index, identity, (dfcache,), scope)
        pairs.append((a, b))
        fan_out[a] = fan_out.get(a, 0) + 1
        fan_in[b] = fan_in.get(b, 0) + 1
        rel = e[3]
        resolution[rung] += 1
        # R89：分桶用的落点**就是**节点映射那一次判定的结果（不许各判一次）。
        if rung == R_EXT:
            cross["unknown"] += 1
        elif rung == R_AMB:
            cross["ambiguous"] += 1
        elif drel == rel:
            cross["internal"] += 1
        else:
            cross["cross"] += 1
        # 目录级只看**判得出来的**：无定义不猜；判不出的同名多定义同样不进
        # 目录统计 —— 宁可少报，不可错报。
        if rung == R_EXT:
            dir_cross["unknown"] += 1
        elif rung != R_AMB:
            if _dir_of(rel) == _dir_of(drel):
                dir_cross["internal"] += 1
            else:
                dir_cross["cross"] += 1

    def _rows(counter, key_name):
        rows = []
        for key, k in counter.items():
            d = _nodeinfo(key, identity, func_index)
            rows.append({key_name: d["name"], "n": k,
                         "file": d["file"], "line": d["line"], "defs": d["defs"]})
        # 定义落点口径下一个名字可以出两行（不同落点）⇒ 必须给一个**只看内容**的
        # 次级键（R88 §4p-4：并列判据不许依赖遍历顺序）。名字级口径下名字唯一
        # ⇒ 次级键从不生效 ⇒ 老读数逐字节不变。
        rows.sort(key=lambda r: (-r["n"], r[key_name], r["file"] or ""))
        return rows

    fin = _rows(fan_in, "callee")
    fout = _rows(fan_out, "caller")

    cycles = None
    cstats = {"components": None, "nodes_in_cycles": None, "biggest": None}
    n_nodes = len(set(list(fan_in) + list(fan_out)))
    if with_cycles:
        # CSR 只在**真的要算环**的时候建 —— 它是一份 O(E) 的额外结构，
        # 而「只报度数结构」这一档（KB 级输出）不该为它付内存。
        _ids, names, head, adj = build_csr(pairs)
        n_nodes = len(names)
        cycles, cstats = strongly_connected(
            names, head, adj, max_cycles=max_cycles,
            label=lambda s: _display(s, identity))

    tr = {
        "fan_in_shown": min(top_n, len(fin)),
        "fan_in_total": len(fin),
        "fan_out_shown": min(top_n, len(fout)),
        "fan_out_total": len(fout),
        "cycles_shown": (min(max_cycles, cstats["components"])
                         if with_cycles else None),
        "cycles_total": (cstats["components"] if with_cycles else None),
        "nodes_total": n_nodes,
        "edges_total": n_edges,
        "reason": ("顶层恒为有界投影 —— 全量关系在内核规模下是 GB 级。"
                   "要逐点看完整关系，用 --callgraph-focus <名字> 展开；"
                   "本块只回答「结构的形状」，不回答「第 N 条边是什么」。"),
    }
    return {
        "version": CALLREL_VERSION,
        "identity": identity,
        "evidence_kind": EVIDENCE_OBSERVED,
        # R89：**解析阶梯**的逐档计数。四（五）档之和恒等于 edges_total ——
        # 这条恒等式是「救回了多少」这个数的**对手方**（没有它，救回数可以靠
        # 改分母变大）。档名与 `scope_of` 的 rung 常量同源。
        "resolution": resolution,
        # R89：阶梯的**自称参数**（口径 / 语言 / 用到哪几级 / 上限 / 诊断）。
        # 为什么参数也要进产物：R87 的教训 —— 「产物字节变了 ≠ 图变了」，
        # 要登记的是**产物自称的参数**，不只字节与 sha。
        "local_scope": scope_report(scope),
        "nodes_total": n_nodes,
        "edges_total": n_edges,
        "unresolved_total": unresolved_total,
        "fan_in_top": fin[:top_n],
        "fan_out_top": fout[:top_n],
        "cross_file": cross,
        "cross_dir": dir_cross,
        "cycles": cycles,
        "cycles_computed": bool(with_cycles),
        "cycle_stats": cstats,
        "truncated": tr,
        "limitations": _limitations(identity, unresolved_total, scope),
    }


def _limitations(identity, unresolved_total, scope=None):
    """**口径自己的局限**必须随口径一起说。名字级那一条与 R86/R87 逐字相同。"""
    if identity == IDENTITY_LOCAL:
        return _limitations_local(unresolved_total, scope)
    if identity == IDENTITY_NAME:
        return [
            "节点身份是**被调函数的原始名**（小写比较），不是「定义落点」。"
            "跨文件同名函数（C 的 static 重名）会合并成一个节点 ⇒ cycles "
            "可能含**假阳性**；要消歧必须看文件，本投影做不到。",
            "未解析调用（%d 条）**不在图里** —— 它们没有 callee 节点。"
            "它们不是「没有关系」，是「没解析出来」。"
            % int(unresolved_total or 0),
            "截断是显式的，见 truncated —— 「我没展开」不等于「没有关系」。",
        ]
    return [
        "节点身份是**定义落点**：源 =「调用点所在文件 + 调用者名」（并在 "
        "func_index 里核对过它确实是定义文件，核不上的标成 K_SITE 而不冒充）；"
        "目标 =「唯一那份定义的落点」。⇒ 同名不同文件的函数**各成节点**，"
        "R86/R87 那个 37,775 成员的假环由此被拆开。",
        "⚠ **同名多定义的被调者仍保持名字级**（标 K_AMB）：边里**不带**命中的"
        "是哪一份定义（resolve_calls 取的是 func.name，没取 file.rel），"
        "所以「它到底调用的是哪一份」**判不出来** —— 本投影不猜。"
        "这一部分条数见 cross_file.ambiguous。",
        "⚠ **K_AMB 节点是汇点**（它没有出边 —— 出边归给了「各定义所在文件」上的"
        "节点）⇒ **经过同名多定义被调者的环不再被报出**。这是「宁可少报，不可错报」"
        "的取向：判不出调的是哪一份，就不宣称它成环。代价是**真环也可能漏**，"
        "漏的量上界 = 指向 K_AMB 的边数（= cross_file.ambiguous）。",
        "⚠ 因为 resolve_calls 对多定义**扇出**，edges_total 不是「调用点条数」，"
        "而是「(调用点 × 命中定义) 对」的条数。",
        "⚠ 节点的 ``file``/``line`` 来自 func_index 的**每（名字·文件）一份**记录；"
        "``defs`` 报的是该名字的定义**总数**（>1 即在同名多定义之列）。"
        "同一文件内同名重复定义时 ``line`` 取第一条（少见，且不影响节点身份）。",
        "⚠ **已声明的缺口**：源侧还有一种身份 ``K_SITE``（调用点文件已知、但它"
        "不是该名字的定义文件，显示成 `名字 @ 文件 %s`）。它**在当前 C 前端上"
        "取不到** —— `call_sites_of_files` 取的是「被解析文件里的包围函数」，而"
        "那个函数必然已用同一个 ``rel`` 注册进 ``func_index`` ⇒ 源侧恒满足"
        "「rel 是调用者的定义文件」。实测 68,030 条边 / 7 份语料：**0 条**。"
        "它是「不冒充定义落点」的护栏，不是当前会出现的形状；"
        "唯一能触发它的是合成夹具（``_r88/probe_defsite.py`` 的 A12）。"
        % SITE_MARK,
        "未解析调用（%d 条）**不在图里** —— 它们没有 callee 节点。"
        "它们不是「没有关系」，是「没解析出来」。"
        % int(unresolved_total or 0),
        "截断是显式的，见 truncated —— 「我没展开」不等于「没有关系」。",
    ]


def _limitations_local(unresolved_total, scope):
    """R89 口径的局限。**规则、它判得出来的边界、它判不出来的部分，三样一起说。**

    ⚠ F7f 会逐条核这里的措辞 —— 口径换了而局限照抄旧口径，是这套门禁里
    最容易被忽略、也最危险的一种漂移。
    """
    sc = scope_report(scope)
    if not sc["applied"]:
        return [
            "⚠ 本口径声明为 `%s`（同文件优先 + 包含闭包），但**本次运行没有启用"
            "阶梯**：语言 %r 不在 %r 里。⇒ 它的读数与 `%s` **逐位相同**。"
            "为什么按语言分：C 的可见性由翻译单元决定（可判定）；Python / JS 的"
            "模块绑定能在运行时被 import / 重赋值改掉，「同名同文件」只是近似 ——"
            "近似冒充结论就会造出**假环**。"
            % (IDENTITY_LOCAL, sc["lang"], list(LOCAL_SCOPE_LANGS),
               IDENTITY_DEFSITE),
            "未解析调用（%d 条）**不在图里** —— 它们没有 callee 节点。"
            % int(unresolved_total or 0),
            "截断是显式的，见 truncated —— 「我没展开」不等于「没有关系」。",
        ]
    rungs = " + ".join(sc["rungs"]) if sc["rungs"] else "（无）"
    return [
        "节点身份是**定义落点**，且同名多定义时按 C 的**翻译单元可见性**判两级："
        "① **同文件优先**（恰一份定义落在调用者文件里 ⇒ 用它）；"
        "② **包含闭包**（`#include` 闭包里恰一份候选 ⇒ 用它，且必须是"
        "**三明治**：欠近似闭包与过近似闭包都恰含同一份；只对 TU 根 "
        "`.c/.cc/.cpp/.cxx` 成立）。本次启用：%s（语言 %r）。"
        % (rungs, sc["lang"]),
        "⚠ 这两级是**推导**（derived）不是观测：它依赖 C 的可见性规则成立。"
        "**已知的判错方向**：同名宏（`#define foo(...)`）会遮蔽同名函数，"
        "而调用提取是纯词法的；闭包按 basename 解析头文件，同名头文件可能张冠"
        "李戴；条件编译（`#ifdef`）不展开。这三种情况下这条边可能被指到"
        "同名的另一份定义上。",
        "⚠ 第二级的「唯一」判的是「这个 basename **解析到几个目标文件**」"
        "（`local_scope.under_basis` = %r），**不是**「有几条 include 行指过来」"
        "—— 后者会把被很多地方包含的头（内核里**最常见**的形状，如 `kernel.h`）"
        "整条丢出欠近似图 ⇒ 三明治在主战场上**恒失败**。R89k 之前正是如此："
        "CROSS 档独立量具测出 2034 条可判，引擎一条也判不出来。"
        % (sc.get("under_basis") or "-"),
        "⚠ **判不出来的部分一律留 `K_AMB` 汇点**（不猜）。它的规模见 "
        "`resolution.ambiguous`，占用的**上界**是「经过同名单定义被调者的环会"
        "漏报」（`K_AMB` 是汇点，没有出边）。本次还有 %d 条边因为**调用点落在"
        "头文件里**而用不上第二级（头文件的 TU 由包含者决定，不由它自己）。"
        % int(sc["header_callers"] or 0),
        "⚠ 闭包 BFS 有上限 %d（`local_scope.closure_cap`）：超限的边**回落 "
        "`K_AMB`** 并计入 `closure_capped`（本次 %d 条）—— 截断后的集合绝不会"
        "被当成结论（截断的方向是**错报**）。"
        % (int(sc["closure_cap"] or 0), int(sc["closure_capped"] or 0)),
        "⚠ 第二级的**成本**也在 `local_scope` 里自称：%d 个调用者文件触发了闭包，"
        "实际算了 %d 次、访问 %d 个节点 —— 不变量是「**每个文件只算两次**"
        "（under + over）」，即 `closure_computed == 2 × rung2_files`；它一破"
        "就说明缓存退化成了重算（R89j 之前正是如此：内核整树这一步 61.4 分钟"
        "没跑完，而**所有读数一个都没变**）。"
        % (int(sc["rung2_files"] or 0), int(sc["closure_computed"] or 0),
           int(sc["closure_visits"] or 0)),
        "**（R90 已修）** `rel` 只相对**被分析根**（与 MATLAB 端 "
        "`p.relative_to(root).as_posix()` 同口径），**不再**依赖调用者的 cwd —— "
        "R90 之前它相对**当前工作目录**算，被分析根在 cwd **之外**时只能退化成 "
        "**basename** ⇒ 同名不同目录的文件被**合并** ⇒ 同一份语料给出**两套读数**"
        "（内核整树实测 `resolution.same_file` 381290 → 348353，而 `edges_total` "
        "与 `unique` **逐位不变** —— 只有量 `rel` 的那几条判据看得见）。"
        "`root` **没有默认值**（漏传当场 `TypeError`）⇒ **不留**静默的 cwd 回退。"
        "**回归判据**：同一份语料在**任意** cwd 下（含「根不在 cwd 之下」的形态）"
        "必须给出**逐位相等**的 `rel` 及其派生读数 —— 「已修」二字由该判据维持，"
        "不是由「改完了」这句话维持。",
        "⚠ 因为 resolve_calls 对多定义**扇出**，edges_total 不是「调用点条数」，"
        "而是「(调用点 × 命中定义) 对」的条数。",
        "未解析调用（%d 条）**不在图里** —— 它们没有 callee 节点。"
        "它们不是「没有关系」，是「没解析出来」。"
        % int(unresolved_total or 0),
        "截断是显式的，见 truncated —— 「我没展开」不等于「没有关系」。",
    ]


# ── 子图（以某函数为中心展开）───────────────────────────────────────────────
def focus_subgraph(edges, focus, depth=DEFAULT_DEPTH,
                   max_nodes=DEFAULT_MAX_NODES, direction="callee",
                   func_index=None, identity=DEFAULT_IDENTITY, lang=None,
                   include_edges=None, max_edges=0):
    """以 ``focus`` 为根做 BFS，展开 ``depth`` 层。``direction`` ∈ callee/caller/both。

    与顶层一样：**超限即停并如实上报**，不静默截断。

    ⚠ **为什么是「逐层重扫边表」而不是「先建邻接表再 BFS」**：内核实测 7,060,966
    条边，建一份 ``dict[name] -> list[(dst, line, rel)]`` 的邻接表要 **~1.7 GB**
    （14M 个小元组 + 每个节点的 list 头），而那是在分析本身已经吃到 **13,135.4 MB**
    峰值的前提上再要 —— 直接把 16 GB 的机器顶爆。逐层重扫只多花 ``depth`` 次 O(E)
    遍历（内核上 ≈ 两趟 700 万次比较，秒级），换掉那一份常驻结构。

    ⚠ R88：定义落点口径下**一个名字可以映到多个节点**。此时必须**报出来**
    （``focus_candidates``）并挑**度数最高**的那个 —— 静默挑一个就是「猜」。

    ``focus`` 两种写法都收（**两条路都通向同一批节点**）：
      * **函数名**（用户敲的，如 ``memcpy``）⇒ 大小写不敏感（沿用老口径 ``_norm``）；
      * **节点名**（``名字 @ 文件``，即 ``hub_of`` 返回的那种）⇒ **精确**比较。
    为什么必须有第二条：默认根来自 ``hub_of``，它返回的是**节点**（定义落点口径下
    形如 ``memcpy @ arch/alpha/lib/memcpy.c``），只按名字匹配的话它会**匹配不上
    任何节点**，默认子图就退化成「1 节点 0 边」。两条路在**名字级口径下完全等价**
    （那时 ``_display(k) == _name_of(k) == k``，精确相等蕴含归一相等），
    所以老读数逐字节不变。

    ⚠ **R91：边数上限（``max_edges``）** —— R87 只给了**节点**上限，边**没有**：
    内核默认根实测 34 节点 / **19,469** 边，而 ``truncated`` 里
    ``fan_in/out`` 有 ``shown/total``、``focus_subgraph`` 对边却什么都不报
    ⇒ 「看不全」可以不上报。本参数把那一半补上：

      * ``max_edges <= 0``（默认）= **不限**，且 ``truncated`` 的键集与 R90
        **逐字相同**（不给开关就没人能截断它，那三项只会是常量，加进去是噪声，
        却会作废 R90 建立的跨轮回归）；
      * ``max_edges > 0`` ⇒ 只保留**先遇到的** ``max_edges`` 条边，并在
        ``truncated`` 里同时给出 ``max_edges`` / ``hit_edge_cap`` /
        ``edges_total``（``edges_total`` 与「不设上限」时的 ``edges_shown``
        **同源**，不是另算一个数）；
      * **只裁边、不动节点** —— ``nodes`` / ``nodes_shown`` / ``hit_node_cap``
        与不设上限时**逐位相同**（判据 F10m 的两向都钉着这条）。
    """
    want = _norm(focus)
    want_node = focus if isinstance(focus, str) else ""
    dfcache = {}
    # R89：作用域与顶层投影**同一份构造**（scope_of 是唯一入口）——
    # 两处若各建一份，同一个名字在顶层与焦点子图里可能映到不同节点。
    scope = scope_of(identity, lang, include_edges)
    pairs = [_edge_nodes(e, func_index, identity, (dfcache,), scope)
             for e in edges]

    # 名字 → 候选节点（按度数降序；次级键只依赖内容，不依赖遍历顺序）。
    deg = {}
    for a, b in pairs:
        for k in (a, b):
            if _name_of(k, identity) == want or _display(k, identity) == want_node:
                deg[k] = deg.get(k, 0) + 1
    cands = sorted(deg.items(), key=lambda kv: (-kv[1], kv[0]))
    if cands:
        root = cands[0][0]
    else:
        # 名字不在图里 —— 退回老行为（一个孤立节点），**不假装找到了**。
        root = want

    level = {root: 0}
    order = [root]
    frontier = set((root,))
    cut = False
    for d in range(1, int(depth) + 1):
        nxt = set()
        for a, b in pairs:
            if direction in ("callee", "both") and a in frontier:
                if b not in level:
                    if len(level) >= max_nodes:
                        cut = True
                    else:
                        level[b] = d
                        order.append(b)
                        nxt.add(b)
            if direction in ("caller", "both") and b in frontier:
                if a not in level:
                    if len(level) >= max_nodes:
                        cut = True
                    else:
                        level[a] = d
                        order.append(a)
                        nxt.add(a)
        frontier = nxt
        if cut or not frontier:
            break

    keep = set(order)
    nodes = []
    for nid in order:
        d = _nodeinfo(nid, identity, func_index)
        nodes.append({"name": d["name"], "level": level[nid],
                      "file": d["file"], "line": d["line"], "defs": d["defs"]})
    sub = []
    cap = int(max_edges or 0)      # <= 0 = 不限
    edge_total = 0                 # 「不设上限时会收多少条」= 两端都在 keep 里的边
    edge_cut = False
    for i, (a, b) in enumerate(pairs):
        if a in keep and b in keep:
            edge_total += 1
            if cap > 0 and len(sub) >= cap:
                # 前缀截断：保留**先遇到的** cap 条，不依赖集合遍历顺序。
                edge_cut = True
                continue
            sub.append({"from": _display(a, identity), "to": _display(b, identity),
                        "line": edges[i][2], "file": edges[i][3]})
    return {
        "focus": _focus_label(root, identity),
        "focus_candidates": len(cands),
        "direction": direction,
        "depth": int(depth),
        "max_nodes": int(max_nodes),
        "nodes": nodes,
        "edges": sub,
        "truncated": _trunc_block(cut, len(nodes), len(sub), max_nodes,
                                  cap, edge_cut, edge_total),
    }


# ── 截断上报块（R91）────────────────────────────────────────────────────────
def _trunc_block(cut, n_nodes, n_edges, max_nodes, max_edges, edge_cut,
                 edges_total):
    """`focus_subgraph` 的 `truncated` 块（抽成函数只为让**键的顺序**可读）。

    ⚠ **不设边上限（`max_edges <= 0`）时键集与 R90 逐字相同**：没有上限就
    不可能被它截断，`max_edges` / `hit_edge_cap` / `edges_total` 三项只会是
    常量（0 / False / == `edges_shown`），带上去纯属噪声，却会把 R90 建立的
    「内核跨轮回归」当场作废 —— 那是**刻意**的条件键，不是遗漏。
    """
    parts = []
    if cut:
        parts.append("达到节点上限 %d，展开在**未探完**处停止 —— "
                     "被停下的那些分支记为「未展开」，不是「无关系」。"
                     % int(max_nodes))
    if edge_cut:
        parts.append("达到边数上限 %d，只保留先遇到的 %d 条边 —— "
                     "被丢掉的边不是「无关系」，是**没展示**。"
                     % (int(max_edges), int(max_edges)))
    out = {
        "hit_node_cap": bool(cut),
        "nodes_shown": int(n_nodes),
        "edges_shown": int(n_edges),
        "reason": " ".join(parts) if parts else "未触发上限。",
    }
    if int(max_edges or 0) > 0:
        out["max_edges"] = int(max_edges)
        out["hit_edge_cap"] = bool(edge_cut)
        out["edges_total"] = int(edges_total)
    return out


# ── 渲染 ────────────────────────────────────────────────────────────────────
def _dot_esc(s):
    """Graphviz DOT 字符串转义（反斜杠与引号）。与 MATLAB 侧 `_dot_label` 同口径。"""
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def to_dot(sub, title="call relations"):
    """把 ``focus_subgraph`` 的结果渲染成 DOT。

    ⚠ 节点 id 用 ``nd["name"]`` —— 定义落点口径下它**已经带着落点**
    （``名字 @ 文件``），所以两个同名不同文件的节点**不会**被 DOT 合并成一个。
    这也是为什么 R88 **没有**给节点加 ``key`` 字段：名字本身就是唯一 id。
    """
    lines = ["digraph callrel {",
             '  label="%s";' % _dot_esc(title),
             "  rankdir=LR;"]
    for nd in sub.get("nodes") or []:
        lab = nd["name"]
        if nd.get("file") and " @ " not in lab:
            lab = "%s\\n%s" % (nd["name"], nd["file"])
        lines.append('  "%s" [label="%s"];'
                     % (_dot_esc(nd["name"]), _dot_esc(lab)))
    for ed in sub.get("edges") or []:
        lines.append('  "%s" -> "%s";'
                     % (_dot_esc(ed["from"]), _dot_esc(ed["to"])))
    lines.append("}")
    return "\n".join(lines) + "\n"


def to_mermaid(sub, title="调用关系"):
    """把 ``focus_subgraph`` 的结果渲染成 Mermaid flowchart。"""
    lines = ["flowchart LR", "  %%%% %s" % (title or "")]
    seen = {}
    for nd in sub.get("nodes") or []:
        i = seen.setdefault(nd["name"], "n%d" % len(seen))
        lab = nd["name"]
        if nd.get("file") and " @ " not in lab:
            lab = "%s<br/>%s" % (nd["name"], nd["file"])
        lines.append('  %s["%s"]' % (i, lab.replace('"', "'")))
    for ed in sub.get("edges") or []:
        a = seen.get(ed["from"])
        b = seen.get(ed["to"])
        if a and b:
            lines.append("  %s --> %s" % (a, b))
    return "\n".join(lines) + "\n"


def format_report(rel):
    """把 ``call_relations`` 的结果渲染成给人读的文本（终端/日志用）。"""
    out = []
    out.append("调用关系（有界投影 · 节点身份=%s · 证据=%s）"
               % (rel.get("identity"), rel.get("evidence_kind")))
    out.append("  节点 %d | 调用边 %d | 未解析（不进图）%d"
               % (rel.get("nodes_total", 0), rel.get("edges_total", 0),
                  rel.get("unresolved_total", 0)))
    cf = rel.get("cross_file") or {}
    out.append("  跨文件：内部 %d | 跨文件 %d | 同名多定义(不猜) %d | 无定义 %d"
               % (cf.get("internal", 0), cf.get("cross", 0),
                  cf.get("ambiguous", 0), cf.get("unknown", 0)))
    rs = rel.get("resolution") or {}
    if rs:
        out.append("  解析阶梯（判得出/判不出，逐档现算）：唯一定义 %d | "
                   "同文件优先 %d | 包含闭包 %d | 仍有歧义(不猜) %d | 无定义 %d"
                   % (rs.get("unique", 0), rs.get("same_file", 0),
                      rs.get("include", 0), rs.get("ambiguous", 0),
                      rs.get("external", 0)))
    tr = rel.get("truncated") or {}
    out.append("  扇入 TOP（被调用最多，改动影响面大）")
    for r in (rel.get("fan_in_top") or [])[:10]:
        out.append("    %6d × %s%s"
                   % (r["n"], r["callee"],
                      ("  (%s:%s)" % (r["file"], r["line"])) if r.get("file") else ""))
    out.append("  扇出 TOP（调用最多）")
    for r in (rel.get("fan_out_top") or [])[:10]:
        out.append("    %6d × %s%s"
                   % (r["n"], r["caller"],
                      ("  (%s:%s)" % (r["file"], r["line"])) if r.get("file") else ""))
    if rel.get("cycles_computed"):
        cs = rel.get("cycle_stats") or {}
        out.append("  调用环：%s 个（环内节点 %s，最大环 %s）"
                   % (cs.get("components"), cs.get("nodes_in_cycles"),
                      cs.get("biggest")))
        for c in (rel.get("cycles") or [])[:5]:
            mem = ", ".join(c["members"][:12])
            if c["size"] > 12:
                mem += ", …"
            out.append("    [%d] %s" % (c["size"], mem))
    else:
        out.append("  调用环：未计算（本档只给度数结构）")
    out.append("  截断：扇入 %s/%s · 扇出 %s/%s · 环 %s/%s"
               % (tr.get("fan_in_shown"), tr.get("fan_in_total"),
                  tr.get("fan_out_shown"), tr.get("fan_out_total"),
                  tr.get("cycles_shown"), tr.get("cycles_total")))
    return "\n".join(out)


def hub_of(rel):
    """不给 `--callgraph-focus` 时的默认根：**枢纽分数**最高的节点。

    分数 = 2×扇入 + 扇出 —— 与 MATLAB 侧首页力导向图的选点口径**同一套**
    （`matlabc.py::_render_callgraph_section` 里的 `x[2]*2 + x[3]`），不为第二处
    再发明一个（「一个量一份实现」）。R88 把它从 `matlabc.py` 搬到这里：它读的是
    `rel` 这份产物、回答的是「默认看谁」，属于本模块的契约，而且搬过来才能被
    隔离探针直接量到。

    ⚠ **R88 修掉一个真缺陷：候选只许取「有出边」的节点。**
    旧口径是「分数 argmax」，而分数里扇入的权重是扇出的两倍 ⇒ 一个**只被调、
    不调人**的节点（`error` / `printk` / `memcpy` 这类）会稳赢。此时的默认子图
    按 `callee` 方向展开，当场退化成 `1 节点 / 0 边` —— 读起来像「这里没有关系」，
    而它对用户要问的问题一点信息量都没有。
    实测（`linux-6.19.14/init`，R88 探针）：旧口径选 `error`（扇入 26 / 出边 0）
    ⇒ `1 节点 / 0 边`；收窄到有出边的候选后选 `unpack_to_rootfs`（扇入 10 /
    扇出 12）⇒ 真子图。旧 docstring 里那句「同分时按名字排序会挑到 helper 这种
    没有出边的叶子」只挡了**同分**情形，挡不住扇入碾压 —— 这就是它当年没防住的原因。

    ⚠ 已知边界：分数只用 `fan_in_top` / `fan_out_top` 这两张**有界投影**
    （各 TOP-30）算 ⇒ 「有出边」是在 TOP-30 里判的。语料小到投影未截断时
    （`len(fan_out_top) < top_n`）它就是全量的；截断时可能把某个真枢纽漏在外面。
    这是有界投影的既定代价（`truncated` 里如实报着），不是新引入的猜测。
    """
    score = {}
    has_out = set()
    for r in (rel.get("fan_in_top") or []):
        n = r.get("callee")
        score[n] = score.get(n, 0) + 2 * (r.get("n") or 0)
    for r in (rel.get("fan_out_top") or []):
        n = r.get("caller")
        score[n] = score.get(n, 0) + (r.get("n") or 0)
        if (r.get("n") or 0) > 0:
            has_out.add(n)
    if not score:
        return None
    # 有出边的优先；一个都没有（语料里没有内部调用）才退回纯分数。
    pool = has_out or set(score)
    return sorted(pool, key=lambda n: (-score.get(n, 0), n))[0]
