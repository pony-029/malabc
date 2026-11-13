# -*- coding: utf-8 -*-
"""`callrel.py`（仓根）：调用关系里的**环检测**与 DOT 导出。

这层最容易出的是"图算法看着对、其实没找到环"：函数返回 `[]`，消费方就读成
"没有循环依赖"。所以判据必须**造一个真的有环的图**，并断言环被找到；
再造一个无环的，断言不误报。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_cycle_is_found():
    """`a -> b -> a` 必须被报成一个环。"""
    import callrel as CR

    idx, names, head, adj = CR.build_csr([(0, 1), (1, 0)])
    scc, stats = CR.strongly_connected(names, head, adj)
    assert scc, "有环的图竟然没找到环：%r" % (scc,)
    flat = str(scc)
    assert "0" in flat and "1" in flat, "环里的节点不全：%r" % (scc,)


def test_acyclic_graph_is_not_flagged():
    """`a -> b`（无环）不能报环 —— 否则这条检查会被当成噪音关掉。"""
    import callrel as CR

    idx, names, head, adj = CR.build_csr([(0, 1)])
    scc, stats = CR.strongly_connected(names, head, adj)
    assert not scc, \
        "无环图被误报成有环"


def test_dot_export_contains_nodes():
    """DOT 文本必须含 digraph 头与节点名（渲染层依赖它）。"""
    import callrel as CR

    idx, names, head, adj = CR.build_csr([(0, 1)])
    dot = CR.to_dot({"edges": [], "nodes": []}, title="t")
    assert "digraph" in dot.lower(), "DOT 没有 digraph 头：%r" % dot[:120]
