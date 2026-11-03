# -*- coding: utf-8 -*-
"""Q15 定点算子：C 实现 vs **独立 Python 参考实现**（差分）。

## 为什么用差分而不是几个手写期望值

Q15 的坑全在边界：饱和方向、负数舍入、`-32768 * -32768` 这类极端乘法。
手写 3 个期望值只能证明"这三个对"，而随机的**符号组合 + 边界值**才能逼近真实失效。

## 参考实现里的两个容易写错的地方

1. 舍入：`(a*b + 2^14) >> 15`。C 的整数除法**向零截断**，Python 的 `//` **向下取整**，
   所以参考实现必须显式取截断，否则负数上会系统性地差 1。
2. 饱和：先算完整精度，**最后一次**夹紧；分步夹紧会在乘法里丢掉中间量。
"""
import os
import random
import shutil
import subprocess
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RT = os.path.join(ROOT, "c_runtime")

MAX = 32767
MIN = -32768
FRAC = 15


def _sat(v):
    return MAX if v > MAX else (MIN if v < MIN else v)


def _trunc_div(num, den):
    """与 C 的整数除法一致：向零截断（不是向下取整）。"""
    return num // den if num >= 0 else -((-num) // den)


def ref_add(a, b):
    return _sat(a + b)


def ref_mul(a, b):
    return _sat(_trunc_div(a * b + (1 << (FRAC - 1)), 1 << FRAC))


def _cc():
    return shutil.which("gcc") or shutil.which("clang")


PROG_HEAD = r"""
#include <stdio.h>
#include "mlc.h"
#include "mlc_ops.h"

static void fill(mlc_array *x, const double *v, int64_t n)
{
    int64_t i;
    mlc_array_init(x, MLC_F64, 1, (int64_t[]){n});
    for (i = 0; i < n; ++i) { ((double *)x->data)[i] = v[i]; }
}

int main(void)
{
    static double av[4096], bv[4096], ov[4096];
    int64_t n = 0, i;
    mlc_array a, b, o;
    char line[64];

    /* 从 stdin 读 "n a0 b0 a1 b1 ..."，每行一组；这里用最简协议：先 n，再 2n 个数 */
    if (scanf("%lld", (long long *)&n) != 1) { return 1; }
    for (i = 0; i < n; ++i) {
        long long x, y;
        if (scanf("%lld %lld", &x, &y) != 2) { return 1; }
        av[i] = (double)x;
        bv[i] = (double)y;
    }
    fill(&a, av, n);
    fill(&b, bv, n);
    mlc_array_init(&o, MLC_F64, 1, (int64_t[]){n});

    if (mlc_op_q15_add(&a, &b, &o) != MLC_OK) { printf("ERR\n"); return 1; }
    printf("ADD");
    for (i = 0; i < n; ++i) { printf(" %.0f", ((double *)o.data)[i]); }
    printf("\n");

    if (mlc_op_q15_mul(&a, &b, &o) != MLC_OK) { printf("ERR\n"); return 1; }
    printf("MUL");
    for (i = 0; i < n; ++i) { printf(" %.0f", ((double *)o.data)[i]); }
    printf("\n");

    mlc_array_free(&a); mlc_array_free(&b); mlc_array_free(&o);
    (void)ov; (void)line;
    return 0;
}
"""


@pytest.mark.skipif(_cc() is None, reason="没有 C 编译器")
def test_q15_add_mul_differential():
    rnd = random.Random(20261101)
    pairs = [(MAX, MAX), (MIN, MIN), (MIN, -1), (MAX, 1), (0, 0),
             (MIN, MAX), (16384, 2), (-16384, 2), (1, -1), (-1, -1)]
    for _ in range(190):
        pairs.append((rnd.randint(MIN, MAX), rnd.randint(MIN, MAX)))

    d = tempfile.mkdtemp(prefix="m2c_q15_")
    try:
        src = os.path.join(d, "q.c")
        with open(src, "w") as f:
            f.write(PROG_HEAD)
        exe = os.path.join(d, "q.exe")
        r = subprocess.run([_cc(), "-std=c99", "-O0",
                            "-I", os.path.join(RT, "include"), src,
                            os.path.join(RT, "src", "mlc_runtime.c"),
                            os.path.join(RT, "src", "mlc_ops.c"),
                            "-o", exe, "-lm"],
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=600)
        assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-800:]

        inp = "%d\n" % len(pairs) + "".join("%d %d\n" % p for p in pairs)
        out = subprocess.run([exe], input=inp.encode(),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             timeout=120).stdout.decode("utf-8", "replace")

        lines = [x for x in out.splitlines() if x.startswith(("ADD", "MUL"))]
        assert len(lines) == 2, out[:400]
        got_add = [int(float(x)) for x in lines[0].split()[1:]]
        got_mul = [int(float(x)) for x in lines[1].split()[1:]]

        want_add = [ref_add(a, b) for a, b in pairs]
        want_mul = [ref_mul(a, b) for a, b in pairs]

        bad_add = [(i, pairs[i], got_add[i], want_add[i])
                   for i in range(len(pairs)) if got_add[i] != want_add[i]]
        bad_mul = [(i, pairs[i], got_mul[i], want_mul[i])
                   for i in range(len(pairs)) if got_mul[i] != want_mul[i]]
        assert not bad_add, "add 与参考实现不一致：%s" % bad_add[:3]
        assert not bad_mul, "mul 与参考实现不一致：%s" % bad_mul[:3]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_q15_constants_match_config_whitelist():
    """运行时常量必须与 `m2c.project.json` 的 Q15 约定一致（16 位、15 位小数）。"""
    h = open(os.path.join(RT, "include", "mlc_ops.h"), encoding="utf-8").read()
    assert "MLC_Q15_BITS   16" in h
    assert "MLC_Q15_FRAC   15" in h
    assert "MLC_Q15_MAX    32767" in h


# ---------------------------------------------------------------------------
# 边界缩放：f64 <-> Q15 定标整数
#
# Q15 只能表示 [-1, 1)。**1.0 * 2^15 = 32768 已越界**，必须饱和到 32767；
# 若用 int 直接转换，1.0 会环绕成 -32768 —— 这类错误不会报错，只会算错。
# ---------------------------------------------------------------------------

def ref_from_f64(x):
    s = x * (1 << FRAC)
    if s >= MAX:
        return MAX
    if s <= MIN:
        return MIN
    return int(s + 0.5) if s >= 0 else -int(-s + 0.5)


def ref_to_f64(q):
    return q / float(1 << FRAC)


PROG_SCALE = r"""
#include <stdio.h>
#include "mlc.h"
#include "mlc_ops.h"

int main(void)
{
    static double xv[4096], qv[4096], bv[4096];
    int64_t n = 0, i;
    mlc_array x, q, b;

    if (scanf("%lld", (long long *)&n) != 1) { return 1; }
    for (i = 0; i < n; ++i) {
        double v;
        if (scanf("%lf", &v) != 1) { return 1; }
        xv[i] = v;
    }
    mlc_array_init(&x, MLC_F64, 1, (int64_t[]){n});
    mlc_array_init(&q, MLC_F64, 1, (int64_t[]){n});
    mlc_array_init(&b, MLC_F64, 1, (int64_t[]){n});
    for (i = 0; i < n; ++i) { ((double *)x.data)[i] = xv[i]; }

    if (mlc_op_q15_from_f64(&x, &q) != MLC_OK) { printf("ERR\n"); return 1; }
    printf("Q");
    for (i = 0; i < n; ++i) { printf(" %.0f", ((double *)q.data)[i]); }
    printf("\n");

    if (mlc_op_q15_to_f64(&q, &b) != MLC_OK) { printf("ERR\n"); return 1; }
    printf("B");
    for (i = 0; i < n; ++i) { printf(" %.17g", ((double *)b.data)[i]); }
    printf("\n");
    (void)qv;
    mlc_array_free(&x); mlc_array_free(&q); mlc_array_free(&b);
    return 0;
}
"""


@pytest.mark.skipif(_cc() is None, reason="没有 C 编译器")
def test_q15_scaling_differential():
    rnd = random.Random(7)
    vals = [0.0, 0.5, -0.5, 0.25, -0.25, 0.999969482421875, -1.0, 1.0,
            1.5, -1.5, 0.0001, -0.0001, 1e-9]
    for _ in range(180):
        vals.append(round(rnd.uniform(-1.2, 1.2), 6))

    d = tempfile.mkdtemp(prefix="m2c_q15s_")
    try:
        src = os.path.join(d, "s.c")
        with open(src, "w") as f:
            f.write(PROG_SCALE)
        exe = os.path.join(d, "s.exe")
        r = subprocess.run([_cc(), "-std=c99", "-O0",
                            "-I", os.path.join(RT, "include"), src,
                            os.path.join(RT, "src", "mlc_runtime.c"),
                            os.path.join(RT, "src", "mlc_ops.c"), "-o", exe, "-lm"],
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=600)
        assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-800:]

        inp = "%d\n" % len(vals) + "".join("%.17g\n" % v for v in vals)
        out = subprocess.run([exe], input=inp.encode(), stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT,
                             timeout=120).stdout.decode("utf-8", "replace")
        lines = [x for x in out.splitlines() if x.startswith(("Q", "B"))]
        assert len(lines) == 2, out[:400]
        got_q = [int(float(x)) for x in lines[0].split()[1:]]
        want_q = [ref_from_f64(v) for v in vals]
        bad = [(i, vals[i], got_q[i], want_q[i])
               for i in range(len(vals)) if got_q[i] != want_q[i]]
        assert not bad, "from_f64 与参考实现不一致：%s" % bad[:3]

        # 1.0 必须饱和到 32767（不是环绕成 -32768）
        assert got_q[vals.index(1.0)] == MAX, "1.0 必须饱和到 32767"
        assert got_q[vals.index(-1.0)] == MIN

        got_b = [float(x) for x in lines[1].split()[1:]]
        for i, v in enumerate(vals):
            assert abs(got_b[i] - ref_to_f64(got_q[i])) < 1e-12
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# 定点归约：sum / mean / max / min
#
# 形状规则与 f64 版**同一条**（沿第一个非单例维：1-D 全元素、2x3 -> 1x3），
# 只是累加在 int64 里做、写回前饱和。mean 用整数除法（向零截断）。
# ---------------------------------------------------------------------------

def ref_reduce(vals, kind, rows=0, cols=0):
    def one(xs):
        if kind == "sum":
            return _sat(sum(xs))
        if kind == "mean":
            return _sat(_trunc_div(sum(xs), len(xs)))
        if kind == "max":
            return max(xs)
        return min(xs)

    if not rows or rows <= 1:
        return [one(list(vals))]
    return [one([vals[i * cols + j] for i in range(rows)]) for j in range(cols)]


PROG_RED = r"""
#include <stdio.h>
#include "mlc.h"
#include "mlc_ops.h"

int main(void)
{
    static double buf[4096];
    int64_t rows = 0, cols = 0, i, n;
    mlc_array a, o;
    mlc_status st;
    const char *names[4] = {"sum", "mean", "max", "min"};
    mlc_status (*fs[4])(const mlc_array *, mlc_array *) = {
        mlc_op_q15_sum, mlc_op_q15_mean, mlc_op_q15_max, mlc_op_q15_min};
    int k;

    if (scanf("%lld %lld", (long long *)&rows, (long long *)&cols) != 2) { return 1; }
    n = rows * cols;
    for (i = 0; i < n; ++i) {
        long long v;
        if (scanf("%lld", &v) != 1) { return 1; }
        buf[i] = (double)v;
    }
    for (k = 0; k < 4; ++k) {
        int64_t shape[2];
        shape[0] = rows;
        shape[1] = cols;
        if (mlc_array_init(&a, MLC_F64, 2, shape) != MLC_OK) { return 1; }
        for (i = 0; i < n; ++i) { ((double *)a.data)[i] = buf[i]; }
        if (mlc_array_init(&o, MLC_F64, 1, (int64_t[]){0}) != MLC_OK) { return 1; }
        st = fs[k](&a, &o);
        printf("%s st=%d", names[k], (int)st);
        for (i = 0; i < mlc_array_numel(&o); ++i) {
            printf(" %.0f", ((double *)o.data)[i]);
        }
        printf("\n");
        mlc_array_free(&o);
        mlc_array_free(&a);
    }
    return 0;
}
"""


@pytest.mark.skipif(_cc() is None, reason="没有 C 编译器")
def test_q15_reductions_differential():
    rnd = random.Random(31337)
    cases = [(1, 4), (2, 3), (3, 3), (2, 1)]
    for _ in range(40):
        cases.append((rnd.randint(1, 4), rnd.randint(1, 4)))

    d = tempfile.mkdtemp(prefix="m2c_q15r_")
    try:
        src = os.path.join(d, "r.c")
        with open(src, "w") as f:
            f.write(PROG_RED)
        exe = os.path.join(d, "r.exe")
        r = subprocess.run([_cc(), "-std=c99", "-O0",
                            "-I", os.path.join(RT, "include"), src,
                            os.path.join(RT, "src", "mlc_runtime.c"),
                            os.path.join(RT, "src", "mlc_ops.c"), "-o", exe, "-lm"],
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=600)
        assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-800:]

        bad = []
        for (rows, cols) in cases:
            vals = [rnd.randint(MIN, MAX) for _ in range(rows * cols)]
            inp = "%d %d\n%s\n" % (rows, cols, " ".join(str(v) for v in vals))
            out = subprocess.run([exe], input=inp.encode(), stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT,
                                 timeout=120).stdout.decode("utf-8", "replace")
            got = {}
            for ln in out.splitlines():
                p = ln.split()
                if len(p) >= 2 and p[0] in ("sum", "mean", "max", "min"):
                    got[p[0]] = [int(float(x)) for x in p[2:]]
            for kind in ("sum", "mean", "max", "min"):
                want = ref_reduce(vals, kind, rows, cols)
                if got.get(kind) != want:
                    bad.append((kind, (rows, cols), got.get(kind), want))
        assert not bad, "定点归约与参考实现不一致：%s" % bad[:3]
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# Q15 除法：round(a_q * 2^15 / b_q)，半值远离零，饱和；**除零明确拒绝**
#
# 为什么不能"用 f64 除再转回来"：中间量会多走一次浮点舍入，
# 在 `a_q * 2^15` 恰好落在 .5 边界时与整数实现差 1 —— 而这正是定点最不该有的不确定。
# ---------------------------------------------------------------------------

def ref_div(a, b):
    """返回定标整数；除零返回 None（对应 C 的 MLC_ERR）。"""
    if b == 0:
        return None
    num = a << FRAC
    neg = (num < 0) != (b < 0)
    an, ad = abs(num), abs(b)
    q = (an + ad // 2) // ad
    if neg:
        q = -q
    return _sat(q)


PROG_DIV = r"""
#include <stdio.h>
#include "mlc.h"
#include "mlc_ops.h"

int main(void)
{
    static double av[4096], bv[4096];
    int64_t n = 0, i;
    mlc_array a, b, o;
    mlc_status st;

    if (scanf("%lld", (long long *)&n) != 1) { return 1; }
    for (i = 0; i < n; ++i) {
        long long x, y;
        if (scanf("%lld %lld", &x, &y) != 2) { return 1; }
        av[i] = (double)x;
        bv[i] = (double)y;
    }
    mlc_array_init(&a, MLC_F64, 1, (int64_t[]){n});
    mlc_array_init(&b, MLC_F64, 1, (int64_t[]){n});
    mlc_array_init(&o, MLC_F64, 1, (int64_t[]){n});
    for (i = 0; i < n; ++i) {
        ((double *)a.data)[i] = av[i];
        ((double *)b.data)[i] = bv[i];
    }
    st = mlc_op_q15_div(&a, &b, &o);
    printf("st=%d", (int)st);
    if (st == MLC_OK) {
        for (i = 0; i < n; ++i) { printf(" %.0f", ((double *)o.data)[i]); }
    }
    printf("\n");
    mlc_array_free(&a); mlc_array_free(&b); mlc_array_free(&o);
    return 0;
}
"""


@pytest.mark.skipif(_cc() is None, reason="没有 C 编译器")
def test_q15_div_differential():
    rnd = random.Random(4242)
    pairs = [(MAX, 1), (MIN, -1), (MAX, -1), (MIN, 1), (16384, 2), (-16384, 2),
             (16384, 3), (1, MAX), (MIN, MAX), (0, 5), (0, -5), (1, 2), (-1, 2)]
    for _ in range(180):
        b = rnd.randint(MIN, MAX)
        if b == 0:
            b = 3
        pairs.append((rnd.randint(MIN, MAX), b))

    d = tempfile.mkdtemp(prefix="m2c_q15d_")
    try:
        src = os.path.join(d, "d.c")
        with open(src, "w") as f:
            f.write(PROG_DIV)
        exe = os.path.join(d, "d.exe")
        r = subprocess.run([_cc(), "-std=c99", "-O0",
                            "-I", os.path.join(RT, "include"), src,
                            os.path.join(RT, "src", "mlc_runtime.c"),
                            os.path.join(RT, "src", "mlc_ops.c"), "-o", exe, "-lm"],
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=600)
        assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-800:]

        inp = "%d\n" % len(pairs) + "".join("%d %d\n" % p for p in pairs)
        out = subprocess.run([exe], input=inp.encode(), stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT,
                             timeout=120).stdout.decode("utf-8", "replace")
        line = [x for x in out.splitlines() if x.startswith("st=")]
        assert line, out[:300]
        assert line[0].startswith("st=0"), "不该被拒：%s" % line[0]
        got = [int(float(x)) for x in line[0].split()[1:]]
        want = [ref_div(a, b) for (a, b) in pairs]
        bad = [(i, pairs[i], got[i], want[i])
               for i in range(len(pairs)) if got[i] != want[i]]
        assert not bad, "q15_div 与参考实现不一致：%s" % bad[:3]
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.skipif(_cc() is None, reason="没有 C 编译器")
def test_q15_div_by_zero_is_rejected():
    """除零必须明确拒绝，不能返回 0 或饱和值。"""
    d = tempfile.mkdtemp(prefix="m2c_q15z_")
    try:
        src = os.path.join(d, "d.c")
        with open(src, "w") as f:
            f.write(PROG_DIV)
        exe = os.path.join(d, "d.exe")
        subprocess.run([_cc(), "-std=c99", "-O0",
                        "-I", os.path.join(RT, "include"), src,
                        os.path.join(RT, "src", "mlc_runtime.c"),
                        os.path.join(RT, "src", "mlc_ops.c"), "-o", exe, "-lm"],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=600, check=True)
        out = subprocess.run([exe], input=b"2\n1000 0\n1000 5\n",
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             timeout=120).stdout.decode("utf-8", "replace")
        assert out.startswith("st=1"), out[:200]
    finally:
        shutil.rmtree(d, ignore_errors=True)
