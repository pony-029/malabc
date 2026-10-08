function y = callbacks(c)
% CALLBACKS 演示 cellfun 字符串回调、函数句柄与 feval/str2func 动态调用
y1 = cellfun('isempty', c);
y2 = cellfun(@process, c);
y3 = feval('process', c);
y4 = str2func('process');
y = y1 + y2 + y3 + y4;
end

function z = process(v)
z = sum(v);
end
