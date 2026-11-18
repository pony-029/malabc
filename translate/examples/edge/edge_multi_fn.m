function [a, b, c] = edge_multi_fn(x)
% 一个文件里 5 个函数（多 MATLAB 函数 → 单个 .c）+ 多返回值
% @m2c shape x 4
% @m2c shape a 4
% @m2c shape b 1
% @m2c shape c 1
  a = helper_scale(x, 2);
  b = helper_sum(a);
  c = helper_max(a);
end

function y = helper_scale(x, k)
% @m2c shape x 4
% @m2c i64 k
% @m2c shape y 4
  y = x * k;
end

function s = helper_sum(x)
% @m2c shape x 4
% @m2c shape s 1
  s = sum(x);
end

function m = helper_max(x)
% @m2c shape x 4
% @m2c shape m 1
  m = max(x);
end
