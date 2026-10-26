function y = findnz(x)
% @m2c shape x 4
% find(x)：非零元素的 1-based 下标（此前被误判成"对名为 find 的数组取下标"）
y = find(x);
end
