function y = endsemi(x)
% @m2c shape x 4
% @m2c shape y 1
% 块结束符后带分号（`end;`）在真实工程里很常见（YALMIP 里 35 处）。
% 早先解析器只认裸 `end`，于是块深度不降 —— 后续语句会被嵌进错误的块。
y = 0;
if x(1) > 0
  y = 7;
else
  y = 3;
end;
end
