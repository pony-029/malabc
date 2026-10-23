% matlab_baseline.m —— 在 **MATLAB**（不是 Octave）里跑同一批负载，得到 JIT 基线。
%
% 为什么需要它：仓库里的 tools/bench.py 只能对照 Octave（解释执行），
% 而 MATLAB 有 JIT，循环类负载的差距会**小很多**。不说清这一点，
% 「59×」「15×」这类数字会被误读成「相对 MATLAB 也这么快」。
%
% 用法：把本文件所在目录加入 path，然后
%     >> matlab_baseline
% 把输出的毫秒数填回 tools/bench.py 的报告表里，就能得到「C 相对 MATLAB」的比值。

more off;
x  = reshape(1:1000, [1000, 1]);      % bench_loop / bench_vec 的输入
xs = reshape(1:200000, [200000, 1]);  % bench_sum 的输入
A  = reshape(1:90000, [300, 300]);    % bench_matmul 的输入
B  = A;

% 预热（让 JIT 有机会编译，避免把首轮解释执行算进去）
bench_loop(x); bench_vec(x); bench_sum(xs); bench_matmul(A, B);

cases = { ...
    'bench_loop',  @() bench_loop(x); ...
    'bench_vec',   @() bench_vec(x); ...
    'bench_sum',   @() bench_sum(xs); ...
    'bench_matmul',@() bench_matmul(A, B)};

fprintf('%-14s %12s %12s\n', 'case', 'best(ms)', 'median(ms)');
for k = 1:size(cases, 1)
    f = cases{k, 2};
    ts = zeros(1, 5);
    for r = 1:5
        t0 = tic; f(); ts(r) = toc(t0) * 1000;
    end
    ts = sort(ts);
    fprintf('%-14s %12.2f %12.2f\n', cases{k, 1}, ts(1), ts(3));
end
