# -*- coding: utf-8 -*-
"""追踪链完整性判据：**每个 in 都必须能追溯到更早的 out**。

与 `test_vm_differential` 的分工：
- 那个问"两条实现算得一样吗"；
- 这个问"这份记录本身自洽吗"。

一份不自洽的追踪比没有追踪更糟 —— 它看起来完整（每步都 ok），却证明不了因果。
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import trace_chain as TC          # noqa: E402

TRACES = os.path.join(ROOT, "flow", "traces")


def _rows():
    out = {}
    for f in sorted(os.listdir(TRACES)):
        if f.endswith(".jsonl"):
            out[f[:-6]] = [json.loads(l) for l in
                           io.open(os.path.join(TRACES, f), encoding="utf-8") if l.strip()]
    return out


def test_every_trace_has_no_broken_link():
    data = _rows()
    assert data, "flow/traces 下没有追踪数据"
    bad = {n: TC.check(rows) for n, rows in data.items() if TC.check(rows)}
    assert not bad, "断链：%r" % bad


def test_every_step_has_status_and_digests():
    """每步都必须有 status；控制流/数据流之外的步不能缺摘要。"""
    for name, rows in _rows().items():
        for r in rows:
            assert r.get("status") in ("ok", "fail", "skip"), (name, r)
            assert r.get("step", "").startswith("S"), (name, r)
            assert str(r.get("out") or "") != "", "空 out：%s %s" % (name, r.get("step"))
