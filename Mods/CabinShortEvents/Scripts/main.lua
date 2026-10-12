local directory = assert(debug.getinfo(1,"S").source:match("^@(.+[/\\])"))
package.path = directory .. "?.lua;" .. package.path
local runtime = require("cabin_runtime")
local codec = require("cabin_codec")
local targets = require("targets")
local mod = runtime.start(directory,require("definition"))
require("cabin_host_settings").start(mod)
local rounds, announced = {}, {}
mod:bind("/Game/CabinGameContent/BoardGameStuff/Board/GameBoard_BP.GameBoard_BP_C:SetCurrentPlayerTurn",function(context)
    local board = context:get()
    if not runtime.valid(board) or not board:HasAuthority() then return end
    local world = board:GetWorld()
    local address = world:GetAddress()
    if not rounds[address] then
        rounds[address]={world=world,values=codec.copy(mod.store.values)}
        mod:log("info","host event settings frozen at first turn world=" .. address)
    end
end)
local function settings(actor)
    assert(runtime.valid(actor) and actor:HasAuthority(),"event target requires authority")
    local world = actor:GetWorld()
    assert(runtime.valid(world),"event world unavailable")
    local address = world:GetAddress()
    if not rounds[address] or not runtime.valid(rounds[address].world) then
        rounds[address] = {world=world,values=codec.copy(mod.store.values)}
        mod:log("info","host event settings captured for round world=" .. address)
    end
    return rounds[address].values
end
local function goal(actor,original,factor)
    local selected = settings(actor)
    local reduced = selected.enabled and targets.reduce(original,selected[factor]) or original
    local key = actor:GetAddress() .. ":" .. original .. ":" .. reduced
    if not announced[key] then
        announced[key] = true
        mod:log("info","event goal actor=" .. actor:GetFullName() .. " original=" .. original .. " target=" .. reduced)
    end
    return reduced
end
mod:bind("/Game/Cursed_Doll/AI_Stuff/ToyTrain/AIPawn_ToyTrain.AIPawn_ToyTrain_C:CabinShortEventGoal",function(context)
    local actor = context:get()
    if not actor:HasAuthority() then return 9 end
    return goal(actor,10,"train_factor")-1
end)
mod:bind("/Game/CabinGameContent/BoardGameStuff/Cards/EventCards/EC_RedBalloons.EC_RedBalloons_C:CabinShortEventGoal",function(context)
    local actor = context:get()
    if not actor:HasAuthority() then return actor.GoldBalloonNum end
    return goal(actor,actor.GoldBalloonNum,"balloon_factor")
end)
return mod
