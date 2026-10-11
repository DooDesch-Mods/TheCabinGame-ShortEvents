"""Compile shipped Lua and exercise each mod's pure behavior in Lua 5.4."""
import json
from pathlib import Path
import runpy
from lupa.lua54 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
NAME = json.loads((ROOT / "package.json").read_text())["mod"]
SCRIPTS = ROOT / "Mods" / NAME / "Scripts"
vm = LuaRuntime(unpack_returned_tuples=True)
compile_lua = vm.eval('function(source,name) return assert(load(source,name,"t",{})) end')
paths = sorted((ROOT / "Mods").rglob("*.lua"))
for path in paths:
    compile_lua(path.read_text(encoding="utf-8"), path.relative_to(ROOT).as_posix())
vm.globals().directory = SCRIPTS.as_posix()
vm.execute('package.path=directory.."/?.lua;"..package.path')
if NAME != "CabinModSettings":
    vm.execute('definition=require("definition");storage=require("cabin_store");defaults=storage.defaults(definition.fields);assert(storage.validate(definition.fields,defaults))')
if NAME == "CabinFastTurns":
    vm.execute('speed=require("speed");assert(speed.rate(0.3,2)==0.6 and speed.delay(3,2)==1.5);assert(not speed.board.IntroRewind_TL and not speed.board.DealCards_TL and not speed.cards.CursorHover_TL)')
elif NAME == "CabinShortEvents":
    vm.execute('targets=require("targets");assert(targets.reduce(10,2/3)==7 and targets.reduce(21,2/3)==14 and targets.reduce(1,2/3)==1);assert(targets.reduce(10,1)==10);assert(not pcall(targets.reduce,10,0))')
for path in sorted((ROOT / "tests").glob("check_behavior_*.py")):
    runpy.run_path(str(path))
print(f"info: {NAME}: {len(paths)} Lua files compile; behavior checks passed; game acceptance pending")
