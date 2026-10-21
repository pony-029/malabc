/*
 * mlc_ops.c —— 算子目录的 C 实现（R432 / P0）。
 *
 * 先只做**能判定对错**的最小集合：加法（含标量广播）、全归约、索引基准。
 * 矩阵乘/转置显式返回 MLC_UNIMPLEMENTED —— 这是诚实边界，不是 TODO。
 */
#include "mlc_ops.h"

#include <stddef.h>

static int mlc_same_shape(const mlc_array *a, const mlc_array *b)
{
    int32_t i;
    if (a->ndim != b->ndim) {
        return 0;
    }
    for (i = 0; i < a->ndim; ++i) {
        if (a->shape[i] != b->shape[i]) {
            return 0;
        }
    }
    return 1;
}

mlc_status mlc_op_add(const mlc_array *a, const mlc_array *b, mlc_array *out)
{
    int64_t na, nb, no, i;
    const double *pa;
    const double *pb;
    double *po;

    if (a == NULL || b == NULL || out == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64 || b->dtype != MLC_F64 || out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    na = mlc_array_numel(a);
    nb = mlc_array_numel(b);
    no = mlc_array_numel(out);
    if (na < 0 || nb < 0 || no < 0) {
        return MLC_ERR;
    }
    /* 只支持三种形态：同形 / a 标量 / b 标量。其余一律报错（不猜广播）。 */
    if (!((na == no && nb == no) || (na == 1 && nb == no) ||
          (nb == 1 && na == no))) {
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
    for (i = 0; i < no; ++i) {
        double va = (na == 1) ? pa[0] : pa[i];
        double vb = (nb == 1) ? pb[0] : pb[i];
        po[i] = va + vb;
    }
    return MLC_OK;
}

mlc_status mlc_op_sum(const mlc_array *a, mlc_array *out)
{
    int64_t n, i;
    const double *pa;
    double *po;
    double acc = 0.0;

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
    pa = (const double *)a->data;
    po = (double *)out->data;
    if (po == NULL) {
        return MLC_ERR;
    }
    if (n > 0 && pa == NULL) {
        return MLC_ERR;
    }
    for (i = 0; i < n; ++i) {
        acc += pa[i];
    }
    po[0] = acc;
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
