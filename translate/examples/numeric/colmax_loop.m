function y = colmax_loop(A)
% @m2c shape A 3,2
% @m2c shape y 1
% 条件里用二维下标：手写求第二列最大值
y = A(1,2);
for i = 2:3
  if A(i,2) > y
    y = A(i,2);
  end
end
end
