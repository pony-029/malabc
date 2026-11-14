# -*- coding: utf-8 -*-
"""`matlabc_task.py`（仓根，2576 行）：任务记录的**空态契约**。

这个模块负责"能不能撤销上次改名"这类能力。它的危险方向是**静默返回空**：
记录没写进去，用户以为能 undo，真去撤时才发现无记录（代码注释里就记着这个教训）。

判据只钉**不依赖真实工程的那部分**：

* `list_tasks(空)` → 空列表（不是 None、不是异常）；
* `prune_tasks(空)` → 四个计数字段齐全且全 0 —— 裁剪**不制造也不吞掉**记录；
* 两者都**幂等**：连跑两次结果一样（不会因为第一次跑就把目录建坏）。
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PRUNE_KEYS = {"total", "removed_undone", "removed_live", "kept"}


def _tmp():
    tmp = os.environ.get("M2C_TMP")
    return tempfile.mkdtemp(prefix="task_",
                            dir=tmp if tmp and os.path.isdir(tmp) else None)


def test_empty_project_lists_nothing():
    """空工程：`list_tasks` 必须给空列表，且 `task_stats` 不炸。"""
    import matlabc_task as MT

    d = _tmp()
    try:
        assert MT.list_tasks(d) == []
        # ⚠ `task_stats` 返回的是**按类型聚合的行**（list），不是 dict ——
        # 第一版按 dict 断言，实测直接红。空工程应给空列表。
        stats = MT.task_stats(d)
        assert isinstance(stats, list), "task_stats 返回类型变了：%r" % (type(stats),)
        assert stats == [], "空工程却有聚合行（无中生有）：%r" % (stats,)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_successful_record_is_listed():
    """记一条成功任务 → 返回非空 id，且能被 `list_tasks` 看到。"""
    import matlabc_task as MT

    d = _tmp()
    try:
        rid = MT.record_task(d, "rename", {"old": "a", "new": "b"}, {})
        assert rid, "record_task 成功路径却返回空串（用户会以为能 undo）"
        rows = MT.list_tasks(d)
        assert len(rows) == 1, "记了一条却列出 %d 条" % len(rows)
        assert rows[0].get("kind") == "rename"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_failure_log_goes_to_project_not_repo():
    """**失败日志必须写在被操作的项目里**，不能写到本仓库根。

    R855 修的真缺陷：早前用 `os.path.dirname(__file__)`，于是操作别人的工程时
    日志落到**本仓库根目录** —— 既污染工作区（多出一个未跟踪文件），
    用户在**自己的项目里**也找不到它。日志要挨着它描述的对象放。
    """
    import matlabc_task as MT

    d = _tmp()
    repo_log = os.path.join(ROOT, "matlabc_task.log")
    if os.path.exists(repo_log):
        os.remove(repo_log)          # 清掉可能的历史残留，再验会不会重新生成
    try:
        # `backup=None` 会在内部 `backup.items()` 处失败 —— 这正是要覆盖的失败路径
        rid = MT.record_task(d, "rename", {"old": "a", "new": "b"}, None)
        assert rid == "", "明知会失败却返回了 id（用户会去 undo 一条不存在的记录）"

        inproj = os.path.join(d, MT.HISTORY_DIR, "matlabc_task.log")
        assert os.path.isfile(inproj), "失败日志没写在项目里（用户找不到）"
        assert not os.path.exists(repo_log), \
            "失败日志写到了本仓库根（污染工作区）"
    finally:
        shutil.rmtree(d, ignore_errors=True)
        if os.path.exists(repo_log):
            os.remove(repo_log)


def test_prune_reports_zero_on_empty_and_is_idempotent():
    """空工程裁剪：四个计数全 0，且连跑两次结果一致。"""
    import matlabc_task as MT

    d = _tmp()
    try:
        first = MT.prune_tasks(d, keep=2, apply_it=True)
        assert set(first) == PRUNE_KEYS, \
            "裁剪结果的字段变了（消费方会 KeyError）：%r" % sorted(first)
        assert all(v == 0 for v in first.values()), \
            "空工程却报出非零计数（无中生有）：%r" % (first,)

        second = MT.prune_tasks(d, keep=2, apply_it=True)
        assert second == first, "裁剪不幂等：%r vs %r" % (first, second)
        assert MT.list_tasks(d) == [], "裁剪后反而出现了记录"
    finally:
        shutil.rmtree(d, ignore_errors=True)
