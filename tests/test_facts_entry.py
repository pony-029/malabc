# -*- coding: utf-8 -*-
"""`facts.py`（仓根）：事实层必须**能对账**、且**位置不撒谎**。

两条互相独立的性质：

* **对账**：`replay_counts(事实)` 必须等于 `expected_counts(报表)`。
  这条不成立时，报表说的数字与事实层实际展开的不是一回事 —— 而两边都"看起来正常"。
* **位置**：每条事实都要带 `loc.file`。缺了不是小事：SARIF / 点击跳转全靠它，
  而缺字段不会报错，只会让"跳转到空"。

第二条的牙齿是实测出来的：我手写的边事实没带文件，`position_problems` 立刻指出
「第 3 条 call 事实没有 loc.file」。所以这里断言**它必须指出**，而不是断言"没问题"。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PAY = {
    "files": [{"rel": "a.m", "kind": "matlab",
               "functions": [{"name": "foo", "line": 3},
                             {"name": "bar", "line": 7}]}],
    "edges": [{"src": "foo", "dst": "bar", "kind": "direct"}],
    "unresolved": [],
    "heuristics": [],
}


def test_replay_matches_declared_counts():
    """事实层回放出来的计数，必须与报表自己声明的一致。"""
    import facts as F

    facts = F.facts_from_payload(PAY)
    assert facts, "报表没展开出任何事实"
    assert F.replay_counts(facts) == F.expected_counts(PAY), \
        "对账不一致：回放 %r vs 声明 %r" % (F.replay_counts(facts),
                                     F.expected_counts(PAY))


def test_missing_file_on_edge_is_reported():
    """**牙齿**：边事实缺 `loc.file` 时，`position_problems` 必须指出来。

    这正是我手写样本时踩到的情形 —— 它不报错，只是让"跳转到空"。
    """
    import facts as F

    probs = F.position_problems(F.facts_from_payload(PAY))
    assert any("loc.file" in p for p in probs), \
        "缺 loc.file 的边事实没被指出（位置判据是摆设）：%r" % (probs,)
    assert any("call" in p for p in probs), \
        "报错没指明是哪一类事实：%r" % (probs,)


def test_zero_line_is_not_a_position_problem():
    """`line=0` **不算**位置问题（0 表示"整个文件级事实"，不是缺位置）。

    反向断言很重要：如果把 0 也算问题，文件级事实会被大量误报，
    于是这条判据会被当成噪音关掉。
    """
    import facts as F

    bad = {"files": [{"rel": "a.m", "kind": "matlab",
                      "functions": [{"name": "foo", "line": 0}]}],
           "edges": []}
    assert F.position_problems(F.facts_from_payload(bad)) == []
