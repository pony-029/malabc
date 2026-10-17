function y = x(a)
% 反例语料：b 从未定义就被读（F3 需要一条真的 uninitialized 告警）
y = a + b;
end
