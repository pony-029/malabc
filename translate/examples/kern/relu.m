function y = relu(x)

% @m2c shape x 6
% @m2c shape y 6
% 单边整流：负数归零。
y = x;
for i = 1:6
  if x(i) < 0
    y(i) = 0;
  end
end
end
