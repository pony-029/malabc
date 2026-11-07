# -*- coding: utf-8 -*-
"""Rust VM（`m2c run`）验收：它算出的数必须与 Octave 真值**逐字一致**。

## 为什么这条判据重要

VM 的目的是**替代 Octave 做自证**。如果它自己算错了，所有基于它的"验证"
都会变成假绿 —— 而且比没有更糟：它跑得快、输出干净，看起来最可信。

所以判据只认一件事：**与 `numeric.expected`（Octave 真值）一致**。
覆盖范围是**整个语料**（58 个），不是抽样。

## 历史

R693 首版：一致 19 ｜ 未覆盖 39（一维值模型 + 二维直接拒绝）
R695 二维值模型：44 ｜ 未覆盖 14
R696 补齐剩余算子：**58 ｜ 未覆盖 0**
"""
import io
import os
import subprocess
import sys
import tempfile

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
def test_vm_matches_octave_on_whole_corpus():
    """**全语料**逐函数比对：任何一处不一致都失败（不许只报通过率）。"""
    exp = _expected()
    d = tempfile.mkdtemp(prefix="vmtest_", dir=WORK if os.path.isdir(WORK) else None)
    bad, skipped = [], []
    checked = 0
    for fn in sorted(os.listdir(CORPUS)):
        if not fn.endswith(".m"):
            continue
        stem = fn[:-2]
        want = exp.get(stem)
        if want is None:
            continue
        mir = os.path.join(d, stem + ".mir")
        subprocess.run([sys.executable, MIR_PY, os.path.join(CORPUS, fn), "-o", mir],
                       stdin=subprocess.DEVNULL, timeout=120,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not os.path.isfile(mir):
            continue
        r = subprocess.run([M2C, "run", "--mir", mir], stdin=subprocess.DEVNULL,
                           timeout=60, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
        out = r.stdout.decode("utf-8", "replace").strip()
        if "不支持" in out or "未实现" in out:
            skipped.append((stem, out.splitlines()[0][:60]))
            continue
        assert r.returncode == 0, "%s：%s" % (stem, out[:120])
        # 多返回值：VM 一行一个，真值文件用 " | " 连接
        parts = [ln.split(":", 1)[1].strip() for ln in out.splitlines() if ":" in ln]
        got = " | ".join(parts) if len(parts) > 1 else (parts[0] if parts else out)
        checked += 1
        if " ".join(got.split()) != " ".join(want.split()):
            bad.append((stem, want, got))

    assert not bad, "VM 与 Octave 不一致 %d 个：%r" % (len(bad), bad[:5])
    assert not skipped, "有函数 VM 声明不支持（应补齐或显式登记）：%r" % (skipped[:5],)
    assert checked >= 55, "有效样本过少（%d），判据等于没跑" % checked


@pytest.mark.skipif(not os.path.isfile(M2C), reason="m2c 未构建")
def test_vm_two_dimension_column_mean():
    """二维形参：`mean(A)` 必须**逐列**（2×3 的 [1..6] → 2.5 3.5 4.5）。

    这条判据原来是"二维必须拒绝"（VM 只有一维时）。R695 支持二维后改成验正确值 ——
    因为"能算"和"算对"是两件事：第一版把 `mean(A)` 算成全元素均值（3.5），形状对、数值错。
    """
    d = WORK if os.path.isdir(WORK) else "."
    p = os.path.join(d, "vm2d.m")
    io.open(p, "w", encoding="utf-8", newline="\n").write(
        "function y = f(A)\n% @m2c shape A 2,3\n% @m2c shape y 1,3\n"
        "y = mean(A);\nend\n")
    mir = os.path.join(d, "vm2d.mir")
    subprocess.run([sys.executable, MIR_PY, p, "-o", mir], stdin=subprocess.DEVNULL,
                   timeout=120, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    r = subprocess.run([M2C, "run", "--mir", mir], stdin=subprocess.DEVNULL,
                       timeout=60, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = r.stdout.decode("utf-8", "replace").strip()
    assert r.returncode == 0, out
    got = out.split(":", 1)[1].strip() if ":" in out else out
    assert " ".join(got.split()) == "2.5 3.5 4.5", "二维 mean 必须逐列，实际：%r" % got
