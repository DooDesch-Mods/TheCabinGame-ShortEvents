# Publishing

Do not publish before the exact runtime payload passes game acceptance. Record six checks in `acceptance.json`: each mod alone, Settings, gameplay, multiplayer, integration and installation. Every passed check names its log, screenshot or other observed evidence. Packaging checks do not replace game acceptance. The payload hash must match the tested Lua and overlay bytes.

CI builds candidates on Linux and Windows. Both archive hashes must match the local build. The manual Release and update Nexus workflow repeats checks, requires acceptance, builds the release and verifies its public tag and downloaded ZIP/checksum. It never runs on a normal push.

For the first Nexus release, create the mod page and Main File from the accepted ZIP and prepared description. Then configure repository variables:

| Variable | Value |
|---|---|
| NEXUS_FILE_GROUP_ID | Numeric API File ID from Main File > Advanced |
| NEXUS_MOD_ID | Numeric Unique Mod ID from the same panel |
| NEXUS_VORTEX_READY | true only after this mod's actual Nexus/Vortex download and deployment pass |

Use the existing organization secret NEXUSMODS_API_KEY. Its value stays in GitHub Secrets. Later releases use the workflow's publish_nexus option. It verifies that the file group belongs to the configured Nexus mod before upload and requires Nexus's version ID after upload.

The first GitHub release can run with publish_nexus disabled. An existing release is reused only if its tag and uploaded bytes match this exact commit. Failed or unclear Nexus uploads must be inspected on Nexus before another upload; do not replay a timed-out upload automatically.

Do not include the game, UE4SS runtime, diagnostics, settings, original extracted assets or private Rejoin copies in a repository or archive. Review the compiled mod overlay inputs when they change.
