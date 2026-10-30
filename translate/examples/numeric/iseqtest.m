function y = iseqtest(x)
% @m2c shape x 4
% @m2c shape y 1
% isequal(a,b) 与 isequal(a,k)：前者同形逐元素比较，后者要求 a 是 1x1
y = 0;
if isequal(x, x)
  y = y + 1;
end
if isequal(x, 0)
  y = y + 10;
end
end
