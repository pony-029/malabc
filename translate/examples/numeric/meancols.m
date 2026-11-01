function y = meancols(A)
% @m2c shape A 2,3
% @m2c shape y 1,3
% R597：`mean` 的 2-D 语义与 `sum` 统一为**列归约**（2x3 -> 1x3）。
% 此前它走"全元素归约"（恒 1x1），与 `sum` 不一致 —— 差分测试抓到的正是这处。
y = mean(A);
end
