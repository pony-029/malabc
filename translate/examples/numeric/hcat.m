function y = hcat(a, b)
% @m2c shape a 2
% @m2c shape b 3
% @m2c shape y 5
% 水平拼接 `[a b]`：a=[1 2]、b=[1 2 3] -> [1 2 1 2 3]
% 只支持 1-D 水平拼接；`[a;b]`（竖直）会改变维度，实现里明确拒绝而不是猜。
y = [a b];
end
