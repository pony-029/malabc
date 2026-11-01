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

/* 分配/释放计数（只读观测）。 */
static int64_t g_alloc_n = 0;
static int64_t g_free_n = 0;

int64_t mlc_rt_alloc_count(void)
{
    return g_alloc_n;
}

int64_t mlc_rt_free_count(void)
{
    return g_free_n;
}

int64_t mlc_rt_alloc_balance(void)
{
    return g_alloc_n - g_free_n;
}


/* ===================== 静态内存池（嵌入式） ===================== */

typedef struct {
    int64_t size;      /* payload 字节数 */
    int64_t next;      /* 空闲链下一个块的 offset（-1 表示尾） */
} m2c_hdr;

#define M2C_HDR ((int64_t)sizeof(m2c_hdr))

static unsigned char *g_pool = NULL;
static int64_t g_pool_bytes = 0;
static int64_t g_pool_align = 8;
static int64_t g_pool_used = 0;      /* 已 bump 到的高度 */
static int64_t g_pool_peak = 0;
static int64_t g_free_head = -1;     /* 空闲链头 offset */

static int64_t m2c_align_up(int64_t n, int64_t a)
{
    if (a <= 1) {
        return n;
    }
    return ((n + a - 1) / a) * a;
}

mlc_status mlc_pool_configure(void *buf, int64_t bytes, int64_t align)
{
    if (buf == NULL || bytes <= 0) {
        return MLC_ERR;
    }
    if (align <= 0 || (align & (align - 1)) != 0) {
        return MLC_ERR;              /* 必须是 2 的幂 */
    }
    g_pool = (unsigned char *)buf;
    g_pool_bytes = bytes;
    g_pool_align = align;
    g_pool_used = 0;
    g_pool_peak = 0;
    g_free_head = -1;
    return MLC_OK;
}

void mlc_pool_reset(void)
{
    g_pool = NULL;
    g_pool_bytes = 0;
    g_pool_used = 0;
    g_pool_peak = 0;
    g_free_head = -1;
}

int mlc_pool_is_active(void)
{
    return g_pool != NULL;
}

int64_t mlc_pool_bytes_used(void)
{
    return g_pool_used;
}

int64_t mlc_pool_peak(void)
{
    return g_pool_peak;
}

int64_t mlc_pool_bytes_left(void)
{
    if (g_pool == NULL) {
        return 0;
    }
    return g_pool_bytes - g_pool_used;
}

/* 池内分配：first-fit 空闲链 -> 否则 bump。返回 payload 指针；失败 NULL。 */
static void *m2c_pool_alloc(int64_t n)
{
    int64_t prev = -1, cur = g_free_head;
    int64_t need;

    if (g_pool == NULL || n <= 0) {
        return NULL;
    }
    while (cur >= 0) {
        m2c_hdr *b = (m2c_hdr *)(void *)(g_pool + cur);
        if (b->size >= n) {
            /* 摘链，整块给出（不切分：切分要合并逻辑，这里刻意简化） */
            if (prev < 0) {
                g_free_head = b->next;
            } else {
                ((m2c_hdr *)(void *)(g_pool + prev))->next = b->next;
            }
            b->next = -1;
            return (void *)(g_pool + cur + M2C_HDR);
        }
        prev = cur;
        cur = b->next;
    }
    need = m2c_align_up(n, g_pool_align);
    if (g_pool_used + M2C_HDR + need > g_pool_bytes) {
        return NULL;                 /* 池耗尽：**不回退到堆** */
    }
    {
        m2c_hdr *b = (m2c_hdr *)(void *)(g_pool + g_pool_used);
        void *payload = g_pool + g_pool_used + M2C_HDR;
        b->size = n;
        b->next = -1;
        g_pool_used += M2C_HDR + need;
        if (g_pool_used > g_pool_peak) {
            g_pool_peak = g_pool_used;
        }
        return payload;
    }
}

static int m2c_pool_owns(const void *p)
{
    const unsigned char *q = (const unsigned char *)p;
    return g_pool != NULL && q >= g_pool && q < g_pool + g_pool_bytes;
}

static void m2c_pool_free(void *p)
{
    int64_t off;
    m2c_hdr *b;

    if (!m2c_pool_owns(p)) {
        return;
    }
    off = (int64_t)((unsigned char *)p - g_pool) - M2C_HDR;
    if (off < 0) {
        return;
    }
    b = (m2c_hdr *)(void *)(g_pool + off);
    b->next = g_free_head;
    g_free_head = off;
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
    if (g_pool != NULL) {
        /* 池已配置：只从池里取，**绝不回退到堆** */
        a->data = m2c_pool_alloc(n * esz);
        if (a->data == NULL) {
            return MLC_ERR;          /* 池耗尽 */
        }
        memset(a->data, 0, (size_t)(n * esz));
        a->owns_data = 1;
        return MLC_OK;               /* 池分配**不计入堆计数** */
    }
    a->data = calloc((size_t)n, esz);
    if (a->data == NULL) {
        return MLC_ERR;
    }
    a->owns_data = 1;
    g_alloc_n += 1;
    return MLC_OK;
}

void mlc_array_free(mlc_array *a)
{
    if (a == NULL) {
        return;
    }
    if (a->owns_data && a->data != NULL) {
        if (m2c_pool_owns(a->data)) {
            m2c_pool_free(a->data);
            a->data = NULL;
            a->owns_data = 0;
            return;
        }
        {
            free(a->data);
        }
        g_free_n += 1;
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
