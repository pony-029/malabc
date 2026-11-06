function y = vcat2(a, b)
% @m2c shape a 2,2
% @m2c shape b 1,2
% @m2c shape y 3,2
% 竖直拼接：列数必须相同，行数相加（1-D 按 1×n 行处理）
y = [a; b];
end
