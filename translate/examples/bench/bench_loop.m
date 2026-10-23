function y = bench_loop(x)
% @m2c shape x 1000
% @m2c shape y 1
% 纯循环热点：200 x 1000 次「取元素 + 乘 + 累加」。
% 用来量「生成的 C」与「Octave 解释执行」的差距 —— 移植工具最该有的数字。
y = 0;
for k = 1:200
  for i = 1:1000
    y = y + x(i) * x(i);
  end
end
end
