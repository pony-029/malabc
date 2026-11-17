function d = spread(x)

% @m2c shape x 6
% @m2c shape d 1
% 极差：最大值减最小值（两个归约 + 一次减法）。
d = max(x) - min(x);
end
