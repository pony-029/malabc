function y = nzcount(x)
% @m2c shape x 4
% @m2c shape y 1
% nnz：非零个数（此前被判成"对名为 nnz 的数组取下标"）
y = nnz(x);
end
