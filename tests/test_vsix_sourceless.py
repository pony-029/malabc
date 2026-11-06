# -*- coding: utf-8 -*-
"""`.vsix` **不得暴露源码**。

## 为什么需要这条判据

R654 把包装方式从"发 `.py`"改成"只发 `.pyc`"，但没有回归锁 ——
任何人把 `build_vsix.py` 里那两处 `_write_py` 改回 `z.write`，
包内容会**静默**变回源码，而所有已有判据都不会红。

`.pyc` 不加密（反编译仍可得逻辑），但它挡住了"解包即读"，
而这正是用户提出的问题。

## 判据两向

1. **包内没有 `.py`**（只有 `.pyc`）；
2. **`.pyc` 真能跑** —— 解包后 `python matlabc.pyc --help` 必须 rc=0。
   只数后缀是不够的：编译失败/入口写死 `.py` 都会让包"看起来对、装上就坏"。
"""
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILDER = os.path.join(ROOT, "tools", "build_vsix.py")
TMPROOT = r"E:\temp\matlabc"


@pytest.fixture(scope="module")
def built_vsix():
    """跑一次真实打包，返回 vsix 路径。"""
    before = set()
    vdir = os.path.join(ROOT, "releases", "vsix")
    if os.path.isdir(vdir):
        before = set(os.listdir(vdir))
    r = subprocess.run([sys.executable, BUILDER], cwd=ROOT,
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=900)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-800:]
    after = set(os.listdir(vdir)) if os.path.isdir(vdir) else set()
    new = [n for n in (after - before) if n.endswith(".vsix")]
    if new:
        return os.path.join(vdir, sorted(new)[0])
    # 没有新文件：取最新的那个
    cands = sorted(n for n in after if n.endswith(".vsix"))
    assert cands, "打包后找不到 .vsix"
    return os.path.join(vdir, cands[-1])


def test_vsix_has_no_python_source(built_vsix):
    with zipfile.ZipFile(built_vsix) as z:
        names = z.namelist()
    py = [n for n in names if n.endswith(".py")]
    pyc = [n for n in names if n.endswith(".pyc")]
    assert not py, "包内不应有 .py 源码，实际 %d 个：%s" % (len(py), py[:5])
    assert len(pyc) > 30, "包内 .pyc 太少（%d 个），打包可能没走 sourceless 路径" % len(pyc)


def test_vsix_pyc_actually_runs(built_vsix):
    base = TMPROOT if os.path.isdir(TMPROOT) else tempfile.gettempdir()
    d = tempfile.mkdtemp(prefix="m2c_vsix_", dir=base)
    try:
        with zipfile.ZipFile(built_vsix) as z:
            z.extractall(d)
        ext = os.path.join(d, "extension")
        # 入口必须能启动（`--help` 是最小可验证行为）
        r = subprocess.run([sys.executable, os.path.join(ext, "matlabc.pyc"), "--help"],
                           cwd=ext, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=180)
        assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-600:]
        # LSP 入口：sourceless 后它必须能找到 matlabc.pyc（R654 踩过）
        r2 = subprocess.run([sys.executable, os.path.join(ext, "matlabc_lsp.pyc")],
                            cwd=ext, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=60)
        out = r2.stdout.decode("utf-8", "replace")
        assert "找不到 matlabc.py" not in out, "LSP 仍在找 .py 源码：%s" % out[:300]
    finally:
        shutil.rmtree(d, ignore_errors=True)
