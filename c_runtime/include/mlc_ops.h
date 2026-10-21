/*
 * mlc_ops.h —— MATLAB 算子目录的 C 落点（R432 / P0）。
 *
 * 每个函数对应 `translate/operators.py` 里的一个算子 ID：
 *   OP-ADD   -> mlc_op_add      （元素级加，支持标量广播）
 *   OP-SUM   -> mlc_op_sum      （全归约）
 *   OP-INDEX -> mlc_op_index    （MATLAB 1-based -> C 0-based）
 *   OP-TRANSPOSE / OP-MATMUL   暂未实现，返回 MLC_UNIMPLEMENTED（**诚实边界**）
 *
 * 约定：`out` 由调用方用 `mlc_array_init` 初始化好 dtype/形状；
 * 算子只填数据，不接管所有权，也不重新分配。
 */
#ifndef MLC_OPS_H
#define MLC_OPS_H

#include "mlc.h"

#ifdef __cplusplus
extern "C" {
#endif

mlc_status mlc_op_add(const mlc_array *a, const mlc_array *b, mlc_array *out);
mlc_status mlc_op_sum(const mlc_array *a, mlc_array *out);
mlc_status mlc_op_index(const mlc_array *a, int64_t matlab_index,
                        mlc_array *out);
mlc_status mlc_op_transpose(const mlc_array *a, mlc_array *out);
mlc_status mlc_op_matmul(const mlc_array *a, const mlc_array *b,
                         mlc_array *out);

#ifdef __cplusplus
}
#endif

#endif /* MLC_OPS_H */
