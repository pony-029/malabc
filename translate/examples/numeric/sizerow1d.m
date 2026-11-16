function n = sizerow1d(x)

% @m2c shape x 3
% @m2c shape n 1
% 一维输入取**第二维**长度：本运行时把一维数组当行向量（1×n），
% 所以 size(x,2) 必须给 3，而不是"维度超出 ndim 就给 1"。
%
% 这条语料是用来覆盖 `mlc_op_size_dim` 里 `ndim == 1` 那条分支的
% （R893 修过它与 `size_all` 的自相矛盾；R897 的覆盖率门因它掉档，
%  说明该分支此前没有用例走过）。
n = size(x, 2);
end
