# -*- coding: utf-8 -*-
"""多返回 `[a,b] = f(x)` 必须**跑出正确的数**，而不仅是能编译。

为什么单独一条：GX1 只做 `-fsyntax-only`，它证明不了 `m2c_twoout(x, &lo, &hi)`
真的把两个值写进了两个不同的对象（写反、只写一个、写成同一个，都能过编译）。
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
SRC = os.path.join(ROOT, "translate", "examples", "multi")


def _cc():
    return shutil.which("gcc") or shutil.which("clang")


@pytest.mark.skipif(_cc() is None, reason="没有 C 编译器")
def test_multi_return_values():
    d = tempfile.mkdtemp(prefix="m2c_multi_")
    mir = os.path.join(d, "m.mir")
    gen = os.path.join(d, "gen")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "translate", "mir.py"),
                        SRC, "-o", mir],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=300)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-400:]

    r = subprocess.run([M2C, "build", "--mir", mir, "--out", gen, "--name", "m"],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=300)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-400:]

    exe = os.path.join(gen, "m.exe")
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
    assert "twoout: 1 | 4" in out, out
    assert "userange: 3" in out, out
