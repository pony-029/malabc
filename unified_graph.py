# -*- coding: utf-8 -*-
"""统一图模型 —— R82 五条贯通线（T1–T5）的共同底座。

为什么先做它（R82 方案 §11/1）：T1 给图加的是**边的种类**（async）、
T2 加的是**跳**（binhop：源码 → 符号 → 库 → 库依赖）、T3 加的是**算子的两侧对齐**、
T4 加的是 **rule 节点**。四条线若各自长出一套边表示，之后要拆两遍。
所以本模块是**唯一的边构造处**（R82 方案 §7.7：「边的构造只在这里」）。

一图看懂（本模块要守的四条恒等式）：

    候选站点 sites                边 edges              节点 nodes
    ┌───────────────┐            ┌──────────────┐      ┌──────────────┐
    │ direct   n1   │───┐        │ direct  e1   │      │ file         │
    │ async    n2   │───┼───────▶│ async   e2   │      │ function     │
    │ callback n3   │   │        │ binhop  e3   │      │ binary       │
    │ indirect n4   │   │        └──────────────┘      │ kernel       │
    │ dynamic  n5   │   │                              │ rule         │
    │ binhop   n6   │   │        A2 引用完整性          └──────────────┘
    ├───────────────┤   │
    │ join      n7  │   └──▶ A1a Σ(产出边的站点) == |edges| ；A1b Σ(全部站点) == declared_sites（**独立分母**）
    │ unknown   n8  │
    └───────────────┘
         │
         └──▶ A3  ∀ binhop 边：hop.via_device 非空（若给了登记表则必须已登记）
              A4  同一 (src,dst,kind) 只许出现一次

**本表的关键结构决定**：`SITE_OUTCOMES` = 全部 `EDGE_KINDS` **加上两个非边结局**
`join` 与 `unknown`。于是恒等式是**「没有任何站点被丢掉」**：

    Σ(全部站点) == |edges| + n_join + n_unknown

它比单纯的「边数守恒」强：同时钉住了「汇合不被误记成并发」（`await` 落进 `join`
而不是变成 `async` 边）与「未识别不被静默丢」（落进 `unknown`）。
`EDGE_PRODUCING_OUTCOMES` 从 `SITE_OUTCOMES` **派生** —— 两张表各写一份必然漂移，
护栏 U1 直接断言 `EDGE_KINDS == EDGE_PRODUCING_OUTCOMES`。

A1a 是 R82-0-2 的验收判据「**注入一条边即破**」：往 `edges` 里塞一条边而不塞
对应站点，左边立刻小于右边，差值恰好是注入的条数。

**为什么还必须有 A1b（一个独立的分母）**：A1a 的两个量**都来自本对象**
（`sites` 与 `edges`）⇒ 只要识别器写成「先造边、再顺手 `add_site`」，A1a
**永远成立**，而它的绿灯与现在**一模一样** —— 判据退化成恒真式。所以本模块
要求一个**独立于 sites 表**的声明量 `declared_sites`（解析器/扫描器报出的候选
站点总数），由 A1b 断言两者相等。

**「站点先行」是构造期要求，不是事后审计**：`add_edge()` 要求该 `kind` 还有
**剩余站点额度**（`sites[kind]` 减去已产出的同类边数 ≥ 1），否则抛 `GraphError`
—— 让「先造边后补站点」这种写法**写不出来**，而不是等 A1a 事后发现（它发现不了）。

**本模块不做识别**：不发边、不读源码、不解析二进制。它只回答
「一张图守恒吗」。造边的装置在 T1–T4 各自的模块里。
"""
import json

# ── 单一事实源（护栏 U1/U2 钉住本表的形状）────────────────────────────────
# 节点种类。`kernel` 专指 **GPU 内核**；`--operator-impact-*` 里的「算子」是
# **静态检查类别**，与本表的 kernel 不是一回事（R82 §2.4 术语冲突，R82-0-1 声明）。
NODE_KINDS = ("file", "function", "binary", "kernel", "rule")

# 边的种类。`async` 缺席时 T1 无从谈起 —— 护栏 U2 把它钉住（删掉即红）。
EDGE_KINDS = ("direct", "async", "callback", "indirect", "dynamic", "binhop")

# **非边结局**：候选站点落进这里时**不产出边**。两个都必须是**一等状态**：
#   join    —— 汇合（`await` / `pthread_join`）：等一个已经在跑的任务。
#              记成 async 边会让「谁先谁后」整体反向（见 concurrency 的表）。
#   unknown —— 诚实：没识别出来。可见且有分母，不是错误，更不是沉默。
NON_EDGE_OUTCOMES = ("join", "unknown")

# 候选站点的**全部结局** = 全部边种类 + 两个非边结局（**派生**，不手抄）。
SITE_OUTCOMES = tuple(EDGE_KINDS) + tuple(NON_EDGE_OUTCOMES)

# 会产出边的结局（**派生**，绝不手写）。A1 用它做分母。
EDGE_PRODUCING_OUTCOMES = tuple(k for k in SITE_OUTCOMES
                                if k not in NON_EDGE_OUTCOMES)

# `declared_sites` 的**来源登记表**。每一条必须回答两个问题：
#   ① 它**独立于** `sites` 表吗？（`independent`）
#   ② 它和别的来源**差在哪**？（`note`）
# 判据 U6 会**拒绝** `independent=False` 的来源。为什么必须是拒绝而不是提醒：
# A1b 的全部价值在于「右边是**外部给的**」；一旦右边可以从 `sites` 派生，
# A1b 立刻退化成恒真式 —— 而它的绿灯与「真的对上了」**一模一样**。
# 「让写不出来的形状，比一条抓不住它的判据可靠」（R82-0b 的 H2 解药）。
DECLARED_SITE_SOURCES = (
    # (标签, 是否独立于 sites 表, 说明)
    ("sites_table", False,
     "从 sites 派生（all_site_count）—— 与 A1a 同源，**禁止**当独立分母"),
    ("file_axis", True,
     "按**文件**轴记的第二本账（逐文件累加，与结局轴 sites 不是一次投影）"),
    ("wordbound_scan", True,
     "用**词界**口径再扫一遍语料（与子串口径并列，互为对手方）"),
    ("parser", True,
     "真解析器报出的候选站点总数（Phase A 之后）"),
)

# 允许当独立分母的来源（**派生**，绝不手写）。
INDEPENDENT_SITE_SOURCES = tuple(s for s, ind, _n in DECLARED_SITE_SOURCES if ind)


class GraphError(ValueError):
    """图结构非法。构造期即失败，远好过运行期静默取错（R82 §4m-3）。"""


class Node(object):
    """一个图节点。`kind` 必须 ∈ NODE_KINDS。"""
    __slots__ = ("nid", "kind", "name", "attrs")

    def __init__(self, nid, kind, name="", attrs=None):
        if kind not in NODE_KINDS:
            raise GraphError("未登记的节点种类 %r（允许 %s）"
                             % (kind, list(NODE_KINDS)))
        if not nid:
            raise GraphError("节点 id 不得为空")
        self.nid = nid
        self.kind = kind
        self.name = name or nid
        self.attrs = dict(attrs or {})

    def to_dict(self):
        return {"id": self.nid, "kind": self.kind, "name": self.name,
                "attrs": dict(self.attrs)}

    @classmethod
    def from_dict(cls, d):
        return cls(d["id"], d["kind"], d.get("name", ""), d.get("attrs"))


class Hop(object):
    """一次「往下跳」的说明。T2 的 binhop 边**必须**带它。

    `via_device` 是**装置名**，必须登记在 `binhops.HOP_DEVICES` 里 ——
    「这条边是谁造出来的」不能靠猜（R82 §7.3 判据 2：未登记的 via_device ⇒ 红）。
    """
    __slots__ = ("via_device", "from_symbol", "to_symbol", "note")

    def __init__(self, via_device, from_symbol="", to_symbol="", note=""):
        if not via_device:
            raise GraphError("Hop.via_device 不得为空")
        self.via_device = via_device
        self.from_symbol = from_symbol
        self.to_symbol = to_symbol
        self.note = note

    def to_dict(self):
        return {"via_device": self.via_device, "from_symbol": self.from_symbol,
                "to_symbol": self.to_symbol, "note": self.note}

    @classmethod
    def from_dict(cls, d):
        return cls(d["via_device"], d.get("from_symbol", ""),
                   d.get("to_symbol", ""), d.get("note", ""))


class Edge(object):
    """一条边。`kind` ∈ EDGE_KINDS；`binhop` 必须带 hop。"""
    __slots__ = ("src", "dst", "kind", "hop", "evidence")

    def __init__(self, src, dst, kind, hop=None, evidence=""):
        if kind not in EDGE_KINDS:
            raise GraphError("未登记的边种类 %r（允许 %s）"
                             % (kind, list(EDGE_KINDS)))
        if kind == "binhop" and hop is None:
            raise GraphError("binhop 边必须带 hop（否则「谁造的」不可追溯）")
        self.src = src
        self.dst = dst
        self.kind = kind
        self.hop = hop
        self.evidence = evidence

    def key(self):
        return (self.src, self.dst, self.kind)

    def to_dict(self):
        return {"src": self.src, "dst": self.dst, "kind": self.kind,
                "hop": self.hop.to_dict() if self.hop else None,
                "evidence": self.evidence}

    @classmethod
    def from_dict(cls, d):
        h = d.get("hop")
        return cls(d["src"], d["dst"], d["kind"],
                   Hop.from_dict(h) if h else None, d.get("evidence", ""))


class UnifiedGraph(object):
    """节点 / 边 / 站点结局的容器。`add_*` 走构造期校验，`from_dict` 不走 ——
    这样守恒判定器能**报出**畸形图，而不是让反序列化先抛（R82 §6「声明⇄实装对账」）。
    """
    __slots__ = ("nodes", "edges", "sites", "meta", "declared_sites",
                 "declared_source")

    def __init__(self):
        self.nodes = {}      # nid -> Node
        self.edges = []      # list[Edge]
        self.sites = {}      # outcome -> 计数
        self.meta = {}
        # 第二个分母：解析器/扫描器报出的**候选站点总数**。None = 本次没有
        # 独立来源 ⇒ A1b **不参与判定**（报告里必须显式写「未行使」，
        # 而不是静默跳过 —— 缺席不能同时也是信号）。
        self.declared_sites = None
        # 那个分母的**来源标签**（必须在 DECLARED_SITE_SOURCES 里且独立）。
        # 它是 A1b 的**前提**，不是注解：没有它，`declared_sites` 与
        # `all_site_count()` 在判定器眼里无法区分。
        self.declared_source = None

    # ── 构造 ────────────────────────────────────────────────────────────
    def add_node(self, node):
        if node.nid in self.nodes:
            raise GraphError("节点 id 重复：%s" % node.nid)
        self.nodes[node.nid] = node
        return node

    def add_site(self, outcome, n=1):
        if outcome not in SITE_OUTCOMES:
            raise GraphError("未登记的站点结局 %r（允许 %s）"
                             % (outcome, list(SITE_OUTCOMES)))
        self.sites[outcome] = self.sites.get(outcome, 0) + int(n)
        return self.sites[outcome]

    def add_edge(self, edge):
        """加入一条边。构造期**两道**校验：端点已登记（A2）+ 站点额度够（站点先行）。

        「站点先行」若留到事后审计就晚了：A1a 的两个量同源，先造边再补站点
        会让它**恒真**（H2）。所以在**这里**拒绝 —— 一个写不出来的形状，
        比一条抓不住它的判据可靠。
        """
        for nid in (edge.src, edge.dst):
            if nid not in self.nodes:
                raise GraphError("边的端点 %r 不是已登记节点（引用完整性）" % nid)
        have = self.sites.get(edge.kind, 0)
        used = self.edge_census().get(edge.kind, 0)
        if have - used < 1:
            raise GraphError(
                "站点先行被违反：边 (%s→%s, %s) 没有可用的站点额度"
                "（该 kind 站点 %d 条、同类边已 %d 条）—— 每条边都必须先有一个"
                "产出它的候选站点；先造边后补站点会让 A1a 退化成恒真式"
                % (edge.src, edge.dst, edge.kind, have, used))
        self.edges.append(edge)
        return edge

    def set_declared_sites(self, n, source=None):
        """登记「候选站点总数」—— A1b 的**第二个分母**。

        **必须**带 `source`，且该来源要在 `DECLARED_SITE_SOURCES` 里、
        `independent` 为真。三种拒绝（各自守一个失败模式）：

          ① 缺 `source`    —— 分母与 `sites` 在判定器眼里无法区分
          ② 未登记的标签   —— 拼错的来源会被静默采纳成"有来源"（§4m-1）
          ③ 非独立标签     —— **拿派生量当独立分母**，A1b 当场退化成恒真式

        传 `n=None` 表示本次**没有**独立来源：那是「未行使」，不是「通过」
        —— 报告里必须显式说出来（R82 §4y-6：缺席不能同时也是信号）。
        """
        if n is None:
            self.declared_sites = None
            self.declared_source = None
            return None
        if int(n) < 0:
            raise GraphError("declared_sites 不得为负：%r" % (n,))
        if not source:
            raise GraphError(
                "declared_sites 必须带 source（独立来源标签）—— 缺来源的分母"
                "与 sites 表无法区分，A1b 会退化成恒真式。允许的来源：%s"
                % (list(INDEPENDENT_SITE_SOURCES),))
        row = [r for r in DECLARED_SITE_SOURCES if r[0] == source]
        if not row:
            raise GraphError(
                "未登记的 declared_sites 来源 %r（允许 %s）"
                % (source, [s for s, _i, _n in DECLARED_SITE_SOURCES]))
        if not row[0][1]:
            raise GraphError(
                "来源 %r 被标注为**非独立**（%s）⇒ 不许当作 A1b 的独立分母"
                % (source, row[0][2]))
        self.declared_sites = int(n)
        self.declared_source = source
        return self.declared_sites

    # ── 统计 ────────────────────────────────────────────────────────────
    def edge_census(self):
        """边种类直方图（**派生量**，不手写）。"""
        c = dict((k, 0) for k in EDGE_KINDS)
        for e in self.edges:
            c[e.kind] = c.get(e.kind, 0) + 1
        return c

    def site_census(self):
        """站点结局直方图。**每一个**结局都要有读数（哪怕是 0）——
        缺席不能同时也是信号（R82 §4y-6）。"""
        return dict((k, self.sites.get(k, 0)) for k in SITE_OUTCOMES)

    def produced_site_count(self):
        """会产出边的站点总数（A1 的左边）。"""
        return sum(self.sites.get(k, 0) for k in EDGE_PRODUCING_OUTCOMES)

    def non_edge_site_count(self):
        """不产出边的站点总数（join + unknown）—— A1 的余量。"""
        return sum(self.sites.get(k, 0) for k in NON_EDGE_OUTCOMES)

    def all_site_count(self):
        """全部候选站点数（= 产出边的 + join + unknown，构造上恒等）。

        ⚠ 它是**派生量**，所以**不能**拿来当 A1b 的右边（那会让 A1b 恒真）。
        A1b 的右边是 `declared_sites` —— 外部给的。
        """
        return self.produced_site_count() + self.non_edge_site_count()

    # ── 序列化 ──────────────────────────────────────────────────────────
    def to_dict(self):
        return {"meta": dict(self.meta),
                "nodes": [self.nodes[k].to_dict() for k in sorted(self.nodes)],
                "edges": [e.to_dict() for e in self.edges],
                "sites": self.site_census(),
                "edge_census": self.edge_census(),
                "declared_sites": self.declared_sites,
                "declared_source": self.declared_source}

    def to_json(self, indent=1):
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, d):
        g = cls()
        g.meta = dict(d.get("meta", {}))
        for nd in d.get("nodes", []):
            n = Node.from_dict(nd)
            if n.nid in g.nodes:
                raise GraphError("反序列化：节点 id 重复：%s" % n.nid)
            g.nodes[n.nid] = n
        # 故意用 append：让守恒判定器**报出**坏边，而不是反序列化先抛。
        for ed in d.get("edges", []):
            g.edges.append(Edge.from_dict(ed))
        g.sites = dict(d.get("sites", {}))
        g.declared_sites = d.get("declared_sites")
        g.declared_source = d.get("declared_source")
        return g


def conservation_problems(g, hop_devices=None):
    """纯函数：返回恒等式被破坏的清单（空 = 守恒）。

    **不抛异常** —— 它要能报出问题，而不是自己先炸（R82 §4k-2：一个从未被
    触发的分支不是判据；所以每条 A* 都必须在自证里被真触发过）。

    A1a 站点-边守恒：Σ(产出边的站点) == |edges|
    A1b 站点总数对账：Σ(全部站点) == declared_sites（**独立分母**；
        declared_sites 为 None ⇒ 本判据**未行使**，报告里必须显式说出来）
    A2 引用完整性：每条边的 src / dst 都是已登记节点
    A3 hop 可追溯：每条 binhop 边有 hop；via_device 非空且（给了表时）已登记
    A4 边唯一：同一 (src, dst, kind) 只许出现一次（重复 = 同一条边被造了两遍）
    """
    probs = []

    # A1a —— 「注入一条边即破」的那条
    produced = g.produced_site_count()
    if produced != len(g.edges):
        probs.append("A1a 站点-边守恒被破坏：产出边的站点 %d 条，实际边 %d 条（差 %+d）"
                     % (produced, len(g.edges), len(g.edges) - produced))

    # A1b —— 第二个分母。**不能**从 sites 派生，否则与 A1a 同源。
    declared = getattr(g, "declared_sites", None)
    if declared is not None:
        # A1b 有**前提**：那个分母必须自带一个**已登记的独立来源**。
        # 反序列化路径（`from_dict`）不走构造期校验，所以这一条必须在这里
        # 也能红 —— 否则「先写 JSON 再读回来」是一条绕过 `set_declared_sites`
        # 的侧门，而它产出的图看起来完全正常。
        src = getattr(g, "declared_source", None)
        if not src:
            probs.append(
                "A1b 前提缺失：declared_sites=%d 却没带来源标签 —— "
                "没有来源的分母无法与 all_site_count() 区分，"
                "判据本身不成立（允许 %s）" % (declared, list(INDEPENDENT_SITE_SOURCES)))
        elif src not in [s for s, _i, _n in DECLARED_SITE_SOURCES]:
            probs.append("A1b 来源未登记：%r（允许 %s）"
                         % (src, [s for s, _i, _n in DECLARED_SITE_SOURCES]))
        elif src not in INDEPENDENT_SITE_SOURCES:
            probs.append(
                "A1b 来源 %r **非独立**（它从 sites 派生）⇒ 这个分母等于 "
                "all_site_count()，A1b 退化成恒真式" % (src,))
        total = g.all_site_count()
        if total != declared:
            probs.append(
                "A1b 站点总数与声明不符：全部站点 %d 条，声明 %d 条（差 %+d）"
                "—— 声明量是独立来源，不等即说明有站点被漏记或重复记"
                % (total, declared, declared - total))

    # A2
    for i, e in enumerate(g.edges):
        for nid in (e.src, e.dst):
            if nid not in g.nodes:
                probs.append("A2 第 %d 条边（%s→%s）的端点 %r 不是已登记节点"
                             % (i, e.src, e.dst, nid))

    # A3
    for i, e in enumerate(g.edges):
        if e.kind != "binhop":
            continue
        if e.hop is None or not e.hop.via_device:
            probs.append("A3 第 %d 条 binhop 边没有 hop.via_device"
                         "（「谁造的」不可追溯）" % i)
            continue
        if hop_devices is not None and e.hop.via_device not in hop_devices:
            probs.append("A3 第 %d 条 binhop 边的 via_device %r 未登记"
                         % (i, e.hop.via_device))

    # A4
    seen = {}
    for i, e in enumerate(g.edges):
        k = e.key()
        if k in seen:
            probs.append("A4 第 %d 条边与第 %d 条重复（%s）—— 同一条边被造了两遍"
                         % (i, seen[k], k))
        else:
            seen[k] = i

    return probs


def demo_graph():
    """自证用的小图：3 节点 + 2 边 + 4 类站点（2 产出边、1 join、1 unknown）。

    护栏 `tools/check_unified_graph.py` 的 U3/U5 直接复用本函数 ——
    「被测图」与「判据」用**同一份**夹具，免得两边各写一份而互相漂移。
    """
    g = UnifiedGraph()
    g.add_node(Node("f:a.m", "file", "a.m"))
    g.add_node(Node("fn:a.m:foo", "function", "foo"))
    g.add_node(Node("fn:a.m:bar", "function", "bar"))
    g.add_site("direct", 1)
    g.add_edge(Edge("f:a.m", "fn:a.m:foo", "direct", evidence="line 3"))
    g.add_site("async", 1)
    g.add_edge(Edge("f:a.m", "fn:a.m:foo", "async",
                    evidence="parfeval @foo at line 9"))
    g.add_site("join", 1)       # 汇合：**不**产出边
    g.add_site("unknown", 1)    # 诚实：没识别出来
    # demo 图自洽：声明量与 sites 一致。A1b 的**红**由护栏的子探针制造
    # （真造一个「声明 5 而实际 4」的图），并断言它被抓到。
    # 来源写 `file_axis` 而不是转发 `all_site_count()`：demo 里 4 条站点
    # 各出自一个文件，文件轴那本账独立数出来的也是 4。**值恰好相等，
    # 但来源是真话** —— 这正是 A1b 想要的形态（两个来源独立数出同一个数）。
    g.set_declared_sites(4, "file_axis")
    return g


if __name__ == "__main__":
    import sys
    sys.exit(0)
