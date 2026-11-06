/*
 * mlc_ops.c —— 算子目录的 C 实现（R432 / P0；R12 扩充）。
 *
 * 四则（add/sub/mul/div）共用一个元素级内核，避免四份重复的校验/广播逻辑；
 * 归约（sum/mean/max/min）各自一个循环。
 * 矩阵乘/转置显式返回 MLC_UNIMPLEMENTED —— 这是诚实边界，不是 TODO。
 */
#include "mlc_ops.h"

#include <math.h>

#include <stddef.h>

enum {
    MLC_BIN_ADD = 0,
    MLC_BIN_SUB = 1,
    MLC_BIN_MUL = 2,
    MLC_BIN_DIV = 3
};

/*
 * 广播形状：按**尾维对齐**，逐维取 max；只有当某一维相等或其中之一为 1 时才算可广播。
 * 返回 0 表示不可广播（调用方应报 MLC_ERR —— 不猜一个形状）。
 */
static int mlc_bcast_shape(const mlc_array *a, const mlc_array *b,
                           int64_t *shape, int32_t *ndim)
{
    int32_t na = a->ndim, nb = b->ndim, n, i;
    if (na <= 0 || nb <= 0 || na > MLC_MAX_DIMS || nb > MLC_MAX_DIMS) {
        return 0;
    }
    n = (na > nb) ? na : nb;
    for (i = 0; i < n; ++i) {
        int32_t ia = na - n + i, ib = nb - n + i;
        int64_t da = (ia >= 0) ? a->shape[ia] : 1;
        int64_t db = (ib >= 0) ? b->shape[ib] : 1;
        if (da != db && da != 1 && db != 1) {
            return 0;
        }
        shape[i] = (da > db) ? da : db;
    }
    *ndim = n;
    return 1;
}

/* 把「输出多下标」映射到某个输入的下标：广播维（输入该维为 1 或缺失）步长记 0。 */
static int64_t mlc_bcast_offset(const mlc_array *x, int32_t out_ndim,
                                const int64_t *idx)
{
    int32_t n = x->ndim, i;
    int64_t off = 0;
    for (i = 0; i < n; ++i) {
        int32_t oi = out_ndim - n + i;
        int64_t d = x->shape[i];
        int64_t pos = (d == 1) ? 0 : idx[oi];
        off += pos * x->strides[i];
    }
    return off;
}

static mlc_status mlc_binary_f64(const mlc_array *a, const mlc_array *b,
                                 mlc_array *out, int op)
{
    int64_t shape[MLC_MAX_DIMS];
    int32_t ndim = 0, i;
    int64_t no, k;
    const double *pa;
    const double *pb;
    double *po;
    int64_t idx[MLC_MAX_DIMS] = {0};   /* ndim==0 时循环不跑，不能靠下游保证 */

    if (a == NULL || b == NULL || out == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64 || b->dtype != MLC_F64 || out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    if (!mlc_bcast_shape(a, b, shape, &ndim)) {
        return MLC_ERR;              /* 不可广播：不猜 */
    }
    /* 输出为空（形状未标注的返回值）：按广播结论**就地分配**。
     * 这是"运行时定形状"的唯一入口：调用方把输出置空，算子自己长出来。 */
    if (mlc_array_numel(out) == 0) {
        if (mlc_array_init(out, MLC_F64, ndim, shape) != MLC_OK) {
            return MLC_ERR;
        }
    }
    /* 其余情况仍要求形状与广播结论一致（调用方负责 init） */
    if (out->ndim != ndim) {
        return MLC_ERR;
    }
    for (i = 0; i < ndim; ++i) {
        if (out->shape[i] != shape[i]) {
            return MLC_ERR;
        }
    }
    no = mlc_array_numel(out);
    if (no < 0) {
        return MLC_ERR;
    }
    if (no == 0) {
        return MLC_OK;
    }
    pa = (const double *)a->data;
    pb = (const double *)b->data;
    po = (double *)out->data;
    if (pa == NULL || pb == NULL || po == NULL) {
        return MLC_ERR;
    }
    for (i = 0; i < ndim; ++i) {
        idx[i] = 0;
    }
    for (k = 0; k < no; ++k) {
        double va = pa[mlc_bcast_offset(a, ndim, idx)];
        double vb = pb[mlc_bcast_offset(b, ndim, idx)];
        switch (op) {
        case MLC_BIN_ADD:
            po[k] = va + vb;
            break;
        case MLC_BIN_SUB:
            po[k] = va - vb;
            break;
        case MLC_BIN_MUL:
            po[k] = va * vb;
            break;
        case MLC_BIN_DIV:
            po[k] = va / vb;
            break;
        default:
            return MLC_ERR;
        }
        /* 行主序推进多下标 */
        for (i = ndim - 1; i >= 0; --i) {
            if (++idx[i] < shape[i]) {
                break;
            }
            idx[i] = 0;
        }
    }
    return MLC_OK;
}

/* 掩码比较：cmp 用整数编码，避免生成侧拼字符串。 */
static int mlc_mask_test(double v, int cmp, double k)
{
    switch (cmp) {
        case 0: return v > k;
        case 1: return v >= k;
        case 2: return v < k;
        case 3: return v <= k;
        case 4: return v == k;
        default: return v != k;
    }
}

mlc_status mlc_op_add(const mlc_array *a, const mlc_array *b, mlc_array *out)
{
    return mlc_binary_f64(a, b, out, MLC_BIN_ADD);
}

mlc_status mlc_op_sub(const mlc_array *a, const mlc_array *b, mlc_array *out)
{
    return mlc_binary_f64(a, b, out, MLC_BIN_SUB);
}

mlc_status mlc_op_mul(const mlc_array *a, const mlc_array *b, mlc_array *out)
{
    return mlc_binary_f64(a, b, out, MLC_BIN_MUL);
}

mlc_status mlc_op_div(const mlc_array *a, const mlc_array *b, mlc_array *out)
{
    return mlc_binary_f64(a, b, out, MLC_BIN_DIV);
}


/* @m2c coverage-exclude begin: Q15 定点路径 —— 不在 f64 语料路径上，由 tests/test_q15_ops.py 守护 */
/* ===================== Q15 定点算子 ===================== */

int64_t mlc_q15_sat(int64_t v)
{
    if (v > (int64_t)MLC_Q15_MAX) {
        return (int64_t)MLC_Q15_MAX;
    }
    if (v < (int64_t)MLC_Q15_MIN) {
        return (int64_t)MLC_Q15_MIN;
    }
    return v;
}

/* a、b、out 必须同形状；不下标广播（定点广播极易静默算错）。 */
static mlc_status mlc_q15_prepare(const mlc_array *a, const mlc_array *b,
                                  mlc_array *out, int64_t *n)
{
    if (a == NULL || b == NULL || out == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64 || b->dtype != MLC_F64 || out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    *n = mlc_array_numel(a);
    if (mlc_array_numel(b) != *n || mlc_array_numel(out) != *n) {
        return MLC_ERR;
    }
    if (*n > 0 && (a->data == NULL || b->data == NULL || out->data == NULL)) {
        return MLC_ERR;
    }
    return MLC_OK;
}

/* 四舍五入到最近整数（.5 远离零），然后饱和到 Q15 整数域。
 * 用 double 相乘再判定边界：Q15_MAX 与 2^15 的差距必须**显式**处理，
 * 否则 1.0 会静默变成 -32768（整型溢出环绕）。 */
static int64_t m2c_q15_from_double(double x)
{
    double s = x * (double)(((int64_t)1) << MLC_Q15_FRAC);
    if (s >= (double)MLC_Q15_MAX) {
        return (int64_t)MLC_Q15_MAX;      /* 含 1.0 与更大的值 */
    }
    if (s <= (double)MLC_Q15_MIN) {
        return (int64_t)MLC_Q15_MIN;      /* 含 -1.0 与更小的值 */
    }
    return (s >= 0.0) ? (int64_t)(s + 0.5) : -(int64_t)(-s + 0.5);
}

mlc_status mlc_op_q15_from_f64(const mlc_array *a, mlc_array *out)
{
    int64_t n, i;
    if (a == NULL || out == NULL || a->dtype != MLC_F64 || out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    n = mlc_array_numel(a);
    if (mlc_array_numel(out) != n) {
        return MLC_ERR;
    }
    if (n > 0 && (a->data == NULL || out->data == NULL)) {
        return MLC_ERR;
    }
    for (i = 0; i < n; ++i) {
        ((double *)out->data)[i] =
            (double)m2c_q15_from_double(((const double *)a->data)[i]);
    }
    return MLC_OK;
}

mlc_status mlc_op_q15_to_f64(const mlc_array *a, mlc_array *out)
{
    int64_t n, i;
    if (a == NULL || out == NULL || a->dtype != MLC_F64 || out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    n = mlc_array_numel(a);
    if (mlc_array_numel(out) != n) {
        return MLC_ERR;
    }
    if (n > 0 && (a->data == NULL || out->data == NULL)) {
        return MLC_ERR;
    }
    for (i = 0; i < n; ++i) {
        ((double *)out->data)[i] =
            ((const double *)a->data)[i] / (double)(((int64_t)1) << MLC_Q15_FRAC);
    }
    return MLC_OK;
}

mlc_status mlc_op_q15_add(const mlc_array *a, const mlc_array *b, mlc_array *out)
{
    int64_t n = 0, i;
    if (mlc_q15_prepare(a, b, out, &n) != MLC_OK) {
        return MLC_ERR;
    }
    for (i = 0; i < n; ++i) {
        int64_t va = (int64_t)(((const double *)a->data)[i]);
        int64_t vb = (int64_t)(((const double *)b->data)[i]);
        ((double *)out->data)[i] = (double)mlc_q15_sat(va + vb);
    }
    return MLC_OK;
}

mlc_status mlc_op_q15_sub(const mlc_array *a, const mlc_array *b, mlc_array *out)
{
    int64_t n = 0, i;
    if (mlc_q15_prepare(a, b, out, &n) != MLC_OK) {
        return MLC_ERR;
    }
    for (i = 0; i < n; ++i) {
        int64_t va = (int64_t)(((const double *)a->data)[i]);
        int64_t vb = (int64_t)(((const double *)b->data)[i]);
        ((double *)out->data)[i] = (double)mlc_q15_sat(va - vb);
    }
    return MLC_OK;
}

mlc_status mlc_op_q15_mul(const mlc_array *a, const mlc_array *b, mlc_array *out)
{
    int64_t n = 0, i;
    const int64_t half = ((int64_t)1) << (MLC_Q15_FRAC - 1);
    if (mlc_q15_prepare(a, b, out, &n) != MLC_OK) {
        return MLC_ERR;
    }
    for (i = 0; i < n; ++i) {
        int64_t va = (int64_t)(((const double *)a->data)[i]);
        int64_t vb = (int64_t)(((const double *)b->data)[i]);
        int64_t prod = va * vb;                 /* |va|,|vb| <= 32768 -> 不溢出 int64 */
        /* 就近舍入：先加半个 LSB，再算术右移 frac 位（负数也按位右移，C99 实现定义但
           gcc/clang 均为算术右移；这里显式用除法规避可移植性问题）。 */
        int64_t num = prod + half;
        int64_t q = num / (((int64_t)1) << MLC_Q15_FRAC);
        ((double *)out->data)[i] = (double)mlc_q15_sat(q);
    }
    return MLC_OK;
}
/* 定点归约核心：kind 0=sum 1=max 2=min 3=mean。
 * 形状规则与 `mlc_reduce_run` **同一条**（2-D 且 rows>1 -> 1xcols），
 * 只是累加用 int64、写回前饱和到 Q15 域。 */
static mlc_status mlc_q15_reduce(const mlc_array *a, mlc_array *out, int kind)
{
    int64_t rshape[MLC_MAX_DIMS];
    int32_t rndim = 1;
    int64_t rows = 0, cols = 0, n, i, j;
    const double *pa;
    double *po;

    if (a == NULL || out == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64 || out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    rshape[0] = 1;
    if (a->ndim == 2 && a->shape[0] > 1 && a->shape[1] > 0) {
        rndim = 2;
        rshape[1] = a->shape[1];
        rows = a->shape[0];
        cols = a->shape[1];
    }
    if (mlc_array_numel(out) == 0) {
        if (mlc_array_init(out, MLC_F64, rndim, rshape) != MLC_OK) {
            return MLC_ERR;
        }
    }
    if (out->ndim != rndim) {
        return MLC_ERR;
    }
    for (i = 0; i < rndim; ++i) {
        if (out->shape[i] != rshape[i]) {
            return MLC_ERR;
        }
    }
    n = mlc_array_numel(a);
    if (n <= 0) {
        return MLC_ERR;             /* 空输入：与 f64 归约一致，诚实拒绝 */
    }
    pa = (const double *)a->data;
    po = (double *)out->data;
    if (pa == NULL || po == NULL) {
        return MLC_ERR;
    }

    if (rows <= 1) {
        int64_t acc = (int64_t)pa[0];
        for (i = 1; i < n; ++i) {
            int64_t v = (int64_t)pa[i];
            if (kind == 0 || kind == 3) { acc += v; }
            else if (kind == 1) { if (v > acc) { acc = v; } }
            else { if (v < acc) { acc = v; } }
        }
        if (kind == 3) { acc = acc / n; }
        po[0] = (double)mlc_q15_sat(acc);
        return MLC_OK;
    }
    for (j = 0; j < cols; ++j) {
        int64_t acc = (int64_t)pa[j];
        for (i = 1; i < rows; ++i) {
            int64_t v = (int64_t)pa[i * cols + j];
            if (kind == 0 || kind == 3) { acc += v; }
            else if (kind == 1) { if (v > acc) { acc = v; } }
            else { if (v < acc) { acc = v; } }
        }
        if (kind == 3) { acc = acc / rows; }
        po[j] = (double)mlc_q15_sat(acc);
    }
    return MLC_OK;
}

mlc_status mlc_op_q15_sum(const mlc_array *a, mlc_array *out)
{
    return mlc_q15_reduce(a, out, 0);
}

mlc_status mlc_op_q15_max(const mlc_array *a, mlc_array *out)
{
    return mlc_q15_reduce(a, out, 1);
}

mlc_status mlc_op_q15_min(const mlc_array *a, mlc_array *out)
{
    return mlc_q15_reduce(a, out, 2);
}

mlc_status mlc_op_q15_mean(const mlc_array *a, mlc_array *out)
{
    return mlc_q15_reduce(a, out, 3);
}

/* Q15 除法：round(a_q * 2^15 / b_q)，半值远离零，结果饱和。
 * 除数为 0 时**明确拒绝** —— 定点里返回 0/饱和值会让下游把错误当数据。 */
mlc_status mlc_op_q15_div(const mlc_array *a, const mlc_array *b, mlc_array *out)
{
    int64_t n = 0, i;

    if (mlc_q15_prepare(a, b, out, &n) != MLC_OK) {
        return MLC_ERR;
    }
    for (i = 0; i < n; ++i) {
        int64_t va = (int64_t)(((const double *)a->data)[i]);
        int64_t vb = (int64_t)(((const double *)b->data)[i]);
        int64_t num, den, an, ad, q;
        int neg;

        if (vb == 0) {
            return MLC_ERR;             /* 除零：不猜 */
        }
        num = va * (((int64_t)1) << MLC_Q15_FRAC);
        den = vb;
        neg = ((num < 0) != (den < 0));
        an = (num < 0) ? -num : num;
        ad = (den < 0) ? -den : den;
        q = (an + ad / 2) / ad;         /* 半值远离零 */
        if (neg) {
            q = -q;
        }
        ((double *)out->data)[i] = (double)mlc_q15_sat(q);
    }
    return MLC_OK;
}

/* @m2c coverage-exclude end */

mlc_status mlc_op_sum(const mlc_array *a, mlc_array *out)
{
    if (mlc_array_numel(out) == 0) {
        /* 形状未标注的返回值：按**MATLAB 语义**算形状 ——
         * 2-D 且行数 > 1 时沿行求和得到 1 x cols，其余为 1x1。
         * 若这里猜成 1x1，下面的一致性检查必然拒绝（差分测试 seed=7 抓到的正是这一步）。 */
        int64_t rshape[MLC_MAX_DIMS];
        int32_t rndim = 1;
        rshape[0] = 1;
        if (a != NULL && a->ndim == 2 && a->shape[0] > 1 && a->shape[1] > 0) {
            rndim = 2;
            rshape[0] = 1;
            rshape[1] = a->shape[1];
        }
        if (mlc_array_init(out, MLC_F64, rndim, rshape) != MLC_OK) {
            return MLC_ERR;
        }
    }

    int64_t n, i, j;
    const double *pa;
    double *po;

    if (a == NULL || out == NULL || a->dtype != MLC_F64
            || out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    pa = (const double *)a->data;
    po = (double *)out->data;
    if (pa == NULL || po == NULL) {
        return MLC_ERR;
    }
    if (a->ndim == 1) {
        double acc = 0.0;
        n = mlc_array_numel(a);
        if (n <= 0 || mlc_array_numel(out) != 1) {
            return MLC_ERR;
        }
        for (i = 0; i < n; ++i) {
            acc += pa[i];
        }
        po[0] = acc;
        return MLC_OK;
    }
    if (a->ndim == 2) {
        int64_t rows = a->shape[0], cols = a->shape[1];
        if (rows <= 0 || cols <= 0) {
            return MLC_ERR;
        }
        if (rows > 1) {
            /* MATLAB 默认沿第一个非单例维：2x3 -> 1x3。 */
            if (out->ndim != 2 || out->shape[0] != 1
                    || out->shape[1] != cols) {
                return MLC_ERR;
            }
            for (j = 0; j < cols; ++j) {
                double acc = 0.0;
                for (i = 0; i < rows; ++i) {
                    acc += pa[i * cols + j];
                }
                po[j] = acc;
            }
            return MLC_OK;
        }
        {
            double acc = 0.0;
            n = rows * cols;
            if (mlc_array_numel(out) != 1) {
                return MLC_ERR;
            }
            for (i = 0; i < n; ++i) {
                acc += pa[i];
            }
            po[0] = acc;
            return MLC_OK;
        }
    }
    return MLC_ERR; /* 3-D+ 暂不静默猜维度 */
}

/* 归约核心（mean/max/min 共用）：与 `mlc_op_sum` **同一套**列语义。
 * kind: 0 = mean, 1 = max, 2 = min。
 * 2-D 且 rows > 1 时沿行归约 -> 1 x cols；其余 -> 1x1。 */
static mlc_status mlc_reduce_run(const mlc_array *a, mlc_array *out, int kind)
{
    int64_t rshape[MLC_MAX_DIMS];
    int32_t rndim = 1;
    int64_t rows = 0, cols = 0, n, i, j;
    const double *pa;
    double *po;
    double acc;

    if (a == NULL || out == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64 || out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    rshape[0] = 1;
    if (a->ndim == 2 && a->shape[0] > 1 && a->shape[1] > 0) {
        rndim = 2;
        rshape[1] = a->shape[1];
        rows = a->shape[0];
        cols = a->shape[1];
    }
    if (mlc_array_numel(out) == 0) {
        if (mlc_array_init(out, MLC_F64, rndim, rshape) != MLC_OK) {
            return MLC_ERR;
        }
    }
    if (out->ndim != rndim) {
        return MLC_ERR;
    }
    for (i = 0; i < rndim; ++i) {
        if (out->shape[i] != rshape[i]) {
            return MLC_ERR;
        }
    }
    n = mlc_array_numel(a);
    if (n <= 0) {
        return MLC_ERR;             /* 空输入：诚实报错，不返回 0/NaN */
    }
    pa = (const double *)a->data;
    po = (double *)out->data;
    if (pa == NULL || po == NULL) {
        return MLC_ERR;
    }
    if (rows <= 1) {
        /* 1x1（或 1-D）：全元素 */
        acc = pa[0];
        for (i = 1; i < n; ++i) {
            if (kind == 0) { acc += pa[i]; }
            else if (kind == 1) { if (pa[i] > acc) { acc = pa[i]; } }
            else { if (pa[i] < acc) { acc = pa[i]; } }
        }
        po[0] = (kind == 0) ? (acc / (double)n) : acc;
        return MLC_OK;
    }
    /* 2-D 且 rows > 1：按列归约（行主序：a[i*cols + j]） */
    for (j = 0; j < cols; ++j) {
        acc = pa[j];
        for (i = 1; i < rows; ++i) {
            double v = pa[i * cols + j];
            if (kind == 0) { acc += v; }
            else if (kind == 1) { if (v > acc) { acc = v; } }
            else { if (v < acc) { acc = v; } }
        }
        po[j] = (kind == 0) ? (acc / (double)rows) : acc;
    }
    return MLC_OK;
}

mlc_status mlc_op_mean(const mlc_array *a, mlc_array *out)
{
    return mlc_reduce_run(a, out, 0);
}

mlc_status mlc_op_max(const mlc_array *a, mlc_array *out)
{
    return mlc_reduce_run(a, out, 1);
}

mlc_status mlc_op_min(const mlc_array *a, mlc_array *out)
{
    return mlc_reduce_run(a, out, 2);
}

mlc_status mlc_op_setidx(mlc_array *a, const mlc_array *v, int64_t i)
{
    int64_t n;

    if (a == NULL || v == NULL || a->data == NULL || v->data == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64 || v->dtype != MLC_F64) {
        return MLC_ERR;
    }
    if (mlc_array_numel(v) != 1) {
        return MLC_ERR;          /* 右值必须是标量（1x1） */
    }
    n = mlc_array_numel(a);
    /* IDX-1：唯一允许 -1 的地方；越界一律 MLC_ERR，不静默截断 */
    if (i < 1 || i > n) {
        return MLC_ERR;
    }
    ((double *)a->data)[i - 1] = ((const double *)v->data)[0];
    return MLC_OK;
}

/* 逐元素标量函数共用实现：形状必须与输入一致（不猜、不广播）。 */
static mlc_status mlc_unary_f64(const mlc_array *a, mlc_array *out, int code)
{
    int64_t i, n;

    if (a == NULL || out == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64 || out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    n = mlc_array_numel(a);
    if (n < 0 || mlc_array_numel(out) != n) {
        return MLC_ERR;
    }
    /* 空数组是**合法输入**：`sqrt([])` 就是 `[]`（MATLAB 语义）。
     * 空数组的 data 必然是 NULL —— 不能在它上面判"未初始化"。 */
    if (n == 0) {
        return MLC_OK;
    }
    if (a->data == NULL || out->data == NULL) {
        return MLC_ERR;
    }
    for (i = 0; i < n; ++i) {
        double v = ((const double *)a->data)[i];
        double r;
        switch (code) {
        case 0: r = sqrt(v); break;
        case 1: r = fabs(v); break;
        case 2: r = exp(v); break;
        case 3: r = log(v); break;
        case 4: r = sin(v); break;
        case 5: r = cos(v); break;
        case 6: r = tan(v); break;
        case 7: r = floor(v); break;
        case 8: r = ceil(v); break;
        case 9: r = round(v); break;
        case 10: r = log2(v); break;
        default: r = log10(v); break;
        }
        ((double *)out->data)[i] = r;
    }
    return MLC_OK;
}

/* 1x1 谓词共用实现：code 0=any 1=all 2=nnz 3=isreal 4=isnumeric */
mlc_status mlc_op_isequal(const mlc_array *a, const mlc_array *b,
                          mlc_array *out)
{
    int64_t n, i;
    int64_t shape1[1];
    const double *pa;
    const double *pb;

    if (a == NULL || b == NULL || out == NULL || out->data == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64 || b->dtype != MLC_F64 || out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    if (mlc_array_numel(out) != 1) {
        return MLC_ERR;              /* 结果恒 1x1 */
    }
    n = mlc_array_numel(a);
    ((double *)out->data)[0] = 0.0;
    if (mlc_array_numel(b) != n) {
        return MLC_OK;               /* 形状不同 -> false，不是错误 */
    }
    pa = (const double *)a->data;
    pb = (const double *)b->data;
    if (n > 0 && (pa == NULL || pb == NULL)) {
        return MLC_ERR;
    }
    for (i = 0; i < n; ++i) {
        if (pa[i] != pb[i]) {
            return MLC_OK;
        }
    }
    ((double *)out->data)[0] = 1.0;
    (void)shape1;
    return MLC_OK;
}

mlc_status mlc_op_isequal_k(const mlc_array *a, double k, mlc_array *out)
{
    if (a == NULL || out == NULL || out->data == NULL || a->data == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64 || out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    if (mlc_array_numel(out) != 1) {
        return MLC_ERR;
    }
    ((double *)out->data)[0] =
        (mlc_array_numel(a) == 1 && ((const double *)a->data)[0] == k) ? 1.0 : 0.0;
    return MLC_OK;
}

static mlc_status mlc_pred_f64(const mlc_array *a, mlc_array *out, int code)
{
    int64_t i, n, cnt = 0, all_nz = 1;

    if (a == NULL || out == NULL || out->data == NULL || a->data == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64 || out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    if (mlc_array_numel(out) != 1) {
        return MLC_ERR;              /* 结果恒 1x1；不符说明调用方算错了形状 */
    }
    n = mlc_array_numel(a);
    if (code == 3 || code == 4) {
        /* 本运行时的数据只有 f64 实数：isreal / isnumeric 恒真 */
        ((double *)out->data)[0] = 1.0;
        return MLC_OK;
    }
    for (i = 0; i < n; ++i) {
        double v = ((const double *)a->data)[i];
        if (v != 0.0) {
            cnt += 1;
        } else {
            all_nz = 0;
        }
    }
    if (code == 0) {
        ((double *)out->data)[0] = (cnt > 0) ? 1.0 : 0.0;
    } else if (code == 1) {
        ((double *)out->data)[0] = (n > 0 && all_nz) ? 1.0 : 0.0;
    } else {
        ((double *)out->data)[0] = (double)cnt;
    }
    return MLC_OK;
}

mlc_status mlc_op_any(const mlc_array *a, mlc_array *out)
{
    return mlc_pred_f64(a, out, 0);
}

mlc_status mlc_op_all(const mlc_array *a, mlc_array *out)
{
    return mlc_pred_f64(a, out, 1);
}

mlc_status mlc_op_nnz(const mlc_array *a, mlc_array *out)
{
    return mlc_pred_f64(a, out, 2);
}

mlc_status mlc_op_isreal(const mlc_array *a, mlc_array *out)
{
    return mlc_pred_f64(a, out, 3);
}

mlc_status mlc_op_isnumeric(const mlc_array *a, mlc_array *out)
{
    return mlc_pred_f64(a, out, 4);
}

mlc_status mlc_op_sqrt(const mlc_array *a, mlc_array *out)
{
    return mlc_unary_f64(a, out, 0);
}

mlc_status mlc_op_abs(const mlc_array *a, mlc_array *out)
{
    return mlc_unary_f64(a, out, 1);
}

mlc_status mlc_op_exp(const mlc_array *a, mlc_array *out)
{
    return mlc_unary_f64(a, out, 2);
}

mlc_status mlc_op_log(const mlc_array *a, mlc_array *out)
{
    return mlc_unary_f64(a, out, 3);
}

mlc_status mlc_op_sin(const mlc_array *a, mlc_array *out)
{
    return mlc_unary_f64(a, out, 4);
}

mlc_status mlc_op_cos(const mlc_array *a, mlc_array *out)
{
    return mlc_unary_f64(a, out, 5);
}

mlc_status mlc_op_tan(const mlc_array *a, mlc_array *out)
{
    return mlc_unary_f64(a, out, 6);
}

mlc_status mlc_op_floor(const mlc_array *a, mlc_array *out)
{
    return mlc_unary_f64(a, out, 7);
}

mlc_status mlc_op_ceil(const mlc_array *a, mlc_array *out)
{
    return mlc_unary_f64(a, out, 8);
}

mlc_status mlc_op_round(const mlc_array *a, mlc_array *out)
{
    return mlc_unary_f64(a, out, 9);
}

mlc_status mlc_op_log2(const mlc_array *a, mlc_array *out)
{
    return mlc_unary_f64(a, out, 10);
}

mlc_status mlc_op_log10(const mlc_array *a, mlc_array *out)
{
    return mlc_unary_f64(a, out, 11);
}

mlc_status mlc_op_colrange(const mlc_array *a, int64_t lo, int64_t hi,
                            mlc_array *out)
{
    int64_t rows, cols, k, i, j;

    if (a == NULL || out == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64 || out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    if (a->ndim != 2) {
        return MLC_ERR;              /* 只对 2-D 取列区间 */
    }
    rows = a->shape[0];
    cols = a->shape[1];
    if (hi < 0) {
        hi = cols;                   /* end */
    }
    if (lo < 1 || hi > cols || hi < lo) {
        return MLC_ERR;
    }
    k = hi - lo + 1;
    if (mlc_array_numel(out) == 0) {
        int64_t sh[2];
        sh[0] = rows;
        sh[1] = k;
        if (mlc_array_init(out, MLC_F64, 2, sh) != MLC_OK) {
            return MLC_ERR;
        }
    }
    if (out->ndim != 2 || out->shape[0] != rows || out->shape[1] != k) {
        return MLC_ERR;
    }
    for (j = 0; j < k; ++j) {
        for (i = 0; i < rows; ++i) {
            /* 行主序：行步长 strides[0]，列步长 strides[1]（与 mlc_op_col 一致） */
            ((double *)out->data)[i * out->strides[0] + j * out->strides[1]] =
                ((const double *)a->data)[i * a->strides[0]
                                          + (lo - 1 + j) * a->strides[1]];
        }
    }
    return MLC_OK;
}

mlc_status mlc_op_col(const mlc_array *a, int64_t j, mlc_array *out)
{
    int64_t i, rows;

    if (a == NULL || out == NULL || out->data == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64 || out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    if (a->ndim != 2) {
        return MLC_ERR;              /* 只对 2-D 取列 */
    }
    rows = a->shape[0];
    if (j < 1 || j > a->shape[1]) {
        return MLC_ERR;              /* 越界：不猜 */
    }
    if (mlc_array_numel(out) != rows) {
        return MLC_ERR;
    }
    for (i = 0; i < rows; ++i) {
        ((double *)out->data)[i] =
            ((const double *)a->data)[i * a->strides[0]
                                      + (j - 1) * a->strides[1]];
    }
    return MLC_OK;
}

mlc_status mlc_op_size_dim(const mlc_array *a, int64_t dim,
                           mlc_array *out)
{
    int64_t n;

    if (a == NULL || out == NULL || out->data == NULL) {
        return MLC_ERR;
    }
    if (out->dtype != MLC_F64 || mlc_array_numel(out) != 1) {
        return MLC_ERR;
    }
    if (dim < 1) {
        return MLC_ERR;
    }
    /* MATLAB 语义：超出 ndim 的维度，长度对非空数组为 1、对空数组为 0 */
    if (dim > a->ndim) {
        n = (mlc_array_numel(a) == 0) ? 0 : 1;
    } else {
        n = a->shape[dim - 1];
    }
    ((double *)out->data)[0] = (double)n;
    return MLC_OK;
}

mlc_status mlc_op_numel(const mlc_array *a, mlc_array *out)
{
    int64_t n;

    if (a == NULL || out == NULL || out->data == NULL) {
        return MLC_ERR;
    }
    if (out->dtype != MLC_F64 || mlc_array_numel(out) != 1) {
        return MLC_ERR;
    }
    n = mlc_array_numel(a);
    if (n < 0) {
        return MLC_ERR;
    }
    ((double *)out->data)[0] = (double)n;
    return MLC_OK;
}

mlc_status mlc_op_length(const mlc_array *a, mlc_array *out)
{
    int64_t i, best = 0;

    if (a == NULL || out == NULL || out->data == NULL) {
        return MLC_ERR;
    }
    if (out->dtype != MLC_F64 || mlc_array_numel(out) != 1) {
        return MLC_ERR;
    }
    /* length(X) = max(size(X))；0 维退回 numel */
    if (a->ndim <= 0) {
        ((double *)out->data)[0] = (double)mlc_array_numel(a);
        return MLC_OK;
    }
    for (i = 0; i < a->ndim; ++i) {
        if (a->shape[i] > best) {
            best = a->shape[i];
        }
    }
    ((double *)out->data)[0] = (double)best;
    return MLC_OK;
}

mlc_status mlc_op_isempty(const mlc_array *a, mlc_array *out)
{
    int64_t n;

    if (a == NULL || out == NULL || out->data == NULL) {
        return MLC_ERR;
    }
    if (out->dtype != MLC_F64 || mlc_array_numel(out) != 1) {
        return MLC_ERR;
    }
    n = mlc_array_numel(a);
    if (n < 0) {
        return MLC_ERR;
    }
    ((double *)out->data)[0] = (n == 0) ? 1.0 : 0.0;
    return MLC_OK;
}

mlc_status mlc_op_row(const mlc_array *a, int64_t row, mlc_array *out)
{
    int64_t cols, base, k;

    if (a == NULL || out == NULL || a->data == NULL || out->data == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64 || out->dtype != MLC_F64 || a->ndim != 2) {
        return MLC_ERR;
    }
    cols = a->shape[1];
    if (mlc_array_numel(out) != cols) {
        return MLC_ERR;              /* 输出长度必须等于列数 */
    }
    if (row < 1 || row > a->shape[0]) {
        return MLC_ERR;              /* 越界一律报错，不截断 */
    }
    base = (row - 1) * a->strides[0];
    for (k = 0; k < cols; ++k) {
        ((double *)out->data)[k] =
            ((const double *)a->data)[base + k * a->strides[1]];
    }
    return MLC_OK;
}

/* 二维下标取值：`A(i,j)`，**形状在运行期才知道**。
 *
 *   L   = (i-1) + (j-1)*rows              MATLAB 列主序线性下标
 *   off = (L % rows) * cols + L / rows    换算到行主序存储
 *
 * 与 `mlc_op_index` 的 ORDER-1 同一套换算，只是起点不同。
 * 只接受 ndim>=2：1-D 的 `A(i,j)` 在 MATLAB 里要求 j==1，猜它不如拒绝。 */
mlc_status mlc_op_idx2(const mlc_array *a, int64_t row, int64_t col,
                       mlc_array *out)
{
    int64_t rows, cols, l;

    if (a == NULL || out == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64 || out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    if (mlc_array_numel(out) != 1) {
        return MLC_ERR;
    }
    if (a->ndim < 2 || a->ndim > MLC_MAX_DIMS) {
        return MLC_ERR;
    }
    rows = a->shape[0];
    cols = a->shape[1];
    if (rows <= 0 || cols <= 0) {
        return MLC_ERR;
    }
    if (row < 1 || row > rows || col < 1 || col > cols) {
        return MLC_ERR;              /* 越界不截断 */
    }
    l = (row - 1) + (col - 1) * rows;
    ((double *)out->data)[0] =
        ((const double *)a->data)[(l % rows) * cols + l / rows];
    return MLC_OK;
}

/* 运行期维度填充：`ones(m,n)` / `zeros(m,n)`，m/n 只在运行时知道。
 *
 * 与 `fill:`（编译期字面量）互补：那边直接写进常量数组，这边必须动态分配。
 * 维度必须 >= 1：MATLAB 里 0 表示空，但这条通道区分不了"空"与"算错"，拒绝更安全。 */
mlc_status mlc_op_fill_alloc(int64_t rows, int64_t cols, double value,
                             mlc_array *out)
{
    int64_t n, i;
    int64_t sh[2];
    double *po;

    if (out == NULL) {
        return MLC_ERR;
    }
    if (rows < 1 || cols < 1) {
        return MLC_ERR;
    }
    n = rows * cols;
    if (n / rows != cols) {
        return MLC_ERR;              /* 乘法溢出 */
    }
    sh[0] = rows;
    sh[1] = cols;
    if (out->ndim == 0 || mlc_array_numel(out) == 0) {
        if (mlc_array_init(out, MLC_F64, 2, sh) != MLC_OK) {
            return MLC_ERR;
        }
    }
    if (out->ndim != 2 || out->shape[0] != rows || out->shape[1] != cols) {
        return MLC_ERR;
    }
    po = (double *)out->data;
    if (po == NULL) {
        return MLC_ERR;
    }
    for (i = 0; i < n; ++i) {
        po[i] = value;
    }
    return MLC_OK;
}

/* 集合差：`setdiff(a,b)`，1-D 标量集合。
 *
 * 规则（与 MATLAB 一致的三条）：A 中元素、排除 B 中出现的、**去重并升序**。
 * 比较用精确相等：我们只处理能精确表示的整数/常量，浮点近似相等会让结果不可预测。
 * 长度运行期才知道 -> 先按 numel(a) 分配，去重后再收窄 shape（缓冲区可多不可少）。 */
mlc_status mlc_op_setdiff_alloc(const mlc_array *a, const mlc_array *b,
                                mlc_array *out)
{
    int64_t na, nb, i, j, k, m;
    int64_t sh[1];
    const double *pa, *pb;
    double *po, t;

    if (a == NULL || b == NULL || out == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64 || b->dtype != MLC_F64) {
        return MLC_ERR;
    }
    /* `out` 零初始化时 dtype == 0（未定形），由下面的就地分配赋类型 */
    if (out->ndim != 0 && out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    if (a->ndim != 1 || b->ndim != 1) {
        return MLC_ERR;              /* 行集合（'rows'）语义不同：拒绝 */
    }
    na = a->shape[0];
    nb = b->shape[0];
    if (na <= 0) {
        return MLC_ERR;
    }
    sh[0] = na;
    if (out->ndim == 0 || mlc_array_numel(out) == 0) {
        if (mlc_array_init(out, MLC_F64, 1, sh) != MLC_OK) {
            return MLC_ERR;
        }
    }
    if (mlc_array_numel(out) < na) {
        return MLC_ERR;
    }
    pa = (const double *)a->data;
    pb = (nb > 0) ? (const double *)b->data : NULL;
    po = (double *)out->data;
    if (pa == NULL || po == NULL) {
        return MLC_ERR;
    }

    /* 1) 筛掉出现在 b 里的 */
    m = 0;
    for (i = 0; i < na; ++i) {
        int hit = 0;
        for (j = 0; j < nb; ++j) {
            if (pa[i] == pb[j]) {
                hit = 1;
                break;
            }
        }
        if (!hit) {
            po[m++] = pa[i];
        }
    }
    /* 2) 插入排序（集合通常很小；O(m^2) 但无额外分配） */
    for (i = 1; i < m; ++i) {
        t = po[i];
        j = i - 1;
        while (j >= 0 && po[j] > t) {
            po[j + 1] = po[j];
            --j;
        }
        po[j + 1] = t;
    }
    /* 3) 去重（原地收窄） */
    k = 0;
    for (i = 0; i < m; ++i) {
        if (k == 0 || po[k - 1] != po[i]) {
            po[k++] = po[i];
        }
    }
    out->shape[0] = (k > 0) ? k : 0;
    return MLC_OK;
}

mlc_status mlc_op_index(const mlc_array *a, int64_t matlab_index,
                        mlc_array *out)
{
    int64_t n, idx0;
    const double *pa;
    double *po;

    if (a == NULL || out == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64 || out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    if (mlc_array_numel(out) != 1) {
        return MLC_ERR;
    }
    n = mlc_array_numel(a);
    if (n < 0) {
        return MLC_ERR;
    }
    idx0 = matlab_index - 1; /* IDX-1：唯一允许做 -1 的地方 */
    if (idx0 < 0 || idx0 >= n) {
        return MLC_ERR;
    }
    pa = (const double *)a->data;
    po = (double *)out->data;
    if (pa == NULL || po == NULL) {
        return MLC_ERR;
    }
    if (a->ndim == 1) {
        po[0] = pa[idx0];
    } else if (a->ndim >= 2 && a->ndim <= MLC_MAX_DIMS) {
        /* ORDER-1：MATLAB 线性下标是列主序；内存是行主序，必须换算。 */
        int64_t rem = idx0, off = 0;
        int32_t d;
        for (d = 0; d < a->ndim; ++d) {
            int64_t dim = a->shape[d];
            int64_t coord;
            if (dim <= 0) {
                return MLC_ERR;
            }
            coord = rem % dim;
            rem /= dim;
            off += coord * a->strides[d];
        }
        po[0] = pa[off];
    } else {
        return MLC_ERR;
    }
    return MLC_OK;
}

/*
 * 转置（`x'`）。MATLAB 的 `'` 是**共轭**转置；本版只支持实数 f64，
 * 所以等价于普通转置 —— 复数进来会因 dtype 不符被拒，不会静默算错。
 *
 * 只做 2-D：`out` 由调用方按 [n, m] 初始化（mlc.h 的约定）。
 */
/*
 * 切片 `x(from:to)`：1-based 闭区间，仅 1-D。
 *
 * 为什么只做 1-D：二维的 `x(1:2)` 在 MATLAB 里是**线性索引**（列优先展开），
 * 而不是"取前两行"。两者语义不同，混着做最容易生成"能跑但算错"的代码。
 */
mlc_status mlc_op_hcat(const mlc_array *a, const mlc_array *b, mlc_array *out)
{
    int64_t na, nb, i;
    int64_t sh;

    if (a == NULL || b == NULL || out == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64 || b->dtype != MLC_F64 || out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    /* 只做 1-D：2-D 的 `[a b]` 是"按列拼"，与这里不是一件事 */
    if (a->ndim != 1 || b->ndim != 1) {
        return MLC_ERR;
    }
    na = a->shape[0];
    nb = b->shape[0];
    if (na < 0 || nb < 0) {
        return MLC_ERR;
    }
    sh = na + nb;
    /* 空数组是**合法**操作数（`[[] b]` 就等于 `b`）：只有当某一侧确实有元素时，
     * 它的 data 才不许是 NULL。把 NULL 一律当"未初始化"会误拒空拼接。 */
    if ((na > 0 && a->data == NULL) || (nb > 0 && b->data == NULL)) {
        return MLC_ERR;
    }
    if (mlc_array_numel(out) == 0) {
        if (mlc_array_init(out, MLC_F64, 1, &sh) != MLC_OK) {
            return MLC_ERR;
        }
    }
    if (mlc_array_numel(out) != sh) {
        return MLC_ERR;
    }
    for (i = 0; i < na; ++i) {
        ((double *)out->data)[i] = ((const double *)a->data)[i];
    }
    for (i = 0; i < nb; ++i) {
        ((double *)out->data)[na + i] = ((const double *)b->data)[i];
    }
    return MLC_OK;
}

mlc_status mlc_op_slice(const mlc_array *a, int64_t from, int64_t to,
                        mlc_array *out)
{
    int64_t n, len, i;
    const double *pa;
    double *po;

    if (a == NULL || out == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64) {
        return MLC_ERR;
    }
    /* `out` 尚未定形时（零初始化 -> ndim == 0、dtype == 0）不校验 dtype：
     * 它会由下面的就地分配赋予正确形状与类型。 */
    if (out->ndim != 0 && out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    if (a->ndim != 1 || (out->ndim != 0 && out->ndim != 1)) {
        return MLC_ERR;              /* 2-D 的线性索引语义不同：拒绝 */
    }
    n = a->shape[0];
    if (from < 1 || to < from || to > n) {
        return MLC_ERR;              /* 越界不截断：截断会让错误静默通过 */
    }
    len = to - from + 1;
    /* 空输出 = 授权按结果形状就地分配（dynshape 入口）。
     * 变量边界时生成端推不出长度，只能由这里定形。
     *
     * `ndim == 0` 也要算"未定形"：生成端现在把临时量零初始化了，
     * 而零初始化后 `numel` 是**空积 = 1**（不是 0），单看 numel 会漏掉这种情况。 */
    if (out->ndim == 0 || mlc_array_numel(out) == 0) {
        if (mlc_array_init(out, MLC_F64, 1, &len) != MLC_OK) {
            return MLC_ERR;
        }
    }
    if (out->ndim != 1 || out->shape[0] != len) {
        return MLC_ERR;
    }
    pa = (const double *)a->data;
    po = (double *)out->data;
    if (pa == NULL || po == NULL) {
        return MLC_ERR;
    }
    for (i = 0; i < len; ++i) {
        po[i * out->strides[0]] = pa[(from - 1 + i) * a->strides[0]];
    }
    return MLC_OK;
}

/*
 * `A(:)`：按列优先展平。
 *
 * 为什么不用 memcpy：MATLAB 的顺序是**列优先**，而 mlc_array 是行主序存储。
 * 直接按内存顺序拷贝在方阵上"看起来对"，非方阵立刻错 —— 这是最典型的静默错误。
 */
mlc_status mlc_op_flatten(const mlc_array *a, mlc_array *out)
{
    int64_t n, i;
    const double *pa;
    double *po;

    if (a == NULL || out == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64 || out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    if (out->ndim != 1) {
        return MLC_ERR;
    }
    n = mlc_array_numel(a);
    if (out->shape[0] != n) {
        return MLC_ERR;
    }
    pa = (const double *)a->data;
    po = (double *)out->data;
    if (pa == NULL || po == NULL) {
        return MLC_ERR;
    }
    if (a->ndim == 1) {
        for (i = 0; i < n; ++i) {
            po[i * out->strides[0]] = pa[i * a->strides[0]];
        }
        return MLC_OK;
    }
    {
        /* 2-D：外层走列、内层走行 —— 这才是 MATLAB 的线性索引顺序 */
        int64_t m = a->shape[0];
        int64_t cols = a->shape[1];
        int64_t k = 0;
        int64_t j;
        for (j = 0; j < cols; ++j) {
            for (i = 0; i < m; ++i) {
                po[k++] = pa[i * a->strides[0] + j * a->strides[1]];
            }
        }
    }
    return MLC_OK;
}

/*
 * `x(x >k)`：取出满足条件的元素并压实。
 *
 * 结果长度是数据相关的：这里要求 out 的长度**等于**命中数，
 * 否则返回 MLC_ERR —— 截断或补零都会让错误静默通过。
 */
mlc_status mlc_op_mask(const mlc_array *a, int cmp, double k, mlc_array *out)
{
    int64_t n, i, hit;
    const double *pa;
    double *po;

    if (a == NULL || out == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64 || out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    if (out->ndim != 1) {
        return MLC_ERR;
    }
    n = mlc_array_numel(a);
    hit = 0;
    pa = (const double *)a->data;
    po = (double *)out->data;
    if (pa == NULL || po == NULL) {
        return MLC_ERR;
    }
    for (i = 0; i < n; ++i) {
        if (mlc_mask_test(pa[i], cmp, k)) {
            ++hit;
        }
    }
    if (out->shape[0] != hit) {
        return MLC_ERR;              /* 长度不符：不截断也不补零 */
    }
    hit = 0;
    for (i = 0; i < n; ++i) {
        if (mlc_mask_test(pa[i], cmp, k)) {
            po[hit * out->strides[0]] = pa[i];
            ++hit;
        }
    }
    return MLC_OK;
}

/*
 * `x(x >k)` 的动态形状版本：长度由命中数决定，由**算子**分配 out。
 *
 * 这是 "算子只填数据、不重新分配" 的唯一例外 —— 因为长度是数据相关的，
 * 调用方不可能预先给出正确形状。所有权转移给调用方（需 mlc_array_free）。
 */
mlc_status mlc_op_mask_alloc(const mlc_array *a, int cmp, double k,
                             mlc_array *out)
{
    int64_t n, i, hit;
    int64_t shape1[1];
    const double *pa;
    double *po;
    mlc_status st;

    if (a == NULL || out == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64) {
        return MLC_ERR;
    }
    n = mlc_array_numel(a);
    pa = (const double *)a->data;
    if (pa == NULL) {
        return MLC_ERR;
    }
    hit = 0;
    for (i = 0; i < n; ++i) {
        if (mlc_mask_test(pa[i], cmp, k)) {
            ++hit;
        }
    }
    shape1[0] = hit;
    st = mlc_array_init(out, MLC_F64, 1, shape1);
    if (st != MLC_OK) {
        return st;
    }
    po = (double *)out->data;
    hit = 0;
    for (i = 0; i < n; ++i) {
        if (mlc_mask_test(pa[i], cmp, k)) {
            po[hit] = pa[i];
            ++hit;
        }
    }
    return MLC_OK;
}

/*
 * `find(x >k)`：返回 1-based 下标，长度由命中数决定。
 *
 * 下标**从 1 开始**：这是 MATLAB 的约定，也是 IDX-1 规则唯一该露出来的地方
 * （其它算子一律 0-based）。写在这里比写在注释里可靠。
 */
mlc_status mlc_op_find_n(const mlc_array *a, int cmp, double k,
                         int64_t n, mlc_array *out)
{
    int64_t i, total, hit, cap;
    int64_t shape1[1];
    const double *pa;
    double *po;

    if (a == NULL || out == NULL || a->data == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64) {
        return MLC_ERR;
    }
    total = mlc_array_numel(a);
    pa = (const double *)a->data;
    hit = 0;
    for (i = 0; i < total; ++i) {
        if (mlc_mask_test(pa[i], cmp, k)) {
            ++hit;
        }
    }
    cap = (n > 0 && n < hit) ? n : hit;     /* 只取前 n 个 */
    shape1[0] = cap;
    if (mlc_array_init(out, MLC_F64, 1, shape1) != MLC_OK) {
        return MLC_ERR;
    }
    po = (double *)out->data;
    hit = 0;
    for (i = 0; i < total && hit < cap; ++i) {
        if (mlc_mask_test(pa[i], cmp, k)) {
            po[hit++] = (double)(i + 1);
        }
    }
    return MLC_OK;
}

mlc_status mlc_op_find_masked(const mlc_array *a, const mlc_array *b,
                              int cmp, mlc_array *out)
{
    int64_t n, i, hit;
    int64_t shape1[1];
    const double *pa;
    const double *pb;
    double *po;

    if (a == NULL || b == NULL || out == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64 || b->dtype != MLC_F64) {
        return MLC_ERR;
    }
    n = mlc_array_numel(a);
    if (mlc_array_numel(b) != n) {
        return MLC_ERR;              /* 逐元素比较要求等长：不符就不猜 */
    }
    pa = (const double *)a->data;
    pb = (const double *)b->data;
    if (pa == NULL || pb == NULL) {
        return MLC_ERR;
    }
    hit = 0;
    for (i = 0; i < n; ++i) {
        if (mlc_mask_test(pa[i], cmp, pb[i])) {
            ++hit;
        }
    }
    shape1[0] = hit;
    if (mlc_array_init(out, MLC_F64, 1, shape1) != MLC_OK) {
        return MLC_ERR;
    }
    po = (double *)out->data;
    hit = 0;
    for (i = 0; i < n; ++i) {
        if (mlc_mask_test(pa[i], cmp, pb[i])) {
            po[hit++] = (double)(i + 1);
        }
    }
    return MLC_OK;
}

mlc_status mlc_op_find_alloc(const mlc_array *a, int cmp, double k,
                             mlc_array *out)
{
    int64_t n, i, hit;
    int64_t shape1[1];
    const double *pa;
    double *po;
    mlc_status st;

    if (a == NULL || out == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64) {
        return MLC_ERR;
    }
    n = mlc_array_numel(a);
    pa = (const double *)a->data;
    if (pa == NULL) {
        return MLC_ERR;
    }
    hit = 0;
    for (i = 0; i < n; ++i) {
        if (mlc_mask_test(pa[i], cmp, k)) {
            ++hit;
        }
    }
    shape1[0] = hit;
    st = mlc_array_init(out, MLC_F64, 1, shape1);
    if (st != MLC_OK) {
        return st;
    }
    po = (double *)out->data;
    hit = 0;
    for (i = 0; i < n; ++i) {
        if (mlc_mask_test(pa[i], cmp, k)) {
            po[hit++] = (double)(i + 1);   /* 1-based */
        }
    }
    return MLC_OK;
}

mlc_status mlc_op_transpose(const mlc_array *a, mlc_array *out)
{
    int64_t m, n, i, j;
    const double *pa;
    double *po;

    if (a == NULL || out == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64 || out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    if (a->ndim != 2) {
        return MLC_ERR;
    }
    m = a->shape[0];
    n = a->shape[1];
    /* 输出为空（形状未标注的返回值）：按转置形状补分配 */
    if (mlc_array_numel(out) == 0) {
        if (mlc_array_init(out, MLC_F64, 2, (int64_t[]){n, m}) != MLC_OK) {
            return MLC_ERR;
        }
    }
    if (out->ndim != 2 || out->shape[0] != n || out->shape[1] != m) {
        return MLC_ERR;
    }
    pa = (const double *)a->data;
    po = (double *)out->data;
    if (pa == NULL || po == NULL) {
        return MLC_ERR;
    }
    for (i = 0; i < m; ++i) {
        for (j = 0; j < n; ++j) {
            po[j * out->strides[0] + i * out->strides[1]] =
                pa[i * a->strides[0] + j * a->strides[1]];
        }
    }
    return MLC_OK;
}

/*
 * 矩阵乘（`A * B`，MATLAB 语义：**不是**元素级）。
 *
 * 只做 2-D f64：真实工程的矩阵运算绝大多数是二维；ND 泛化留给以后，
 * 因为"高维怎么对齐"是另一个语义问题，混在一起会让两类错误互相掩盖。
 * `out` 由调用方按 [m, n] 初始化（mlc.h 的约定）。
 */
mlc_status mlc_op_matmul(const mlc_array *a, const mlc_array *b,
                         mlc_array *out)
{
    int64_t m, k, k2, n, i, j, t;
    const double *pa;
    const double *pb;
    double *po;

    if (a == NULL || b == NULL || out == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64 || b->dtype != MLC_F64 || out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    if (a->ndim != 2 || b->ndim != 2 || out->ndim != 2) {
        return MLC_ERR;
    }
    m = a->shape[0];
    k = a->shape[1];
    k2 = b->shape[0];
    n = b->shape[1];
    if (k != k2) {
        return MLC_ERR;              /* 内维不匹配：不猜截断 */
    }
    if (out->shape[0] != m || out->shape[1] != n) {
        return MLC_ERR;              /* out 形状必须已是 [m, n] */
    }
    pa = (const double *)a->data;
    pb = (const double *)b->data;
    po = (double *)out->data;
    if (pa == NULL || pb == NULL || po == NULL) {
        return MLC_ERR;
    }
    /* 快路径：a/b/out 都是紧凑行主序时，用 ikj（最内层连续、可向量化）。
     *
     * 紧凑行主序 = strides[0] == 列数 且 strides[1] == 1。
     * 实测（300x300）：原 ijk 跨步版 42.7 ms，ikj 版见 bench 报告。
     */
    if (a->strides[0] == k && a->strides[1] == 1 &&
        b->strides[0] == n && b->strides[1] == 1 &&
        out->strides[0] == n && out->strides[1] == 1) {
        /* ---- 4x4 微内核 ----
         *
         * 每个内层迭代取 A 的 4 个元素、B 的 4 个元素，做 16 次乘加。
         * 16 个独立累加器让编译器有机会向量化，且装载开销被摊薄 4 倍。
         * 尾块（行/列不足 4）退回标量 ikj —— 正确性由移植门与基准指纹共同保证。
         */
        for (i = 0; i < m; ++i) {
            for (j = 0; j < n; ++j) {
                po[i * n + j] = 0.0;
            }
        }
        {
            const int64_t m4 = m - (m % 4);
            const int64_t n4 = n - (n % 4);

            for (i = 0; i < m4; i += 4) {
                for (j = 0; j < n4; j += 4) {
                    double c00 = 0, c01 = 0, c02 = 0, c03 = 0;
                    double c10 = 0, c11 = 0, c12 = 0, c13 = 0;
                    double c20 = 0, c21 = 0, c22 = 0, c23 = 0;
                    double c30 = 0, c31 = 0, c32 = 0, c33 = 0;
                    for (t = 0; t < k; ++t) {
                        const double *ar = pa + i * k + t;
                        const double a0 = ar[0];
                        const double a1 = ar[k];
                        const double a2 = ar[2 * k];
                        const double a3 = ar[3 * k];
                        const double *br = pb + t * n + j;
                        const double b0 = br[0], b1 = br[1];
                        const double b2 = br[2], b3 = br[3];
                    c00 += a0 * b0;
                    c01 += a0 * b1;
                    c02 += a0 * b2;
                    c03 += a0 * b3;
                    c10 += a1 * b0;
                    c11 += a1 * b1;
                    c12 += a1 * b2;
                    c13 += a1 * b3;
                    c20 += a2 * b0;
                    c21 += a2 * b1;
                    c22 += a2 * b2;
                    c23 += a2 * b3;
                    c30 += a3 * b0;
                    c31 += a3 * b1;
                    c32 += a3 * b2;
                    c33 += a3 * b3;
                    }
                    {
                        double *p0 = po + i * n + j;
                        double *p1 = p0 + n;
                        double *p2 = p1 + n;
                        double *p3 = p2 + n;
                        p0[0] = c00; p0[1] = c01; p0[2] = c02; p0[3] = c03;
                        p1[0] = c10; p1[1] = c11; p1[2] = c12; p1[3] = c13;
                        p2[0] = c20; p2[1] = c21; p2[2] = c22; p2[3] = c23;
                        p3[0] = c30; p3[1] = c31; p3[2] = c32; p3[3] = c33;
                    }
                }
                /* 右侧尾列 */
                for (j = n4; j < n; ++j) {
                    for (t = 0; t < k; ++t) {
                        const double av = pa[i * k + t];
                        po[i * n + j] += av * pb[t * n + j];
                        po[(i + 1) * n + j] += pa[(i + 1) * k + t] * pb[t * n + j];
                        po[(i + 2) * n + j] += pa[(i + 2) * k + t] * pb[t * n + j];
                        po[(i + 3) * n + j] += pa[(i + 3) * k + t] * pb[t * n + j];
                    }
                }
            }
            /* 下方尾行 */
            for (i = m4; i < m; ++i) {
                for (t = 0; t < k; ++t) {
                    const double av = pa[i * k + t];
                    const double *brow = pb + t * n;
                    for (j = 0; j < n; ++j) {
                        po[i * n + j] += av * brow[j];
                    }
                }
            }
        }
        return MLC_OK;
    }

    for (i = 0; i < m; ++i) {
        for (j = 0; j < n; ++j) {
            double acc = 0.0;
            for (t = 0; t < k; ++t) {
                acc += pa[i * a->strides[0] + t * a->strides[1]] *
                       pb[t * b->strides[0] + j * b->strides[1]];
            }
            po[i * out->strides[0] + j * out->strides[1]] = acc;
        }
    }
    return MLC_OK;
}
