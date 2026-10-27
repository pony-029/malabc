function y = forlen(x)
% @m2c shape x 4
% @m2c shape y 1
% for 上界是调用：for i = 1:length(x)（此前整条 for 进 unmapped）
y = 0;
for i = 1:length(x)
  y = y + 1;
end
end
