function y = while_acc(x)
% @m2c shape x 4
% @m2c shape y 1
% while 累积：迭代解法里最常见的形状
y = 0;
i = 1;
while i <= 4
  y = y + x(i);
  i = i + 1;
end
end
