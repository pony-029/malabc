/*
 * mlc_ops.c —— 算子目录的 C 实现（R432 / P0；R12 扩充）。
 *
 * 四则（add/sub/mul/div）共用一个元素级内核，避免四份重复的校验/广播逻辑；
 * 归约（sum/mean/max/min）各自一个循环。
 * 矩阵乘/转置显式返回 MLC_UNIMPLEMENTED —— 这是诚实边界，不是 TODO。
 */
#include "mlc_ops.h"

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
    int64_t idx[MLC_MAX_DIMS];

    if (a == NULL || b == NULL || out == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64 || b->dtype != MLC_F64 || out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    if (!mlc_bcast_shape(a, b, shape, &ndim)) {
        return MLC_ERR;              /* 不可广播：不猜 */
    }
    /* 输出形状必须与广播结论一致（调用方负责 init） */
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

static mlc_status mlc_reduce_prepare(const mlc_array *a, mlc_array *out,
                                     int64_t *n, const double **pa,
                                     double **po)
{
    if (a == NULL || out == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64 || out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    if (mlc_array_numel(out) != 1) {
        return MLC_ERR;
    }
    *n = mlc_array_numel(a);
    if (*n <= 0) {
        return MLC_ERR; /* 空输入：诚实报错，不返回 0/NaN */
    }
    *pa = (const double *)a->data;
    *po = (double *)out->data;
    if (*pa == NULL || *po == NULL) {
        return MLC_ERR;
    }
    return MLC_OK;
}

mlc_status mlc_op_sum(const mlc_array *a, mlc_array *out)
{
    int64_t n, i;
    const double *pa;
    double *po;
    double acc = 0.0;

    if (mlc_reduce_prepare(a, out, &n, &pa, &po) != MLC_OK) {
        return MLC_ERR;
    }
    for (i = 0; i < n; ++i) {
        acc += pa[i];
    }
    po[0] = acc;
    return MLC_OK;
}

mlc_status mlc_op_mean(const mlc_array *a, mlc_array *out)
{
    int64_t n, i;
    const double *pa;
    double *po;
    double acc = 0.0;

    if (mlc_reduce_prepare(a, out, &n, &pa, &po) != MLC_OK) {
        return MLC_ERR;
    }
    for (i = 0; i < n; ++i) {
        acc += pa[i];
    }
    po[0] = acc / (double)n;
    return MLC_OK;
}

mlc_status mlc_op_max(const mlc_array *a, mlc_array *out)
{
    int64_t n, i;
    const double *pa;
    double *po;
    double best;

    if (mlc_reduce_prepare(a, out, &n, &pa, &po) != MLC_OK) {
        return MLC_ERR;
    }
    best = pa[0];
    for (i = 1; i < n; ++i) {
        if (pa[i] > best) {
            best = pa[i];
        }
    }
    po[0] = best;
    return MLC_OK;
}

mlc_status mlc_op_min(const mlc_array *a, mlc_array *out)
{
    int64_t n, i;
    const double *pa;
    double *po;
    double best;

    if (mlc_reduce_prepare(a, out, &n, &pa, &po) != MLC_OK) {
        return MLC_ERR;
    }
    best = pa[0];
    for (i = 1; i < n; ++i) {
        if (pa[i] < best) {
            best = pa[i];
        }
    }
    po[0] = best;
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
    po[0] = pa[idx0];
    return MLC_OK;
}

mlc_status mlc_op_transpose(const mlc_array *a, mlc_array *out)
{
    (void)a;
    (void)out;
    return MLC_UNIMPLEMENTED;
}

mlc_status mlc_op_matmul(const mlc_array *a, const mlc_array *b,
                         mlc_array *out)
{
    (void)a;
    (void)b;
    (void)out;
    return MLC_UNIMPLEMENTED;
}
