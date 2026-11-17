function y = moving_avg(x, w)

% @m2c shape x 6
% @m2c i64 w
% @m2c shape y 6
% 长度 w 的滑动平均，边界处用原值（不是补零）。
n = length(x);
y = x;
for i = 1:n
  lo = i - w;
  if lo < 1
    lo = 1;
  end
  s = 0;
  k = lo;
  while k <= i
    s = s + x(k);
    k = k + 1;
  end
  y(i) = s / (i - lo + 1);
end
end
