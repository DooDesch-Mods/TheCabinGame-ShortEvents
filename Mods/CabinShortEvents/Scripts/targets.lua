local M = {}
function M.reduce(original,factor)
    assert(math.type(original)=="integer" and original>=1,"original task target must be positive")
    assert(type(factor)=="number" and factor>0 and factor<=1,"task factor must be greater than 0 and at most 1")
    return math.max(1,math.ceil(original*factor))
end
return M
