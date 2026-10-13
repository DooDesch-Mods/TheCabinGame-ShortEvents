# CabinShortEvents

> 🛟 **Need help or found a bug?** Get support at [support.doodesch.de/shortevents](https://support.doodesch.de/shortevents).

Reduces balloon and train tasks by about one third. Original difficulty and player count still determine the starting goal.

## Installation

Requires UE4SS `v3.0.1-1164-g5e627997`, installed separately. Target game version: Steam build `25553694` (Unreal 5.5).

1. Close the game and install UE4SS.
2. Copy the archive's `Mods/CabinShortEvents` folder into `the_cabin_game/Binaries/Win64/ue4ss/Mods`.
3. Copy the archive's `the_cabin_game/Content/Paks/~mods` files into the same path in your game folder. Keep `CabinShortEvents_P.pak`, `CabinShortEvents_P.utoc` and `CabinShortEvents_P.ucas` together.

## Settings

The mod is enabled by default. Balloon and train task sizes are each set to two thirds of their original goal, rounded up to at least one.

Install the optional CabinModSettings mod to adjust each task size from 1% to 100% or disable the mod through the Settings card. A task size of 100% keeps the original goal. Without CabinModSettings, CabinShortEvents uses its defaults and its own validated settings file.

The host controls these settings. Changes take effect next round.

## Removal

Close the game. Back up `Mods/CabinShortEvents/Scripts/settings.dat` if you want to keep your preferences, then remove the `Mods/CabinShortEvents` folder and the three `CabinShortEvents_P` container files.

## Building from source

Use Python 3.13. Install development dependencies with `python -m pip install -r requirements-dev.txt`, run `python -m unittest discover -s tests -v` and `python tests/check_lua.py`, then build with `python tools/package.py`.

The builder writes a ZIP and checksum to `dist` using the committed overlay containers. See [publishing](docs/publishing.md) for release checks and [Nexus description](docs/nexus.md) for listing text.
