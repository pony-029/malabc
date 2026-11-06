function y = oneslen(n)
% @m2c shape n 3
% @m2c shape y 3,1
% 维度来自**尺寸查询**：`ones(length(n),1)` —— YALMIP 里 `ones` 最常见的形态
y = ones(length(n), 1);
end
