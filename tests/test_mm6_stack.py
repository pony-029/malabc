# -*- coding: utf-8 -*-
"""MM6：`max_stack_bytes` 必须**真的被检查**（此前只声明、从不核对）。

为什么需要这条判据：配置里出现一个字段、却没有任何代码读它，
等于给用户一个**看起来生效、实际无效**的约束 —— 这类"劝告式配置"比没有更危险。
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PM = os.path.join(ROOT, "translate", "project_map.py")
EXAMPLE = os.path.join(ROOT, "translate", "examples", "m2c.project.json")


def _run(path):
    r = subprocess.run([sys.executable, PM, path], stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900)
    return r.returncode, r.stdout.decode("utf-8", "replace")


def _copy_with(base_src, mutate):
    """把示例工程（含 matlab/ 与 c_runtime/）复制到临时目录后改配置。"""
    d = tempfile.mkdtemp(prefix="m2c_mm6_")
    exdir = os.path.dirname(EXAMPLE)
    for name in os.listdir(exdir):
        s = os.path.join(exdir, name)
        if os.path.isdir(s):
            shutil.copytree(s, os.path.join(d, name))
    cfg = json.load(io.open(EXAMPLE, encoding="utf-8"))
    mutate(cfg)
    p = os.path.join(d, "m2c.project.json")
    io.open(p, "w", encoding="utf-8").write(json.dumps(cfg, ensure_ascii=False, indent=2))
    return d, p


@pytest.mark.skipif(not os.path.isfile(EXAMPLE), reason="缺示例配置")
def test_mm6_stack_budget_is_enforced():
    # 1) 极小的上限 -> 必须报 MM6（证明它在检查）
    d, p = _copy_with(EXAMPLE, lambda c: [
        t.setdefault("max_stack_bytes", 1).__class__
        for t in [(c["targets"]["mcu"])]
    ] and None)
    try:
        cfg = json.load(io.open(p, encoding="utf-8"))
        cfg["targets"]["mcu"]["max_stack_bytes"] = 64      # 任何函数都超过
        io.open(p, "w", encoding="utf-8").write(json.dumps(cfg, ensure_ascii=False, indent=2))
        rc, out = _run(p)
        assert "MM6" in out, "极小上限必须触发 MM6，实际输出：%s" % out[-500:]
        assert rc != 0, "有 problem 时退出码必须非 0"
    finally:
        shutil.rmtree(d, ignore_errors=True)

    # 2) 宽松上限 -> 不该报 MM6（避免误报）
    d, p = _copy_with(EXAMPLE, lambda c: c["targets"]["mcu"].__setitem__("max_stack_bytes", 65536))
    try:
        rc, out = _run(p)
        assert "MM6" not in out, "宽松上限不该报 MM6：%s" % out[-400:]
    finally:
        shutil.rmtree(d, ignore_errors=True)
