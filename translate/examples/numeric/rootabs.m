function y = rootabs(x)
% @m2c shape x 3
% @m2c shape y 3
% 逐元素标量函数：此前 sqrt(x) 会被当成"对名为 sqrt 的数组取下标"（静默误判）
y = sqrt(x);
end
