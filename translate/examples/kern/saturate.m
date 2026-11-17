function y = saturate(x)

% @m2c shape x 6
% @m2c shape y 6
% 双侧饱和：正负各夹一次。
p = clip(x, 0, 3);
y = p;
end
