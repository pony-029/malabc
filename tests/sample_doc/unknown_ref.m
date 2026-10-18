function r = unknown_ref(a)
% 反例语料：下面提到 zzz_ghost —— 它从不被赋值、不被调用、
% 也不是参数或字段。悬停它时不许沉默，也不许说它是函数。
r = a;
end
