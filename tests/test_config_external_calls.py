# -*- coding: utf-8 -*-
"""P3 判据（配置驱动）：`c.external_calls` 决定**工程外调用**是否进契约块。

## 守什么

`--external-calls` 是个危险的开关（把"现在可诊断"变成"运行期才失败"），
所以它**不能靠人记命令行**，只能靠配置里一行显式声明。这条判据同时钉住两向：

    P3e-1 配置里没有 external_calls → MIR 里是 `unmapped:`（默认行为不变）
    P3e-2 配置里写了 true        → MIR 里是 `call:`，头文件出现 `m2c_ext_*`
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

import project_map as PM          # noqa: E402

WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"

SRC = ("function y = uses_ext(x)\n% @m2c shape x 3\n% @m2c shape y 3\n"
       "y = external_magic(x);\nend\n")


def _cfg(external_calls):
    """造一个最小 v2 配置（matlab/c/modules/targets）。"""
    c = {"root": "build/gen", "project": "ext_demo", "prefix": "m2c_",
         "runtime": "c_runtime"}
    if external_calls is not None:
        c["external_calls"] = external_calls
    return {
        "version": 2,
        "matlab": {"root": "src", "recursive": True, "exclude": []},
        "c": c,
        "dtypes": {"default": "f64"},
        "targets": {"pc": {"abi": "host", "allow_heap": True, "dtype": "f64"}},
        "modules": [{"id": "m", "sources": ["uses_ext.m"]}],
    }


def _run(external_calls):
    d = tempfile.mkdtemp(prefix="p3e_", dir=WORK if os.path.isdir(WORK) else None)
    src = os.path.join(d, "src")
    os.makedirs(src)
    io.open(os.path.join(src, "uses_ext.m"), "w", encoding="utf-8",
            newline="\n").write(SRC)
    cfg_path = os.path.join(d, "m2c.project.json")
    io.open(cfg_path, "w", encoding="utf-8", newline="\n").write(
        json.dumps(_cfg(external_calls), ensure_ascii=False, indent=2) + "\n")
    cfg = PM.load2(cfg_path)
    rc, log, out = PM.run_build(cfg, d, cfg_path)
    mir = io.open(os.path.join(d, ".m2c", "project.mir"), encoding="utf-8",
                  errors="replace").read()
    hdr_path = os.path.join(d, cfg["c"]["root"], "include", "ext_demo.h")
    hdr = io.open(hdr_path, encoding="utf-8").read() if os.path.isfile(hdr_path) else ""
    shutil.rmtree(d, ignore_errors=True)
    return rc, mir, hdr, out


def test_default_keeps_unmapped():
    """P3e-1：配置里没写 → 仍是 `unmapped:`（默认行为不变）。"""
    rc, mir, _hdr, out = _run(None)
    assert rc == 0, out[-400:]
    assert "unmapped:y = external_magic(x);" in mir, \
        "默认应如实标未映射，实际 MIR：\n%s" % mir[-300:]
    assert "call:y:external_magic" not in mir


def test_config_enables_contract():
    """P3e-2：配置写 true → `call:` + 头文件契约。"""
    rc, mir, hdr, out = _run(True)
    assert rc == 0, out[-400:]
    assert "call:y:external_magic:x" in mir, "开了配置仍没保留成 call:"
    assert "m2c_ext_external_magic" in hdr, \
        "配置开了但头文件没有契约声明：\n%s" % hdr[-300:]
