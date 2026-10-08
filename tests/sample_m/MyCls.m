classdef MyCls
% 样例类，确保类 / 方法解析不崩溃
    properties
        val
    end
    methods
        function obj = MyCls(x)
            if nargin > 0
                obj.val = x;
            else
                obj.val = 0;
            end
        end
        function y = foo(obj, x)
            y = x * 2 + obj.val;
        end
    end
end
