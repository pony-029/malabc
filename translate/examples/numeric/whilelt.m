function y = whilelt(x)
% @m2c shape x 3
% @m2c shape y 1
% while 严格小于 + 每轮重算累乘（同时压住「标量变量参与乘法」这条路径）
y = 1;
i = 1;
while i < 4
  y = y * i;
  i = i + 1;
end
end
