function y = col1(A)
% @m2c shape A 2,3
% @m2c shape y 2
% A(:,2)：取第 2 列（此前只有 A(i,:) 行切片）
y = A(:, 2);
end
