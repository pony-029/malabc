function top(a)
% 反例语料：`step` 被 `top` 在 **9 个不同的行**上调用。
%
% 为什么必须分 9 行：`call_sites` 按行去重 —— 一行里写三次
% `step(a)+step(a)+step(a)` 只记 1 个调用点。这一点本轮实测过。
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
