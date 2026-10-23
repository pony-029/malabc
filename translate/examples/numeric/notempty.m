function y = notempty(x)
% @m2c shape x 3
% @m2c shape y 1
% 取反的裸条件：~isempty(x) 为真时走 then
if ~isempty(x)
  y = x(1);
else
  y = 0;
end
end
