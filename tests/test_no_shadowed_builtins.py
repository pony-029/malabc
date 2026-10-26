# -*- coding: utf-8 -*-
"""语料里不得出现「内置名被当作数组下标」的静默误判。

为什么必须常驻：这类缺陷已出现六次（`isempty`/`numel`/`sqrt`/`find`/`any`/`nnz`…）。
它的特征是**能编译、能运行、结果是错的** —— 任何"跑通了"的信号都不会报警，
只有一致性检验能发现：**取下标的名字在该函数里从未声明**。

两向：语料必须为 0；临时造一个 `y = foo(x)`（foo 非算子、非工程函数）必须被抓到。
"""
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import scan_shadowed_builtins as S  # noqa: E402

MIRPY = os.path.join(ROOT, "translate", "mir.py")


def _mir_of(target, extra=()):
    import tempfile
    out = os.path.join(tempfile.mkdtemp(prefix="m2c_shadow_"), "s.mir")
    cmd = [sys.executable, MIRPY, target, "-o", out] + list(extra)
    r = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=600)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-400:]
    import io
    return io.open(out, encoding="utf-8", errors="replace").read()


def test_corpus_has_no_shadowed_index():
    rows = S.scan(_mir_of(os.path.join(ROOT, "translate", "examples")))
    assert rows == [], "语料里出现静默误判：%s" % rows[:3]


def test_postpass_turns_shadowed_index_into_unmapped():
    """后处理：`op:OP-INDEX` 的目标名若从未声明 -> 改写成如实拒绝。

    这是 `isempty`/`numel`/`sqrt`/`find`/`any`/`nnz` 六次误判的结构性收口：
    它们都表现为「能编译、能运行、答案错」，而任何"跑通了"的信号都不会报警。
    """
    import translate.mir as M

    lines = ["func:f", "arg:x:f64:4", "ret:y:f64:1",
             "op:OP-INDEX:y:zzz:x", "end"]
    out = M._drop_shadowed_indices(lines)
    assert "# why:shadowed" in out, out
    assert not any(x.startswith("op:OP-INDEX:y:zzz") for x in out), out


def test_postpass_keeps_declared_index():
    """已声明的数组取下标必须原样保留（不能误伤）。"""
    import translate.mir as M

    lines = ["func:f", "arg:x:f64:4", "ret:y:f64:1",
             "op:OP-INDEX:y:x:1", "end"]
    out = M._drop_shadowed_indices(lines)
    assert "op:OP-INDEX:y:x:1" in out, out
    assert "# why:shadowed" not in out, out
