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
mlc_status mlc_op_slice(const mlc_array *a, int64_t from, int64_t to,
                        mlc_array *out)
{
    int64_t n, len, i;
    const double *pa;
    double *po;

    if (a == NULL || out == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != MLC_F64 || out->dtype != MLC_F64) {
        return MLC_ERR;
    }
    if (a->ndim != 1 || out->ndim != 1) {
        return MLC_ERR;              /* 2-D 的线性索引语义不同：拒绝 */
    }
    n = a->shape[0];
    if (from < 1 || to < from || to > n) {
        return MLC_ERR;              /* 越界不截断：截断会让错误静默通过 */
    }
    len = to - from + 1;
    if (out->shape[0] != len) {
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
    if (a->ndim != 2 || out->ndim != 2) {
        return MLC_ERR;
    }
    m = a->shape[0];
    n = a->shape[1];
    if (out->shape[0] != n || out->shape[1] != m) {
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
