"""Exercise async UFunction readiness before pinned UE4SS RegisterHook allocates refs."""
from pathlib import Path
import hashlib
import json
import unittest
from lupa.lua54 import LuaRuntime

REPO=Path(__file__).resolve().parents[1]
ROOT=REPO.parents[2]
SOURCE=REPO/'Mods/CabinShortEvents/Scripts/cabin_runtime.lua'
OUT=REPO/'dist/checks/hook-readiness'
OLD=ROOT/'Workspace/evidence/nexus-drafts/capture/all-mods-slider-labels1/ue4ss/Mods/CabinShortEvents/Scripts/cabin_runtime.lua'
FIXTURE=r'''
local runtimepath=...
logs,registrations,allocated_refs={},{},0
function print(message) logs[#logs+1]=message end
EObjectFlags={RF_NeedInitialization=0x200,RF_NeedLoad=0x400,RF_NeedPostLoad=0x1000,RF_NeedPostLoadSubobjects=0x2000}
local function object()
    local value={alive=true,flags=0}
    function value:IsValid() return self.alive end
    function value:HasAnyFlags(mask) return self.flags & mask~=0 end
    return value
end
outer=object();target=object();target.func=0
function target:GetOuter() return outer end
function StaticFindObject(path) return target end
function IsInGameThread() return true end
function LoopInGameThreadWithDelay(ms,callback) assert(ms==100);poll=callback;return 1 end
function IsValidDelayedActionHandle(id) return id==1 end
ModRef={}
package.loaded.cabin_store={new=function() return {read=function() return {},0 end} end}
package.loaded.cabin_registry={new=function() return {register=function() end,poll=function() end} end}
function RegisterHook(path,callback,post)
    allocated_refs=allocated_refs+1
    if target.func==0 then error("Was unable to register a hook with Lua function 'RegisterHook', information:\nFunctionName: "..path.."\nUFunction::Func: 0x0\nProcessInternal: 0x7ff7b77b11b0\nFUNC_Native: 0") end
    if reject_other then error('original unsupported hook failure') end
    registrations[#registrations+1]={path=path,callback=callback,post=post};return 5,5
end
runtime=assert(loadfile(runtimepath))()
mod=runtime.start('fixture/',{name='CabinShortEvents',id='cabin_short_events',fields={}})
path='/Game/Cursed_Doll/AI_Stuff/ToyTrain/AIPawn_ToyTrain.AIPawn_ToyTrain_C:CabinShortEventGoal'
mod:bind(path,function() return 6 end)
'''

class HookReadiness(unittest.TestCase):
    def vm(self,path=SOURCE):
        vm=LuaRuntime(unpack_returned_tuples=True);vm.execute(FIXTURE,path.as_posix());return vm

    @unittest.skipUnless(OLD.is_file(), 'sealed local baseline is absent; current readiness cases remain active')
    def test_original_race_disables_hook_permanently_after_allocating_ref(self):
        vm=self.vm(OLD)
        vm.execute("mod:tick();assert(mod.hooks[path].failed and allocated_refs==1 and #registrations==0);target.func=1;mod:tick();assert(#registrations==0 and allocated_refs==1)")

    def test_function_loading_waits_without_allocating_refs_then_binds_once(self):
        vm=self.vm()
        vm.execute("target.flags=EObjectFlags.RF_NeedLoad|EObjectFlags.RF_NeedPostLoad;for i=1,100 do mod:tick() end;assert(allocated_refs==0 and #registrations==0 and not mod.hooks[path].failed and mod.hooks[path].waiting_count==100);target.flags=0;target.func=1;mod:tick();for i=1,5 do mod:tick() end;assert(#registrations==1 and allocated_refs==1 and mod.hooks[path].bound and registrations[1].callback()==6);local waits,recovery=0,0;for _,line in ipairs(logs) do if line:find('bind waiting:',1,true) then waits=waits+1 end;if line:find('readiness recovered:',1,true) then recovery=recovery+1 end end;assert(waits==1 and recovery==1)")

    def test_outer_postload_and_reason_changes_wait_without_new_hook_refs(self):
        vm=self.vm()
        vm.execute("target.flags=EObjectFlags.RF_NeedInitialization;mod:tick();target.flags=0;outer.flags=EObjectFlags.RF_NeedPostLoadSubobjects;for i=1,3 do mod:tick() end;assert(allocated_refs==0 and mod.hooks[path].waiting_reason=='outer load/postload pending');outer.flags=0;target.func=1;mod:tick();assert(#registrations==1 and allocated_refs==1 and mod.hooks[path].waiting_count==4)")

    def test_func_zero_after_loading_clear_is_terminal_without_blind_retry(self):
        vm=self.vm()
        vm.execute("mod:tick();assert(mod.hooks[path].failed and mod.hooks[path].error:find('UFunction::Func: 0x0',1,true));target.func=1;for i=1,10 do mod:tick() end;assert(allocated_refs==1 and #registrations==0)")

    def test_unrelated_registration_failure_remains_visible_and_terminal(self):
        vm=self.vm()
        vm.execute("target.func=1;reject_other=true;mod:tick();assert(mod.hooks[path].failed and mod.hooks[path].error:find('original unsupported hook failure',1,true));mod:tick();assert(allocated_refs==1 and #registrations==0)")

    def test_missing_readiness_api_is_visible_before_any_registration(self):
        vm=self.vm()
        vm.execute("target.HasAnyFlags=nil;mod:tick();assert(mod.hooks[path].failed and mod.hooks[path].error:find('HasAnyFlags',1,true) and allocated_refs==0)")

    def test_callback_error_preserves_original_cause(self):
        vm=self.vm()
        vm.execute("mod.hooks[path].callback=function() error('original goal callback failure') end;target.func=1;mod:tick();local ok,cause=pcall(registrations[1].callback);assert(not ok and tostring(cause):find('original goal callback failure',1,true))")

    def test_absent_function_can_load_later_without_an_attempt(self):
        vm=self.vm()
        vm.execute("target.alive=false;mod:tick();assert(allocated_refs==0 and not mod.hooks[path].failed);target.alive=true;target.flags=EObjectFlags.RF_NeedPostLoad;mod:tick();assert(allocated_refs==0);target.flags=0;target.func=1;mod:tick();assert(#registrations==1)")

def run():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(HookReadiness))
    OUT.mkdir(parents=True,exist_ok=True)
    receipt={'game_acceptance':False,'checks':result.testsRun,'passed':result.wasSuccessful(),'source':str(SOURCE),'sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'baseline_source':str(OLD),'baseline_sha256':hashlib.sha256(OLD.read_bytes()).hexdigest() if OLD.is_file() else None,
        'skipped':[{'test':str(test),'reason':reason} for test,reason in result.skipped],
        'failures':[{'test':str(test),'cause':cause} for test,cause in result.errors+result.failures],
        'limitations':['Fixtures prove load-flag guards and no RegisterHook retry; actual native race flags and successful train goal hook need root live evidence.','Func=0 after flags clear stays a visible terminal failure; synthetic metadata validity is not assumed.']}
    (OUT/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    if not result.wasSuccessful(): raise SystemExit(1)

run()
