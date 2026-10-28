# -*- coding: utf-8 -*-
"""生成物里**同一函数内不得重复声明**同一个名字。

## 为什么

R575/R576 的 P0：序言有三个声明循环（`temps` / `consts` / `fills`），
只在 `fills` 里做了「已在 temps 里就跳过」，`consts` 与另两者的交集无人处理 →
`mlc_array ia;` 出现两次 → `gcc: redeclaration of 'ia'` → **整个 YALMIP 编译不过**。

这个缺陷在 `check_all` 41 道门全绿的同时存活了 3+ 轮，因为**没有任何门去编译真实工程**。
这里用一个**通用不变量**代替"跑一遍 YALMIP"（后者要 60s，进不了门）：

> 每个生成函数体内，`mlc_array <name>;` 形式的声明对同一个 `name` 至多出现一次。

它比"编译通过"弱，但**快、确定、且正好命中这一类**。
"""
import collections
import glob
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release", "m2c.exe")


def _cc():
    return shutil.which("gcc") or shutil.which("clang")


@pytest.mark.skipif(not os.path.isfile(M2C), reason="m2c 未构建")
def test_no_duplicate_array_declarations():
    d = tempfile.mkdtemp(prefix="m2c_dups_")
    mir = os.path.join(d, "n.mir")
    subprocess.run([sys.executable, os.path.join(ROOT, "translate", "mir.py"),
                    os.path.join(ROOT, "translate", "examples", "numeric"),
                    "-o", mir],
                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                   stderr=subprocess.STDOUT, timeout=600, check=True)
    gen = os.path.join(d, "g")
    subprocess.run([M2C, "build", "--mir", mir, "--out", gen, "--name", "numeric"],
                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                   stderr=subprocess.STDOUT, timeout=900, check=True)

    files = [os.path.join(gen, "src", "gen.c")] + glob.glob(
        os.path.join(gen, "src", "gen", "*.c"))
    bad = []
    for p in files:
        src = io.open(p, encoding="utf-8", errors="replace").read()
        # 每个函数体单独统计
        for blk in re.split(r"(?=^mlc_status m2c_)", src, flags=re.M):
            if not blk.startswith("mlc_status m2c_"):
                continue
            fn = re.search(r"mlc_status (m2c_\w+)\(", blk).group(1)
            cnt = collections.Counter(
                m.group(1) for m in re.finditer(r"^\s*mlc_array (\w+);", blk, re.M))
            for name, k in cnt.items():
                if k >= 2:
                    bad.append((os.path.basename(p), fn, name, k))

    assert not bad, (
        "同一函数内重复声明（gcc 会报 redeclaration of 'x'）：%s\n"
        "来源通常是序言的 temps/consts/fills 三个声明循环没有共享去重集合" % bad[:5])


@pytest.mark.skipif(_cc() is None or not os.path.isfile(M2C),
                    reason="没有 C 编译器或 m2c 未构建")
def test_generated_c_compiles():
    """粗一层：语料工程的生成物必须能编译（不需要运行）。"""
    d = tempfile.mkdtemp(prefix="m2c_cc_")
    mir = os.path.join(d, "n.mir")
    subprocess.run([sys.executable, os.path.join(ROOT, "translate", "mir.py"),
                    os.path.join(ROOT, "translate", "examples", "numeric"),
                    "-o", mir],
                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                   stderr=subprocess.STDOUT, timeout=600, check=True)
    gen = os.path.join(d, "g")
    subprocess.run([M2C, "build", "--mir", mir, "--out", gen, "--name", "numeric"],
                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                   stderr=subprocess.STDOUT, timeout=900, check=True)
    r = subprocess.run([_cc(), "-std=c99", "-fsyntax-only",
                        "-I", os.path.join(gen, "include"),
                        "-I", os.path.join(ROOT, "c_runtime", "include"),
                        os.path.join(gen, "src", "gen.c")],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=600)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-800:]
