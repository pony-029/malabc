function y = setdiff1(a, b)
% @m2c shape a 3
% @m2c shape b 2
% @m2c shape y 3
% 集合差：A 中元素去掉 B 里出现的，再**去重升序**（MATLAB setdiff 语义）
y = setdiff(a, b);
end
