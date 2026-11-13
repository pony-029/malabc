# -*- coding: utf-8 -*-
"""`unified_graph.py`（仓根）：**守恒恒等式**必须真的会响。

`conservation_problems()` 是本仓少见的"纯不变量"函数 —— 它不抛异常，只返回问题清单。
正因为它温和，最容易变成"永远返回 []"的摆设：图坏了也照样空。

所以这里三向验证：
* 示范图 → 空清单（不误报）；
* **站点没有对应边** → A1a 必须报（少造边 = 图上少了调用关系）；
* **边指向未登记节点** → A2 必须报（引用完整性，否则渲染期才发现 KeyError）。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_demo_graph_is_conserved():
    """示范图必须无问题（否则判据自己先偏）。"""
    import unified_graph as U

    g = U.demo_graph()
    assert list(g.nodes), "示范图没有节点"
    assert list(g.edges), "示范图没有边"
    assert U.conservation_problems(g) == [], \
        "示范图本身不守恒：%r" % (U.conservation_problems(g),)


def test_a1a_fires_when_sites_produce_no_edges():
    """**A1a 会响**：有"产出边"的站点、却没有边 —— 差值必须被报出来。"""
    import unified_graph as U

    g = U.UnifiedGraph()
    g.add_node(U.Node("n1", "function"))
    g.add_site("direct", 3)                 # 3 个站点声称产出边
    probs = U.conservation_problems(g)    # 但一条边都没加
    assert any("A1a" in p for p in probs), \
        "A1a 没响（站点 3、边 0 竟然判守恒）：%r" % (probs,)


def test_a2_dangling_edge_rejected_at_insert():
    """A2 在**插入期**就拒（实测比事后检查更早、更准）。

    我原本以为悬空边会一路进图、由 `conservation_problems` 报 A2；
    实际是 `add_edge` 直接抛 `GraphError`。**这更好**：问题在产生点就停住，
    而不是等渲染期 KeyError（那时已经找不到是谁造的边）。
    """
    import pytest                 # noqa: PLC0415

    import unified_graph as U

    g = U.UnifiedGraph()
    g.add_node(U.Node("n1", "function"))
    with pytest.raises(U.GraphError):
        g.add_edge(U.Edge("n1", "n2", "direct"))    # n2 从未 add_node
    assert not list(g.edges), "悬空边竟然被加进图里了"
