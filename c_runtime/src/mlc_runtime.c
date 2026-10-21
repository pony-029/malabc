/*
 * mlc_runtime.c —— `mlc.h` 的最小实现（R432 / P0）。
 *
 * 目标不是性能，而是把**契约**变成可执行事实：
 *   * 形状/步长计算只有一处；
 *   * 分配/释放的所有权只有一处；
 *   * 错误码只有 0/1/2，不返回“看起来对”的值。
 */
#include "mlc.h"

#include <stdlib.h>
#include <string.h>

const char *mlc_status_string(mlc_status st)
{
    switch (st) {
    case MLC_OK:
        return "ok";
    case MLC_ERR:
        return "error";
    case MLC_UNIMPLEMENTED:
        return "unimplemented";
    default:
        return "unknown";
    }
}

size_t mlc_dtype_size(mlc_dtype dt)
{
    switch (dt) {
    case MLC_F64:
        return sizeof(double);
    case MLC_F32:
        return sizeof(float);
    case MLC_I64:
        return sizeof(int64_t);
    case MLC_I32:
        return sizeof(int32_t);
    case MLC_U8:
        return sizeof(uint8_t);
    case MLC_BOOL:
        return sizeof(uint8_t);
    default:
        return 0;
    }
}

int64_t mlc_array_numel(const mlc_array *a)
{
    int64_t n = 1;
    int32_t i;
    if (a == NULL || a->ndim < 0 || a->ndim > MLC_MAX_DIMS) {
        return -1;
    }
    for (i = 0; i < a->ndim; ++i) {
        if (a->shape[i] < 0) {
            return -1;
        }
        if (a->shape[i] != 0 && n > (INT64_MAX / a->shape[i])) {
            return -1; /* 溢出：宁可报错，也不给一个错的总数 */
        }
        n *= a->shape[i];
    }
    return n;
}

static mlc_status mlc_compute_strides(mlc_array *a)
{
    int32_t i;
    int64_t acc = 1;
    for (i = a->ndim - 1; i >= 0; --i) {
        a->strides[i] = acc;
        if (a->shape[i] != 0 && acc > (INT64_MAX / a->shape[i])) {
            return MLC_ERR;
        }
        acc *= a->shape[i];
    }
    return MLC_OK;
}

mlc_status mlc_array_init(mlc_array *a, mlc_dtype dt, int32_t ndim,
                          const int64_t *shape)
{
    int64_t n;
    size_t esz;
    int32_t i;

    if (a == NULL || shape == NULL || ndim < 0 || ndim > MLC_MAX_DIMS) {
        return MLC_ERR;
    }
    esz = mlc_dtype_size(dt);
    if (esz == 0) {
        return MLC_ERR;
    }
    memset(a, 0, sizeof(*a));
    a->dtype = dt;
    a->ndim = ndim;
    for (i = 0; i < ndim; ++i) {
        if (shape[i] < 0) {
            return MLC_ERR;
        }
        a->shape[i] = shape[i];
    }
    if (mlc_compute_strides(a) != MLC_OK) {
        return MLC_ERR;
    }
    n = mlc_array_numel(a);
    if (n < 0) {
        return MLC_ERR;
    }
    if (n == 0) {
        a->data = NULL;
        a->owns_data = 1;
        return MLC_OK;
    }
    a->data = calloc((size_t)n, esz);
    if (a->data == NULL) {
        return MLC_ERR;
    }
    a->owns_data = 1;
    return MLC_OK;
}

void mlc_array_free(mlc_array *a)
{
    if (a == NULL) {
        return;
    }
    if (a->owns_data && a->data != NULL) {
        free(a->data);
    }
    a->data = NULL;
    a->owns_data = 0;
    a->ndim = 0;
}

mlc_status mlc_array_view(mlc_array *out, const mlc_array *src)
{
    if (out == NULL || src == NULL) {
        return MLC_ERR;
    }
    *out = *src;
    out->owns_data = 0; /* 视图不拥有数据：释放它是调用方的错误 */
    return MLC_OK;
}

mlc_status mlc_array_require(const mlc_array *a, mlc_dtype dt, int32_t ndim)
{
    if (a == NULL) {
        return MLC_ERR;
    }
    if (a->dtype != dt || a->ndim != ndim) {
        return MLC_ERR;
    }
    return MLC_OK;
}
