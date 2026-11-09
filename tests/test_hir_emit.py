# -*- coding: utf-8 -*-
"""`--hir-emit`：**MIR 由 HIR 产出**之后，产物必须仍然编译并算对。

## 这条判据守什么

`--via-hir`（R734）只**比对**；`--hir-emit`（R738）**替换产物** —— 风险高一个量级：
折树会把实参重新编排，位置敏感的实参（比较码、下标、维度、被比较的标量）一错，
发射器要么编译失败，要么算出错值。

所以这里不看"能不能产出"，只看三件事：
1. `m2c build` 通过；2. `gcc` 通过；3. 运行后**没有 unimplemented**，且抽查数值正确。

R738 实测：56/58 函数由 HIR 产出，`iseqtest` 因 `isequalk(x,0)` 的 `0` 被物化而
unimplemented（已修：`pred` 族加入 keep_literal）。
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MIR_PY = os.path.join(ROOT, "translate", "mir.py")
CORPUS = os.path.join(ROOT, "translate", "examples", "numeric")
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release",
                   "m2c.exe" if os.name == "nt" else "m2c")
RT_INC = os.path.join(ROOT, "c_runtime", "include")
RT_SRC = [os.path.join(ROOT, "c_runtime", "src", "mlc_runtime.c"),
          os.path.join(ROOT, "c_runtime", "src", "mlc_ops.c")]
WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"


def _run(cmd, timeout=600):
    return subprocess.run(cmd, stdin=subprocess.DEVNULL, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


@pytest.fixture(scope="module")
def emitted():
    """跑一次 --hir-emit 并编译，返回 (exe 输出, 说明)。"""
    if not os.path.isfile(M2C):
        pytest.skip("m2c 未构建")
    d = tempfile.mkdtemp(prefix="he_", dir=WORK if os.path.isdir(WORK) else None)
    mir = os.path.join(d, "he.mir")
    r = _run([sys.executable, MIR_PY, CORPUS, "--hir-emit", "-o", mir], 300)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-400:]

    g = os.path.join(d, "g")
    r = _run([M2C, "build", "--mir", mir, "--out", g, "--name", "he"], 300)
    assert r.returncode == 0, "HIR 产出的 MIR 编不过：%s" % \
        r.stdout.decode("utf-8", "replace")[-300:]

    cc = shutil.which("gcc") or shutil.which("clang")
    exe = os.path.join(g, "he" + (".exe" if os.name == "nt" else ""))
    r = _run([cc, "-std=c99", "-O1", "-I", os.path.join(g, "include"),
              "-I", RT_INC, os.path.join(g, "src", "gen.c"),
              os.path.join(g, "src", "main.c")] + RT_SRC + ["-o", exe], 900)
    assert r.returncode == 0, "gcc 失败：%s" % r.stdout.decode("utf-8", "replace")[-300:]

    r = _run([exe], 300)
    return r.stdout.decode("utf-8", "replace")


def test_no_unimplemented(emitted):
    """HIR 产出的 MIR 不允许留下 unimplemented —— 那等于"产出成功但不可用"。"""
    bad = [ln.strip() for ln in emitted.splitlines() if "unimplemented" in ln]
    assert not bad, "HIR 产出后有 %d 个 unimplemented：%r" % (len(bad), bad[:4])


@pytest.mark.parametrize("name,want", [
    ("above", "3 4 5"),
    ("colmean", "1 3 5"),
    ("snr", "0"),
    ("iseqtest", "1"),        # 真值文件里就是 1（`isequalk(x,0)` 为假时 +10 不执行）
    ("col2sum", "12"),
])
def test_spots_match(emitted, name, want):
    """抽查：值与真值一致（覆盖一维/二维/条件/谓词四种形态）。"""
    got = None
    for ln in emitted.splitlines():
        if ln.startswith(name + ":"):
            got = " ".join(ln.split(":", 1)[1].split())
            break
    assert got is not None, "没有 %s 的输出" % name
    assert got == want, "%s：得 %r 期望 %r" % (name, got, want)
