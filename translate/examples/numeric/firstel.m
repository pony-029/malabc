function y = firstel(x)
% @m2c shape x 3
% @m2c shape y 1
% 裸条件 + isempty：空则 0，否则取首元素
if isempty(x)
  y = 0;
else
  y = x(1);
end
end
