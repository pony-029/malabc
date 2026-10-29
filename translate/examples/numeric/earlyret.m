function y = earlyret(x)
% @m2c shape x 4
% @m2c shape y 1
% return：提前结束函数（应保留 y=7，而不是继续走到 y=3）
y = 0;
if x(1) > 0
  y = 7;
  return
end
y = 3;
end
