function r = dot_norm(x)

% @m2c shape x 6
% @m2c shape r 1
% 欧氏范数：先平方和，再开方。
n = length(x);
s = 0;
for i = 1:n
  s = s + x(i) * x(i);
end
r = sqrt(s);
end
