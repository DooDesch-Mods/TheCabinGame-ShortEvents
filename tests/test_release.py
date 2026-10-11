"""Exercise release boundaries, acceptance invalidation and canonical ZIPs."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import package


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        (package.ROOT / "dist").mkdir(exist_ok=True)

    def test_build_repeats_exact_bytes(self):
        archive = package.build()
        first = archive.read_bytes()
        self.assertEqual(first, package.build().read_bytes())
        package.verify(archive)
        checksum = (archive.parent / "SHA256SUMS.txt").read_text().split()[0]
        self.assertEqual(hashlib.sha256(first).hexdigest(), checksum)

    def test_unaccepted_release_is_blocked(self):
        with tempfile.TemporaryDirectory(dir=package.ROOT / "dist") as folder, patch.object(package, "ROOT", Path(folder)):
            (Path(folder) / "acceptance.json").write_text('{"accepted":false}')
            with self.assertRaisesRegex(ValueError, "game acceptance is pending"):
                package.require_acceptance({"a.lua": b"return 1"})

    def test_changed_payload_and_missing_evidence_block(self):
        files = {"a.lua": b"return 1", "a.utoc": b"overlay"}
        accepted = {"accepted": True, "payload_sha256": package.fingerprint(files),
                    "game_build": package.CONFIG["game_build"], "ue4ss": package.CONFIG["ue4ss"],
                    "checks": {name: {"passed": True, "evidence": "fixture-only"} for name in package.REQUIRED}}
        with tempfile.TemporaryDirectory(dir=package.ROOT / "dist") as folder, patch.object(package, "ROOT", Path(folder)):
            path = Path(folder) / "acceptance.json"
            path.write_text(json.dumps(accepted))
            package.require_acceptance(files)
            for name in files:
                changed = dict(files)
                changed[name] += b"changed"
                with self.assertRaisesRegex(ValueError, "payload mismatch"):
                    package.require_acceptance(changed)
            accepted["checks"]["multiplayer"]["evidence"] = ""
            path.write_text(json.dumps(accepted))
            with self.assertRaisesRegex(ValueError, "multiplayer"):
                package.require_acceptance(files)

    def test_routes_do_not_replace_shared_loader_files(self):
        files = package.payload()
        self.assertTrue(all(name.startswith(f"Mods/{package.MOD}/") or name.startswith("the_cabin_game/Content/Paks/~mods/") for name in files))
        self.assertFalse(any(Path(name).name in {"mods.txt", "mods.json", "UE4SS.dll", "UE4SS-settings.ini"} for name in files))
        self.assertEqual(package.fingerprint(files), json.loads((package.ROOT / "acceptance.json").read_text())["payload_sha256"])


if __name__ == "__main__":
    unittest.main()
