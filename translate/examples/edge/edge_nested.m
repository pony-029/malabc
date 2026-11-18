function y = edge_nested(x)
% 三层嵌套 + 提前 return（极限控制流）
% @m2c shape x 4
% @m2c shape y 1
  y = 0;
  for i = 1:3
    for j = 1:2
      if x(i) > 0
        if x(j) >= 0
          y = y + x(i);
        else
          y = y - 1;
        end
      end
    end
  end
  if y > 100
    return;
  end
  y = y + 1;
end
