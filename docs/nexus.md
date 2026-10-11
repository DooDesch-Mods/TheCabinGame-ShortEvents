# CabinShortEvents

> 🛟 **Need help or found a bug?** Get support at [support.doodesch.de/shortevents](https://support.doodesch.de/shortevents).

Reduces balloon and train tasks by about one third. Original difficulty and player count still determine the starting goal.

**Status: private test candidate. Game acceptance is pending. No public release yet.**

Target: Steam build `25553694`, Unreal 5.5 and UE4SS `v3.0.1-1164-g5e627997`. Install UE4SS separately.

1. Close the game and install the required UE4SS runtime in your private test copy.
2. Copy `Mods/CabinShortEvents` into `the_cabin_game/Binaries/Win64/ue4ss/Mods`.
3. Copy the archive's `the_cabin_game/Content/Paks/~mods` files to the same path in your game folder. Keep the three container files together.

CabinModSettings is optional. Each function mod uses its defaults and its own validated settings file without the Settings card. GraphicsProfiles supplies profile templates without the Settings card and never applies a profile on startup.

FastTurns and ShortEvents settings take effect next round and are controlled by the host. FastTurns requires its Lua and overlay on every participating client. Other settings are local. Multiplayer acceptance is pending.

Close the game before removal. Remove only this mod's folder and its named container files, if included. Back up `Scripts/settings.dat` first to keep preferences. GraphicsProfiles does not restore graphics automatically on removal; use Restore previous before removal if required.

Rejoin integration requires its matching layout/host-settings adapter and authority copies. That combined installation is private and unaccepted. Do not overwrite an active Rejoin runtime.

