function y = combine(x)
% @m2c shape x 3
% @m2c shape y 3
% **跨文件调用**：addone 与 scale2 分别在别的 .m 里
y = addone(x);
y = scale2(y);
end
