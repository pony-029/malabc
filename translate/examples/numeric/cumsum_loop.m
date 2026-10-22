function y = cumsum_loop(x)
% @m2c shape x 4
% @m2c shape y 4
% 前缀和（典型数值核）：需要**数组元素赋值** y(i) = ...
y = zeros(1,4);
for i = 1:4
  y(i) = x(i);
end
end
