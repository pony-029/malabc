# -*- coding: utf-8 -*-
"""`agent_loop.py`（仓根，705 行）：修复循环的**摘要渲染**。

这个函数的消费者是"看命令行的人"——它不出错、也不返回值，只是把结果印出来。
所以判据盯**信息是否齐全**：

* 项目名 / 模式 / `max_turns` / 基线告警数 —— 少了任何一项，人无法判断这次跑的是什么；
* 每轮的 `attempt` / `verdict`；
* 终止原因与终态告警数；
* **两个自证分支**：`accepted=True` 说"通过(PASS)"，`accepted=False` 说"不通过(FAIL)"
  —— 分支写反是最坏的情形：回退了却显示"已保留"。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _result(accepted=True, review_pending=False):
    return {
        "project": "demo-proj",
        "mode": "fix",
        "used_git": True,
        "max_turns": 3,
        "baseline": {"total": 2, "by_rule": {"R1": 2}},
        "turns": [{
            "attempt": 1, "strategy": "minimal", "patch_bytes": 42,
            "verdict": "improved", "feedback": "",
            "verified": {"total": 1, "no_new_alerts": True, "progress": True},
        }],
        "termination": {"reason": "no_progress", "turns_used": 1},
        "result": {"final_total": 1, "tier": 2, "final_by_rule": {"R1": 1},
                   "accepted": accepted, "review_pending": review_pending,
                   "checkpoint": None},
    }


def test_summary_contains_core_fields():
    """摘要必须带上：项目名、模式、max_turns、基线数、终止原因、终态数。"""
    import agent_loop as A

    out = A.summarize_loop(_result())
    assert "demo-proj" in out, "摘要里没有项目名"
    assert "fix" in out, "摘要里没有模式"
    assert "max_turns=3" in out, "摘要里没有 max_turns（无法判断跑了多少轮）"
    assert "基线告警：2" in out, "摘要里没有基线告警数"
    assert "no_progress" in out, "摘要里没有终止原因"
    assert "终态告警：1" in out, "摘要里没有终态告警数"
    assert "turn 1" in out, "摘要里没有逐轮信息"


def test_pass_branch_says_pass():
    """`accepted=True` → 必须说"通过(PASS)"。"""
    import agent_loop as A

    out = A.summarize_loop(_result(accepted=True))
    assert "通过(PASS)" in out, "accepted=True 却没显示通过：\n%s" % out[-300:]
    assert "不通过(FAIL)" not in out, "accepted=True 同时出现了 FAIL"


def test_fail_branch_says_fail():
    """**反向**：`accepted=False` → 必须说"不通过(FAIL)"（分支写反最坏）。"""
    import agent_loop as A

    out = A.summarize_loop(_result(accepted=False))
    assert "不通过(FAIL)" in out, "accepted=False 却没说失败：\n%s" % out[-300:]
    assert "通过(PASS)" not in out, "accepted=False 同时出现了 PASS"


def test_review_pending_is_distinguished():
    """`review_pending=True` 时要说"未落地/exit 3" —— 与"已保留"区分开。"""
    import agent_loop as A

    out = A.summarize_loop(_result(accepted=True, review_pending=True))
    assert "复核" in out or "exit 3" in out, \
        "review_pending 没有单独说明：\n%s" % out[-300:]
