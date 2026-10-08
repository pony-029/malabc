function out = parallel(x)
% parfor 并行块 + 数组索引生产形态样本
out = zeros(size(x));
parfor i = 1:numel(x)
    out(i) = x(i) * 2;
end
end
