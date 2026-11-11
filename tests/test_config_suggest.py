# -*- coding: utf-8 -*-
"""P4 判据：**图上每个节点都能给出「该配什么」，且采纳后复扫有变化**。

## 「复扫有变化」是这条判据的全部价值

一条建议最容易犯的错，是**说得对但没用**：文案看起来合理（"把元胞改成数组"），
可采纳之后诊断一条没少 —— 因为卡点其实来自别处。

所以这里做的不是"断言建议文案里含某几个字"，而是：

    扫一次 → 有 cell 卡点 12 条
    按建议改源文件（数值化）
    再扫一次 → cell 卡点必须下降

## 两向

    * 采纳**应当**让卡点下降（正向）
    * 不采纳时**必须**还在（反向：证明不是"本来就没有"）
"""
import io
import json
import os
import shutil
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "translate"))

import config_suggest as CS       # noqa: E402

WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"

#: 含元胞（`{...}`）—— 必然产生 `cell` 卡点
BEFORE = ("function y = fit(a)\n% @m2c shape a 3\n% @m2c shape y 3\n"
          "c = {1, 2, 3};\ny = a;\nend\n")

#: 采纳建议后：元胞改成定长数值数组
AFTER = ("function y = fit(a)\n% @m2c shape a 3\n% @m2c shape y 3\n"
         "% @m2c shape c 3\nc = a;\ny = a;\nend\n")


def _project(src_text):
    d = tempfile.mkdtemp(prefix="p4_", dir=WORK if os.path.isdir(WORK) else None)
    io.open(os.path.join(d, "fit.m"), "w", encoding="utf-8",
            newline="\n").write(src_text)
    cfg = {"matlab": {"root": "."},
           "modules": [{"id": "algo", "sources": ["fit.m"]}]}
    return d, cfg


def _kinds(cfg, d):
    rows, _miss = CS.suggest(cfg, d)
    return {r["kind"]: r["count"] for r in rows if r.get("kind")}


def test_suggestion_points_at_a_real_config_key():
    """P4a：卡点必须映射到**具体的配置形态**（注解/配置键），不是一句散文。"""
    d, cfg = _project(BEFORE)
    try:
        rows, _miss = CS.suggest(cfg, d)
        assert rows, "没有任何建议行"
        cell = [r for r in rows if r["kind"] == "cell"]
        assert cell, "含元胞的源文件没有 cell 建议：%r" % rows
        r = cell[0]
        assert r["where"] == "annotation", "应指向 `.m` 注解，实得 %r" % r["where"]
        assert "@m2c" in r["config"], "配置形态必须可抄（含 `% @m2c`）：%r" % r["config"]
        assert r["count"] >= 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_rescan_changes_after_adopting():
    """P4b：**采纳后复扫必须有变化** —— 这是"建议有效"的唯一证据。"""
    d, cfg = _project(BEFORE)
    try:
        before = _kinds(cfg, d)
        assert "cell" in before, "样本没有产生 cell 卡点（判据前提不成立）"

        io.open(os.path.join(d, "fit.m"), "w", encoding="utf-8",
                newline="\n").write(AFTER)
        after = _kinds(cfg, d)
        assert after.get("cell", 0) < before["cell"], \
            "采纳建议后 cell 卡点没有下降：%r → %r" % (before, after)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_clean_file_has_no_blocking_row():
    """P4c：干净文件不该被塞一条"假阻塞"建议。"""
    d, cfg = _project("function y = ok(a)\n% @m2c shape a 3\n% @m2c shape y 3\n"
                      "y = a + a;\nend\n")
    try:
        rows, _miss = CS.suggest(cfg, d)
        assert rows, "干净文件也应该有一行（『无卡点』）"
        assert all(r["kind"] is None for r in rows), \
            "干净文件给出了卡点建议：%r" % rows
        assert rows[0]["count"] == 0
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_missing_source_is_reported():
    """P4d：图上有节点、磁盘上没文件时，必须报"缺失"而不是静默跳过。"""
    d = tempfile.mkdtemp(prefix="p4m_", dir=WORK if os.path.isdir(WORK) else None)
    try:
        cfg = {"matlab": {"root": "."},
               "modules": [{"id": "algo", "sources": ["nope.m"]}]}
        rows, miss = CS.suggest(cfg, d)
        assert not rows
        assert miss and miss[0]["reason"] == "文件不存在", miss
    finally:
        shutil.rmtree(d, ignore_errors=True)
