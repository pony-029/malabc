function r = pipeline(x)

% @m2c shape x 6
% @m2c shape r 1
% 三级流水线：滑动平均 -> 截断 -> 范数。真实工程里最常见的组合。
a = moving_avg(x, 2);
b = clip(a, 0, 4);
r = dot_norm(b);
end
