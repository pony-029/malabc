function y = shadowij(i, j)
% @m2c shape i 1
% @m2c shape j 1
% @m2c shape y 1
% 参数名取 `i`/`j`：生成器的 driver 曾用 `int64_t i` 作循环变量，
% 与参数同名遮蔽 -> `&i` 变成 int64_t* -> 整个生成工程编译不过。
% 这条语料就是那个缺陷的回归锁（修好前它直接编译失败）。
y = i + j;
end
