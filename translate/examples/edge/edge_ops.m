function y = edge_ops(x)
% 算子密集（极限算子条数：加法/切片/拼接/转置/求和）
% @m2c shape x 4
% @m2c shape y 4
  a = x + 1;
  b = a(2:3);
  c = [b b];
  d = c';
  y = d(1:4);
end
