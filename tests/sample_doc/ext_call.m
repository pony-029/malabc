function r = ext_call(a)
% 反例语料：调用一个本库没有、也不是内置的函数。
% 这种 name(...) 看着像调用，但 F12 不该沉默 —— 它要说清「本库没有定义」。
r = some_toolbox_fn(a) + 1;
end
