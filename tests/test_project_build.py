# -*- coding: utf-8 -*-
"""`project_map.py --build` 的端到端判据（在**临时目录**里跑，不污染仓库）。

上上轮的教训：`--build` 的产物落进仓库，被 EOL 门扫到（门看文件系统，不看 `.gitignore`）。
所以这里一切都在 `tempfile` 里做。

判据分两向：
1. **正向**：配置 `static_pool: 4096` → 构建、编译、运行 → 各函数输出正确，
   且生成的 `gen.c` 里真的有 `m2c_pool_boot`、`main.c` 第一句就调它；
2. **反向**：把池改成 32 字节（连一个 4 元数组都装不下）→ 程序**不再产出结果**
   —— 这证明池确实在分配路径上，而不是写着好看。
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RT = os.path.join(ROOT, "c_runtime")
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release", "m2c.exe")
PM_PY = os.path.join(ROOT, "translate", "project_map.py")
SRC = os.path.join(ROOT, "translate", "examples", "numeric")

PICK = ("above.m", "anyv.m", "col1.m", "col2sum.m")


def _cc():
    return shutil.which("gcc") or shutil.which("clang")


def _setup(d, pool_bytes):
    m = os.path.join(d, "m")
    os.makedirs(m, exist_ok=True)
    for n in PICK:
        src = os.path.join(SRC, n)
        if os.path.isfile(src):
            shutil.copy(src, m)
    cfg = {
        "version": 2,
        "matlab": {"root": "m", "recursive": False, "exclude": []},
        "c": {"root": "gen", "project": "demo", "prefix": "m2c_", "runtime": "c_runtime"},
        "targets": {"mcu": {"abi": "arm", "allow_heap": False, "dtype": "f64",
                            "memory": {"strategy": "static_pool",
                                       "pool_bytes": pool_bytes, "alignment": 8}}},
        "modules": [{"id": "m1", "targets": ["mcu"], "sources": ["above"]}],
        "operators": {},
        "constraints": {},
    }
    p = os.path.join(d, "m2c.project.json")
    io.open(p, "w", encoding="utf-8").write(json.dumps(cfg, ensure_ascii=False))
    return p


def _build(d, pool_bytes, cc):
    p = _setup(d, pool_bytes)
    r = subprocess.run([sys.executable, PM_PY, p, "--build"],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=900, cwd=d)
    # P2（R773）起，**超预算在生成期就失败**，不再等运行期 OOM。
    # 老版本这里断言 rc==0（构建成功、运行崩），那是 P2 之前的行为。
    if pool_bytes < 4096:
        assert r.returncode != 0, "池子 %d 字节竟然构建成功（应超预算失败）" % pool_bytes
        out = r.stdout.decode("utf-8", "replace")
        assert "超预算" in out, "失败信息里没有『超预算』：%s" % out[-400:]
        return
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-800:]

    gen = os.path.join(d, "gen")
    exe = os.path.join(d, "n.exe")
    r2 = subprocess.run([cc, "-std=c99", "-O1",
                         "-I", os.path.join(gen, "include"),
                         "-I", os.path.join(RT, "include"),
                         os.path.join(gen, "src", "gen.c"),
                         os.path.join(gen, "src", "main.c"),
                         os.path.join(RT, "src", "mlc_runtime.c"),
                         os.path.join(RT, "src", "mlc_ops.c"),
                         "-o", exe, "-lm"],
                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, timeout=900)
    assert r2.returncode == 0, r2.stdout.decode("utf-8", "replace")[-800:]
    out = subprocess.run([exe], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT,
                         timeout=120).stdout.decode("utf-8", "replace")
    return gen, out


@pytest.mark.skipif(_cc() is None or not os.path.isfile(M2C), reason="缺编译器或 m2c")
def test_build_generates_pool_and_runs():
    d = tempfile.mkdtemp(prefix="m2c_projbuild_")
    try:
        gen, out = _build(d, 4096, _cc())
        gen_c = io.open(os.path.join(gen, "src", "gen.c"), encoding="utf-8").read()
        main_c = io.open(os.path.join(gen, "src", "main.c"), encoding="utf-8").read()
        assert "m2c_pool_boot" in gen_c, "gen.c 里应有池的启动函数"
        assert "mlc_pool_configure" in gen_c
        assert "m2c_pool_boot();" in main_c, "main 第一句必须配置池"
        # 正向：语料函数必须真的算出数
        lines = [x for x in out.splitlines() if ":" in x]
        assert len(lines) >= 3, out
        assert "above:" in out, out
        assert ": error" not in out, out
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.skipif(_cc() is None or not os.path.isfile(M2C), reason="缺编译器或 m2c")
def test_tiny_pool_is_rejected_at_generation():
    """反向：32 字节池连一个 4 元数组都装不下 —— **在生成期就拒绝**。

    ⚠ 这条判据在 R773（P2）之前断言的是"构建成功、运行期不出结果"。
    P2 把超预算提前到生成期（`budget.json` + 指名函数/变量），
    所以现在要断言"构建失败且说明超预算" —— 比"运行期悄悄没了结果"可行动得多。
    """
    d1 = tempfile.mkdtemp(prefix="m2c_poolbig_")
    d2 = tempfile.mkdtemp(prefix="m2c_pooltiny_")
    try:
        _, big = _build(d1, 4096, _cc())
        assert big.strip(), "大池应当有输出"
        # 32 字节池：`_build` 内部已断言"必须失败且含『超预算』"
        _build(d2, 32, _cc())
    finally:
        shutil.rmtree(d1, ignore_errors=True)
        shutil.rmtree(d2, ignore_errors=True)
        shutil.rmtree(d2, ignore_errors=True)
