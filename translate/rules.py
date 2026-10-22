# -*- coding: utf-8 -*-
"""C ↔ MATLAB 互转的**规则表** —— R82/T4 的单一事实源（R82-0-4 骨架）。

R82 白帽实测（§2.2）：`matlab2c` / `c2matlab` / `mexFunction` 全 **0** 命中；
`转换` 30 处**全是 MATLAB 类型转换函数**（`cast`/`int8`…），`translate` 4 处
**全是 SVG transform** ⇒ 本仓**没有任何代码翻译能力**。T4 从这张表开始。

一图看懂（规则表在链路里的位置，R82 §7.5）：

    源码 ──▶ ① 确定性段（零 AI）──▶ {mapped | unmapped}
                  │  命中规则就必须**引用规则 ID**；
                  │  没有规则能命中 ⇒ 进 unmapped（**不是猜一个翻译**）
                  ▼
              ② AI 段（只吃 unmapped）──▶ 补丁草稿
                  │
                  ▼
              ③ 双语对照执行器 ──▶ verified | unverified（**默认 unverified**）

本表的**对手方**（护栏 `tools/check_unified_graph.py` 的 U7 钉住 ——
⚠ 此处曾写成 `tools/check_translate_rules.py`，那个文件**不存在**：
一个指空的指针看起来完全正常，因为它没写错任何东西）：
  * B1  命中了**未登记**的规则 ID ⇒ 红（不许发明规则）
  * B2  登记了却**从未命中**的规则 ⇒ 红（陈旧声明）
  * B3  ID 重复 ⇒ 红
  * U7  **验证分母**：三分必须构成划分，且「已支持」⊆「已验证」
        （`verified_by` 为空 ⇒ **不得**以「已支持」出现）

规则条目字段（最小集）：
    id            唯一，形如 `IDX-1`
    from_ / to_  语义两端，形如 `matlab:1-based` / `c:0-based`
    note          一句话说清差异
    verified_by   哪组夹具/测试能证明它。**空 = 未验证**，是一等状态：
                  它可以存在、必须可枚举、**不得**被当成「已支持」
                  （`verification_census()` 报它的分母；Phase D 收敛它）
"""

RULES_VERSION = "1.0"

# 表本身。Phase 0 收录**四类真实语义差异**（R82 §9 把这一块交给 deep-research
# 做多源交叉验证）；Phase D 会按需扩张，并逐条补 verified_by。
RULES = (
    {"id": "IDX-1",
     "from_": "matlab:1-based", "to_": "c:0-based",
     "note": "索引基准：MATLAB 从 1 起，C 从 0 起 ⇒ 下标表达式整体 -1",
     "verified_by": "translate/golden/op_index_2d_linear.json"},
    {"id": "ORDER-1",
     "from_": "matlab:column-major", "to_": "c:row-major",
     "note": "内存序：MATLAB 列主序，C 行主序 ⇒ 线性下标换算需转置语义",
     "verified_by": "translate/golden/op_index_2d_linear.json,"
                    "translate/golden/op_sum_2d.json"},
    {"id": "EXPAND-1",
     "from_": "matlab:implicit-expansion", "to_": "c:explicit-loop",
     "note": "隐式扩展：MATLAB 单例维度自动广播，C 需显式循环或扩容拷贝",
     "verified_by": "translate/golden/op_add_broadcast_2d.json"},
    {"id": "INT-1",
     "from_": "matlab:double-default", "to_": "c:int-overflow",
     "note": "数值语义：MATLAB 默认 double 且整数运算饱和/回绕规则不同，"
             "C 的整型溢出是未定义行为",
     "verified_by": ""},
)


def rule_ids(rules=None):
    """登记的全部规则 ID（保持出现顺序、去重）。"""
    out = []
    for r in (RULES if rules is None else rules):
        if r["id"] not in out:
            out.append(r["id"])
    return out


def verified_rule_ids(rules=None):
    """**已验证**的规则 ID（`verified_by` 非空）。派生量。"""
    return tuple(r["id"] for r in (RULES if rules is None else rules)
                 if r.get("verified_by"))


def unverified_rule_ids(rules=None):
    """**未验证**的规则 ID。它是**一等状态**，不是缺陷 —— 但必须可见、
    必须有分母（R82 §5.4：「未验证」的度量是它的**分母与可见性**，
    不是它的**消失**）。"""
    return tuple(r["id"] for r in (RULES if rules is None else rules)
                 if not r.get("verified_by"))


def verification_census(rules=None):
    """验证状态的**三分普查**（H6 的分母）。派生量，绝不手写。

    `verified + unverified == total` 必须成立 —— 判据（U7）会断言这一点：
    「看不清」不得被折进任何一边（判据设计纪律 #3）。
    """
    rs = list(RULES if rules is None else rules)
    v = [r for r in rs if r.get("verified_by")]
    return {"total": len(rs), "verified": len(v),
            "unverified": len(rs) - len(v)}


def supported_rule_ids(rules=None, claimed=None):
    """**「已支持」的规则** —— 判定口径写在这里，且只有一处。

    口径：`已支持 == 已验证`。未验证的规则**不得**出现在这个集合里。
    `claimed` 可注入：它模拟「某份报告/CLI 声称支持了哪些规则」，
    用来给 U7 造反例（谎报 ⇒ 红）。
    """
    if claimed is not None:
        return tuple(claimed)
    return verified_rule_ids(rules)


def rule_problems(rules=None, hit_ids=(), used_ids=None):
    """纯函数：规则表的**两向**对手方。空 = 干净。**不抛异常**（要能报出问题）。

    B1 命中了未登记的 ID     —— 「不许发明规则」
    B2 登记了却从未命中      —— 「陈旧声明」（只在给出 used_ids 时才判，
                                因为「本轮没用到」≠「永远用不到」）
    B3 ID 重复               —— 归一化的代价必须显式付（R82 §4m-3）
    """
    rules = RULES if rules is None else rules
    probs = []
    known = []
    for r in rules:
        rid = r.get("id", "")
        if not rid:
            probs.append("B3 有一条规则没有 id")
            continue
        if rid in known:
            probs.append("B3 规则 ID 重复：%s" % rid)
        known.append(rid)

    known_set = set(known)
    for hid in hit_ids:
        if hid not in known_set:
            probs.append("B1 命中了未登记的规则 ID %r（不许发明规则）" % hid)

    if used_ids is not None:
        used = set(used_ids)
        for rid in known:
            if rid not in used:
                probs.append("B2 规则 %s 登记了却从未命中（陈旧声明）" % rid)
    return probs


def census(rules=None):
    """按前缀分组的直方图（`IDX` / `ORDER` / …）—— **派生量**。"""
    buckets = {}
    for rid in rule_ids(rules):
        p = rid.split("-", 1)[0]
        buckets[p] = buckets.get(p, 0) + 1
    return buckets
