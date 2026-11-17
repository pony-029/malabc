function g = grade(s)

% @m2c shape g 1
% @m2c i64 s
% 分数分级：switch/case 的典型用法。
switch s
  case 1
    g = 90;
  case 2
    g = 80;
  case 3
    g = 70;
  otherwise
    g = 60;
end
end
