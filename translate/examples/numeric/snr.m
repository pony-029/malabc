function y = snr(sig, noise)
% @m2c shape sig 4
% @m2c shape noise 4
% @m2c shape y 1
% 信噪比（dB）。R594 的端到端演示，现固化成语料：
% 它压住「二元形状求解 + 逐元素乘 + 归约 + 标量链 + 条件」这一整条链路。
s2 = sig .* sig;
n2 = noise .* noise;
ms = mean(s2);
mn = mean(n2);
r = ms / mn;
y = 10 * log10(r);
if y < 0
  y = 0;
end
end
