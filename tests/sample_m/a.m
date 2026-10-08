function y = a(x)
% 入口函数，调用 b 与 c；b 又回调用 a（形成循环调用）
y = b(x) + c(x);
end

function z = b(x)
% 被 a 调用，但内部又调用 a（循环）
z = a(x) + 1;
end

function w = c(x)
% 被 a 调用，跨文件调用 d.m 中的 d
w = d(x) * 2;
end
