"""Check announcement boundaries without Discord credentials or publication."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("discord_release", Path(__file__).resolve().parents[1] / "tools/announce-release.py")
discord = importlib.util.module_from_spec(spec)
spec.loader.exec_module(discord)

class Announcement(unittest.TestCase):
    def test_send_without_release_tag_stops_before_network(self):
        with patch.dict(os.environ, {"RELEASE_TAG": "", "SEND_ANNOUNCEMENT": "true"}), patch.object(discord, "request_json") as request:
            with self.assertRaisesRegex(ValueError, "published release tag"):
                discord.run()
            request.assert_not_called()

    def test_draft_cannot_be_announced(self):
        with self.assertRaisesRegex(ValueError, "not published"):
            discord.build_payload({"draft": True}, "Test", "Summary", "https://example.test", "https://example.test/icon.png")

    def test_pre_release_and_mentions(self):
        payload = discord.build_payload({"draft": False, "published_at": "2026-10-11", "prerelease": True, "tag_name": "v0.1.2", "html_url": "https://example.test/release"}, "Test", "Summary", "https://example.test/support", "https://example.test/icon.png")
        self.assertIn("pre-release", payload["embeds"][0]["title"])
        self.assertEqual(payload["allowed_mentions"], {"parse": []})
        self.assertEqual(payload["embeds"][0]["thumbnail"]["url"], "https://example.test/icon.png")

    def test_missing_thumbnail_stops_before_send(self):
        release = {"draft": False, "published_at": "2026-10-11"}
        with self.assertRaisesRegex(ValueError, "thumbnail requires"):
            discord.build_payload(release, "Test", "Summary", "https://example.test/support", "")

    def test_wrong_channel_stops_before_send(self):
        with patch.object(discord, "request_json", return_value={"channel_id": "wrong"}) as request:
            with self.assertRaisesRegex(ValueError, "destination mismatch"):
                discord.announce("https://discord.com/api/webhooks/123/test", "456", {}, True, {})
            self.assertEqual(request.call_count, 1)

    def test_manual_check_never_posts(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temporary:
            previous = os.getcwd()
            try:
                os.chdir(temporary)
                with patch.object(discord, "request_json", return_value={"channel_id": "456"}) as request:
                    result = discord.announce("https://discord.com/api/webhooks/123/test/github", "456", {}, False, {})
                    self.assertEqual(result["status"], "checked")
                    self.assertEqual(request.call_count, 1)
            finally:
                os.chdir(previous)

    def test_sent_message_is_read_back(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temporary:
            previous = os.getcwd()
            try:
                os.chdir(temporary)
                responses = [{"channel_id": "456", "guild_id": "789"}, {"channel_id": "456", "id": "1000"}, {"channel_id": "456", "id": "1000"}]
                with patch.object(discord, "request_json", side_effect=responses) as request:
                    result = discord.announce("https://discord.com/api/webhooks/123/test", "456", {}, True, {})
                    self.assertEqual(result["status"], "confirmed")
                    self.assertEqual(request.call_args.args[0], "https://discord.com/api/webhooks/123/test/messages/1000")
            finally:
                os.chdir(previous)



class ProductAnnouncement(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.folder.cleanup)
        previous = os.getcwd()
        os.chdir(self.folder.name)
        self.addCleanup(os.chdir, previous)
        self.environment = {"GITHUB_REPOSITORY": discord.PRODUCT["repository"], "DISCORD_CHANNEL_ID": discord.CHANNEL,
            "GH_TOKEN": "fixture-token", "DISCORD_RELEASE_WEBHOOK": "https://discord.com/api/webhooks/123/test",
            "GITHUB_STEP_SUMMARY": str(Path(self.folder.name) / "summary.md"), "RELEASE_TAG": "v0.1.0", "SEND_ANNOUNCEMENT": "true"}
        self.environment.update({"PRODUCT_" + key.upper(): discord.PRODUCT[key] for key in ("name", "summary", "support", "thumbnail")})
        self.release = {"id": "100", "draft": False, "published_at": "2026-10-12", "prerelease": False, "tag_name": "v0.1.0", "html_url": "https://github.com/" + discord.PRODUCT["repository"] + "/releases/tag/v0.1.0"}

    def test_product_identity_support_thumbnail_and_pinned_channel(self):
        short = discord.PRODUCT["repository"].removeprefix("DooDesch-Mods/TheCabinGame-")
        self.assertEqual(discord.PRODUCT["support"], "https://support.doodesch.de/" + short.lower())
        self.assertEqual(discord.PRODUCT["thumbnail"], "https://raw.githubusercontent.com/" + discord.PRODUCT["repository"] + "/main/docs/thumbnail.png")
        self.assertTrue(discord.PRODUCT["name"].startswith("Cabin "))
        self.assertEqual(discord.CHANNEL, "1534536549642014810")
        with patch.dict(os.environ, self.environment, clear=True):
            discord.check_product()

    def test_wrong_product_or_channel_stops_before_network(self):
        for key in ("GITHUB_REPOSITORY", "DISCORD_CHANNEL_ID", "PRODUCT_SUPPORT", "PRODUCT_THUMBNAIL"):
            with self.subTest(key=key), patch.dict(os.environ, dict(self.environment, **{key: "wrong"}), clear=True), patch.object(discord, "request_json") as request:
                with self.assertRaises(ValueError):
                    discord.run()
                request.assert_not_called()

    def test_missing_actual_png_stops_before_webhook_read_or_send(self):
        actual_check = discord.check_thumbnail
        missing = Path(self.folder.name) / "absent.png"
        with patch.dict(os.environ, self.environment, clear=True), patch.object(discord, "check_thumbnail", side_effect=lambda: actual_check(missing)), patch.object(discord, "request_json", return_value=self.release) as request:
            with self.assertRaisesRegex(ValueError, "actual product PNG is missing"):
                discord.run()
            self.assertEqual(request.call_count, 1)
            self.assertTrue(request.call_args.args[0].startswith("https://api.github.com/"))
            self.assertFalse(Path("discord-result.json").exists())

    def test_thumbnail_crc_and_complete_structure(self):
        import struct
        import zlib
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00")) + chunk(b"IEND", b"")
        path = Path(self.folder.name) / "fixture.png"
        path.write_bytes(data)
        self.assertEqual(len(discord.check_thumbnail(path)), 64)
        for invalid in (b"not PNG", data[:-1], data + b"tail", data[:-5] + b"wrong"):
            path.write_bytes(invalid)
            with self.subTest(invalid=invalid[-8:]), self.assertRaises(ValueError):
                discord.check_thumbnail(path)

    def test_prior_attempt_blocks_all_network_and_replay(self):
        import json
        for status in ("attempted", "acknowledged", "confirmed"):
            Path("discord-result.json").write_text(json.dumps({"status": status}), encoding="utf-8")
            with self.subTest(status=status), patch.dict(os.environ, self.environment, clear=True), patch.object(discord, "request_json") as request:
                with self.assertRaisesRegex(ValueError, "prior Discord send attempt retained"):
                    discord.run()
                request.assert_not_called()

    def test_manual_channel_check_never_sends_or_requires_thumbnail(self):
        with patch.dict(os.environ, dict(self.environment, RELEASE_TAG="", SEND_ANNOUNCEMENT="false"), clear=True), patch.object(discord, "check_thumbnail") as thumbnail, patch.object(discord, "request_json", return_value={"channel_id": discord.CHANNEL}) as request:
            discord.run()
            thumbnail.assert_not_called()
            self.assertEqual(request.call_count, 1)
            self.assertEqual(len(request.call_args.args), 3)

    def test_prerelease_stops_before_webhook(self):
        with patch.dict(os.environ, self.environment, clear=True), patch.object(discord, "request_json", return_value=dict(self.release, prerelease=True)) as request:
            with self.assertRaisesRegex(ValueError, "published full release"):
                discord.run()
            self.assertEqual(request.call_count, 1)

    def test_send_failure_retains_attempt_and_original_cause(self):
        import json
        cause = RuntimeError("send Discord announcement: fixture timeout; delivery is unconfirmed")
        with patch.object(discord, "request_json", side_effect=[{"channel_id": discord.CHANNEL, "guild_id": "789"}, cause]) as request:
            with self.assertRaisesRegex(RuntimeError, "fixture timeout") as caught:
                discord.announce(self.environment["DISCORD_RELEASE_WEBHOOK"], discord.CHANNEL, {}, True, {})
            self.assertIs(caught.exception, cause)
            self.assertEqual(request.call_count, 2)
            self.assertEqual(json.loads(Path("discord-result.json").read_text())["status"], "attempted")


if __name__ == "__main__":
    unittest.main()
