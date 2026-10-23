function y = bench_sum(x)
% @m2c shape x 200000
% @m2c shape y 1
% 大数组归约：Octave 的 sum 是编译好的内建，我们的是朴素单循环。
% 两者都"向量化"，这条用来量「内存带宽型负载」的差距。
y = sum(x);
end
