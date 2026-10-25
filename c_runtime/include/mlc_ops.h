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

/* `A(:)`：按**列优先**展平成 1-D（MATLAB 的线性索引顺序）。
   与"按内存顺序 memcpy"不同 —— 行主序存储时必须换序。 */
mlc_status mlc_op_flatten(const mlc_array *a, mlc_array *out);

/* `x(x >k)`：取出满足条件的元素并**压实**。
   结果长度是**数据相关**的，所以 out 必须由调用方按声明的长度初始化；
   实际命中数与 out 长度不符时返回 MLC_ERR（不截断、不补零）。 */
mlc_status mlc_op_mask(const mlc_array *a, int cmp, double k,
                       mlc_array *out);

/* `x(x >k)` 的**动态形状**版本：长度由数据决定，算子自己分配 `out`。
   这是 ABI "算子只填数据、不重新分配" 的**唯一例外**，理由：
   长度是数据相关的，调用方无法预先给出正确形状。
   所有权：成功时 `out` 由调用方 `mlc_array_free`。 */
mlc_status mlc_op_mask_alloc(const mlc_array *a, int cmp, double k,
                             mlc_array *out);

/* `find(x >k)`：返回满足条件的**1-based 下标**（长度数据相关 -> 由本函数分配）。
   与 mlc_op_mask 一样是 ABI 的分配例外；所有权转交调用方。 */
mlc_status mlc_op_find_alloc(const mlc_array *a, int cmp, double k,
                             mlc_array *out);

/* y(i) = v：把 a 的第 i 个元素（1-based）写成 v[0]。
 * 就地修改 a —— 它是**目标数组**，不是新分配的产物。 */
mlc_status mlc_op_setidx(mlc_array *a, const mlc_array *v, int64_t i);

/* y = A(i,:)：取第 i 行（1-based）。按 strides 拷，不假设存储顺序。 */
mlc_status mlc_op_row(const mlc_array *a, int64_t row, mlc_array *out);

/* col(a, j)：取第 j 列（1 起），输出一维、长度 = 行数。 */
mlc_status mlc_op_col(const mlc_array *a, int64_t j,
                      mlc_array *out);

/* size(x, dim)：第 dim 维的长度，写进 1x1 输出（dim 从 1 起）。 */
mlc_status mlc_op_size_dim(const mlc_array *a, int64_t dim,
                           mlc_array *out);

/* numel(x) / length(x)：标量结果写进 1x1 输出。 */
mlc_status mlc_op_numel(const mlc_array *a, mlc_array *out);
mlc_status mlc_op_length(const mlc_array *a, mlc_array *out);

/* isempty(x)：空数组返回 1，否则 0（输出必须是 1x1）。 */
mlc_status mlc_op_isempty(const mlc_array *a, mlc_array *out);

mlc_status mlc_op_index(const mlc_array *a, int64_t matlab_index,
                        mlc_array *out);
mlc_status mlc_op_transpose(const mlc_array *a, mlc_array *out);
mlc_status mlc_op_matmul(const mlc_array *a, const mlc_array *b,
                         mlc_array *out);

#ifdef __cplusplus
}
#endif

#endif /* MLC_OPS_H */
