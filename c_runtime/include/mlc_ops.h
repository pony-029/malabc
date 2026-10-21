/*
 * mlc_ops.h —— MATLAB 算子目录的 C 落点（R432 / P0；R12 扩充）。
 *
 * 每个函数对应 `translate/operators.py` 里的一个算子 ID：
 *   OP-ADD / OP-SUB / OP-MUL / OP-DIV   -> 元素级四则（支持标量广播）
 *   OP-SUM / OP-MEAN / OP-MAX / OP-MIN  -> 全归约
 *   OP-INDEX                            -> MATLAB 1-based -> C 0-based
 *   OP-TRANSPOSE / OP-MATMUL            -> 暂未实现，返回 MLC_UNIMPLEMENTED
 *
 * 约定：`out` 由调用方用 `mlc_array_init` 初始化好 dtype/形状；
 * 算子只填数据，不接管所有权，也不重新分配。
 * 空输入：四则/归约返回 MLC_ERR（**不返回一个看起来对的 0/NaN**）。
 */
#ifndef MLC_OPS_H
#define MLC_OPS_H

#include "mlc.h"

#ifdef __cplusplus
extern "C" {
#endif

mlc_status mlc_op_add(const mlc_array *a, const mlc_array *b, mlc_array *out);
mlc_status mlc_op_sub(const mlc_array *a, const mlc_array *b, mlc_array *out);
mlc_status mlc_op_mul(const mlc_array *a, const mlc_array *b, mlc_array *out);
mlc_status mlc_op_div(const mlc_array *a, const mlc_array *b, mlc_array *out);

mlc_status mlc_op_sum(const mlc_array *a, mlc_array *out);
mlc_status mlc_op_mean(const mlc_array *a, mlc_array *out);
mlc_status mlc_op_max(const mlc_array *a, mlc_array *out);
mlc_status mlc_op_min(const mlc_array *a, mlc_array *out);

/* 切片 `x(from:to)`：1-based **闭区间**，仅 1-D。
   二维的 `x(1:2)` 在 MATLAB 里是**线性索引**（列优先），语义不同，
   所以这里明确拒绝 2-D —— 不猜。 */
mlc_status mlc_op_slice(const mlc_array *a, int64_t from, int64_t to,
                        mlc_array *out);

mlc_status mlc_op_index(const mlc_array *a, int64_t matlab_index,
                        mlc_array *out);
mlc_status mlc_op_transpose(const mlc_array *a, mlc_array *out);
mlc_status mlc_op_matmul(const mlc_array *a, const mlc_array *b,
                         mlc_array *out);

#ifdef __cplusplus
}
#endif

#endif /* MLC_OPS_H */
