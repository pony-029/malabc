function y = addone(x)
% @m2c shape x 3
% @m2c shape y 3
% 元素级：y = x + x
y = x + x;
end

function z = pick(v, i)
% @m2c shape v 3
% @m2c shape z 1
% @m2c i64 i
% 下标（1-based 由 mlc_op_index 负责换成 0-based）
z = v(i);
end

function s = sumall(v)
% @m2c shape v 3
% @m2c shape s 1
% 归约
s = sum(v);
end

function [y, s] = add_and_sum(x)
% @m2c shape x 3
% @m2c shape y 3
% @m2c shape s 1
% 多返回值：每个返回值各自有形状
y = x + x;
s = sum(x);
end

function r = pickbig(v, i)
% @m2c shape v 3
% @m2c shape r 1
% @m2c i64 i
% 分支：i > 1 取单个元素，否则求和
if i > 1
r = v(i);
else
r = sum(v);
end
end

function r = lastpick(v, i)
% @m2c shape v 3
% @m2c shape r 1
% @m2c i64 i
% 循环 + 标量赋值：把下标递减到 1，再取第一个元素
while i > 1
i = i - 1;
end
r = v(i);
end

function s = viasum(v)
% @m2c shape v 3
% @m2c shape s 1
% 调用同文件里的另一个生成函数（不是算子）
s = sumall(v);
end

function r = accumlast(v)
% @m2c shape v 3
% @m2c shape r 1
% 数组累加：循环里把 v(1) 加到 r 上（验证"表达式降级"：取元素 + 相加两条语句）
r = sum(v);
for k = 1:2
r = r + v(1);
end
end

function r = scale(v)
% @m2c shape v 3
% @m2c shape r 3
% 立即数：MATLAB 里标量就是 1x1 数组，所以 r = v * 2 是元素级缩放
r = v * 2;
end

function r = zerosum(v)
% @m2c shape v 3
% @m2c shape r 1
% 多维常量：zeros(1,3) 是 1x3 的矩阵；两侧都是归约调用
z = zeros(1,3);
r = sum(z) + sum(v);
end

function C = mm(A, B)
% @m2c shape A 2,3
% @m2c shape B 3,2
% @m2c shape C 2,2
% 矩阵乘：MATLAB 的 `*` 不是元素级（`.*` 才是）
C = A * B;
end

function y = repeater(x)
% @m2c shape x 3
% @m2c shape y 3
% 循环：同一语句执行 3 次（用来证明 for 真的被发射）
for k = 1:3
y = x + x;
end
end

function y = fancy(x)
% @m2c shape x 1,3
% @m2c shape y 3,1
% 转置：2-D 才成立（1-D 会被 C 侧拒绝 —— 那是语义，不是缺陷）
y = x';
end

function y = slicer(x)
% @m2c shape x 3
% @m2c shape y 2
% 负面夹具：切片 x(1:2) 尚未支持 -> 必须返回 unimplemented（不能返回垃圾值）
y = x(1:2);
end
