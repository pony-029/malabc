# -*- coding: utf-8 -*-
"""生成的 C **必须能编译** —— 对每个示例工程做一次 `gcc -fsyntax-only`。

为什么需要：R486–R487 那个 `'d' redeclared` 缺陷能产出**语法正确、语义可用**的
MIR，却生成**编译不过**的 C。它能一路通过 16 道门（那些门只比对输出数值，
不编译整工程），只有人手动跑 gcc 才会暴露。

判据宁可"傻"也要在：**转出来的东西，至少要能被编译器接受。**
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
EX = os.path.join(ROOT, "translate", "examples")

#: (源路径, 是否是目录)
CASES = [
    (os.path.join(EX, "numeric"), True),
    (os.path.join(EX, "proj"), True),
    (os.path.join(EX, "multi"), True),
    (os.path.join(EX, "nouns"), True),
    (os.path.join(EX, "demo_port.m"), False),
]


def _cc():
    return shutil.which("gcc") or shutil.which("clang") or shutil.which("cc")


def _run(cmd, **kw):
    return subprocess.run(cmd, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=600, **kw)


@pytest.mark.skipif(_cc() is None, reason="没有 C 编译器")
@pytest.mark.parametrize("src,is_dir", CASES,
                         ids=[os.path.basename(s) for s, _ in CASES])
def test_generated_project_compiles(src, is_dir):
    if not os.path.exists(src):
        pytest.skip("%s 不存在" % src)
    d = tempfile.mkdtemp(prefix="m2c_cc_")
    mir = os.path.join(d, "p.mir")
    gen = os.path.join(d, "gen")
    cmd = [sys.executable, os.path.join(ROOT, "translate", "mir.py"), src,
           "-o", mir]
    r = _run(cmd)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-400:]

    r = _run([M2C, "build", "--mir", mir, "--out", gen, "--name", "p"])
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-400:]

    r = _run([_cc(), "-std=c99", "-fsyntax-only",
              "-I", os.path.join(gen, "include"),
              "-I", os.path.join(ROOT, "c_runtime", "include"),
              os.path.join(gen, "src", "gen.c")])
    assert r.returncode == 0, (
        "生成的 C 编译不过：\n"
        + r.stdout.decode("utf-8", "replace")[-1200:])
