/*
 * mlc.h —— MATLAB → C 移植的**唯一 ABI 契约**（R432 / P0）。
 *
 * 设计纪律（与仓库既有纪律一致）：
 *   1. 对外函数**不得**出现裸 `double *` / `float *`；一律走 `mlc_array`。
 *   2. 返回值一律 `mlc_status`：0=OK / 1=ERR / 2=UNIMPLEMENTED。
 *      **绝不返回一个“看起来对”的值**（沿用 malabc-rt 的 0/1/2 约定）。
 *   3. 谁分配谁释放：`owns_data=1` 才由 `mlc_array_free` 释放；
 *      `mlc_array_view` 产出的视图 `owns_data=0`，**不得**被释放。
 *   4. 形状/步长用 `int64_t`，步长单位是**元素**（不是字节），行主序。
 *
 * 这个头文件是 C 侧适配器（`translate/adapters.py` 生成）与算子实现
 * （`c_runtime/src/mlc_ops.c`）的共同落点。没有它，移植代码无处安放。
 */
#ifndef MLC_H
#define MLC_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MLC_ABI_VERSION 1
#define MLC_MAX_DIMS 8

/* 退出码：与 Python CLI / Rust 骨架保持同一套语义。 */
typedef enum {
    MLC_OK = 0,
    MLC_ERR = 1,
    MLC_UNIMPLEMENTED = 2
} mlc_status;

/* 只收录 MATLAB 默认数值类型与常用整型；新增必须同步 translate/adapters.py。 */
typedef enum {
    MLC_F64 = 1,
    MLC_F32 = 2,
    MLC_I64 = 3,
    MLC_I32 = 4,
    MLC_U8 = 5,
    MLC_BOOL = 6
} mlc_dtype;

/*
 * 数组视图。`strides` 以**元素**为单位；行主序时最后一维步长为 1。
 * `owns_data` 只描述 `data` 是否由本结构负责释放，不描述别名关系。
 */
typedef struct {
    void *data;
    mlc_dtype dtype;
    int32_t ndim;
    int64_t shape[MLC_MAX_DIMS];
    int64_t strides[MLC_MAX_DIMS];
    int32_t owns_data;
} mlc_array;

const char *mlc_status_string(mlc_status st);
size_t mlc_dtype_size(mlc_dtype dt);

/* 元素总数；维度非法/溢出返回 -1（调用方必须检查）。 */
int64_t mlc_array_numel(const mlc_array *a);

/* 分配并零初始化；失败返回 MLC_ERR，不改动已分配内存。 */
mlc_status mlc_array_init(mlc_array *a, mlc_dtype dt, int32_t ndim,
                          const int64_t *shape);
void mlc_array_free(mlc_array *a);

/* 浅视图：不拷贝、不拥有；用于把子块传给算子。 */
mlc_status mlc_array_view(mlc_array *out, const mlc_array *src);

/* 适配器前置校验：类型/维度必须精确匹配，否则 MLC_ERR。 */
mlc_status mlc_array_require(const mlc_array *a, mlc_dtype dt, int32_t ndim);

#ifdef __cplusplus
}
#endif

#endif /* MLC_H */
