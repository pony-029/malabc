function y = userange(x)
% @m2c shape x 4
% @m2c shape y 1
% 多返回调用的使用侧：`[lo,hi] = twoout(x)` 后算极差
[lo, hi] = twoout(x);
y = hi - lo;
end
