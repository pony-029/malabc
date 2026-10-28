# -*- coding: utf-8 -*-
"""算子的**错误路径**单元断言：直接调 C，断言"该拒绝的都拒绝了"。

## 为什么需要它（有实测数字支撑）

gcov 基准（`docs/COVERAGE_BASELINE.md`）：语料 40 例全过时，
`mlc_ops.c` 行覆盖只有 **56.98%**，而**未覆盖的行几乎全是 `return MLC_ERR`
及其卫语句** —— 因为语料只喂合法输入。

⇒ 此前"cppcheck 干净 + 语料全过"的结论**只覆盖 happy path**；而早期 `return`
正是泄漏最容易发生的位置（跳过后面的 free）。这一层专门点亮那些分支。

## 判据

每个用例都断言 **返回码 != MLC_OK**（拒绝），并且程序不崩：
* 空指针 / dtype 不符
* 不可广播的形状
* 输出形状与广播结论不一致
* 下标越界（col/row/colrange）
* 矩阵乘内维不匹配
* `find(a==b)` 两数组不等长
* `mlc_array_init` 的 ndim 超上限
"""
import os
import shutil
import subprocess
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RT = os.path.join(ROOT, "c_runtime")

_PROG = r"""
#include <stdio.h>
#include <string.h>
#include "mlc_ops.h"

static mlc_array mk(int64_t r, int64_t c, const double *v)
{
    mlc_array a;
    int64_t sh[2];
    int64_t i;
    sh[0] = r; sh[1] = c;
    mlc_array_init(&a, MLC_F64, 2, sh);
    if (v != NULL) {
        for (i = 0; i < r * c; ++i) { ((double *)a.data)[i] = v[i]; }
    }
    return a;
}

int main(void)
{
    double v6[6] = {1, 2, 3, 4, 5, 6};
    double v4[4] = {1, 2, 3, 4};
    mlc_array a = mk(2, 3, v6);
    mlc_array b4 = mk(2, 2, v4);
    mlc_array out;
    int64_t sh1[1] = {6};
    mlc_array_init(&out, MLC_F64, 1, sh1);

    /* E1 空指针 */
    printf("null_add=%d\n", (int)mlc_op_add(NULL, &a, &out));

    /* E2 不可广播：(2,3) vs (2,2) */
    printf("bad_bcast=%d\n", (int)mlc_op_add(&a, &b4, &out));

    /* E3 输出形状与广播结论不一致 */
    {
        mlc_array o2;
        int64_t bad[1] = {1};
        mlc_array_init(&o2, MLC_F64, 1, bad);
        printf("out_shape=%d\n", (int)mlc_op_add(&a, &a, &o2));
        mlc_array_free(&o2);
    }

    /* E4 dtype 不符（i64 数组参与 f64 运算） */
    {
        mlc_array i64a;
        int64_t shi[1] = {2};
        mlc_array_init(&i64a, MLC_I64, 1, shi);
        printf("bad_dtype=%d\n", (int)mlc_op_add(&i64a, &i64a, &out));
        mlc_array_free(&i64a);
    }

    /* E5 下标越界 */
    printf("col_oob=%d\n", (int)mlc_op_col(&a, 9, &out));
    printf("col_zero=%d\n", (int)mlc_op_col(&a, 0, &out));
    printf("row_oob=%d\n", (int)mlc_op_row(&a, 9, &out));

    /* E6 列区间越界 */
    {
        mlc_array o3;
        memset(&o3, 0, sizeof(o3));
        printf("colrange_oob=%d\n", (int)mlc_op_colrange(&a, 9, 12, &o3));
    }

    /* E7 矩阵乘内维不匹配 (2,3)x(2,2) */
    {
        mlc_array o4;
        memset(&o4, 0, sizeof(o4));
        printf("matmul_bad=%d\n", (int)mlc_op_matmul(&a, &b4, &o4));
    }

    /* E8 find(a==b) 两数组不等长 */
    {
        mlc_array o5;
        memset(&o5, 0, sizeof(o5));
        printf("find2_len=%d\n", (int)mlc_op_find_masked(&a, &b4, 4, &o5));
    }

    /* E9 ndim 超上限 */
    {
        mlc_array bad;
        int64_t shx[MLC_MAX_DIMS + 1];
        int i;
        for (i = 0; i <= MLC_MAX_DIMS; ++i) { shx[i] = 1; }
        printf("bad_ndim=%d\n",
               (int)mlc_array_init(&bad, MLC_F64, MLC_MAX_DIMS + 1, shx));
    }

    /* E10 非 2-D 取列 */
    {
        mlc_array o6;
        int64_t shv[1] = {3};
        mlc_array vv;
        memset(&o6, 0, sizeof(o6));
        mlc_array_init(&vv, MLC_F64, 1, shv);
        printf("col_1d=%d\n", (int)mlc_op_col(&vv, 1, &o6));
        mlc_array_free(&vv);
    }

    printf("done=1\n");
    mlc_array_free(&a);
    mlc_array_free(&b4);
    mlc_array_free(&out);
    return 0;
}
"""

EXPECT_NONZERO = ("null_add", "bad_bcast", "out_shape", "bad_dtype", "col_oob",
                  "col_zero", "row_oob", "colrange_oob", "matmul_bad",
                  "find2_len", "bad_ndim", "col_1d")


def _cc():
    return shutil.which("gcc") or shutil.which("clang")


@pytest.mark.skipif(_cc() is None, reason="没有 C 编译器")
def test_error_paths_all_rejected():
    d = tempfile.mkdtemp(prefix="m2c_errpath_")
    src = os.path.join(d, "e.c")
    with open(src, "w") as f:
        f.write(_PROG)
    exe = os.path.join(d, "e.exe")
    r = subprocess.run([_cc(), "-std=c99", "-O0",
                        "-I", os.path.join(RT, "include"),
                        src,
                        os.path.join(RT, "src", "mlc_runtime.c"),
                        os.path.join(RT, "src", "mlc_ops.c"),
                        "-o", exe, "-lm"],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=600)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-600:]

    out = subprocess.run([exe], stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         timeout=300).stdout.decode("utf-8", "replace")

    # 程序必须跑完（没有崩溃）
    assert "done=1" in out, out[-400:]

    got = {}
    for ln in out.splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            got[k.strip()] = v.strip()
    missing = [k for k in EXPECT_NONZERO if k not in got]
    assert not missing, "缺结果：%s\n%s" % (missing, out)

    bad = [(k, got[k]) for k in EXPECT_NONZERO if got[k] == "0"]
    assert not bad, "这些错误路径**没有拒绝**（返回 0）：%s" % bad
