# -*- coding: utf-8 -*-
"""运行时分配/释放**配平**的债务锁（本机无 ASan 时的替代观测）。

`docs/LEAK_AUDIT.md` 记录了实测清单：

| 场景 | 形态 | 期望 |
|---|---|---|
| S1 | `init` → `free` | 0 |
| S2 | 驱动 `init{1}` → 函数内再 `init{0}`（`findhash`/`pickbig` 形态） | **已知 +1** |
| S3 | 两次非空 `init` → `free` | **已知 +1** |
| S4 | dynshape：`init{0}` → 算子就地分配 → free | 0 |

## 为什么断言"已知泄漏"而不是断言 0

因为现在修不了 —— 修法要改 `init` 的核心语义（R568 试过，两条既有判据当场变红）。
于是这里采用**债务锁**：把当前已知的泄漏**钉成数字**。
* 泄漏变多 → 红（说明新代码又加了一处）；
* 有人把它修好 → **也红**，提醒同步更新本文档与 `LEAK_AUDIT.md`（修好必须被记录，不能悄悄发生）。

这是"已知债务"与"未知债务"的分界线：前者有数字，后者没有。
"""
import os
import shutil
import subprocess
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RT = os.path.join(ROOT, "c_runtime")

#: 已知债务（`docs/LEAK_AUDIT.md` 第二节）。修好之后必须改成 0。
KNOWN_LEAK_S2 = 1
KNOWN_LEAK_S3 = 1

_PROG = r"""
#include <stdio.h>
#include "mlc.h"
#include "mlc_ops.h"

int main(void)
{
    int64_t sh1[1] = {1};
    int64_t sh4[1] = {4};
    int64_t sh0[1] = {0};
    int64_t base;
    mlc_array a;

    base = mlc_rt_alloc_balance();
    mlc_array_init(&a, MLC_F64, 1, sh4);
    mlc_array_free(&a);
    printf("s1=%lld\n", (long long)(mlc_rt_alloc_balance() - base));

    base = mlc_rt_alloc_balance();
    mlc_array_init(&a, MLC_F64, 1, sh1);
    mlc_array_init(&a, MLC_F64, 1, sh0);
    mlc_array_free(&a);
    printf("s2=%lld\n", (long long)(mlc_rt_alloc_balance() - base));

    base = mlc_rt_alloc_balance();
    mlc_array_init(&a, MLC_F64, 1, sh4);
    mlc_array_init(&a, MLC_F64, 1, sh4);
    mlc_array_free(&a);
    printf("s3=%lld\n", (long long)(mlc_rt_alloc_balance() - base));

    printf("done=1\n");
    return 0;
}
"""


def _cc():
    return shutil.which("gcc") or shutil.which("clang")


@pytest.mark.skipif(_cc() is None, reason="没有 C 编译器")
def test_known_leak_debt_is_locked():
    d = tempfile.mkdtemp(prefix="m2c_balance_")
    src = os.path.join(d, "b.c")
    with open(src, "w") as f:
        f.write(_PROG)
    exe = os.path.join(d, "b.exe")
    r = subprocess.run([_cc(), "-std=c99", "-O0",
                        "-I", os.path.join(RT, "include"), src,
                        os.path.join(RT, "src", "mlc_runtime.c"),
                        os.path.join(RT, "src", "mlc_ops.c"),
                        "-o", exe, "-lm"],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=600)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-600:]

    out = subprocess.run([exe], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT,
                         timeout=300).stdout.decode("utf-8", "replace")
    assert "done=1" in out, out[-300:]

    got = {}
    for ln in out.splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            got[k.strip()] = v.strip()

    assert got.get("s1") == "0", "S1 本应配平：%s" % out
    assert got.get("s2") == str(KNOWN_LEAK_S2), (
        "S2 的已知泄漏是 %d，实测 %s —— 变多说明新代码又加了一处；"
        "变少说明有人修好了，请同步 docs/LEAK_AUDIT.md 并把这里的常量改成 0。\n%s"
        % (KNOWN_LEAK_S2, got.get("s2"), out))
    assert got.get("s3") == str(KNOWN_LEAK_S3), (
        "S3 的已知泄漏是 %d，实测 %s（同上）\n%s"
        % (KNOWN_LEAK_S3, got.get("s3"), out))
