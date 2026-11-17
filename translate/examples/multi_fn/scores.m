function y = scores(x)

% @m2c shape x 6
% @m2c shape y 6
% 主函数 + 4 个局部函数，全部在同一个文件里（真实工程的常态）。
a = normalize(x);
b = scale(a);
c = shift(b);
y = clamp(c);
end

function y = normalize(x)
% @m2c shape x 6
% @m2c shape y 6
n = length(x);
s = 0;
for i = 1:n
  s = s + x(i) * x(i);
end
r = sqrt(s);
y = x;
for i = 1:n
  y(i) = x(i) / r;
end
end

function y = scale(x)
% @m2c shape x 6
% @m2c shape y 6
y = x;
for i = 1:6
  y(i) = x(i) * 2;
end
end

function y = shift(x)
% @m2c shape x 6
% @m2c shape y 6
y = x;
for i = 1:6
  y(i) = x(i) + 1;
end
end

function y = clamp(x)
% @m2c shape x 6
% @m2c shape y 6
y = x;
for i = 1:6
  if x(i) > 1
    y(i) = 1;
  end
end
end
