function y = while2d(A)
% @m2c shape A 3,2
% @m2c shape y 1
% while 条件里用二维下标：累加第二列直到超过阈值
y = 0;
i = 1;
while A(i,2) <= 4
  y = y + A(i,2);
  i = i + 1;
end
end
