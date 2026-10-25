# -*- coding: utf-8 -*-
"""下标类算子的**单元级**断言：直接调 C 算子，不经驱动、不经端到端对拍。

为什么必须有这一层：
`mlc_op_col` 曾带着一个 strides 错误（`i + (j-1)*strides[1]`）通过全部端到端对拍
（`[TP7] 28/28`）—— 因为语料里没有"行主序填充 + 取中间列"的组合，
而那个错误公式在 **方阵**（行数==列数）下与正确公式给出同一个答案。

所以这里的判据是：
  1) 用**行列不相等**的形状（2×3）
  2) 数据按行主序填 1..6，断言取列结果与 MATLAB 语义逐元素相等
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
#include "mlc_ops.h"

static mlc_array mk(int64_t r, int64_t c, const double *v)
{
    mlc_array a;
    int64_t sh[2];
    int64_t i;
    sh[0] = r; sh[1] = c;
    mlc_array_init(&a, MLC_F64, 2, sh);
    for (i = 0; i < r * c; ++i) { ((double *)a.data)[i] = v[i]; }
    return a;
}

static void show(const char *tag, mlc_array *x)
{
    int64_t i;
    printf("%s", tag);
    for (i = 0; i < mlc_array_numel(x); ++i) {
        printf(" %g", ((double *)x->data)[i]);
    }
    printf("\n");
}

int main(void)
{
    /* A = [1 2 3; 4 5 6]，行主序填充 */
    double v[6] = {1, 2, 3, 4, 5, 6};
    mlc_array a = mk(2, 3, v);
    mlc_array c;
    int64_t sh[1];

    sh[0] = 2;
    mlc_array_init(&c, MLC_F64, 1, sh);
    printf("col_rc=%d\n", (int)mlc_op_col(&a, 2, &c));
    show("col2", &c);

    sh[0] = 3;                      /* 行切片输出长度 = 列数 */
    mlc_array_init(&c, MLC_F64, 1, sh);
    printf("row_rc=%d\n", (int)mlc_op_row(&a, 2, &c));
    show("row2", &c);
    return 0;
}
"""


def _cc():
    return shutil.which("gcc") or shutil.which("clang")


@pytest.mark.skipif(_cc() is None, reason="没有 C 编译器")
def test_col_and_row_on_nonsquare():
    d = tempfile.mkdtemp(prefix="m2c_unit_idx_")
    csrc = os.path.join(d, "t.c")
    exe = os.path.join(d, "t.exe")
    with open(csrc, "w", encoding="utf-8") as f:
        f.write(_PROG)

    r = subprocess.run([_cc(), "-std=c99", "-O1",
                        "-I", os.path.join(RT, "include"),
                        csrc,
                        os.path.join(RT, "src", "mlc_runtime.c"),
                        os.path.join(RT, "src", "mlc_ops.c"),
                        "-o", exe],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=600)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-800:]

    out = subprocess.run([exe], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT,
                         timeout=300).stdout.decode("utf-8", "replace")
    # A(:,2) = [2; 5]
    assert "col_rc=0" in out, out
    assert "col2 2 5" in out, out
    # A(2,:) = [4 5 6]
    assert "row_rc=0" in out, out
    assert "row2 4 5 6" in out, out
