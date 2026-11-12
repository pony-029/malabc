# -*- coding: utf-8 -*-
"""整体状态判据：**计划阶段的完成必须有证据，且证据必须真的在跑**。

## 这条判据守的是"完成度"这个词的分母

一个阶段被称"完成"，通常靠三样东西之一：
    a) 文档里写了「已完成」          → 会过期，且没人核对
    b) 有个测试文件                  → 可能存在但**没人跑**（本项目踩过：15 个孤儿测试）
    c) 判据存在 **且** 已被门引用     → 这才是可验证的完成

所以这里只认 (c)：`tools/project_status.py` 给出的每个阶段都必须 `done`，
而 `done` 的定义是「证据文件存在 **且** 出现在 GX2 清单里」。

## 为什么不顺带断言"图都是现行的"

`flow/figures` 下 20 张图当前**全部滞后**（落后 >10 个提交）。把它断言成零
会逼着每次改代码都重渲染全部图 —— 那是另一个成本量级的事。这里只断言
**数字是诚实的**（张数 == 磁盘目录数、三档之和 == 张数），滞后本身由
`flow/catalog.html` 展示给人看。
"""
import io
import json
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import project_status as PS       # noqa: E402


@pytest.fixture(scope="module")
def status():
    return PS.build()


def test_every_phase_has_running_evidence(status):
    """每个计划阶段都必须：证据文件存在 + 已接入 GX2。"""
    bad = []
    for p in status["phases"]:
        if p["status"] != "done":
            bad.append("%s（缺 %s / 未接线 %s）"
                       % (p["id"], p["missing"], p["not_gated"]))
    assert not bad, "阶段完成度不可判定：%s" % bad


def test_phase_evidence_files_really_registered(status):
    """证据文件必须真的是 `tests/` 下的文件（防止写个名字充数）。"""
    for p in status["phases"]:
        for e in p["evidence"]:
            assert os.path.isfile(os.path.join(ROOT, e)), "%s 的证据不存在：%s" % (
                p["id"], e)
            assert re.match(r"^tests/test_[a-z0-9_]+\.py$", e), \
                "证据必须是 tests/ 下的用例文件：%r" % e


def test_figure_counts_are_honest(status):
    """图张数与三档之和必须对得上磁盘（数字可以难看，但不能说谎）。"""
    f = status["figures"]
    base = os.path.join(ROOT, "flow", "figures")
    if not os.path.isdir(base):
        pytest.skip("没有 flow/figures")
    on_disk = len([d for d in os.listdir(base)
                   if os.path.isdir(os.path.join(base, d))])
    assert f["count"] == on_disk, \
        "统计到 %d 张，磁盘上 %d 张" % (f["count"], on_disk)
    s = (f["current"] + f["recent"] + f["stale"] + f["unknown"]
         + f.get("historical", 0))
    assert s == f["count"], "各档之和 %d != 张数 %d" % (s, f["count"])


def test_gx2_list_is_nonempty(status):
    """GX2 清单非空 —— 否则"已接线"这个判定会在空集上恒真。"""
    assert status["gx2_tests"] >= 50, \
        "GX2 只引用了 %d 个测试文件（判据可能被清空）" % status["gx2_tests"]


def test_historical_figures_are_registered_with_reason():
    """历史图必须**带理由**，且**不能被标成现行**（两向）。

    * 有 `meta.status == "historical"` 却没有理由 ⇒ 红（免检要写清为什么）；
    * 标了 historical 却已经是现行（revision == HEAD）⇒ 陈旧登记 ⇒ 红
      （它其实能刷新，不该挂在历史档里）。

    这条守的是登记制最容易烂掉的方式：**只加不减**。
    """
    base = os.path.join(ROOT, "flow", "figures")
    if not os.path.isdir(base):
        pytest.skip("没有 flow/figures")
    head = PS._head()
    missing_reason, stale_mark = [], []
    for d in sorted(os.listdir(base)):
        p = os.path.join(base, d, "candidate.json")
        if not os.path.isfile(p):
            continue
        c = json.load(io.open(p, encoding="utf-8"))
        meta = c.get("meta") or {}
        if (meta.get("status") or "") != "historical":
            continue
        if len((meta.get("historical_reason") or "").strip()) < 12:
            missing_reason.append(d)
        rev = ((meta.get("repository") or {}).get("revision") or "").strip()
        if rev and head and rev == head:
            stale_mark.append(d)
    assert not missing_reason, "历史图缺理由（或太短）：%r" % missing_reason[:5]
    assert not stale_mark, \
        "这些图标了 historical 但已是现行 —— 应摘掉标记：%r" % stale_mark[:5]
