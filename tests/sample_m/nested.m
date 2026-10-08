function y = nested(x)
% NESTED 演示嵌套函数：父函数 body 应延伸到其 end，内层 inner 之后的 tail 调用不应漏检
    y = inner(x);
    function z = inner(v)
        z = v + 1;
    end
    y = y + tail(x);
end

function w = tail(v)
w = v * 2;
end
