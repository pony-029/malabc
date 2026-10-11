# -*- coding: utf-8 -*-
"""callrel.py —— 调用关系（call relations）的**有界投影**。

为什么这个模块存在
==================
分析器**早就算出了**调用边。实测（Linux 内核整树）：C 函数 743,518 个、
调用边 **7,065,831** 条、未解析调用 1,295,146 条。可是**交付出去的结果里
一条关系都没有**，根因是产物环节而不是分析环节：

  * `--json-level summary` 的载荷**结构上不含 `edges`**（`matlabc.py` 的
    摘要支路只写 `summary.edges` 这个**计数**，非摘要支路才写
    `"edges": [{"caller","callee","line","file"}, ...]`）；
  * 全量 `edges` 在内核规模下是 GB 级（7.07M 条 × ~130 B ≈ 919 MB，加上
    每文件明细，实测外推 ~2.6 GB）——**把 GB 级 JSON 丢给用户不是解法**。

于是本模块给出第三条路：**有界投影**。规模再大，顶层输出恒为 KB 级；
被丢掉的那部分**必须如实上报**（``truncated`` 里给 ``*_total`` / ``*_shown``
两对数）。这一条与 R86-2 的 ``skipped ≠ not_found`` 同源 ——
**「我没展开」不等于「没有关系」。**

三条口径必须并列陈述（不许同化）
================================
1. **节点身份 = 被调函数的原始名**（小写后比较）——``identity`` 写成字面量。
   代价：跨文件的同名函数（C 里最常见的 ``static`` 重名）会被**合并成一个
   节点 ⇒ ``cycles`` 有**假阳性**风险。这条不许省略，见 ``limitations``。
2. **未解析调用不在图里** —— 它们没有 callee 节点。它们**不是**「没有关系」，
   而是「这条关系没解析出来」。计数并列给出（``unresolved_total``）。
3. **截断显式** —— 见上。

零第三方依赖 / Python 3.6.5 兼容 / 无全局可变状态。
"""

# 形状版本：键的增删改都要 +1（下游按它判断兼容性）。
CALLREL_VERSION = 1

# 节点身份口径。写成常量是为了让「口径被默默换掉」可被判据看见。
IDENTITY_NAME = "callee-name"

# 证据档：本模块的读数全部来自**已经解析出的边**，是读出来的不是推出来的。
EVIDENCE_OBSERVED = "observed"

# 顶层有界投影的默认上限。与 MATLAB 侧首页力导向图（max_nodes=1200）**不同**
# 是刻意的：那边是交互式 SVG，这边是给人读的文本/结构化产物。
DEFAULT_TOP_N = 30
DEFAULT_MAX_CYCLES = 20
DEFAULT_MAX_NODES = 300
DEFAULT_DEPTH = 2


def _norm(name):
    """节点身份的归一：小写。空名归一到空串（不是 None，避免 dict 键类型漂移）。"""
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


def _dir_of(rel):
    if not rel:
        return None
    i = rel.rfind("/")
    if i < 0:
        i = rel.rfind("\\")
    return rel[:i] if i >= 0 else ""


# ── 邻接表（CSR）────────────────────────────────────────────────────────────
def build_csr(edges):
    """把 ``[(caller, callee, line, rel)]`` 压成 CSR。

    为什么不用 ``dict[str, list]``：内核规模下 7.07M 条边，Python 的
    ``list`` 每个元素一个指针 + int 对象，实测要多占数百 MB；而 ``array('i')``
    是裸 4 字节。分析本身峰值就到过 13 GB（实测 13,072.9 MB），这里**不再加
    一份 O(E) 的 Python 对象层**是硬要求。

    返回 ``(ids, names, head, adj)``：
        ids    : 名字 -> 节点号
        names  : 节点号 -> 名字（原始大小写，取首次出现的那份）
        head   : 长度 n+1 的偏移表（CSR 标准形状）
        adj    : 长度 E 的扁平后继表（**含重边** —— 重复调用是事实，不去重）
    """
    from array import array

    ids = {}
    names = []
    src = array("i")
    dst = array("i")
    for e in edges:
        a = e[0]
        b = e[1]
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
def strongly_connected(names, head, adj, max_cycles=DEFAULT_MAX_CYCLES):
    """name-level SCC（size > 1 才算环）。**迭代**实现，不用递归。

    为什么必须迭代：内核语料 743,518 个节点，递归 Tarjan 的深度会跟最长简单
    路径走 —— 那是个不受控的量，Python 默认递归上限 1000，一撞就是
    ``RecursionError``（而 `parse()` 那一层的 except 接不住它）。

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

    cycles = []
    nodes_in = 0
    biggest = 0
    for comp in comps:
        members = sorted(names[k] for k in comp)
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
                   unresolved_total=0):
    """产出**有界**调用关系投影。规模无关，输出恒为 KB 级。

    ``edges``            ``[(caller, callee, line, rel)]``（与统一 IR 同源）
    ``func_index``       ``{小写名: [{"file": pf, "func": fn}]}``，用于回指文件/行
    ``unresolved_total`` 未解析调用条数（**不进图**，但要并列报出来）
    """
    n_edges = len(edges)

    fan_out = {}
    fan_in = {}
    cross = {"internal": 0, "cross": 0, "ambiguous": 0, "unknown": 0}
    dir_cross = {"internal": 0, "cross": 0, "unknown": 0}
    for e in edges:
        a = _norm(e[0])
        b = _norm(e[1])
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
        for name, k in counter.items():
            rel, line, ndef = _home(func_index, name)
            rows.append({key_name: name, "n": k,
                         "file": rel, "line": line, "defs": ndef})
        rows.sort(key=lambda r: (-r["n"], r[key_name]))
        return rows

    fin = _rows(fan_in, "callee")
    fout = _rows(fan_out, "caller")

    cycles = None
    cstats = {"components": None, "nodes_in_cycles": None, "biggest": None}
    n_nodes = len(set(list(fan_in) + list(fan_out)))
    if with_cycles:
        # CSR 只在**真的要算环**的时候建 —— 它是一份 O(E) 的额外结构，
        # 而「只报度数结构」这一档（KB 级输出）不该为它付内存。
        _ids, names, head, adj = build_csr(edges)
        n_nodes = len(names)
        cycles, cstats = strongly_connected(names, head, adj,
                                            max_cycles=max_cycles)

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
        "identity": IDENTITY_NAME,
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
        "limitations": [
            "节点身份是**被调函数的原始名**（小写比较），不是「定义落点」。"
            "跨文件同名函数（C 的 static 重名）会合并成一个节点 ⇒ cycles "
            "可能含**假阳性**；要消歧必须看文件，本投影做不到。",
            "未解析调用（%d 条）**不在图里** —— 它们没有 callee 节点。"
            "它们不是「没有关系」，是「没解析出来」。"
            % int(unresolved_total or 0),
            "截断是显式的，见 truncated —— 「我没展开」不等于「没有关系」。",
        ],
    }


# ── 子图（以某函数为中心展开）───────────────────────────────────────────────
def focus_subgraph(edges, focus, depth=DEFAULT_DEPTH,
                   max_nodes=DEFAULT_MAX_NODES, direction="callee",
                   func_index=None):
    """以 ``focus`` 为根做 BFS，展开 ``depth`` 层。``direction`` ∈ callee/caller/both。

    与顶层一样：**超限即停并如实上报**，不静默截断。

    ⚠ **为什么是「逐层重扫边表」而不是「先建邻接表再 BFS」**：内核实测 7,065,831
    条边，建一份 ``dict[name] -> list[(dst, line, rel)]`` 的邻接表要 **~1.7 GB**
    （14M 个小元组 + 每个节点的 list 头），而那是在分析本身已经吃到 **13,072.9 MB**
    峰值的前提上再要 —— 直接把 16 GB 的机器顶爆。逐层重扫只多花 ``depth`` 次 O(E)
    遍历（内核上 ≈ 两趟 700 万次比较，秒级），换掉那一份常驻结构。
    """
    want = _norm(focus)
    level = {want: 0}
    order = [want]
    frontier = set((want,))
    cut = False
    for d in range(1, int(depth) + 1):
        nxt = set()
        for e in edges:
            a = _norm(e[0])
            b = _norm(e[1])
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
        rel, line, ndef = _home(func_index, nid)
        nodes.append({"name": nid, "level": level[nid],
                      "file": rel, "line": line, "defs": ndef})
    sub = []
    for e in edges:
        a = _norm(e[0])
        b = _norm(e[1])
        if a in keep and b in keep:
            sub.append({"from": a, "to": b, "line": e[2], "file": e[3]})
    return {
        "focus": want,
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
    """把 ``focus_subgraph`` 的结果渲染成 DOT。"""
    lines = ["digraph callrel {",
             '  label="%s";' % _dot_esc(title),
             "  rankdir=LR;"]
    for nd in sub.get("nodes") or []:
        lab = nd["name"]
        if nd.get("file"):
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
        if nd.get("file"):
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
