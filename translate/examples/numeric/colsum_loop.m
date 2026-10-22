function y = colsum_loop(A)
% @m2c shape A 3,2
% @m2c shape y 1
% 循环 + 二维下标（表达式里）+ 标量累加
y = 0;
for i = 1:3
  y = y + A(i,2);
end
end
