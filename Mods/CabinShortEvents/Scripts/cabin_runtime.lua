local storage = require("cabin_store")
local registry = require("cabin_registry")
local M = {}
function M.valid(object) return object and object:IsValid() end
function M.start(directory,definition)
    local self = {definition=definition,hooks={},observers={}}
    function self:log(level,message) print("[" .. definition.name .. "] " .. level .. ": " .. message .. "\n") end
    local log = function(level,message) self:log(level,message) end
    self.store = storage.new(directory .. "settings.dat",definition.fields,log)
    self.registry = registry.new(ModRef,log)
    _G.CabinModSettingsV1 = self.registry
    if definition.register~=false then self.registry:register(definition,{
        read=function() return self.store:read() end,
        apply=function(values,action)
            if self.apply then return self.apply(values,action) end
            assert(action == "","this mod has no settings actions")
            return self.store:save(values)
        end,
    }) end
    function self:bind(path,callback,phase)
        assert(not self.hooks[path],"duplicate hook: " .. path)
        self.hooks[path] = {callback=callback,bound=false,phase=phase or "post"}
    end
    function self:observe(name,callback)
        assert(not self.observers[name],"duplicate observer")
        self.observers[name] = {callback=callback,failed=false}
    end
    function self:tick()
        assert(IsInGameThread(),"runtime callback outside game thread")
        self.registry:poll()
        for path,hook in pairs(self.hooks) do
            if not hook.bound and not hook.failed and M.valid(StaticFindObject(path)) then
                local ok,cause = pcall(function()
                    local callback = function(...)
                        local result = table.pack(xpcall(hook.callback,debug.traceback,...))
                        if not result[1] then
                            log("error","hook " .. path .. ": " .. tostring(result[2]))
                            error(result[2])
                        end
                        return table.unpack(result,2,result.n)
                    end
                    local first,second
                    if path:sub(1,8)=="/Script/" and hook.phase=="post" then
                        first,second = RegisterHook(path,function() end,callback)
                    else first,second = RegisterHook(path,callback) end
                    assert(type(first)=="number" and type(second)=="number","hook registration IDs unavailable")
                    hook.ids,hook.bound = {first,second},true
                    log("info","hook bound: " .. path)
                end)
                if not ok then hook.failed=true; log("error","bind " .. path .. ": " .. tostring(cause)) end
            end
        end
        for name,observer in pairs(self.observers) do
            if not observer.failed then
                local ok,cause = xpcall(observer.callback,debug.traceback)
                if not ok then observer.failed=true; log("error","observer " .. name .. " stopped: " .. tostring(cause)) end
            end
        end
    end
    assert(type(LoopInGameThreadWithDelay)=="function" and type(IsValidDelayedActionHandle)=="function","required pinned UE4SS delayed-action API missing")
    self.handle = LoopInGameThreadWithDelay(100,function() self:tick() end)
    assert(math.type(self.handle)=="integer" and self.handle>0 and IsValidDelayedActionHandle(self.handle),"mod poll registration unconfirmed")
    log("info","registered settings schema 1; gameplay acceptance pending")
    return self
end
return M
