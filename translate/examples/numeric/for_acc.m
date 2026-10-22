function y = for_acc(x)
% @m2c shape x 4
% @m2c shape y 1
% for 累积（标量累加器 + 下标取值）
y = 0;
for i = 1:4
  y = y + x(i);
end
end
