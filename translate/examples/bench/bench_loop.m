function y = bench_loop(x)
% @m2c shape x 1000
% @m2c shape y 1
% 纯循环热点：500 x 1000 次「取元素 + 乘 + 累加」。
% 工作量要足够大，否则进程启动与调度噪声会盖过真实差异。
y = 0;
for k = 1:500
  for i = 1:1000
    y = y + x(i) * x(i);
  end
end
end
