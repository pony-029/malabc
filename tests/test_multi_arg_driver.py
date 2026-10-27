# -*- coding: utf-8 -*-
"""驱动的**每个**数组入参都要拿到默认形状（不只第一个）。

背景（R558）：驱动只给 `arrays[0]` 假设 `[4]`，其余按声明形状构造 —— 无注解时
是 `mlc_array_init(&t, MLC_F64, 0, {})`，即 ndim 0、numel 0 的**空数组**。
于是 `find(T == t)` 因两数组不等长被正确拒绝，函数报 error。
修好后 `addtwo(a,b)` 的两个入参都有 `assumed shape [4]`，结果 `2 4 6 8`。
"""
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RT = os.path.join(ROOT, "c_runtime")
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release", "m2c.exe")


def _cc():
    return shutil.which("gcc") or shutil.which("clang")


@pytest.mark.skipif(_cc() is None or not os.path.isfile(M2C),
                    reason="没有 C 编译器或 m2c 未构建")
def test_every_array_arg_gets_default_shape():
    import tempfile

    d = tempfile.mkdtemp(prefix="m2c_multiarg_")
    mir = os.path.join(d, "n.mir")
    subprocess.run([sys.executable, os.path.join(ROOT, "translate", "mir.py"),
                    os.path.join(ROOT, "translate", "examples", "nouns"),
                    "-o", mir],
                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                   stderr=subprocess.STDOUT, timeout=600, check=True)
    gen = os.path.join(d, "gen")
    subprocess.run([M2C, "build", "--mir", mir, "--out", gen, "--name", "nouns"],
                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                   stderr=subprocess.STDOUT, timeout=900, check=True)

    exe = os.path.join(d, "n.exe")
    r = subprocess.run([_cc(), "-std=c99", "-O1",
                        "-I", os.path.join(gen, "include"),
                        "-I", os.path.join(RT, "include"),
                        os.path.join(gen, "src", "gen.c"),
                        os.path.join(gen, "src", "main.c"),
                        os.path.join(RT, "src", "mlc_runtime.c"),
                        os.path.join(RT, "src", "mlc_ops.c"),
                        "-o", exe],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=900)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-600:]

    out = subprocess.run([exe], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT,
                         timeout=300).stdout.decode("utf-8", "replace")
    # 两个入参都要有默认形状，且结果正确
    assert "a: assumed shape [4]" in out, out
    assert "b: assumed shape [4]" in out, out
    assert "addtwo: 2 4 6 8" in out, out
