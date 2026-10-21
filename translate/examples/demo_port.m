function y = addone(x)
% 加法（已映射）
y = x + x;
end

function z = pick(v, i)
% @m2c i64 i
% 下标（索引基准由 C 侧 mlc_op_index 负责 -1）
z = v(i);
end

function s = sumall(v)
% 归约
s = sum(v);
end

function y = fancy(x)
% 故意未映射：转置与矩阵乘仍是诚实边界
y = x';
end
