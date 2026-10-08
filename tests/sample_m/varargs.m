function varargout = varargs(varargin)
% varargout/varargin 可变参数 + 可变长度输出生产形态样本
n = nargin;
for k = 1:n
    varargout{k} = varargin{k};
end
end
