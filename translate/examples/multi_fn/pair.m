function y = pair(x)

% @m2c shape x 6
% @m2c shape y 1
a = twice(x);
y = dot2(a);
end

function y = twice(x)
% @m2c shape x 6
% @m2c shape y 6
y = x;
for i = 1:6
  y(i) = x(i) * 2;
end
end

function r = dot2(x)
% @m2c shape x 6
% @m2c shape r 1
s = 0;
for i = 1:6
  s = s + x(i) * x(i);
end
r = s;
end
