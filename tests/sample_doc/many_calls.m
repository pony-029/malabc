function top(a)
% 反例语料：`step` 被 `top` 在 **9 个不同的行**上调用。
%
% 为什么必须分 9 行：`call_sites` **每个语句只记一次** ——
% `r = step(a)+step(a)+step(a)` 是**一个语句**，只记 1 个调用点；
% 而用 `...` 续行的三行也仍然是同一个语句，同样只记 1 个。
% （这一点本轮实测过两次：一行三次调用 → 1 处；三行续行 → 1 处。）
%
% 所以图上「调用自 3 4 5」说的是**语句数**，不是**调用次数**。
%
% 用途：关系图里 step 会显示「调用自 3 4 5 …」九个数，那一串会撑开
% 一行，所以展示层要截断并声明还剩几处；而**服务端不许截断**，
% 否则「还剩几处」这个数根本算不出来。
step(a);
step(a);
step(a);
step(a);
step(a);
step(a);
step(a);
step(a);
step(a);
end

function y = step(a)
% 被 top 调用 9 次；它自己又调用 leaf 一次
y = leaf(a) + 1;
end

function z = leaf(x)
% 这轮的观察目标：它的直接上游是 step，而 step 有 9 个调用点
z = x;
end
