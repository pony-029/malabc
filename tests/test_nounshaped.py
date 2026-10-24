# -*- coding: utf-8 -*-
"""零注解路径必须**跑出正确的数**：驱动默认形状 + 算子运行时定形状。

为什么单独一条：YALMIP 全线没有 `% @m2c shape`，这条链是唯一能验证它的路；
而它曾经因为驱动里 `ndim` 取错（`arr.shape.len()` 在无注解时为 0）
导致**所有函数一律 MLC_ERR**，却没有任何判据看得见。
"""
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release",
                   "m2c.exe" if os.name == "nt" else "m2c")
SRC = os.path.join(ROOT, "translate", "examples", "nouns")


def _cc():
    return shutil.which("gcc") or shutil.which("clang")


@pytest.mark.skipif(_cc() is None, reason="没有 C 编译器")
def test_nounshaped_runs_with_default_shape():
    d = tempfile.mkdtemp(prefix="m2c_nouns_")
    mir = os.path.join(d, "n.mir")
    gen = os.path.join(d, "gen")

    r = subprocess.run([sys.executable, os.path.join(ROOT, "translate", "mir.py"),
                        SRC, "-o", mir],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=300)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-400:]

    r = subprocess.run([M2C, "build", "--mir", mir, "--out", gen, "--name", "n"],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=300)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-400:]

    exe = os.path.join(gen, "n.exe")
    r = subprocess.run([_cc(), "-std=c99", "-O1",
                        "-I", os.path.join(gen, "include"),
                        "-I", os.path.join(ROOT, "c_runtime", "include"),
                        os.path.join(gen, "src", "gen.c"),
                        os.path.join(gen, "src", "main.c"),
                        os.path.join(ROOT, "c_runtime", "src", "mlc_runtime.c"),
                        os.path.join(ROOT, "c_runtime", "src", "mlc_ops.c"),
                        "-o", exe],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=600)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-800:]

    out = subprocess.run([exe], stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         timeout=300).stdout.decode("utf-8", "replace")
    # 默认形状必须显式写出来（不假装是注解）
    assert "k: assumed shape [4]" in out, out
    # 数值必须正确：k = 1..4，v = 2*k
    assert "scale2x: 2 4 6 8" in out, out
