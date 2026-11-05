function y = filla(k)
% @m2c shape k 1
% @m2c shape y 2,1
% ones/zeros 的**变量维度**：长度运行期才知道，走 OP-FILLA（不是 fill: 常量）
y = ones(2, k);
end
