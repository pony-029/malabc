function y = sumcols(A)
% @m2c shape A 2,3
% @m2c shape y 1,3
% MATLAB 的 sum(A) 沿**第一个非单例维**：2x3 -> 1x3（列和）。
% R593 修的正是这条语义（自动分配曾猜成 1x1，导致 MLC_ERR）。
y = sum(A);
end
