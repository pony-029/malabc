# -*- coding: utf-8 -*-
"""`return` 的清理段必须**真的释放临时量**（不只是"有个标签"）。

R579 加了 `m2c_cleanup:`，R581 又修了它吞掉 `UNIMPLEMENTED` 的问题。
但到现在为止，验证的都是"标签存在/编译通过"——**没人验证过它真的释放了东西**。

做法：生成 `earlyret`（`if x(1) > 0 → y = 7; return`）的 C，用自定义 main 调它一次，
读 `mlc_rt_alloc_balance()`：
* `>0` = 泄漏（清理段没释放）；
* `<0` = 多释放（double free）。
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release", "m2c.exe")
RT = os.path.join(ROOT, "c_runtime")
SRC = os.path.join(ROOT, "translate", "examples", "numeric", "earlyret.m")

_MAIN = r"""
#include <stdio.h>
#include "mlc.h"
#include "earlyret.h"

int main(void)
{
    int64_t sh[1] = {4};
    mlc_array x, y;
    int64_t i;
    mlc_status st;

    mlc_array_init(&x, MLC_F64, 1, sh);
    for (i = 0; i < 4; ++i) { ((double *)x.data)[i] = (double)(i + 1); }

    y = (mlc_array){0};
    st = m2c_earlyret(x, &y);
    printf("rc=%d y=%.0f bal=%lld\n", (int)st,
           (mlc_array_numel(&y) > 0) ? ((double *)y.data)[0] : -1.0,
           (long long)mlc_rt_alloc_balance());
    mlc_array_free(&x);
    mlc_array_free(&y);
    printf("after_free_bal=%lld\n", (long long)mlc_rt_alloc_balance());
    return 0;
}
"""


def _cc():
    return shutil.which("gcc") or shutil.which("clang")


@pytest.mark.skipif(_cc() is None or not os.path.isfile(M2C),
                    reason="没有 C 编译器或 m2c 未构建")
def test_return_path_releases_temps():
    d = tempfile.mkdtemp(prefix="m2c_retfree_")
    mir = os.path.join(d, "e.mir")
    subprocess.run([sys.executable, os.path.join(ROOT, "translate", "mir.py"),
                    os.path.dirname(SRC), "-o", mir],
                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                   stderr=subprocess.STDOUT, timeout=600, check=True)
    gen = os.path.join(d, "g")
    subprocess.run([M2C, "build", "--mir", mir, "--out", gen, "--name", "earlyret"],
                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                   stderr=subprocess.STDOUT, timeout=900, check=True)

    main_c = os.path.join(d, "m.c")
    with open(main_c, "w") as f:
        f.write(_MAIN)
    exe = os.path.join(d, "m.exe")
    r = subprocess.run([_cc(), "-std=c99", "-O0",
                        "-I", os.path.join(gen, "include"),
                        "-I", os.path.join(RT, "include"),
                        os.path.join(gen, "src", "gen.c"), main_c,
                        os.path.join(RT, "src", "mlc_runtime.c"),
                        os.path.join(RT, "src", "mlc_ops.c"),
                        "-o", exe, "-lm"],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=900)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-800:]

    out = subprocess.run([exe], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT,
                         timeout=300).stdout.decode("utf-8", "replace")
    m = re.search(r"rc=(\d+) y=(-?\d+) bal=(-?\d+)", out)
    assert m, out[-400:]
    rc, y, bal = int(m.group(1)), int(m.group(2)), int(m.group(3))

    assert rc == 0, "函数应成功返回：%s" % out
    assert y == 7, ("`return` 之后不该再执行 y = 3；实测 y=%d\n%s" % (y, out))
    # 关键：调用结束后，**存活的只能是调用方自己的 x 与 y**（2 个）。
    # 若清理段没释放临时量（`__t1` 这种），这里会 >2。
    assert bal == 2, (
        "调用后存活分配 = %d，应为 2（只有 x 与 y）—— 多出来的就是清理段没释放的临时量\n%s"
        % (bal, out))

    m2 = re.search(r"after_free_bal=(-?\d+)", out)
    assert m2 and int(m2.group(1)) == 0, out
