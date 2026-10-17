function r = many_ext(a)
% 反例语料：7 个**互不相同**的、本库没有的名字。
% 存在的意义只有一个 —— 让「最多列 5 个」这条截断**被说出来**。
% 如果只列 5 个而不说还有几个，读者会以为一共就 5 个。
r = alpha_tool(a) + beta_tool(a) + gamma_tool(a) + delta_tool(a) ...
    + epsilon_tool(a) + zeta_tool(a) + eta_tool(a);
end
