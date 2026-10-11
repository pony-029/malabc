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

零第三方依赖 / Python 3.6.5 兼容 / 无全局可变状态。
"""

# 形状版本：键的增删改都要 +1（下游按它判断兼容性）。
#
# R88：1 → 2。理由**不是内容变了**（键集合没动），而是焦点子图**多了一个键**
# ``focus_candidates``，而它是**有意义的**：名字级口径下一个名字恒等于一个
# 节点 ⇒ 候选恒为 1；定义落点口径下一个名字可以映到多个节点 ⇒ 它必须被报出来
# （否则 ``--callgraph-focus memcpy`` 会在若干个 memcpy 里**静默挑一个**）。
CALLREL_VERSION = 2

# 节点身份口径。写成常量是为了让「口径被默默换掉」可被判据看见。
IDENTITY_NAME = "callee-name"
IDENTITY_DEFSITE = "definition-site"

# R88：默认改成定义落点。老口径**保留且可复现**（``--callgraph-identity callee-name``）。
DEFAULT_IDENTITY = IDENTITY_DEFSITE
IDENTITIES = (IDENTITY_NAME, IDENTITY_DEFSITE)

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


def _sym(func_index, name):
    """名字 → ``(kind, rel, line, ndef)``。**一个量一份实现**（与 ``_home`` 同源）。"""
    hits = (func_index or {}).get(_norm(name))
    if not hits:
        return (K_EXT, None, None, 0)
    h = hits[0]
    pf = h.get("file") or {}
    fn = h.get("func") or {}
    rel = pf.get("rel")
    if len(hits) > 1:
        return (K_AMB, rel, fn.get("line"), len(hits))
    return (K_DEF, rel, fn.get("line"), 1)


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


def _edge_nodes(e, func_index, identity, caches=None):
    """边 → ``(源键, 目标键)``。``identity`` 决定**节点身份口径**。

    这是**唯一**的「边的两端各是谁」判定点 —— 顶层投影与焦点子图都从这里取，
    不许各写一份（R87 的教训：同一个量两份实现必然分叉）。
    """
    caller = e[0]
    callee = e[1]
    if identity != IDENTITY_DEFSITE:
        # 老口径：名字即身份。逐字节复现 R86/R87 的读数。
        return (_norm(caller), _norm(callee))

    rel = e[3]
    dcache = caches[0] if caches is not None else {}
    # 源：调用者。调用点所在文件**通常就是**它的定义文件；核不上就标 K_SITE。
    if rel and rel in _defset(func_index, caller, dcache):
        src = _key(K_DEF, rel, caller)
    else:
        src = _key(K_SITE, rel, caller)
    # 目标：被调者。
    kind, drel, _ln, _nd = _sym(func_index, callee)
    if kind == K_DEF:
        dst = _key(K_DEF, drel, callee)
    elif kind == K_AMB:
        dst = _key(K_AMB, None, callee)
    else:
        dst = _key(K_EXT, None, callee)
    return (src, dst)


def _display(key, identity):
    """节点键 → **可读且唯一的**节点名。名字级口径下就是键本身（老行为）。"""
    if identity != IDENTITY_DEFSITE:
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
    if identity != IDENTITY_DEFSITE:
        return key
    return _key_parts(key)[2]


def _focus_label(s, identity):
    """``focus`` 这一栏的显示名。

    ``s`` 可能是**节点键**（内部分隔符 U+001F 在，来自 ``hub_of`` / 内部消歧），
    也可能是**用户敲的名字**（没有分隔符）。前者要转成可读形状，后者**原样回显**
    —— 名字不在图里时更应该让用户看到他敲的是什么，而不是把内部键形状漏出去。
    名字级口径下两种情形都返回 ``s`` 本身 ⇒ 老读数逐字节不变。
    """
    if identity != IDENTITY_DEFSITE:
        return s
    return _display(s, identity) if isinstance(s, str) and SEP in s else s


def _nodeinfo(key, identity, func_index):
    """节点键 → ``{"name","file","line","defs"}``（**字段集合与老口径一致**）。"""
    if identity != IDENTITY_DEFSITE:
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
                   unresolved_total=0, identity=DEFAULT_IDENTITY):
    """产出**有界**调用关系投影。规模无关，输出恒为 KB 级。

    ``edges``            ``[(caller, callee, line, rel)]``（与统一 IR 同源）
    ``func_index``       ``{小写名: [{"file": pf, "func": fn}]}``，用于回指文件/行
    ``unresolved_total`` 未解析调用条数（**不进图**，但要并列报出来）
    ``identity``         ``callee-name`` | ``definition-site``（默认后者，R88）
    """
    n_edges = len(edges)
    dfcache = {}

    fan_out = {}
    fan_in = {}
    cross = {"internal": 0, "cross": 0, "ambiguous": 0, "unknown": 0}
    dir_cross = {"internal": 0, "cross": 0, "unknown": 0}
    pairs = []
    for e in edges:
        a, b = _edge_nodes(e, func_index, identity, (dfcache,))
        pairs.append((a, b))
        fan_out[a] = fan_out.get(a, 0) + 1
        fan_in[b] = fan_in.get(b, 0) + 1
        rel = e[3]
        crel, _cline, ndef = _home(func_index, e[1])
        if ndef == 0:
            cross["unknown"] += 1
        elif ndef > 1:
            cross["ambiguous"] += 1
        elif crel == rel:
            cross["internal"] += 1
        else:
            cross["cross"] += 1
        # 目录级只看**判得出来的**：无定义（unknown）不猜；同名多定义（ambiguous）
        # 同样不进目录统计 —— 宁可少报，不可错报。
        if ndef == 1:
            if _dir_of(rel) == _dir_of(crel):
                dir_cross["internal"] += 1
            else:
                dir_cross["cross"] += 1
        elif ndef == 0:
            dir_cross["unknown"] += 1

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
        "limitations": _limitations(identity, unresolved_total),
    }


def _limitations(identity, unresolved_total):
    """**口径自己的局限**必须随口径一起说。名字级那一条与 R86/R87 逐字相同。"""
    if identity != IDENTITY_DEFSITE:
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


# ── 子图（以某函数为中心展开）───────────────────────────────────────────────
def focus_subgraph(edges, focus, depth=DEFAULT_DEPTH,
                   max_nodes=DEFAULT_MAX_NODES, direction="callee",
                   func_index=None, identity=DEFAULT_IDENTITY):
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
    """
    want = _norm(focus)
    want_node = focus if isinstance(focus, str) else ""
    dfcache = {}
    pairs = [_edge_nodes(e, func_index, identity, (dfcache,)) for e in edges]

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
    for i, (a, b) in enumerate(pairs):
        if a in keep and b in keep:
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
        "truncated": {
            "hit_node_cap": bool(cut),
            "nodes_shown": len(nodes),
            "edges_shown": len(sub),
            "reason": ("达到节点上限 %d，展开在**未探完**处停止 —— "
                       "被停下的那些分支记为「未展开」，不是「无关系」。"
                       % int(max_nodes)) if cut else "未触发上限。",
        },
    }


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
