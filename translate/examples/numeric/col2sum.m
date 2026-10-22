function y = col2sum(A)
% @m2c shape A 3,2
% @m2c shape y 1
% 第二列求和：列切片 + 归约（链式临时量）
y = sum(A(:,2));
end
