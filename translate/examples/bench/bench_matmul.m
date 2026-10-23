function y = bench_matmul(A, B)
% @m2c shape A 300,300
% @m2c shape B 300,300
% @m2c shape y 300,300
% 矩阵乘：Octave 走 BLAS，我们的 C 是朴素三重循环 —— 这里**预计会输**。
% 测它的意义不是赢，而是诚实地标出「哪类负载我们不如参考实现」。
y = A * B;
end
