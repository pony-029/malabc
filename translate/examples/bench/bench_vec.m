function y = bench_vec(x)
% @m2c shape x 1000
% @m2c shape y 1
% 向量化写法：与 bench_loop 做同样的事，但不写循环。
% 真实 MATLAB 代码多半长这样 —— 用它看「循环热点」与「向量化」的差距差多少。
y = sum(x .* x);
end
