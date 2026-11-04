function [y, g] = fir_lp(x, h, k)
% @m2c shape x 4
% @m2c shape h 3
% @m2c shape k 1
% @m2c shape y 1
% @m2c shape g 3
% FIR 低通 + 增益估计（真实信号处理里最常见的两段）
%   y = 当前输出的归一化幅值
%   g = 每级抽头的贡献（h .* x 的三元切片）
acc = 0;
i = 1;
while i <= 1
  seg = x(i:i+2);
  g = h .* seg;
  acc = sum(g);
  i = i + 1;
end
e = abs(acc);
y = e / (abs(k) + 1);
end
