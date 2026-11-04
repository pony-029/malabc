function y = idx2var(A, i, j)
% @m2c shape A 2,3
% @m2c shape i 1
% @m2c shape j 1
% @m2c shape y 1
% 二维变量下标 `A(i,j)`：线性下标公式早就对，但 `setb` 不收 f64 操作数，
% 于是整函数退化成桩。修好后 A(2,1) = 4。
y = A(i, j);
end
