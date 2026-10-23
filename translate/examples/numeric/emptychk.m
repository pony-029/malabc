function y = emptychk(x)
% @m2c shape x 3
% @m2c shape y 1
% 空数组 + isempty：A = [] 一定为空，所以走 then 分支
A = [];
if isempty(A)
  y = 1;
else
  y = 0;
end
end
