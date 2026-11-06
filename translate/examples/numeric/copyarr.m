function y = copyarr(A)
% @m2c shape A 3
% @m2c shape y 3
% 整体拷贝：此前直接退化成桩（生成端只处理标量赋值）
y = A;
end
