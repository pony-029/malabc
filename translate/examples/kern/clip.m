function y = clip(x, lo, hi)

% @m2c shape x 6
% @m2c i64 lo
% @m2c i64 hi
% 逐元素截断到 [lo, hi]。真实代码里到处都有它。
n = length(x);
y = x;
for i = 1:n
  if x(i) < lo
    y(i) = lo;
  elseif x(i) > hi
    y(i) = hi;
  end
end
end
