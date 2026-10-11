# -*- coding: utf-8 -*-
"""登记制静态护栏：统一图模型的**恒等式** + 三张**登记表**的自洽性（R82-0b）。

R82 方案 §11/1 说 Phase 0 是「唯一不做就白做的一步」—— 因为 T1–T4 都要往
同一张图上加东西。但「先立模型」这句话本身**没有对手方**：模型写完没人知道
它守没守住。本门就是它的对手方，判据族 **U1–U8**。

一图看懂（每条判据拦什么）：

    U1  单一事实源形状          三张表非空、无重复；且
                                EDGE_KINDS == EDGE_PRODUCING_OUTCOMES
                                == SITE_OUTCOMES − NON_EDGE_OUTCOMES
                                （**两张表各写一份必然漂移** —— 建门时真撞到过）
    U2  T1 的图前提             async / callback ∈ EDGE_KINDS；
                                unknown **与** join ∈ SITE_OUTCOMES
    U2b 五语言原语表            **逐条**比对一张**显式期望表**（不读被测对象
                                自己的结局，否则是自证）：20 条一条不对即红；
                                表里多出未审原语也红；且 async ∩ join == ∅
    U3  **注入即破**（执行版）   真造图、真跑 conservation_problems。
                                A1a 注入一条边 ⇒ 红；补站点+同步声明 ⇒ 归零；
                                **A1b** 把声明量少报 1 ⇒ 红（第二个分母）。
                                另含 A2 / A3 / A4 子探针，且**每个子探针
                                只许触发自己那一维**（反例不得污染别的维）
    U4  binhop 装置登记         未登记的 via_device ⇒ A3 红
    U5  序列化往返              from_dict(to_dict(g)) 与原图逐节点逐边等价
                                （含 declared_sites）
    U6  **站点先行**            没有站点额度时 add_edge 必须**拒绝**（构造期，
                                不是事后审计）；有额度时通过；额度用完即拒绝
    U7  互转规则的验证分母      三分（verified/unverified/total）必须构成划分，
                                且「已支持」⊆「已验证」—— 未验证的不得以
                                「已支持」出现（H6：一个会一直空下去的字段）
    U8  站点**匹配口径**         词界口径必须在**故意的前后缀语料**上真的比子串
                                口径少收（delta>0，否则词界化等于没做）；三个
                                已知误报（`__future__`/`signaling`/`callbacks`）
                                必须被排除；驼峰（`hThread`/`myThreadPool`）与
                                短语（`new Promise`/`.then(`）必须仍被命中
                                （口径不许修过头）；两词干族必须不交

**U8 为什么必须有**（R82b 黑帽 B5 实测）：分母可以被两件事**悄悄换掉**，
而全部门禁**全程绿** —— ① 匹配用**子串**（`signal_struct` 里的 `signal` 也算）；
② 「锁/信号量」被收进 `unknown`（互斥同步 != 异步站点）。两本账共用一个错口径时，
**对账永远对得上**（内核树上实测 13.4 万全绿，而分母早被换成了「并发相关词频」）。
⇒ **只加「对账」不够，必须给口径本身配对手方。** U8 的形态是「并列报两种口径，
并断言它们**真的不同**」—— 若两个读数完全相同，说明口径对手方退化成了同一把尺子
（这比「不一致」更坏：它看起来像已经量过了）。

**U3 为什么是本门的心脏**（R82-0-2 的验收判据字面就是「注入一条边即破」）：
把那句话写成注释是**没有对手方**的；写成一条**真跑**的探针，它才是判据
（本仓纪律 §4k-2：「一个从未被触发的分支不是判据」）。

**U3 为什么要两条守恒式**（H2，上一轮黑帽判为最严重）：
`Σ(产出边的站点) == |edges|` 的两个量**都来自同一个对象** ⇒ 只要识别器写成
「先造边、再顺手 `add_site`」，它**永远成立**，而绿灯与现在**一模一样**。
所以加了 A1b（`Σ(全部站点) == declared_sites`，声明量是**独立来源**），
并把「站点先行」做成 **U6 的构造期拒绝** —— 一个写不出来的形状，
比一条抓不住它的判据可靠。

用法：
    python tools/check_unified_graph.py            # 检查仓库 0=干净 1=有违规 2=缺输入
    python tools/check_unified_graph.py --selftest # 两向自证

退出码：
    0  = 形状合法、前提在场、守恒判定器两向、装置登记两向、往返无损、站点先行、验证分母成划分、匹配口径两向
    1  = 有违规（形状非法 / 前提缺失 / 判定器抓不到注入 / 未登记装置 / 往返漂移 / 额度失效 / 未验证报成已支持 / 口径未生效）
    2  = 缺输入（导不到 unified_graph / binhops / concurrency / site_matching / translate.rules）
"""
import argparse
import os
import sys

# R62/P5：「质量门表」里本门那一行的**签名**。它必须逐字出现在两处：
#   ① 本门的成功行（下面 main() 打印的那一行）；
#   ② README.md / README_CN.md 里本门那一行。
# 对手方 = tools/check_readme_parity.py 的 P5（表行内容 ⇄ 门）。
ROW_SIGNATURE = "U1–U8"

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _load():
    """导入被测模块。任何一个导不到 ⇒ 缺输入（返回 None）。"""
    try:
        import unified_graph as ug
        import binhops as bh
        import concurrency as cc
        import site_matching as sm
        import translate.rules as tr
    except ImportError:
        return None
    return ug, bh, cc, sm, tr


# ── U1：单一事实源的形状（**两张表必须绑死**）────────────────────────────
def model_shape_problems(node_kinds, edge_kinds, site_outcomes,
                         non_edge_outcomes, edge_producing):
    """纯函数。返回问题列表（空 = 合法）。

    这里最值钱的一条是「派生性」：`EDGE_PRODUCING_OUTCOMES` 必须是
    `SITE_OUTCOMES − NON_EDGE_OUTCOMES`，且必须**逐位等于** `EDGE_KINDS`。
    建门时就撞到过这条：`binhop` 一开始只进了 EDGE_KINDS 没进 SITE_OUTCOMES，
    于是 A1 对 binhop 边**结构性不成立**（而当时没有任何东西会说「不」）。
    """
    probs = []
    for name, seq in (("NODE_KINDS", node_kinds), ("EDGE_KINDS", edge_kinds),
                      ("SITE_OUTCOMES", site_outcomes)):
        if not seq:
            probs.append("U1 %s 为空 —— 空表是最隐蔽的「静默空转」" % name)
        elif len(set(seq)) != len(seq):
            dups = sorted(set(x for x in seq if list(seq).count(x) > 1))
            probs.append("U1 %s 有重复项 %s（归一化的代价必须显式付）"
                         % (name, dups))
    want = tuple(k for k in site_outcomes if k not in tuple(non_edge_outcomes))
    if tuple(edge_producing) != want:
        probs.append("U1 EDGE_PRODUCING_OUTCOMES 不是从 SITE_OUTCOMES 派生的："
                     "得到 %s，应为 %s（**两处各写一份必然漂移**）"
                     % (list(edge_producing), list(want)))
    if tuple(edge_kinds) != tuple(edge_producing):
        probs.append("U1 EDGE_KINDS 与 EDGE_PRODUCING_OUTCOMES 不等："
                     "每种边都必须有一个**产出它的站点结局**，否则那条边"
                     "无法被 A1a 计账（得到 %s vs %s）"
                     % (list(edge_kinds), list(edge_producing)))
    return probs


# ── U2：T1 的图前提 ────────────────────────────────────────────────────
def t1_premise_problems(edge_kinds, site_outcomes):
    """异步必须是一等的**边种类**；汇合与未识别必须是一等的**站点结局**。"""
    probs = []
    if "async" not in edge_kinds:
        probs.append("U2 EDGE_KINDS 里没有 'async' —— T1 无从谈起"
                     "（异步边与直接边混在一起，顺序结论会整体反向）")
    if "callback" not in edge_kinds:
        probs.append("U2 EDGE_KINDS 里没有 'callback' —— 注册回调无处安放")
    if "unknown" not in site_outcomes:
        probs.append("U2 SITE_OUTCOMES 里没有 'unknown' —— 未识别的并发站点"
                     "会静默消失（诚实状态降级成沉默）")
    if "join" not in site_outcomes:
        probs.append("U2 SITE_OUTCOMES 里没有 'join' —— 汇合站点无处安放，"
                     "只能被误记成 async 边")
    return probs


# ── U2b：五语言原语表**逐条**比对期望 ───────────────────────────────────
# ⚠ 这是**判据自己的**期望表，**不读 `concurrency.PRIMITIVES` 的结局**
#   —— 从被测对象读自己的期望，那是自证不是判据（本仓纪律 §4m-4 的精神）。
EXPECTED_OUTCOMES = {
    "c": (("pthread_create", "async"), ("fork", "async"),
          ("pthread_join", "join"), ("signal", "callback")),
    "cpp": (("std::thread", "async"), ("std::async", "async"),
            ("std::future", "join"), ("std::condition_variable", "callback")),
    "py": (("asyncio.create_task", "async"), ("asyncio.ensure_future", "async"),
           ("await", "join"), ("loop.call_later", "callback")),
    "js": (("new Promise", "async"), (".then(", "callback"),
           ("addEventListener", "callback"), ("setTimeout", "callback")),
    "matlab": (("parfeval", "async"), ("parfor", "async"),
               ("batch", "async"), ("timer", "callback")),
}
VALID_OUTCOMES = ("async", "join", "callback", "unknown")


def primitives_problems(primitives, languages, expected=None,
                        async_pairs=(), join_pairs=()):
    """五语言原语表：**逐条**比对期望表 + 查「多出来的」+ 查 async∩join。

    为什么要逐条（H4）：上一版只钉住 `await` 一条，20 条映射里另外 19 条
    改错（例如把 `pthread_join` 挪进 async）**不会有任何东西变红**。
    而「把 join 记成 async」正是这张表存在的全部理由。
    """
    exp = EXPECTED_OUTCOMES if expected is None else expected
    probs = []
    if not languages:
        probs.append("U2b 并发原语表没有任何语言 —— 空表")
    for lg in languages:
        rows = primitives.get(lg)
        if not rows:
            probs.append("U2b 语言 %s 的并发原语表为空（缺输入不得视为通过）" % lg)
            continue
        got = dict((t, o) for t, o, _n in rows)
        want = dict(exp.get(lg, ()))
        if not want:
            probs.append("U2b 期望表里没有语言 %s —— 期望表本身漏了"
                         "（判据的分母必须自证）" % lg)
        for tok in sorted(want):
            if tok not in got:
                probs.append("U2b %s 表里缺了 %r（期望结局 %s）"
                             % (lg, tok, want[tok]))
            elif got[tok] != want[tok]:
                probs.append("U2b %s/%s 的结局是 %r，期望 %r%s"
                             % (lg, tok, got[tok], want[tok],
                                "—— **join 记成 async 会让「谁先谁后」整体反向**"
                                if want[tok] == "join" else ""))
        for tok in sorted(set(got) - set(want)):
            probs.append("U2b %s 表里多出未审原语 %r（结局 %s）—— 新增原语"
                         "必须同时进期望表，否则它永不被告" % (lg, tok, got[tok]))
        for tok, outcome, _n in rows:
            if outcome not in VALID_OUTCOMES:
                probs.append("U2b %s/%s 的结局 %r 未登记" % (lg, tok, outcome))

    # 反向前提：汇合原语**不得**同时出现在「产出 async 边」的名单里
    # ⚠ 身份是 **(语言, 原语)** 这一对，不是语言名 —— 取错元素会让这个断言
    #   在真实仓库上恒真/恒假（本轮真踩到过：取语言名 ⇒ 交集恒非空）。
    a_set = set(tuple(x) for x in async_pairs)
    j_set = set(tuple(x) for x in join_pairs)
    both = sorted(a_set & j_set)
    if both:
        probs.append("U2b 同一个原语同时被算作 async 与 join：%s"
                     "（一个站点不能既发起又汇合 —— 这两条边方向相反）" % both)
    if not j_set:
        probs.append("U2b 汇合原语集合为空 —— 反向前提在空集上恒真"
                     "（§4h-2：反例不能是空集）")

    py = dict((t, o) for t, o, _n in primitives.get("py", ()))
    if "await" not in py:
        probs.append("U2b py 表里没有 'await' —— 汇合原语是全表最关键的一条")
    elif py["await"] != "join":
        probs.append("U2b py 表把 'await' 记成 %r —— 它必须是 'join'："
                     "await 等的是已存在的任务，本身不发起并行工作；"
                     "记成 async 会让「谁先谁后」整体反向" % py["await"])
    return probs


# ── U4：binhop 装置登记 ────────────────────────────────────────────────
def hop_device_problems(hop_devices, unregistered_fn, registered_fn):
    """登记表非空；未登记的 device 必须**被抓到**（不是默认放行）。"""
    probs = []
    if not hop_devices:
        probs.append("U4 HOP_DEVICES 为空 —— 空白登记表下「谁造的跳」无从追溯")
    got = unregistered_fn(["__no_such_device__"])
    if got != ["__no_such_device__"]:
        probs.append("U4 未登记的 device 没有被 unregistered_devices 抓到：%r"
                     "（判据在空转）" % (got,))
    if hop_devices and not any(registered_fn(x) for x in hop_devices):
        probs.append("U4 已登记的 device 一个都没被判为已登记（两向都不成立）")
    return probs


# ── U6：站点先行（**构造期**拒绝，不是事后审计）────────────────────────
def scheduling_precedence_problems(ug, make_graph=None, make_node=None,
                                   make_edge=None):
    """U6：构造期拒绝 —— 「站点先行」+ 「分母来源必须独立」。

    七条断言，缺一不可：
      ① 没额度 ⇒ **拒绝**（这是 H2 的解药：先造边后补站点必须写不出来）
      ② 有额度 ⇒ **通过**（正例：否则「一律拒绝」也能骗过 ①）
      ③ 额度**只能消费一次** ⇒ 同类第二条边必须再被拒
      ④ `declared_sites` **缺来源** ⇒ 拒绝（无来源的分母与 `all_site_count()`
         在判定器眼里无法区分，A1b 退化成恒真式）
      ⑤ 来源标为**非独立** ⇒ 拒绝 —— 这一条字面就是「拿派生量当独立分母」
         必须**写不出来**（R82b 黑帽 B1）
      ⑥ 来源**未登记** ⇒ 拒绝（拼错的标签会被静默采纳成「有来源」）
      ⑦ 独立来源 ⇒ **通过**（正例：否则「一律拒绝」也能骗过 ④⑤⑥）

    构造器可注入（本仓 §4o-4：「判据必须可注入」）—— 否则夹具拿不到
    一个「不检查额度的假图」，第 ①③ 条就无法两向自证。
    """
    mk_g = make_graph or ug.UnifiedGraph
    mk_n = make_node or ug.Node
    mk_e = make_edge or ug.Edge
    probs = []

    g = mk_g()
    g.add_node(mk_n("f:a.m", "file", "a.m"))
    g.add_node(mk_n("fn:a.m:foo", "function", "foo"))

    # ① 先造边（没有站点额度）⇒ 必须拒绝
    raised = False
    try:
        g.add_edge(mk_e("f:a.m", "fn:a.m:foo", "direct"))
    except ug.GraphError:
        raised = True
    if not raised:
        probs.append("U6 「站点先行」没有生效：没有站点额度时 add_edge "
                     "**照样接受** —— 先造边后补站点会让 A1a 退化成恒真式（H2）")

    # ② 正例：先 add_site 再 add_edge ⇒ 必须通过
    g.add_site("direct", 1)
    try:
        g.add_edge(mk_e("f:a.m", "fn:a.m:foo", "direct"))
    except ug.GraphError as e:
        probs.append("U6 正例被误拦：先 add_site 再 add_edge 应当通过，却抛了 %s" % e)

    # ③ 额度只能消费一次：另一类边（async 无站点）仍须被拒
    raised2 = False
    try:
        g.add_edge(mk_e("f:a.m", "fn:a.m:foo", "async"))
    except ug.GraphError:
        raised2 = True
    if not raised2:
        probs.append("U6 额度没有被消费：另一类没有站点的边仍被接受"
                     "（额度检查必须**按 kind** 而非全局）")

    # ④⑤⑥⑦ 分母的**来源标签**（三条拒绝 + 一条正例）──
    g2 = mk_g()
    for tag, args, why in (
            ("缺来源", (4,), "分母与 sites 表在判定器眼里无法区分"),
            ("非独立来源", (4, "sites_table"),
             "字面就是「拿派生量当独立分母」"),
            ("未登记来源", (4, "__no_such_source__"),
             "拼错的标签会被静默采纳成「有来源」")):
        raised = False
        try:
            g2.set_declared_sites(*args)
        except ug.GraphError:
            raised = True
        if not raised:
            probs.append("U6 declared_sites 的来源检查漏了【%s】⇒ 被采纳"
                         "（%s）" % (tag, why))
    got = g2.set_declared_sites(4, "file_axis")
    if got != 4:
        probs.append("U6 正例被误拦：独立来源 file_axis 应当通过，得到 %r"
                     % (got,))
    return probs


# ── U7：互转规则的验证分母 ─────────────────────────────────────────────
def rule_registry_problems(census, rule_ids, supported_ids, verified_ids):
    """纯函数（数据进、问题出）。

    U7 三条：
      ① 普查的分母必须等于真实规则数（不能自报一个好看的数）
      ② verified + unverified == total（三分必须构成**划分**，
         不许出现第 4 种去向 —— 「看不清」不得折进任何一边）
      ③ 「已支持」⊆「已验证」（H6 的正面修法）

    `supported_ids` **可注入**：它模拟的是「某份报告/CLI 声称支持了哪些规则」，
    真值在 `verified_ids`（来自 rules.py 登记表）。两者分开，判据才有对手方。
    """
    probs = []
    rule_ids = tuple(rule_ids)
    if not rule_ids:
        probs.append("U7 规则表为空 —— 空白登记表下「验证了什么」无从谈起")
        return probs
    if census.get("total") != len(rule_ids):
        probs.append("U7 验证普查的分母不对：census total=%r，真实规则 %d 条"
                     % (census.get("total"), len(rule_ids)))
    if census.get("verified", 0) + census.get("unverified", 0) != census.get("total"):
        probs.append("U7 三分不构成划分：verified %r + unverified %r != total %r"
                     "（「看不清」不得被折进任何一边）"
                     % (census.get("verified"), census.get("unverified"),
                        census.get("total")))
    stray = sorted(set(supported_ids) - set(verified_ids))
    if stray:
        probs.append("U7 未验证的规则被报成「已支持」：%s —— 未验证是一等状态，"
                     "不是通过" % stray)
    outside = sorted((set(supported_ids) | set(verified_ids)) - set(rule_ids))
    if outside:
        probs.append("U7 出现了不存在于规则表的 id：%s" % outside)
    return probs


# ── U3/U5：真跑守恒判定器（注入即破 / 往返无损）────────────────────────
# ── U8：匹配口径（**给口径本身配对手方**）──────────────────────────────
# 故意塞满前后缀的语料：每一条 token 都出现「真站点」与「子串陷阱」两种形态。
# 它是**夹具**，所以必须自己声明：这些 token 就是 U8 要裁决的那一批。
CALIBER_CORPUS = (
    "signal_struct x; signaling y; forked z; threads w; callbacks v;\n"
    "__future__ import; pthread_create(f); hThread = 1; std::thread t;\n"
)
CALIBER_TOKENS = ("signal", "fork", "thread", "callback", "pthread_create")


def matching_caliber_problems(sm, corpus=None, tokens=None):
    """U8：站点匹配的**口径**必须自洽（纯函数，可注入）。

    六条，各守一个失败模式：
      ① 两口径必须**真的不同** —— 读出一模一样时，词界化等于没做，
         而报告照样「通过」（这是本判据存在的理由，也是最该红的那一条）
      ② 三个**已知误报**必须被排除（`__future__` / `signaling` / `callbacks`）
         —— 不修的话「缺口规模」被系统性高估，而高估的方向恰好看不见
      ③ 驼峰必须**仍被命中**（`hThread` / `myThreadPool`）——
         口径修过头与没修一样坏，而且更隐蔽（它会静默删掉真站点）
      ④ 短语 / 命名空间 token 不许被一刀切词界化打死
         （`new Promise` 里没有「标识符边界」可言）
      ⑤ 两个词干族必须**不交**（否则桶归属依赖遍历顺序 ⇒ 静默取错）
      ⑥ 每族都必须**非空**（空族会让 `bucket_of` 恒返回 None，
         而「分不出桶」与「没有桶」读数相同）
    """
    probs = []
    text = CALIBER_CORPUS if corpus is None else corpus
    toks = CALIBER_TOKENS if tokens is None else tokens
    hint = sm.hint_regex()

    # ① 两口径必须真的不同
    cal = sm.compare_calibers(text, toks)
    if cal["substring"] == cal["wordbound"]:
        probs.append(
            "U8 两种口径的读数完全相同（各 %d）—— 词界化【没有生效】，"
            "口径对手方退化成了同一把尺子（这比不一致更坏：它看起来像量过了）"
            % cal["substring"])
    elif cal["delta"] <= 0:
        probs.append(
            "U8 子串口径没有多收任何东西（delta=%d）—— 在一份**故意塞满**"
            "前后缀陷阱的语料上，这不可能是真的" % cal["delta"])

    # ② 已知误报必须被排除
    for bad, why in (("__future__", "双下划线包裹：`future` 不是独立词"),
                     ("signaling", "后缀 -ing：`signal` 不是独立词"),
                     ("callbacks", "复数后缀：`callback` 不是独立词"),
                     ("forked", "后缀 -ed：`fork` 不是独立词")):
        if hint.search(bad):
            probs.append("U8 词界口径仍收进误报 %r（%s）—— 缺口规模会被系统性高估"
                         % (bad, why))

    # ③ 驼峰必须仍被命中
    for ok, why in (("hThread", "前缀驼峰（要左边界就会漏掉它）"),
                    ("myThreadPool", "带前缀的驼峰"),
                    ("spinLock", "spin_lock 的驼峰形态"),
                    ("asyncTask", "连写驼峰")):
        if not hint.search(ok):
            probs.append("U8 词界口径漏掉了真站点 %r（%s）—— 修过头与没修一样坏"
                         % (ok, why))

    # ④ 短语 / 命名空间 token 不许失配
    for tok, sample in (("new Promise", "new Promise(executor)"),
                        (".then(", "p.then(cb)"),
                        ("std::thread", "std::thread t;")):
        if sm.count_wordbound(sample, tok) < 1:
            probs.append("U8 短语/命名空间 token %r 在 %r 上失配 —— "
                         "词界化修过头（短语没有标识符边界可言）" % (tok, sample))

    # ⑤ 两族不交
    both = sorted(set(sm.ASYNC_STEMS) & set(sm.SYNC_STEMS))
    if both:
        probs.append("U8 词干族不交性被破坏：%s 同时在两族"
                     "（桶归属会依赖遍历顺序 ⇒ 静默取错）" % both)

    # ⑥ 两族非空
    for name, fam in (("ASYNC_STEMS", sm.ASYNC_STEMS),
                      ("SYNC_STEMS", sm.SYNC_STEMS)):
        if not fam:
            probs.append("U8 %s 为空 —— 空族让每个词都落不进桶，"
                         "而「分不出桶」与「没有桶」读数相同" % name)
    return probs


def _injection_probe(ug, hop_devices):
    """返回 dict：每个子探针的 (干净, 注入后) 问题列表。

    ⚠ 除被测那一维外**其余各维都必须保持干净**：否则 `startswith(tag)` 会被
    「别的维也在报」满足（§4k-3：反例必须**只**触发被测的那一条，本轮由
    `audit()` 里的 `stray` 断言把这件事锁死）。
    """
    out = {}
    clean = ug.conservation_problems(ug.demo_graph(), hop_devices)

    # A1a：往 edges 里 append 一条边（绕过 add_edge），站点与声明都不动
    g = ug.demo_graph()
    g.edges.append(ug.Edge("f:a.m", "fn:a.m:bar", "direct"))
    out["A1a"] = (clean, ug.conservation_problems(g, hop_devices))

    # A1a_restore：补上同类站点 **且** 同步声明量 ⇒ 必须重新归零。
    #   ⚠ 只补站点不同步声明 ⇒ A1b 会红（这正是第二个分母在起作用的证据，
    #   本轮落地时它当场抓到过一次）。
    g.add_site("direct", 1)
    # 声明量由**夹具自己数**（demo 的 4 条 + 本步补的 1 条 = 5），
    # **不能**写成 `g.all_site_count()` —— 那正是「拿派生量当独立分母」：
    # 值可能对，但来源是假的，而 A1b 的全部价值就在那个来源上。
    g.set_declared_sites(5, "file_axis")
    out["A1a_restore"] = (clean, ug.conservation_problems(g, hop_devices))

    # A1b：站点与边都对得上，但**声明量**故意少报 1（独立分母动手）
    g5 = ug.demo_graph()
    g5.set_declared_sites(3, "file_axis")        # demo 真值 4，故意少报 1
    out["A1b"] = (clean, ug.conservation_problems(g5, hop_devices))

    # A2：端点不存在（站点与声明**先**补齐，只留 A2 一维）
    g2 = ug.demo_graph()
    g2.add_site("direct", 1)
    g2.edges.append(ug.Edge("f:missing", "fn:a.m:foo", "direct"))
    g2.set_declared_sites(5, "file_axis")
    out["A2"] = (clean, ug.conservation_problems(g2, hop_devices))

    # A3：binhop 边用了未登记的装置（binhop 是合法的站点结局）
    g3 = ug.demo_graph()
    g3.add_site("binhop", 1)
    g3.edges.append(ug.Edge("f:a.m", "fn:a.m:foo", "binhop",
                            hop=ug.Hop("__no_such_device__")))
    g3.set_declared_sites(5, "file_axis")        # demo 的 4 条 + 本步补的 binhop 1 条
    out["A3"] = (clean, ug.conservation_problems(g3, hop_devices))

    # A4：同一条边造两遍
    g4 = ug.demo_graph()
    g4.add_site("direct", 1)
    g4.edges.append(ug.Edge("f:a.m", "fn:a.m:foo", "direct"))
    g4.set_declared_sites(5, "file_axis")
    out["A4"] = (clean, ug.conservation_problems(g4, hop_devices))
    return out


def roundtrip_problems(ug):
    """to_dict → from_dict 后，节点、边与声明量必须逐条等价。"""
    g = ug.demo_graph()
    try:
        g2 = ug.UnifiedGraph.from_dict(g.to_dict())
    except Exception as e:                      # 判据要能报出问题
        return ["U5 往返抛异常：%s" % e]
    probs = []
    if sorted(g.nodes) != sorted(g2.nodes):
        probs.append("U5 往返后节点集合变了：%s → %s"
                     % (sorted(g.nodes), sorted(g2.nodes)))
    if [(e.src, e.dst, e.kind) for e in g.edges] != \
       [(e.src, e.dst, e.kind) for e in g2.edges]:
        probs.append("U5 往返后边集合变了")
    if dict(g.site_census()) != dict(g2.site_census()):
        probs.append("U5 往返后站点结局分布变了：%s → %s"
                     % (g.site_census(), g2.site_census()))
    if getattr(g, "declared_sites", None) != getattr(g2, "declared_sites", None):
        probs.append("U5 往返后 declared_sites 漂移：%r → %r"
                     % (getattr(g, "declared_sites", None),
                        getattr(g2, "declared_sites", None)))
    for e1, e2 in zip(g.edges, g2.edges):
        if (e1.hop is None) != (e2.hop is None):
            probs.append("U5 往返后 hop 有无漂移：%s" % (e1.key(),))
        elif e1.hop is not None and e1.hop.to_dict() != e2.hop.to_dict():
            probs.append("U5 往返后 hop 内容漂移：%s" % (e1.key(),))
    return probs


def audit(ug, bh, cc, sm, tr):
    """返回问题列表（空 = 干净）。缺模块由调用方先拦。"""
    probs = []
    probs += model_shape_problems(ug.NODE_KINDS, ug.EDGE_KINDS, ug.SITE_OUTCOMES,
                                  ug.NON_EDGE_OUTCOMES, ug.EDGE_PRODUCING_OUTCOMES)
    probs += t1_premise_problems(ug.EDGE_KINDS, ug.SITE_OUTCOMES)
    probs += primitives_problems(cc.PRIMITIVES, cc.LANGUAGES,
                                 async_pairs=cc.async_tokens(),
                                 join_pairs=cc.join_tokens())
    probs += hop_device_problems(bh.HOP_DEVICES, bh.unregistered_devices,
                                 bh.is_registered)
    probs += scheduling_precedence_problems(ug)
    probs += rule_registry_problems(tr.verification_census(), tr.rule_ids(),
                                    tr.supported_rule_ids(),
                                    tr.verified_rule_ids())
    probs += matching_caliber_problems(sm)

    # U3：注入即破（R82-0-2 验收判据的**执行版**）
    probe = _injection_probe(ug, bh.HOP_DEVICES)
    for tag in sorted(probe):
        clean, injected = probe[tag]
        if clean:
            probs.append("U3 子探针 %s：干净图竟然不守恒 %s" % (tag, clean))
            continue
        if tag.endswith("_restore"):
            if injected:
                probs.append("U3 %s 还原失败：补上站点与声明后仍不守恒 %s"
                             % (tag, injected))
            continue
        if not injected:
            probs.append("U3 子探针 %s：注入后**仍判守恒** —— 判据在空转" % tag)
            continue
        # 反例只许触发被测那一维（§4k-3）
        stray = [p for p in injected if not p.startswith(tag)]
        if stray:
            probs.append("U3 子探针 %s 污染了别的维：%s"
                         "（反例必须**只**触发被测的那一条）" % (tag, stray))
        if not any(p.startswith(tag) for p in injected):
            probs.append("U3 子探针 %s：注入后报的是别的问题 %s"
                         "（判据没打在它那一维）" % (tag, injected))

    probs += roundtrip_problems(ug)
    return probs


class _LaxSM(object):
    """U8 的**变异体**：接住真模块，只改一处 —— 用来证明每条断言能被打红。

    `bound=""` 把词界边界去掉（词界退化成子串）；
    `async_extra` 往异步族里塞词干（制造两族相交）；
    `sync=()` 把同步族清空。
    """

    def __init__(self, sm, bound=None, async_extra=(), sync=None):
        self._sm = sm
        self._bound = bound
        self._async_extra = tuple(async_extra)
        self._sync = sync
        for name in ("count_substring", "count_wordbound",
                     "hint_regex", "split_hints", "bucket_of", "stem_regex",
                     "camel", "namespace_parts", "ident_part", "is_phrase",
                     "known_stems_by_lang", "token_regex", "bucket_totals"):
            setattr(self, name, getattr(sm, name))
        self.BUCKET_ASYNC = sm.BUCKET_ASYNC
        self.BUCKET_SYNC = sm.BUCKET_SYNC
        self.HINT_BUCKETS = sm.HINT_BUCKETS
        self.SYNC_STEMS = sm.SYNC_STEMS if sync is None else tuple(sync)
        self.ASYNC_STEMS = tuple(sm.ASYNC_STEMS) + self._async_extra

    def hint_regex(self):
        return self._sm.stem_regex(tuple(self.ASYNC_STEMS)
                                   + tuple(self.SYNC_STEMS))

    def compare_calibers(self, text, tokens):
        """`bound=""` 时把词界**退化成子串** —— 用来打红 ①（口径未生效）。

        ⚠ 变异要**只**作用于这一维：`hint_regex` 不动，所以 ②③ 保持原样。
        若两维一起变异，`expect(..., True)` 会被别的维的报错满足（§4k-3）。
        """
        if self._bound is None:
            return self._sm.compare_calibers(text, tokens)
        per = {}
        sub = wb = 0
        for t in tokens:
            a = text.count(t)
            b = text.count(t)          # 退化：词界 == 子串
            per[t] = {"substring": a, "wordbound": b}
            sub += a
            wb += b
        return {"substring": sub, "wordbound": wb, "delta": sub - wb,
                "per_token": per}


def _selftest():
    """两向自证：好样本必须放行，坏样本必须抓到，且**每条判据都被触发过**。"""
    loaded = _load()
    if loaded is None:
        print("SELFTEST 无法自证：导不到 unified_graph / binhops / concurrency / "
              "translate.rules")
        return 2
    ug, bh, cc, sm, tr = loaded

    bad = good = 0
    fails = []

    def expect(tag, probs, want_problem):
        nonlocal bad, good
        ok = bool(probs) == want_problem
        label = "反例" if want_problem else "正例"
        print("  [%s] %-46s -> %s%s"
              % (label, tag, "抓到" if probs else "放行",
                 "" if ok else "   *** 不符预期 ***"))
        if not ok:
            fails.append(tag)
        if want_problem:
            bad += 1
        else:
            good += 1

    # ── 正例：真实仓库必须干净 ──
    expect("真实仓库（U1–U8 全量）", audit(ug, bh, cc, sm, tr), False)
    expect("守恒判定器：干净 demo 图",
           ug.conservation_problems(ug.demo_graph(), bh.HOP_DEVICES), False)

    # ── 反例：U1 形状 ──
    expect("U1 NODE_KINDS 为空",
           model_shape_problems((), ug.EDGE_KINDS, ug.SITE_OUTCOMES,
                                ug.NON_EDGE_OUTCOMES, ug.EDGE_PRODUCING_OUTCOMES),
           True)
    expect("U1 EDGE_KINDS 有重复",
           model_shape_problems(ug.NODE_KINDS, ug.EDGE_KINDS + ("direct",),
                                ug.SITE_OUTCOMES, ug.NON_EDGE_OUTCOMES,
                                ug.EDGE_PRODUCING_OUTCOMES), True)
    expect("U1 边种类没进站点结局（binhop 那次真实事故）",
           model_shape_problems(ug.NODE_KINDS, ug.EDGE_KINDS,
                                ("direct", "async", "join", "unknown"),
                                ug.NON_EDGE_OUTCOMES, ug.EDGE_PRODUCING_OUTCOMES),
           True)
    expect("U1 EDGE_PRODUCING 不是派生量",
           model_shape_problems(ug.NODE_KINDS, ug.EDGE_KINDS, ug.SITE_OUTCOMES,
                                ug.NON_EDGE_OUTCOMES, tuple(ug.SITE_OUTCOMES)), True)

    # ── 反例：U2 T1 前提 ──
    expect("U2 删掉 async 边种类",
           t1_premise_problems(tuple(k for k in ug.EDGE_KINDS if k != "async"),
                               ug.SITE_OUTCOMES), True)
    expect("U2 删掉 unknown 站点结局",
           t1_premise_problems(ug.EDGE_KINDS,
                               tuple(k for k in ug.SITE_OUTCOMES if k != "unknown")),
           True)
    expect("U2 删掉 join 站点结局",
           t1_premise_problems(ug.EDGE_KINDS,
                               tuple(k for k in ug.SITE_OUTCOMES if k != "join")),
           True)

    # ── 反例：U2b 逐条映射（每条都要有**能单独打红它**的变异）──
    def _cc_with(lang, tok, outcome):
        rows = tuple((t, outcome if t == tok else o, n)
                     for t, o, n in cc.PRIMITIVES[lang])
        return dict(cc.PRIMITIVES, **{lang: rows})

    def _cc_drop(lang, tok):
        rows = tuple((t, o, n) for t, o, n in cc.PRIMITIVES[lang] if t != tok)
        return dict(cc.PRIMITIVES, **{lang: rows})

    def _cc_add(lang, extra, outcome):
        return dict(cc.PRIMITIVES,
                    **{lang: cc.PRIMITIVES[lang] + ((extra, outcome, ""),)})

    def _u2b(prims, a=None, j=None):
        return primitives_problems(prims, cc.LANGUAGES,
                                   async_pairs=cc.async_tokens() if a is None else a,
                                   join_pairs=cc.join_tokens() if j is None else j)

    expect("U2b py 表把 await 记成 async",
           _u2b(_cc_with("py", "await", "async")), True)
    expect("U2b c 表把 pthread_join 记成 async（**H4 的原缺口**）",
           _u2b(_cc_with("c", "pthread_join", "async")), True)
    expect("U2b cpp 表把 std::future 记成 async",
           _u2b(_cc_with("cpp", "std::future", "async")), True)
    expect("U2b matlab 表把 parfor 记成 callback",
           _u2b(_cc_with("matlab", "parfor", "callback")), True)
    expect("U2b js 表删掉 setTimeout（期望表里的缺失）",
           _u2b(_cc_drop("js", "setTimeout")), True)
    expect("U2b 表里多出未审原语",
           _u2b(_cc_add("matlab", "spmd", "async")), True)
    expect("U2b 某语言表为空",
           _u2b(dict(cc.PRIMITIVES, js=())), True)
    expect("U2b 同一原语同时算 async 与 join",
           _u2b(cc.PRIMITIVES,
                a=list(cc.async_tokens()) + [("py", "await")],
                j=cc.join_tokens()), True)
    expect("U2b 汇合集合为空（反例不能是空集）",
           _u2b(cc.PRIMITIVES, j=()), True)

    # ── 反例：U4 装置登记 ──
    expect("U4 HOP_DEVICES 为空",
           hop_device_problems({}, bh.unregistered_devices, bh.is_registered), True)
    expect("U4 unregistered_devices 被改成空转",
           hop_device_problems(bh.HOP_DEVICES, lambda ids: [], lambda d: True), True)

    # ── U6 站点先行：正例 + 反例（假图**不检查额度**）──
    expect("U6 真实模型：站点先行三条全过",
           scheduling_precedence_problems(ug), False)

    class _LaxGraph(object):
        """假图：add_edge **不检查站点额度** —— 用来证明 U6 能被打红。"""

        def __init__(self):
            self.nodes = {}
            self.sites = {}
            self.edges = []

        def add_node(self, n):
            self.nodes[n.nid] = n

        def add_site(self, k, n=1):
            self.sites[k] = self.sites.get(k, 0) + int(n)

        def add_edge(self, e):
            self.edges.append(e)

        def set_declared_sites(self, n, source=None):
            """假图**也不检查来源** —— 让 U6 的 ④⑤⑥ 能被打红。"""
            self.declared_sites = n
            return n

    expect("U6 假图不检查额度 ⇒ 必须被抓到",
           scheduling_precedence_problems(ug, make_graph=_LaxGraph), True)

    # ── U7 验证分母：正例 + 三种反例 ──
    expect("U7 真实登记表：三分成划分且 supported ⊆ verified",
           rule_registry_problems(tr.verification_census(), tr.rule_ids(),
                                  tr.supported_rule_ids(), tr.verified_rule_ids()),
           False)
    expect("U7 未验证的规则被报成「已支持」",
           rule_registry_problems(
               tr.verification_census(), tr.rule_ids(),
               tuple(tr.rule_ids()),                       # 谎报：全部「已支持」
               tr.verified_rule_ids()), True)
    expect("U7 三分不构成划分（分母对不上）",
           rule_registry_problems({"total": len(tr.RULES), "verified": 0,
                                   "unverified": 0},
                                  tr.rule_ids(), (), ()), True)
    expect("U7 普查分母自报了一个好看的小数",
           rule_registry_problems({"total": 1, "verified": 1, "unverified": 0},
                                  tr.rule_ids(), (), tr.rule_ids()[:1]), True)

    # ── U8 匹配口径：正例 + 反例（每条都要有**能单独打红它**的变异）──
    expect("U8 真实口径：两口径真的不同、误报被排除、驼峰仍命中",
           matching_caliber_problems(sm), False)
    expect("U8 词界退化回子串（边界被去掉）⇒ 必须抓到",
           matching_caliber_problems(
               _LaxSM(sm, bound=""), corpus=CALIBER_CORPUS,
               tokens=CALIBER_TOKENS), True)
    expect("U8 词干族相交 ⇒ 必须抓到",
           matching_caliber_problems(
               _LaxSM(sm, async_extra=("lock",))), True)
    expect("U8 某一族为空 ⇒ 必须抓到",
           matching_caliber_problems(_LaxSM(sm, sync=())), True)
    buckets, unclassified = sm.split_hints(
        {"hThread": 3, "pthreadMutex": 2})
    expect("U8 分桶对真命中是**划分**（不完备项为空）",
           [] if (not unclassified
                  and buckets[sm.BUCKET_ASYNC].get("hThread") == 3
                  and buckets[sm.BUCKET_SYNC].get("pthreadMutex") == 2)
           else ["x"], False)
    buckets2, unclassified2 = sm.split_hints(
        {"hThread": 3, "NotAStem": 5})
    expect("U8 分桶不完备时必须**报出来**（不许静默丢）",
           unclassified2 if unclassified2 == ["NotAStem"] else ["y"], True)

    # ── 反例：U3 注入即破（逐维）+ 还原 ──
    probe = _injection_probe(ug, bh.HOP_DEVICES)
    for tag in ("A1a", "A1b", "A2", "A3", "A4"):
        _c, injected = probe[tag]
        expect("U3 注入 %s 必须被守恒判定器抓到" % tag, injected, True)
        expect("U3 %s 不得污染别的维" % tag,
               [p for p in injected if not p.startswith(tag)], False)
    _c, restored = probe["A1a_restore"]
    expect("U3 A1a 补站点+同步声明后必须重新守恒", restored, False)

    # ── 反例：U5 往返漂移 ──
    g = ug.demo_graph()
    d = g.to_dict()
    d["edges"][0]["kind"] = "dynamic"         # 伪造：direct 被改成 dynamic
    got = [(e.src, e.dst, e.kind) for e in ug.UnifiedGraph.from_dict(d).edges]
    want = [(e.src, e.dst, e.kind) for e in g.edges]
    expect("U5 往返后边集合漂移", ["x"] if got != want else [], True)

    d2 = ug.demo_graph().to_dict()
    d2["declared_sites"] = (d2.get("declared_sites") or 0) + 7
    got2 = getattr(ug.UnifiedGraph.from_dict(d2), "declared_sites", None)
    want2 = getattr(ug.demo_graph(), "declared_sites", None)
    expect("U5 往返后 declared_sites 漂移", ["x"] if got2 != want2 else [], True)

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    if fails:
        print("SELFTEST FAILED: %s" % fails)
        return 1
    print("SELFTEST PASSED")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="两向自证")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    loaded = _load()
    if loaded is None:
        print("check_unified_graph: 导不到 unified_graph / binhops / concurrency / "
              "site_matching / translate.rules（缺输入 → 红）")
        return 2
    ug, bh, cc, sm, tr = loaded
    probs = audit(ug, bh, cc, sm, tr)
    if probs:
        print("check_unified_graph: %d 项违规" % len(probs))
        for p in probs:
            print("  - " + p)
        return 1
    print("check_unified_graph: OK（统一图恒等式 + 三张登记表自洽 + 站点先行生效 "
          "+ 匹配口径两向；判据族 %s）" % ROW_SIGNATURE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
