# -*- coding: utf-8 -*-
"""拼接的**空操作数**边界：`[[] b]` 必须等于 `b`。

这个分支差分装置没扫到（形状面没抽中空数组），是探针发现的，
所以这里落一条常驻判据 —— 与「一元算子拒绝空输入」是同一类错误：
**把 `data == NULL` 一律当"未初始化"**，而空数组的 data 必然是 NULL。
"""
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RT = os.path.join(ROOT, "c_runtime")
sys.path.insert(0, ROOT)

from translate import mir_eval as E  # noqa: E402

PROG = r'''
#include <stdio.h>
#include "mlc.h"
#include "mlc_ops.h"

static void run(int na, int nb, const char *tag)
{
    mlc_array a, b, o;
    mlc_status st;
    int64_t sa = na, sb = nb, i;
    mlc_array_init(&a, MLC_F64, 1, &sa);
    mlc_array_init(&b, MLC_F64, 1, &sb);
    for (i = 0; i < na; ++i) { ((double *)a.data)[i] = (double)(i + 1); }
    for (i = 0; i < nb; ++i) { ((double *)b.data)[i] = (double)(10 + i); }
    mlc_array_init(&o, MLC_F64, 1, (int64_t[]){0});
    st = mlc_op_hcat(&a, &b, &o);
    printf("%s %d %lld", tag, (int)st, (long long)mlc_array_numel(&o));
    for (i = 0; i < mlc_array_numel(&o); ++i) {
        printf(" %.0f", ((double *)o.data)[i]);
    }
    printf("\n");
    mlc_array_free(&o);
    mlc_array_free(&b);
    mlc_array_free(&a);
}

int main(void)
{
    run(0, 3, "empty_first");
    run(3, 0, "empty_second");
    run(0, 0, "both_empty");
    return 0;
}
'''


def _cc():
    return shutil.which("gcc") or shutil.which("clang")


@pytest.mark.skipif(_cc() is None, reason="没有 C 编译器")
def test_hcat_with_empty_operand():
    d = tempfile.mkdtemp(prefix="m2c_hce_")
    try:
        src = os.path.join(d, "h.c")
        with open(src, "w") as f:
            f.write(PROG)
        exe = os.path.join(d, "h.exe")
        r = subprocess.run([_cc(), "-std=c99", "-O0", "-I", os.path.join(RT, "include"),
                            src, os.path.join(RT, "src", "mlc_runtime.c"),
                            os.path.join(RT, "src", "mlc_ops.c"), "-o", exe, "-lm"],
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=600)
        assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-600:]
        out = subprocess.run([exe], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT,
                             timeout=60).stdout.decode("utf-8", "replace")
        got = {}
        for ln in out.splitlines():
            p = ln.split()
            if len(p) >= 3:
                got[p[0]] = (int(p[1]), int(p[2]), [float(x) for x in p[3:]])

        # 与解释器**同一份语义**：拼接=长度相加，空操作数不改变另一侧
        cases = {"empty_first": (0, 3), "empty_second": (3, 0), "both_empty": (0, 0)}
        for tag, (na, nb) in cases.items():
            a = E.Arr([float(i + 1) for i in range(na)], [na])
            b = E.Arr([float(10 + i) for i in range(nb)], [nb])
            ref = E.apply_op("OP-HCAT", [a, b])
            st, n, data = got[tag]
            assert st == 0, "%s 不该被拒（空数组是合法操作数）" % tag
            assert n == len(ref.data), "%s 长度应 %d，实际 %d" % (tag, len(ref.data), n)
            assert data == [float(x) for x in ref.data], "%s 内容与解释器不一致" % tag
    finally:
        shutil.rmtree(d, ignore_errors=True)
