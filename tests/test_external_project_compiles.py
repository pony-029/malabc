# -*- coding: utf-8 -*-
"""真实工程的**编译冒烟**：拿曾出事的真实文件，验证生成物能编译。

## 为什么需要

R575/R576 的 P0（`int64_t temp = last_monoms;` 与 `redeclaration of 'ia'`）
在 `check_all` 41 道门全绿的同时存活了 3+ 轮 —— 因为**没有任何门去编译真实工程**。
跑完整 YALMIP（1204 个函数）要 60s+，进不了门；但**出过事的那几个文件**只要 2~3 秒。

选样原则：**只放真实出过错的形态**，不放"好看"的样本。
* `extras/monpowers.m` —— 数组经 `set:` 传递（`last_monoms = all_monoms`）
* `extras/setdiff1d.m` —— 同名同时进 consts / fills（重复声明）

外部工程不在仓库里，所以有则跑、无则跳过（打印原因，不假装通过）。
"""
import glob
import io
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release", "m2c.exe")
RT = os.path.join(ROOT, "c_runtime")

#: 外部真实工程（不在仓库内）
YALMIP = r"C:\Temp\yalmip"

#: 曾出事的文件（相对 YALMIP 根）
CASES = ("extras/monpowers.m", "extras/setdiff1D.m")


def _cc():
    return shutil.which("gcc") or shutil.which("clang")


@pytest.mark.skipif(_cc() is None or not os.path.isfile(M2C),
                    reason="没有 C 编译器或 m2c 未构建")
@pytest.mark.skipif(not os.path.isdir(YALMIP),
                    reason="外部工程 %s 不存在（跳过，不假装通过）" % YALMIP)
def test_known_bad_real_files_compile():
    d = tempfile.mkdtemp(prefix="m2c_ext_")
    src = os.path.join(d, "src")
    os.makedirs(src)
    picked = []
    for rel in CASES:
        p = os.path.join(YALMIP, rel.replace("/", os.sep))
        if os.path.isfile(p):
            shutil.copy(p, src)
            picked.append(rel)
    # 缺任何一个都不许"静默变小" —— 那会让这条判据看着绿、其实只测了一半
    assert len(picked) == len(CASES), (
        "应有 %d 个真实文件，实际找到 %d 个（%s）—— 文件名或路径变了"
        % (len(CASES), len(picked), picked))

    mir = os.path.join(d, "e.mir")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "translate", "mir.py"),
                        src, "-o", mir],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=600)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-600:]

    gen = os.path.join(d, "g")
    r = subprocess.run([M2C, "build", "--mir", mir, "--out", gen, "--name", "ext"],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=900)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-600:]

    r = subprocess.run([_cc(), "-std=c99", "-fsyntax-only",
                        "-I", os.path.join(gen, "include"),
                        "-I", os.path.join(RT, "include"),
                        os.path.join(gen, "src", "gen.c")],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=600)
    out = r.stdout.decode("utf-8", "replace")
    assert r.returncode == 0, (
        "真实文件（%s）的生成物编译失败 —— 这类回归此前存活了 3+ 轮：\n%s"
        % (", ".join(picked), out[-900:]))
