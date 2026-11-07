# -*- coding: utf-8 -*-
"""Rust VM（`m2c run`）验收：它算出的数必须与 Octave 真值一致。

## 为什么要有这条判据

VM 的目的是**替代 Octave 做自证**。如果它自己算错了，那所有基于它的"验证"
都会变成假绿 —— 而且比没有更糟：它跑得快、输出干净，看起来最可信。

所以判据只认一件事：**与 `numeric.expected`（Octave 真值）逐字一致**。

## 为什么只挑部分函数

VM 的值模型是**一维**。二维函数（`meancols`/`sumcols`/`vcat2`）它会**主动拒绝**
（而不是算成"全元素均值"那种形状对、值错的结果）。
本判据只覆盖它声明支持的子集；未覆盖由 `m2c run` 自己报 `skip`/`error`，不静默。
"""
import io
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MIR_PY = os.path.join(ROOT, "translate", "mir.py")
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release", "m2c.exe")
CORPUS = os.path.join(ROOT, "translate", "examples", "numeric")
EXP = os.path.join(ROOT, "translate", "examples", "numeric.expected")
WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"


def _expected():
    d = {}
    for ln in io.open(EXP, encoding="utf-8", errors="replace"):
        ln = ln.strip()
        if ln and ":" in ln:
            k, v = ln.split(":", 1)
            d[k.strip()] = v.strip()
    return d


@pytest.mark.skipif(not os.path.isfile(M2C), reason="m2c 未构建")
@pytest.mark.parametrize("fn", ["snr", "sumsq", "cumsum_loop", "while_acc", "condsize"])
def test_vm_matches_octave(fn):
    src = os.path.join(CORPUS, fn + ".m")
    if not os.path.isfile(src):
        pytest.skip("语料里没有 " + fn)
    want = _expected().get(fn)
    if want is None:
        pytest.skip("没有真值：" + fn)

    d = WORK if os.path.isdir(WORK) else None
    mir = os.path.join(d or ".", "vm_" + fn + ".mir")
    r = subprocess.run([sys.executable, MIR_PY, src, "-o", mir],
                       stdin=subprocess.DEVNULL, timeout=120,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert r.returncode == 0
    r = subprocess.run([M2C, "run", "--mir", mir], stdin=subprocess.DEVNULL,
                       timeout=60, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = r.stdout.decode("utf-8", "replace").strip()
    if "不支持" in out or "未支持" in out or "未实现" in out:
        pytest.skip("VM 声明不支持：" + out.splitlines()[0][:60])
    assert r.returncode == 0, out
    got = out.split(":", 1)[1].strip() if ":" in out else out
    assert " ".join(got.split()) == " ".join(want.split()), \
        "%s：VM=%r 期望=%r" % (fn, got, want)


@pytest.mark.skipif(not os.path.isfile(M2C), reason="m2c 未构建")
def test_vm_two_dimension_column_mean():
    """二维形参：`mean(A)` 必须**逐列**（2×3 的 [1..6] → 2.5 3.5 4.5）。

    这条判据原来是"二维必须拒绝"（VM 只有一维时）。R695 支持二维后，
    它改成验**正确的列均值** —— 因为"能算"和"算对"是两件事：
    VM 第一版把 `mean(A)` 算成**全元素均值**（3.5），形状对、数值错。
    """
    d = WORK if os.path.isdir(WORK) else "."
    p = os.path.join(d, "vm2d.m")
    io.open(p, "w", encoding="utf-8", newline="\n").write(
        "function y = f(A)\n% @m2c shape A 2,3\n% @m2c shape y 1\n"
        "y = mean(A);\nend\n")
    mir = os.path.join(d, "vm2d.mir")
    subprocess.run([sys.executable, MIR_PY, p, "-o", mir], stdin=subprocess.DEVNULL,
                   timeout=120, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    r = subprocess.run([M2C, "run", "--mir", mir], stdin=subprocess.DEVNULL,
                       timeout=60, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = r.stdout.decode("utf-8", "replace").strip()
    assert r.returncode == 0, out
    got = out.split(":", 1)[1].strip() if ":" in out else out
    assert " ".join(got.split()) == "2.5 3.5 4.5", \
        "二维 mean 必须逐列，实际：%r" % got
