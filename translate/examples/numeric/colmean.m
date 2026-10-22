function y = colmean(A)
% @m2c shape A 3,2
% @m2c shape y 3
% 取第一列的均值：需要**二维冒号切片** A(:,1)
y = A(:,1);
end
