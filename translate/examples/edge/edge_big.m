function y = edge_big(x)
% 大数组（n=200 极限尺寸）
% @m2c shape x 200
% @m2c shape y 1
  y = 0;
  for i = 1:200
    y = y + x(i);
  end
end
