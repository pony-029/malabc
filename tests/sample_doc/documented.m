function y = documented(x, n)
% 计算 x 的 n 次方。
% Input:
%   x    double   底数，标量或数组
%   n    int      指数，正整数
% Output:
%   y    double   结果，与 x 同尺寸
y = x .^ n;
end

function z = no_doc(a, b)
% 这个函数没有参数表，只有一句描述。
z = a + b;
end
