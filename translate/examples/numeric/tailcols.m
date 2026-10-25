function y = tailcols(A)
% @m2c shape A 2,3
% A(:,2:end)：最常见的切片写法之一（end 的长度只有运行期知道）
y = A(:, 2:end);
end
