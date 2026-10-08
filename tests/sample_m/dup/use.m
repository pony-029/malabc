function y = use(x)
% USE 调用同名函数 duplicate，按「同文件 → 同目录 → 其余」就近解析到同目录 first.m
y = duplicate(x);
end
