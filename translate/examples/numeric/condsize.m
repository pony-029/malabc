function y = condsize(A)
% @m2c shape A 2,3
% @m2c shape y 1
% 条件**两侧都是调用**：if size(A,1) ~= size(A,2)
y = 0;
if size(A, 1) ~= size(A, 2)
  y = 1;
end
end
