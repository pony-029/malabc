function y = lerp(a, b, t)

% @m2c shape y 1
% 线性插值，t 越界时夹紧（真实代码通常这么做）。
if t < 0
  y = a;
elseif t > 1
  y = b;
else
  y = a + (b - a) * t;
end
end
