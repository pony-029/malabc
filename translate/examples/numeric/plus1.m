function y = plus1(x)
% @m2c shape x 3
% @m2c shape y 3
% 数组 + 标量字面量（const 临时量）：这条链本来就是通的，之前被误判为"形状推不出"
a = abs(x);
y = a + 1;
end
