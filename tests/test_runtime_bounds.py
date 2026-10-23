# -*- coding: utf-8 -*-
"""运行时边界：越界必须**报错**，不能静默截断或返回垃圾。

为什么值得一条独立判据：语料全是"正常路径"（20/20 都对），
而越界行为只在真实输入出错时才暴露 —— 那时已经离现场很远了。
这里直接调 C 运行时，锁住 `mlc_op_index/row/slice/setidx` 的越界语义。
"""
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROG = r"""
#include <stdio.h>
#include "mlc.h"
#include "mlc_ops.h"

static int fails = 0;

static void expect_err(const char *what, mlc_status st)
{
    if (st == MLC_OK) {
        printf("BAD %s: 越界却返回 MLC_OK\n", what);
        fails++;
    }
}

int main(void)
{
    mlc_array a, one;
    int64_t d3[1] = {3};
    int64_t d1[1] = {1};
    int64_t d2[2] = {2, 3};
    mlc_array m;

    if (mlc_array_init(&a, MLC_F64, 1, d3) != MLC_OK) return 2;
    if (mlc_array_init(&one, MLC_F64, 1, d1) != MLC_OK) return 2;
    if (mlc_array_init(&m, MLC_F64, 2, d2) != MLC_OK) return 2;
    ((double *)a.data)[0] = 1; ((double *)a.data)[1] = 2; ((double *)a.data)[2] = 3;
    ((double *)one.data)[0] = 9;

    expect_err("index 0",   mlc_op_index(&a, 0, &one));
    expect_err("index 4",   mlc_op_index(&a, 4, &one));
    expect_err("slice 2..5", mlc_op_slice(&a, 2, 5, &one));
    expect_err("row on 1-D", mlc_op_row(&a, 1, &one));

    /* 行切片：2x3 取第 3 行越界 */
    {
        mlc_array out23;
        int64_t d3c[1] = {3};
        if (mlc_array_init(&out23, MLC_F64, 1, d3c) != MLC_OK) return 2;
        expect_err("row 3 of 2", mlc_op_row(&m, 3, &out23));
        mlc_array_free(&out23);
    }

    /* 元素赋值：下标 0 / 4 越界 */
    expect_err("setidx 0", mlc_op_setidx(&a, &one, 0));
    expect_err("setidx 4", mlc_op_setidx(&a, &one, 4));

    if (fails) { printf("FAILS %d\n", fails); return 1; }
    printf("OK\n");
    mlc_array_free(&a); mlc_array_free(&one); mlc_array_free(&m);
    return 0;
}
"""


def _cc():
    for name in ("gcc", "clang", "cc"):
        p = shutil.which(name)
        if p:
            return p
    return None


@pytest.mark.skipif(_cc() is None, reason="没有 C 编译器")
def test_out_of_range_returns_error():
    cc = _cc()
    d = tempfile.mkdtemp(prefix="mlc_bounds_")
    src = os.path.join(d, "t.c")
    exe = os.path.join(d, "t.exe")
    with open(src, "w", encoding="utf-8", newline="") as fh:
        fh.write(PROG)
    build = subprocess.run(
        [cc, "-std=c99", "-O1",
         "-I", os.path.join(ROOT, "c_runtime", "include"),
         src,
         os.path.join(ROOT, "c_runtime", "src", "mlc_runtime.c"),
         os.path.join(ROOT, "c_runtime", "src", "mlc_ops.c"),
         "-o", exe],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=300)
    assert build.returncode == 0, build.stdout.decode("utf-8", "replace")[-500:]

    run = subprocess.run([exe], stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         timeout=120)
    out = run.stdout.decode("utf-8", "replace")
    assert run.returncode == 0, "越界没有全部报错：%s" % out.strip()
    assert "OK" in out, out
