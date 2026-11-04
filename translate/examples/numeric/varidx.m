function y = varidx(x, k)
% @m2c shape x 4
% @m2c shape k 1
% @m2c shape y 1
% 下标是**变量**（`x(k)`）：此前被误判成"未知函数调用"，整条进 unmapped；
% 修好后走 OP-INDEX，索引由 f64 参数转成 i64 临时量。
y = x(k);
end
