function y = findeq(a, b)
% @m2c shape a 4
% @m2c shape b 4
% find(a == b)：逐元素比较两个**数组**（不是 a 对 b[0]）
y = find(a == b);
end
