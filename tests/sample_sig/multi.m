function [alpha, beta] = ...
    multi(first, second, ...
          third)
% 多行函数签名：参数分布在三行上
alpha = first + second;
beta = third;
end

function single(a, b)
% 单行签名，作为对照
c = a + b;
end
