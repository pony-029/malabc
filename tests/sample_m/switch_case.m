function y = switch_case(x, A, B)
% switch 多分支 + end 复杂索引 + try/catch 生产形态样本
switch x
    case 1
        y = A(end, :);
    case 2
        y = B{end};
    case 3
        y = A(1:end-1);
    otherwise
        try
            y = A(end).field;
        catch
            y = 0;
        end
end
end
