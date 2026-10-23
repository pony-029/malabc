function y = bench_loop(x)
% @m2c shape x 1000
% @m2c shape y 1
% 纯循环热点：500 x 1000 次「取元素 + 乘 + 累加」。
%
% 注意：写成 `y = y + x(i) * x(i);` 是**三个操作数的嵌套式**，当前降级不支持，
% 会生成 unimplemented 桩 —— 那样 bench 测到的只是进程启动时间。
% 拆成两条语句，才是真实可执行的负载。
y = 0;
for k = 1:500
  for i = 1:1000
    t = x(i) * x(i);
    y = y + t;
  end
end
end
