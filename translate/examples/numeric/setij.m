function y = setij(A, i, j)
% @m2c shape A 2,3
% @m2c shape i 1
% @m2c shape j 1
% @m2c shape y 1
% 二维元素赋值（形状由注解给出），写后读回验证偏移换算
A(i, j) = 99;
y = A(i, j);
end
