function v = addtwo(a, b)
% 两个数组入参都要拿到默认形状 [4]（此前只有第一个有，其余是 ndim 0 的空数组）
v = a + b;
end
