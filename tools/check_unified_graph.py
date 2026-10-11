# -*- coding: utf-8 -*-
"""登记制静态护栏：统一图模型的**四条恒等式** + T1 的图前提（R82-0-3）。

R82 方案 §11/1 说 Phase 0 是「唯一不做就白做的一步」—— 因为 T1–T4 都要往
同一张图上加东西。但「先立模型」这句话本身**没有对手方**：模型写完没人知道
它守没守住。本门就是它的对手方，判据族 **U1–U5**。

一图看懂（每条判据拦什么）：

    U1  单一事实源形状          三张表非空、无重复；且
                                EDGE_KINDS == EDGE_PRODUCING_OUTCOMES
                                == SITE_OUTCOMES − NON_EDGE_OUTCOMES
                                （**两张表各写一份必然漂移** —— 建门时真撞到过）
    U2  T1 的图前提             async / callback ∈ EDGE_KINDS；
                                unknown **与** join ∈ SITE_OUTCOMES；
                                五语言并发表非空，且 **await 是 join 不是 async**
    U3  **注入一条边即破**      真造图、真跑 conservation_problems：
                                干净图 0 问题；注入一条边 ⇒ A1 红；
                                补上对应站点 ⇒ 又归零（证明判据抓的是恒等式本身，
                                不是「有边就算坏」）。另含 A2 / A3 / A4 子探针。
    U4  binhop 装置登记         未登记的 via_device ⇒ A3 红
    U5  序列化往返              from_dict(to_dict(g)) 与原图逐节点逐边等价

为什么 U3 是本门的心脏：R82-0-2 的验收判据字面就是「**注入一条边即破**」。
把这句话写成注释是**没有对手方**的；把它写成一条**真跑**的探针，它才是判据
（本仓纪律 §4k-2：「一个从未被触发的分支不是判据」）。

用法：
    python tools/check_unified_graph.py            # 检查仓库 0=干净 1=有违规 2=缺输入
    python tools/check_unified_graph.py --selftest # 两向自证

退出码：
    0  = 模型形状合法、T1 前提在场、守恒判定器两向成立、装置登记两向、往返无损
    1  = 有违规（形状非法 / 前提缺失 / 守恒判定器抓不到注入 / 未登记装置 / 往返漂移）
    2  = 缺输入（导不到 unified_graph / binhops / concurrency —— 缺输入 → 红）
"""
import argparse
import os
import sys

# R62/P5：「质量门表」里本门那一行的**签名**。它必须逐字出现在两处：
#   ① 本门的成功行（下面 main() 打印的那一行）；
#   ② README.md / README_CN.md 里本门那一行。
# 对手方 = tools/check_readme_parity.py 的 P5（表行内容 ⇄ 门）。
ROW_SIGNATURE = "U1–U5"

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _load():
    """导入三个被测模块。任何一个导不到 ⇒ 缺输入（返回 None）。"""
    try:
        import unified_graph as ug
        import binhops as bh
        import concurrency as cc
    except ImportError:
        return None
    return ug, bh, cc


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
                     "无法被 A1 计账（得到 %s vs %s）"
                     % (list(edge_kinds), list(edge_producing)))
    return probs


# ── U2：T1 的图前提 + 并发表的区分 ──────────────────────────────────────
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


def primitives_problems(primitives, languages):
    """五语言表非空；且 `await` 必须是 **join**（不是 async）。"""
    probs = []
    if not languages:
        probs.append("U2 并发原语表没有任何语言 —— 空表")
    for lg in languages:
        rows = primitives.get(lg)
        if not rows:
            probs.append("U2 语言 %s 的并发原语表为空（缺输入不得视为通过）" % lg)
            continue
        for tok, outcome, _note in rows:
            if outcome not in ("async", "join", "callback", "unknown"):
                probs.append("U2 %s/%s 的结局 %r 未登记" % (lg, tok, outcome))
    py = dict((t, o) for t, o, _n in primitives.get("py", ()))
    if "await" not in py:
        probs.append("U2 py 表里没有 'await' —— 汇合原语是全表最关键的一条")
    elif py["await"] != "join":
        probs.append("U2 py 表把 'await' 记成 %r —— 它必须是 'join'："
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


# ── U3/U5：真跑守恒判定器（注入即破 / 往返无损）────────────────────────
def _injection_probe(ug, hop_devices):
    """返回 dict：每个子探针的 (干净, 注入后) 问题列表。"""
    out = {}
    clean = ug.conservation_problems(ug.demo_graph(), hop_devices)

    # A1：直接往 edges 里 append 一条边（绕过 add_edge），站点不动
    g = ug.demo_graph()
    g.edges.append(ug.Edge("f:a.m", "fn:a.m:bar", "direct"))
    out["A1"] = (clean, ug.conservation_problems(g, hop_devices))
    # A1-restore：补上对应站点 ⇒ 必须重新归零
    g.add_site("direct", 1)
    out["A1_restore"] = (clean, ug.conservation_problems(g, hop_devices))

    # A2：端点不存在
    g2 = ug.demo_graph()
    g2.edges.append(ug.Edge("f:missing", "fn:a.m:foo", "direct"))
    g2.add_site("direct", 1)
    out["A2"] = (clean, ug.conservation_problems(g2, hop_devices))

    # A3：binhop 边用了未登记的装置（binhop 现在是合法的站点结局）
    g3 = ug.demo_graph()
    g3.edges.append(ug.Edge("f:a.m", "fn:a.m:foo", "binhop",
                            hop=ug.Hop("__no_such_device__")))
    g3.add_site("binhop", 1)
    out["A3"] = (clean, ug.conservation_problems(g3, hop_devices))

    # A4：同一条边造两遍
    g4 = ug.demo_graph()
    g4.edges.append(ug.Edge("f:a.m", "fn:a.m:foo", "direct"))
    g4.add_site("direct", 1)
    out["A4"] = (clean, ug.conservation_problems(g4, hop_devices))
    return out


def roundtrip_problems(ug):
    """to_dict → from_dict 后，节点与边必须逐条等价（顺序也算）。"""
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
    for e1, e2 in zip(g.edges, g2.edges):
        if (e1.hop is None) != (e2.hop is None):
            probs.append("U5 往返后 hop 有无漂移：%s" % (e1.key(),))
        elif e1.hop is not None and e1.hop.to_dict() != e2.hop.to_dict():
            probs.append("U5 往返后 hop 内容漂移：%s" % (e1.key(),))
    return probs


def audit(ug, bh, cc):
    """返回问题列表（空 = 干净）。缺模块由调用方先拦。"""
    probs = []
    probs += model_shape_problems(ug.NODE_KINDS, ug.EDGE_KINDS, ug.SITE_OUTCOMES,
                                  ug.NON_EDGE_OUTCOMES, ug.EDGE_PRODUCING_OUTCOMES)
    probs += t1_premise_problems(ug.EDGE_KINDS, ug.SITE_OUTCOMES)
    probs += primitives_problems(cc.PRIMITIVES, cc.LANGUAGES)
    probs += hop_device_problems(bh.HOP_DEVICES, bh.unregistered_devices,
                                 bh.is_registered)

    # U3：注入即破（这是 R82-0-2 验收判据的**执行版**）
    probe = _injection_probe(ug, bh.HOP_DEVICES)
    for tag in sorted(probe):
        clean, injected = probe[tag]
        if clean:
            probs.append("U3 子探针 %s：干净图竟然不守恒 %s" % (tag, clean))
            continue
        if tag == "A1_restore":
            if injected:
                probs.append("U3 A1 还原失败：补上站点后仍不守恒 %s" % injected)
            continue
        if not injected:
            probs.append("U3 子探针 %s：注入后**仍判守恒** —— 判据在空转" % tag)
        elif not any(p.startswith(tag) for p in injected):
            probs.append("U3 子探针 %s：注入后报的是别的问题 %s"
                         "（判据没打在它那一维）" % (tag, injected))

    probs += roundtrip_problems(ug)
    return probs


def _selftest():
    """两向自证：好样本必须放行，坏样本必须抓到，且**每条判据都被触发过**。"""
    loaded = _load()
    if loaded is None:
        print("SELFTEST 无法自证：导不到 unified_graph / binhops / concurrency")
        return 2
    ug, bh, cc = loaded

    bad = good = 0
    fails = []

    def expect(tag, probs, want_problem):
        nonlocal bad, good
        ok = bool(probs) == want_problem
        label = "反例" if want_problem else "正例"
        print("  [%s] %-44s -> %s%s"
              % (label, tag, "抓到" if probs else "放行",
                 "" if ok else "   *** 不符预期 ***"))
        if not ok:
            fails.append(tag)
        if want_problem:
            bad += 1
        else:
            good += 1

    # ── 正例：真实仓库必须干净 ──
    expect("真实仓库（U1–U5 全量）", audit(ug, bh, cc), False)
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
    expect("U2 py 表把 await 记成 async",
           primitives_problems(
               dict(cc.PRIMITIVES,
                    py=tuple(("await", "async", "x") if t == "await"
                             else (t, o, n) for t, o, n in cc.PRIMITIVES["py"])),
               cc.LANGUAGES), True)
    expect("U2 某语言表为空",
           primitives_problems(dict(cc.PRIMITIVES, js=()), cc.LANGUAGES), True)

    # ── 反例：U4 装置登记 ──
    expect("U4 HOP_DEVICES 为空",
           hop_device_problems({}, bh.unregistered_devices, bh.is_registered), True)
    expect("U4 unregistered_devices 被改成空转",
           hop_device_problems(bh.HOP_DEVICES, lambda ids: [], lambda d: True), True)

    # ── 反例：U3 注入即破（逐维）+ 还原 ──
    probe = _injection_probe(ug, bh.HOP_DEVICES)
    for tag in ("A1", "A2", "A3", "A4"):
        _c, injected = probe[tag]
        expect("U3 注入 %s 必须被守恒判定器抓到" % tag, injected, True)
    _c, restored = probe["A1_restore"]
    expect("U3 A1 补上站点后必须重新守恒", restored, False)

    # ── 反例：U5 往返漂移 ──
    g = ug.demo_graph()
    d = g.to_dict()
    d["edges"][0]["kind"] = "dynamic"         # 伪造：direct 被改成 dynamic
    got = [(e.src, e.dst, e.kind) for e in ug.UnifiedGraph.from_dict(d).edges]
    want = [(e.src, e.dst, e.kind) for e in g.edges]
    expect("U5 往返后边集合漂移", ["x"] if got != want else [], True)

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
        print("check_unified_graph: 导不到 unified_graph / binhops / concurrency"
              "（缺输入 → 红）")
        return 2
    ug, bh, cc = loaded
    probs = audit(ug, bh, cc)
    if probs:
        print("check_unified_graph: %d 项违规" % len(probs))
        for p in probs:
            print("  - " + p)
        return 1
    print("check_unified_graph: OK（统一图四条恒等式 + T1 图前提全绿；"
          "判据族 %s）" % ROW_SIGNATURE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
