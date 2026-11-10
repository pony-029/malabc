# -*- coding: utf-8 -*-
"""诊断**逐字一致**：`check` 在两条 MIR 生成路径下必须输出完全相同的结果。

## 为什么这条比"行号覆盖 95%"更硬

`# src:` 数量相等只说明"行号条数对上"，不排除**指错行**（值错了但条数一样）。
R750 还发现过更隐蔽的形态：行号对、**类别**丢（`# why:` 没带过去 → 全退化成 `[misc]`）。

这条判据不看中间产物，直接比**用户看到的东西**：同一份 `.m`，两种生成方式，
`check` 的完整输出必须逐字节相同。

## 怎么切换路径

`translate/check.py` 读环境变量 `M2C_MIR_ARGS`（默认空 = 与直接调 `mir.py` 相同）。
"""
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CHECK_PY = os.path.join(ROOT, "translate", "check.py")

#: 两份形态不同的样本：一个含大量未映射（jsonlab 有则用），一个纯数值。
CORPUS = os.path.join(ROOT, "translate", "examples", "numeric")
SAMPLES = [os.path.join(CORPUS, "snr.m"),
           os.path.join(CORPUS, "colmax_loop.m"),
           os.path.join(CORPUS, "iseqtest.m")]


def _check(path, mir_args):
    env = dict(os.environ)
    env["M2C_MIR_ARGS"] = mir_args
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run([sys.executable, CHECK_PY, path],
                       stdin=subprocess.DEVNULL, timeout=180, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return r.returncode, r.stdout.decode("utf-8", "replace").replace("\r\n", "\n")


@pytest.mark.parametrize("path", SAMPLES, ids=[os.path.basename(p) for p in SAMPLES])
def test_check_output_identical_on_both_paths(path):
    if not os.path.isfile(path):
        pytest.skip("样本不存在：%s" % path)

    rc_base, out_base = _check(path, "")             # 直出
    rc_he, out_he = _check(path, "--hir-emit")       # HIR 产出

    assert rc_base == rc_he, "退出码不同：%d vs %d" % (rc_base, rc_he)
    if out_base != out_he:
        la, lb = out_base.split("\n"), out_he.split("\n")
        diff = [(i + 1, x, y) for i, (x, y) in enumerate(zip(la, lb)) if x != y]
        head = "\n".join("  行%d\n    直出: %s\n    HIR : %s" % (i, x[:90], y[:90])
                         for i, x, y in diff[:3])
        pytest.fail("诊断输出不同（%d 行差异）：\n%s" % (len(diff), head))
