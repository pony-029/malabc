# -*- coding: utf-8 -*-
"""静态内存池：`strategy: static_pool` 在**运行时**真的生效。

配置文件里写 `"strategy": "static_pool"` 只是一句话；真正重要的是三件事：

1. **不碰堆**：池配置后，`mlc_array_init` 不得再调用 `calloc`
   （用 `mlc_rt_alloc_count()` 断言：它只统计堆分配）；
2. **耗尽即报错**：池不够时返回 `MLC_ERR`，**绝不回退到堆**
   —— 否则"无堆"在现场才暴露；
3. **释放可复用**：反复申请/释放同一尺寸，峰值不应无限增长。
"""
import os
import re
import shutil
import subprocess
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RT = os.path.join(ROOT, "c_runtime")

PROG = r"""
#include <stdio.h>
#include <string.h>
#include "mlc.h"

static int64_t sh2[2] = {2, 2};

int main(void)
{
    static unsigned char pool[4096];
    mlc_array a, b, c;
    int rc1, rc2, rc3;
    int64_t peak1, peak2;

    /* 1) 未配置池：走堆 */
    mlc_array_init(&a, MLC_F64, 2, sh2);
    printf("heap_allocs=%lld\n", (long long)mlc_rt_alloc_count());
    mlc_array_free(&a);

    /* 2) 配置池：之后的分配不得再增加堆计数 */
    if (mlc_pool_configure(pool, (int64_t)sizeof(pool), 8) != MLC_OK) {
        printf("configure=ERR\n");
        return 1;
    }
    printf("pool_active=%d\n", mlc_pool_is_active());
    mlc_array_init(&a, MLC_F64, 2, sh2);
    mlc_array_init(&b, MLC_F64, 2, sh2);
    printf("after_pool_heap=%lld\n", (long long)mlc_rt_alloc_count());
    printf("after_pool_used=%lld\n", (long long)mlc_pool_bytes_used());

    /* 3) 释放 + 再分配：应复用，峰值不涨 */
    mlc_array_free(&a);
    mlc_array_free(&b);
    peak1 = mlc_pool_peak();
    mlc_array_init(&a, MLC_F64, 2, sh2);
    mlc_array_init(&b, MLC_F64, 2, sh2);
    peak2 = mlc_pool_peak();
    printf("peak1=%lld\n", (long long)peak1);
    printf("peak2=%lld\n", (long long)peak2);
    mlc_array_free(&a);
    mlc_array_free(&b);

    /* 4) 耗尽：用一个刚好装不下的尺寸 */
    {
        static unsigned char tiny[64];
        mlc_pool_configure(tiny, (int64_t)sizeof(tiny), 8);
        rc1 = mlc_array_init(&a, MLC_F64, 1, (int64_t[]){1000});
        printf("oom_rc=%d\n", (int)rc1);
        printf("oom_heap_delta=%lld\n", (long long)mlc_rt_alloc_count());
    }

    /* 5) 错误参数：对齐必须是 2 的幂 */
    rc2 = mlc_pool_configure(pool, 1024, 3);
    rc3 = mlc_pool_configure(NULL, 1024, 8);
    printf("bad_align=%d\n", (int)rc2);
    printf("null_buf=%d\n", (int)rc3);
    (void)c;
    return 0;
}
"""


def _cc():
    return shutil.which("gcc") or shutil.which("clang")


@pytest.mark.skipif(_cc() is None, reason="没有 C 编译器")
def test_static_pool_behaviour():
    d = tempfile.mkdtemp(prefix="m2c_pool_")
    src = os.path.join(d, "p.c")
    with open(src, "w") as f:
        f.write(PROG)
    exe = os.path.join(d, "p.exe")
    r = subprocess.run([_cc(), "-std=c99", "-O0", "-I", os.path.join(RT, "include"),
                        src, os.path.join(RT, "src", "mlc_runtime.c"),
                        "-o", exe], stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-800:]

    out = subprocess.run([exe], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT,
                         timeout=120).stdout.decode("utf-8", "replace")
    m = {}
    for ln in out.splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            m[k.strip()] = v.strip()

    # 1) 未配池时确实走了堆
    assert m.get("heap_allocs") == "1", out
    # 2) 配池后堆计数**不变** —— 这是"无堆"的唯一证据
    assert m.get("pool_active") == "1", out
    assert m.get("after_pool_heap") == "1", ("池分配不得增加堆计数：" + out)
    # 3) 释放后复用：峰值不增长
    assert int(m.get("peak2", "0")) <= int(m.get("peak1", "0")), (
        "释放后复用失败，峰值涨了：%s" % out)
    # 4) 池耗尽 -> MLC_ERR，且不回退堆
    assert m.get("oom_rc") == "1", out          # MLC_ERR = 1
    assert m.get("oom_heap_delta") == "1", ("池耗尽时不得回退到堆：" + out)
    # 5) 非法参数
    assert m.get("bad_align") == "1" and m.get("null_buf") == "1", out


def test_pool_api_declared():
    """头文件必须公开池接口（否则生成代码无法配置池）。"""
    h = open(os.path.join(RT, "include", "mlc.h"), encoding="utf-8").read()
    for fn in ("mlc_pool_configure", "mlc_pool_reset", "mlc_pool_is_active",
               "mlc_pool_bytes_left"):
        assert fn in h, fn
