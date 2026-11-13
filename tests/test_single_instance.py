# -*- coding: utf-8 -*-
"""长任务门的**单实例锁**（`tools/check_generated_compiles.py`）。

## 为什么这条判据存在

GX2 要跑 6 分钟。R845 实测：我连续几轮都以为它"跑得慢"，真相是**上一轮的实例
从未退出**，两个任务在互相抢 CPU —— 越重试越慢，且永远不会自己变好。

锁的四条语义，每条都对应一种真实故障：

| 情形 | 期望 | 不对时会怎样 |
|---|---|---|
| 锁里是**活着的别人** | 拒绝启动 | 又变成两个实例抢 CPU |
| 锁里是**已死的 pid**（上次被 kill） | **直接接管** | 要人工删锁才能跑，没人知道删哪个 |
| 锁里是**自己** | 允许（不算冲突） | 递归/重入时把自己挡住 |
| 释放时锁属于别人 | **不许删** | 误删正在跑的那个实例的锁 |
"""
import json
import os
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import check_generated_compiles as G      # noqa: E402


def _tmp_lock(d):
    return os.path.join(d, "x.lock")


def _write(path, pid):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"pid": pid, "ts": "test"}, f)


def test_stale_lock_is_taken_over():
    """上次被 kill 留下的锁（pid 已死）必须**直接接管**。"""
    d = tempfile.mkdtemp(prefix="lock_")
    p = _tmp_lock(d)
    # ⚠ 不能用"刚退出的子进程 pid"：Windows 下 Popen 仍持有句柄，
    #   `OpenProcess` 依旧成功 —— 它被判"活着"（实测）。所以用一个几乎不可能存在的 pid。
    dead = 999999
    if G.pid_alive(dead):
        pytest.skip("本机上 %d 恰好被占用，换一个死 pid 才能测" % dead)
    _write(p, dead)
    ok, why = G.acquire_lock(p)
    assert ok, "死锁没被接管（要人工删锁才能跑）：%s" % why
    G.release_lock(p)
    assert not os.path.isfile(p), "释放后锁文件还在"


def test_live_other_instance_blocks():
    """锁里是**活着的别人** → 必须拒绝，并说出是谁。"""
    d = tempfile.mkdtemp(prefix="lock_")
    p = _tmp_lock(d)
    other = subprocess.Popen([sys.executable, "-c",
                             "import time; time.sleep(30)"])
    try:
        _write(p, other.pid)
        ok, why = G.acquire_lock(p)
        assert not ok, "别人在跑竟然放行（会变回两个实例抢 CPU）"
        assert str(other.pid) in why, "拒绝理由里没有 pid：%r" % why
    finally:
        other.kill()
        other.wait(timeout=30)


def test_lock_of_self_is_not_a_conflict():
    """锁里是**自己**的 pid → 不算冲突（重入/重跑同一个进程）。"""
    d = tempfile.mkdtemp(prefix="lock_")
    p = _tmp_lock(d)
    _write(p, os.getpid())
    ok, why = G.acquire_lock(p)
    assert ok, "被自己的旧锁挡住了：%s" % why
    G.release_lock(p)


def test_release_does_not_steal_others_lock():
    """释放时若锁属于别人，**不许删** —— 否则会把在跑的实例的锁删掉。"""
    d = tempfile.mkdtemp(prefix="lock_")
    p = _tmp_lock(d)
    _write(p, 999999)                            # 不存在的 pid，但不是自己
    G.release_lock(p)
    assert os.path.isfile(p), "属于别人的锁被误删了"
