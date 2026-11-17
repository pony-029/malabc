function y = orphan_use(x)

% @m2c shape x 6
% @m2c shape y 1
y = orphan_inner(x);
end

function r = orphan_inner(x)
% @m2c shape x 6
% @m2c shape r 1
r = numel(x);
end
