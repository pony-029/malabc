function y = rng_demo()
% @m2c shape y 4
% 等差序列生成：`1:4` -> OP-RANGE（与 A(:,p:q) 的切片语义不同）。
% **两端都是字面量**，输出形状 4 在编译期就确定 —— 这是本用例能进
% numeric 语料的前提（`1:n` 那种运行期形状会被 C 侧按 "no shape" 跳过）。
y = 1:4;
end
