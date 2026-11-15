# -*- coding: utf-8 -*-
"""`matlabc_task.prune_tasks`：**真记录下的裁剪语义**（此前只测过空态）。

空态只证明"不在空工程上崩"，而裁剪真正会出错的地方都在有记录时：

* 裁多了 → 用户丢掉还能撤销的历史；
* 裁少了 → 目录无限增长，而返回值看起来"正常"；
* 计数不自洽（`total != 三类之和`）→ 报表里"裁了 3 条"与"剩 2 条"对不上，
  而没人会去手工验算。

所以判据要有四条：真裁、幂等、不越界、计数自洽。
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


def _project(n):
    """造一个有 `n` 条成功记录的工程。"""
    import matlabc_task as MT

    tmp = os.environ.get("M2C_TMP")
    d = tempfile.mkdtemp(prefix="prune_",
                         dir=tmp if tmp and os.path.isdir(tmp) else None)
    for i in range(n):
        rid = MT.record_task(d, "rename", {"i": i}, {})
        assert rid, "第 %d 条记录没写进去（后续裁剪无意义）" % i
    return d


def test_prune_keeps_exactly_k():
    """5 条记录、`keep=2` → 留 2 条、删 3 条（都是"还能撤"的那类）。"""
    import matlabc_task as MT

    d = _project(5)
    try:
        res = MT.prune_tasks(d, keep=2, apply_it=True)
        assert set(res) == PRUNE_KEYS, "返回字段变了：%r" % sorted(res)
        assert res["total"] == 5, "total 应为本轮看到的条数：%r" % (res,)
        assert res["kept"] == 2, "没裁到 keep=2：%r" % (res,)
        assert res["removed_live"] == 3, "删的条数不对：%r" % (res,)
        assert len(MT.list_tasks(d)) == 2, "磁盘上还剩 %d 条" % len(MT.list_tasks(d))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_prune_is_idempotent():
    """再裁一次不该继续删（否则重复调用会把历史清空）。"""
    import matlabc_task as MT

    d = _project(5)
    try:
        MT.prune_tasks(d, keep=2, apply_it=True)
        again = MT.prune_tasks(d, keep=2, apply_it=True)
        assert again["removed_live"] == 0 and again["removed_undone"] == 0, \
            "第二次裁剪仍在删：%r" % (again,)
        assert again["kept"] == 2, "第二次裁剪改变了保留数：%r" % (again,)
        assert len(MT.list_tasks(d)) == 2
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_prune_does_not_delete_when_under_limit():
    """**反向**：条数没超上限时一条都不能删。"""
    import matlabc_task as MT

    d = _project(3)
    try:
        res = MT.prune_tasks(d, keep=10, apply_it=True)
        assert res["removed_live"] == 0 and res["removed_undone"] == 0, \
            "没超上限却删了记录：%r" % (res,)
        assert len(MT.list_tasks(d)) == 3, "记录被误删，只剩 %d 条" % len(MT.list_tasks(d))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_counts_are_self_consistent():
    """`total == removed_undone + removed_live + kept` —— 报表要能自己对上。"""
    import matlabc_task as MT

    d = _project(6)
    try:
        res = MT.prune_tasks(d, keep=4, apply_it=True)
        s = res["removed_undone"] + res["removed_live"] + res["kept"]
        assert s == res["total"], \
            "计数不自洽：total=%r，三类之和=%d（%r）" % (res["total"], s, res)
    finally:
        shutil.rmtree(d, ignore_errors=True)
