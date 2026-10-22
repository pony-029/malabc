function y = relu(x)
% @m2c shape x 5
% 负值截断：用掩码构造（x(x<1) 语义不同，这里用 x>2 的同类写法）
y = x(x > 0);
end
