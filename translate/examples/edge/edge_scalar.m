function y = edge_scalar(a, b)
% 纯标量运算（最容易退化成数组的极限）
% @m2c i64 a
% @m2c i64 b
% @m2c i64 y
  y = a * b + (a - b);
end
