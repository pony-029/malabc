function [lo, hi] = twoout(x)
% @m2c shape x 4
% @m2c shape lo 1
% @m2c shape hi 1
% 多返回值：一次调用取两个输出
lo = min(x);
hi = max(x);
end
