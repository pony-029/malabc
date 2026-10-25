function y = trigfns(x)
% @m2c shape x 3
% @m2c shape y 3
% 逐元素族扩展：sin/cos/tan/floor/ceil/round/log2/log10
a = sin(x);
y = floor(a * 10);
end
