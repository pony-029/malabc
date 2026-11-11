# -*- coding: utf-8 -*-
"""P2 判据：预算**在生成期**算出来、写进产物、超限即失败。

## 三层，缺一层都不算实现

    P2a 算得对：`translate/budget.py` 的字节数与手算一致
    P2b 落进产物：`run_build` 之后 `<c_root>/budget.json` 存在且字段齐全
    P2c 超限即失败：池子小于需求时 `run_build` 返回非零，且**指名**函数/变量
    P2d 两处同口径：`tools/project_budget.py` 与 `translate/budget.py` 读数一致
        （同一功能两个实现，最危险的是慢慢分叉）
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
sys.path.insert(0, os.path.join(ROOT, "translate"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import budget as B               # noqa: E402
import project_map as PM         # noqa: E402
import project_budget as PB      # noqa: E402

CFG = os.path.join(ROOT, "translate", "examples", "m2c.project.json")
WORK = os.environ.get("M2C_TMP") or None

MIR = ("version 3\nfunc:a\narg:x:f64:4\nret:y:f64:1\nend\n"
       "func:b\narg:z:f64:2,3\nend\n")


def test_bytes_are_correct():
    """P2a：4×8 + 1×8 = 40 ｜ 6×8 = 48（手算）。"""
    pf = B.parse(MIR)
    assert pf["a"]["bytes"] == 40, pf["a"]
    assert pf["b"]["bytes"] == 48, pf["b"]


def test_two_implementations_agree():
    """P2d：命令行工具与库的读数必须一致（防分叉）。"""
    a = B.parse(MIR)
    c = PB.parse(MIR)
    assert {k: v["bytes"] for k, v in a.items()} == \
           {k: v["bytes"] for k, v in c.items()}


def _build(pool):
    cfg = PM.load2(CFG)
    cfg["matlab"]["root"] = os.path.join(os.path.dirname(CFG),
                                         cfg["matlab"]["root"])
    for t in (cfg.get("targets") or {}).values():
        mem = t.get("memory") or {}
        if mem.get("strategy") == "static_pool":
            mem["pool_bytes"] = pool
    if (cfg.get("memory") or {}).get("strategy") == "static_pool":
        cfg["memory"]["pool_bytes"] = pool
    d = tempfile.mkdtemp(prefix="p2_", dir=WORK)
    rc, log, out = PM.run_build(cfg, d, CFG)
    return cfg, d, rc, log, out


@pytest.fixture(scope="module")
def built():
    cfg, d, rc, log, out = _build(65536)
    yield cfg, d, rc, log, out
    shutil.rmtree(d, ignore_errors=True)


def test_budget_json_written(built):
    """P2b：构建产物里必须有 `budget.json`，且字段齐全。"""
    cfg, d, rc, _log, out = built
    assert rc == 0, out[-400:]
    p = os.path.join(d, cfg["c"]["root"], "budget.json")
    assert os.path.isfile(p), "构建后没有 budget.json：%s" % p
    j = json.load(io.open(p, encoding="utf-8"))
    for k in ("functions", "total_bytes", "pool_bytes", "within_budget"):
        assert k in j, "budget.json 缺字段 %s：%r" % (k, list(j))
    assert j["pool_bytes"] == 65536
    assert j["within_budget"] is True
    assert j["total_bytes"] > 0


def test_over_budget_fails_and_names_vars():
    """P2c：池子 1 字节 → 必须失败，并指名函数/变量。"""
    cfg, d, rc, _log, out = _build(1)
    try:
        assert rc != 0, "池子 1 字节竟然构建成功"
        assert "超预算" in out, "失败信息里没有『超预算』：%s" % out[-300:]
        # 明细行形如 `   while2d          A                  48 字节`
        assert "字节" in out, "没有指名函数/变量：%s" % out[-300:]
    finally:
        shutil.rmtree(d, ignore_errors=True)
