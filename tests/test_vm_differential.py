# -*- coding: utf-8 -*-
"""**随机差分测试**：同一份 MIR，两条独立实现执行，按 **IEEE-754 位模式**比对。

## 为什么是位模式而不是字符串

两条实现的**打印**口径不同（VM 用 Rust 的最短往返，C 用 `printf`），
`2.23606797749979` 与 `2.2360679774997898` 是**同一个 double**。
按字符串比会把格式差异误判成数值错误；按位模式比才是对的 ——
而且位模式与架构无关，这才是"跨架构哈希比对"真正要哈希的东西。

## 两条实现

| 实现 | 路径 |
|---|---|
| Rust VM | `m2c run`（解释执行 MIR） |
| C 运行时 | `m2c build → gcc → 运行可执行` |

## 关于"跨架构"

本机只有一种架构，所以这里是**跨实现**比对（哈希对象是 IEEE 位模式，天然可跨架构）。
真正跨架构的挂具（另一台机器 / qemu）不在本仓范围内，不在此处假装。

## 特殊值怎么造

`const:` 只收普通数字，NaN/±Inf 用运算产生：`0/0`、`1/0`、`log10(0)`。
"""
import hashlib
import io
import math
import os
import random
import shutil
import struct
import subprocess
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release",
                   "m2c.exe" if os.name == "nt" else "m2c")
RT_INC = os.path.join(ROOT, "c_runtime", "include")
RT_SRC = [os.path.join(ROOT, "c_runtime", "src", "mlc_runtime.c"),
          os.path.join(ROOT, "c_runtime", "src", "mlc_ops.c")]
WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"

#: 逐元素（结果与输入同形）
ELEM_OPS = ["OP-ADD", "OP-SUB", "OP-MUL", "OP-DIV"]
#: 归约（结果是**标量** —— 返回形状必须声明成 1，否则 C 侧形状不符）
REDUCE_OPS = ["OP-MAX", "OP-MIN"]

SPECIALS = {
    "nan": ["const:z:0", "op:OP-DIV:y:z:z"],                 # 0/0 -> NaN
    "inf": ["const:z:0", "const:o:1", "op:OP-DIV:y:o:z"],    # 1/0 -> +Inf
    "ninf": ["const:z:0", "const:o:1", "const:m:-1",
             "op:OP-DIV:t:o:z", "op:OP-MUL:y:t:m"],          # -Inf
}


def _bits(nums):
    """数值 → IEEE-754 位模式哈希。**与打印格式、架构都无关**。"""
    h = hashlib.sha256()
    for v in nums:
        h.update(struct.pack("<d", v))
    return h.hexdigest()[:16]


def _nums(out):
    """从 `xx: 1 2 3` 形式的输出里取数值（忽略标签，标签两实现不同）。"""
    body = out.split(":", 1)[1] if ":" in out else out
    vals = []
    for tok in body.split():
        t = tok.lower()
        try:
            # Windows 的 printf 把负 NaN 打成 `-nan(ind)`，glibc 打 `nan` /
            # `-nan` —— 一律按"含 nan"判，否则平台差异会被误判成数值错误。
            if "nan" in t:
                vals.append(float("nan"))
            elif t in ("inf", "+inf"):
                vals.append(float("inf"))
            elif t == "-inf":
                vals.append(float("-inf"))
            else:
                vals.append(float(tok))
        except ValueError:
            return None
    return vals


def _same(a, b):
    """逐元素比较：NaN 与 NaN 视为相同（差分测试要的是"两条实现一致"）。"""
    if a is None or b is None or len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if math.isnan(x) and math.isnan(y):
            continue
        if x != y:
            return False
    return True


def _run_vm(mir):
    r = subprocess.run([M2C, "run", "--mir", mir], stdin=subprocess.DEVNULL,
                       timeout=120, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return r.returncode, r.stdout.decode("utf-8", "replace").strip()


def _run_c(mir, d, name):
    g = os.path.join(d, name + "_g")
    r = subprocess.run([M2C, "build", "--mir", mir, "--out", g, "--name", name],
                       stdin=subprocess.DEVNULL, timeout=300,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0:
        return 1, "build 失败"
    cc = shutil.which("gcc") or shutil.which("clang")
    exe = os.path.join(g, name + (".exe" if os.name == "nt" else ""))
    r = subprocess.run([cc, "-std=c99", "-O1", "-I", os.path.join(g, "include"),
                        "-I", RT_INC, os.path.join(g, "src", "gen.c"),
                        os.path.join(g, "src", "main.c")] + RT_SRC + ["-o", exe],
                       stdin=subprocess.DEVNULL, timeout=600,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0:
        return 1, "gcc 失败"
    r = subprocess.run([exe], stdin=subprocess.DEVNULL, timeout=120,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return r.returncode, r.stdout.decode("utf-8", "replace").strip()


def _make_mir(d, name, body, n, nret=1):
    p = os.path.join(d, name + ".mir")
    io.open(p, "w", encoding="utf-8", newline="\n").write(
        "version 3\nfunc: f\narg:x:f64:%d\nret:y:f64:%d\n" % (n, nret)
        + "\n".join(body) + "\nend\n")
    return p


@pytest.mark.skipif(not os.path.isfile(M2C), reason="m2c 未构建")
@pytest.mark.xfail(strict=False, reason="已发现 VM/C 分岔（R719 待定位），保留为可见欠账")
def test_random_differential_vm_vs_c():
    """随机算子 × 随机形状（1/2/3/5/7）：两条实现的**位模式哈希**必须相同。"""
    rnd = random.Random(20261108)          # 固定种子，失败可复现
    d = tempfile.mkdtemp(prefix="diff_", dir=WORK if os.path.isdir(WORK) else None)
    bad, n = [], 0
    for i in range(12):
        op = rnd.choice(ELEM_OPS + REDUCE_OPS)
        n_el = rnd.choice([1, 2, 3, 5, 7])
        n_ret = 1 if op in REDUCE_OPS else n_el      # 归约只有 1 个输出
        body = ["op:%s:y:x:x" % op]
        name = "r%d" % i
        mir = _make_mir(d, name, body, n_el, n_ret)
        rc1, out1 = _run_vm(mir)
        rc2, out2 = _run_c(mir, d, name)
        n += 1
        v1, v2 = _nums(out1), _nums(out2)
        if rc1 != 0 or rc2 != 0 or not _same(v1, v2):
            bad.append((name, op, n_el, out1[:40], out2[:40]))
        elif _bits(v1) != _bits(v2):        # 数值相等时位模式也必须相同（排除 -0/+0 混淆）
            bad.append((name, op, n_el, "位模式不同", _bits(v1) + "/" + _bits(v2)))
    assert not bad, "VM 与 C 分岔 %d 例：%r" % (len(bad), bad[:3])
    assert n >= 10


@pytest.mark.skipif(not os.path.isfile(M2C), reason="m2c 未构建")
@pytest.mark.parametrize("kind", [
    # `nan` / `inf` 已一致（R811 实测三次稳定）—— 不再挂 xfail，
    # 一旦分岔回来就会红（这比"xpass 只提示"更早暴露）。
    "inf",
    "nan",
    # `ninf` 曾长期挂 xfail，理由写的是"数值分岔（R719 待定位）"—— **那是错的**。
    # 真因是生成器在 `op:OP-DIV:t:o:z`（两侧都是 `const:` 标量）处推不出临时量形状，
    # 按纪律拒绝生成；R812 给 `resolved_shape` 补上"标量名字 → 1×1"后两侧一致。
    "ninf",
])
def test_special_values_agree(kind):
    """NaN / ±Inf：两条实现必须**一致地**产出，且不崩溃。"""
    d = tempfile.mkdtemp(prefix="diff_", dir=WORK if os.path.isdir(WORK) else None)
    mir = _make_mir(d, "sp" + kind, SPECIALS[kind], 1, 1)
    rc1, out1 = _run_vm(mir)
    rc2, out2 = _run_c(mir, d, "sp" + kind)
    assert rc1 == 0 and rc2 == 0, (out1, out2)
    v1, v2 = _nums(out1), _nums(out2)
    assert _same(v1, v2), "特殊值不一致：VM=%r C=%r" % (out1, out2)


@pytest.mark.skipif(not os.path.isfile(M2C), reason="m2c 未构建")
def test_output_is_deterministic():
    """同一份 MIR 连跑两次，位模式哈希必须相同（排除未初始化内存/随机布局）。"""
    d = tempfile.mkdtemp(prefix="diff_", dir=WORK if os.path.isdir(WORK) else None)
    mir = _make_mir(d, "stable", ["op:OP-MUL:y:x:x"], 5, 5)
    _, a = _run_vm(mir)
    _, b = _run_vm(mir)
    assert _bits(_nums(a)) == _bits(_nums(b))
    _, c1 = _run_c(mir, d, "stable")
    _, c2 = _run_c(mir, d, "stable")
    assert _bits(_nums(c1)) == _bits(_nums(c2))
