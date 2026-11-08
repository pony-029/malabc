# -*- coding: utf-8 -*-
"""往返闭环（**只用 Rust VM**，不碰 Octave）：58 个语料必须全部一致。

## 为什么单独一条

`test_roundtrip.py` 走的是 Octave 路线，而 `roundtrip.py` 在 VM 失败时会**回退
Octave** —— 于是"回译产物解析不了"这类失败会被兜底吞掉，报表依然全绿（R700）。

这条判据把兜底关掉：
  `.m → MIR → .m' → MIR' → VM`，两侧数值必须相等，且**不允许跳过**。

它是本项目"闭环"的最后一道：正向、反向、以及**反向产物能否被自己解析**。
"""
import io
import os
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from translate import roundtrip as RT        # noqa: E402
from translate import unmir as U             # noqa: E402

CORPUS = os.path.join(ROOT, "translate", "examples", "numeric")
MIR_PY = os.path.join(ROOT, "translate", "mir.py")
WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"


@pytest.mark.skipif(not os.path.isfile(RT.M2C), reason="m2c 未构建")
def test_roundtrip_vm_only_covers_whole_corpus():
    d = tempfile.mkdtemp(prefix="rtvm_", dir=WORK if os.path.isdir(WORK) else None)
    os.makedirs(os.path.join(d, "back"), exist_ok=True)

    ok, bad, skipped = [], [], []
    for fn in sorted(os.listdir(CORPUS)):
        if not fn.endswith(".m"):
            continue
        stem = fn[:-2]
        mir = os.path.join(d, stem + ".mir")
        subprocess.run([sys.executable, MIR_PY, os.path.join(CORPUS, fn), "-o", mir],
                       stdin=subprocess.DEVNULL, timeout=120,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not os.path.isfile(mir):
            skipped.append((stem, "无 MIR"))
            continue
        out_m = os.path.join(d, "back", fn)
        if U.convert(mir, out_m):
            skipped.append((stem, "回译有算子不认识"))
            continue
        bmir = os.path.join(d, stem + "_b.mir")
        subprocess.run([sys.executable, MIR_PY, out_m, "-o", bmir],
                       stdin=subprocess.DEVNULL, timeout=120,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not os.path.isfile(bmir):
            bad.append((stem, "回译产物无法解析"))
            continue
        txt = io.open(bmir, encoding="utf-8").read()
        if "unmapped:" in txt:
            first = [l for l in txt.splitlines() if l.startswith("unmapped:")][0][9:]
            bad.append((stem, "回译产物有未映射：" + first[:40]))
            continue
        shapes = RT._arg_shapes(mir)
        a = RT._vm_values(mir, shapes)
        b = RT._vm_values(bmir, shapes)
        if a is None or b is None:
            skipped.append((stem, "VM 算不了"))
        elif " ".join(a.split()) == " ".join(b.split()):
            ok.append(stem)
        else:
            bad.append((stem, "%r vs %r" % (a, b)))

    assert not bad, "往返不一致 %d 个：%r" % (len(bad), bad[:5])
    assert not skipped, "有函数被跳过（不允许用跳过掩盖）：%r" % (skipped[:5],)
    assert len(ok) >= 55, "有效样本过少（%d），判据等于没跑" % len(ok)
