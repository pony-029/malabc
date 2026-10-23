function y = bench_null(A, B)
% @m2c shape A 300,300
% @m2c shape B 300,300
% @m2c shape y 300,300
% 空载对照：与 bench_matmul 完全相同的输入构造与内存分配，但只做一次逐元素加。
% 用来把「构造输入 + 启动」的成本从被测用例里扣掉 —— 否则测的是管线开销，不是矩阵乘。
y = A + B;
end
