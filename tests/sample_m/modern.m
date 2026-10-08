function y = modern(x, opts)
% MODERN 演示 arguments 参数验证块（R2019b+）与 end 索引运算符
arguments
    x (1,1) double = 0
    opts.scale (1,1) double = 1
end
n = numel(x);
y = x(end) * opts.scale + x(1:end-1);
end
