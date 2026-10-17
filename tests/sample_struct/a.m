function y = build(a)
% 反例语料：结构体成员写入与读取
s.name = 'x';
s.count = a;
y = s.name;
y = y + s.count;
end
