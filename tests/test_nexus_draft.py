import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

spec = importlib.util.spec_from_file_location("nexus_draft", Path(__file__).resolve().parents[1] / "tools/nexus_draft.py")
draft = importlib.util.module_from_spec(spec)
spec.loader.exec_module(draft)

class ApiResponseTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(draft.os.environ, {"NEXUSMODS_API_KEY": "fixture-secret"}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def reply(self, method, path, body, status=200, payload=None):
        response = MagicMock()
        response.status = status
        response.headers = {"Content-Type": "application/json"}
        response.read.return_value = body
        response.__enter__.return_value = response
        with patch.object(draft.urllib.request, "urlopen", return_value=response) as opened:
            result = draft.api(method, path, payload)
        request = opened.call_args.args[0]
        self.assertEqual(request.get_method(), method)
        self.assertEqual(request.full_url, draft.BASE + path)
        if payload is not None:
            self.assertEqual(json.loads(request.data), payload)
        return result

    def test_standard_data_envelopes_are_unwrapped(self):
        for method, path, data in [
            ("POST", "/mods/batch", {"mods": []}),
            ("GET", "/games/thecabingame/mods/6", {"id": "45363444580358", "game_id": "10562", "game_scoped_id": "6"}),
            ("GET", "/mods/45363444580358/files", {"mod_files": []}),
            ("GET", "/mod-files/8138724/versions", {"versions": []}),
        ]:
            with self.subTest(path=path):
                payload = {"mod_ids": ["45363444580358"]} if method == "POST" else None
                self.assertEqual(self.reply(method, path, json.dumps({"data": data}).encode(), payload=payload), data)

    def test_standard_dependency_responses_are_flat(self):
        for suffix, field in [("ranges", "dependency_definitions"), ("dlc", "dlc_dependency_definitions")]:
            with self.subTest(suffix=suffix):
                data = {field: []}
                self.assertEqual(self.reply("GET", "/mod-file-versions/123/dependencies/" + suffix, json.dumps(data).encode()), data)

    def test_204_update_has_no_json_body(self):
        self.assertIsNone(self.reply("PUT", "/mod-file-versions/123/dependencies/ranges", b"", 204, {"dependency_definitions": []}))

    def test_missing_data_and_error_data_do_not_become_success(self):
        for body, reason in [({"mods": []}, "missing or invalid data object"), ({"errorData": {"detail": "fixture-secret"}}, "errorData response")]:
            with self.subTest(reason=reason), self.assertRaisesRegex(RuntimeError, "Nexus POST /mods/batch: " + reason) as caught:
                self.reply("POST", "/mods/batch", json.dumps(body).encode())
            self.assertNotIn("fixture-secret", str(caught.exception))
            self.assertIn("HTTP 200", str(caught.exception))
            self.assertIn("Content-Type=application/json", str(caught.exception))
            self.assertIn("fields=" + json.dumps(sorted(body)), str(caught.exception))

    def test_required_response_array_is_checked_before_caller_access(self):
        for body in [{"data": {}}, {"data": {"mods": None}}, {"data": {"mods": {}}}]:
            with self.subTest(body=body), self.assertRaisesRegex(RuntimeError, "Nexus POST /mods/batch: missing or invalid mods array"):
                self.reply("POST", "/mods/batch", json.dumps(body).encode())
        with self.assertRaisesRegex(RuntimeError, "missing or invalid dependency_definitions array"):
            self.reply("GET", "/mod-file-versions/123/dependencies/ranges", b'{"data": {"dependency_definitions": []}}')

    def test_empty_200_and_invalid_json_remain_visible(self):
        for body, reason in [(b"", "empty response"), (b"{", "invalid response JSON"), (b"[]", "response is not a JSON object")]:
            with self.subTest(reason=reason), self.assertRaisesRegex(RuntimeError, "Nexus POST /mods/batch: " + reason):
                self.reply("POST", "/mods/batch", body)

    def test_problem_details_cannot_be_mistaken_for_success(self):
        problem = {"type": "https://api.nexusmods.com/problems/forbidden", "title": "Forbidden", "status": 403,
                   "detail": "access denied for fixture-secret", "instance": "/mods/batch"}
        with self.assertRaisesRegex(RuntimeError, "Nexus POST /mods/batch: API status=403; access denied") as caught:
            self.reply("POST", "/mods/batch", json.dumps(problem).encode())
        self.assertNotIn("fixture-secret", str(caught.exception))

    def test_http_problem_preserves_status_and_redacted_original_detail(self):
        problem = {"type": "https://api.nexusmods.com/problems/forbidden", "title": "Forbidden", "status": 403,
                   "detail": "access denied for fixture-secret", "instance": "/mods/batch"}
        cause = draft.urllib.error.HTTPError(draft.BASE + "/mods/batch", 403, "Forbidden", {}, io.BytesIO(json.dumps(problem).encode()))
        with patch.object(draft.urllib.request, "urlopen", side_effect=cause):
            with self.assertRaisesRegex(RuntimeError, "Nexus POST /mods/batch: HTTP 403; access denied") as caught:
                draft.api("POST", "/mods/batch")
        self.assertIs(caught.exception.__cause__, cause)
        self.assertNotIn("fixture-secret", str(caught.exception))

    def test_http_non_json_error_stays_an_http_failure(self):
        cause = draft.urllib.error.HTTPError(draft.BASE + "/mods/batch", 502, "Bad Gateway", {}, io.BytesIO(b"not-json"))
        with patch.object(draft.urllib.request, "urlopen", side_effect=cause):
            with self.assertRaisesRegex(RuntimeError, "Nexus POST /mods/batch: HTTP 502; invalid problem JSON"):
                draft.api("POST", "/mods/batch")

    def test_network_failure_preserves_operation_and_original_cause(self):
        cause = draft.urllib.error.URLError("fixture connection failure")
        with patch.object(draft.urllib.request, "urlopen", side_effect=cause):
            with self.assertRaisesRegex(RuntimeError, "Nexus POST /mods/batch: fixture connection failure") as caught:
                draft.api("POST", "/mods/batch")
        self.assertIs(caught.exception.__cause__, cause)

class DraftGuardTests(unittest.TestCase):
    def setUp(self):
        self.identity = {"uid": "45363444580358", "scoped": "6", "file": "8138724"}
        self.row = {"id": self.identity["uid"], "game_id": "10562", "status": "not_published"}
        self.details = {"id": self.identity["uid"], "game_id": "10562", "game_scoped_id": "6"}
        self.files = [{"id": "8138724"}]

    def test_only_unpublished_parent_is_allowed(self):
        draft.check_parent(self.identity, [self.row], self.details, self.files)
        for status in ("published", "hidden", "under_moderation", "removed", None):
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "required=not_published"):
                draft.check_parent(self.identity, [dict(self.row, status=status)], self.details, self.files)

    def test_wrong_game_and_wrong_file_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "game differs"):
            draft.check_parent(self.identity, [dict(self.row, game_id="130")], self.details, self.files)
        with self.assertRaisesRegex(ValueError, "does not belong"):
            draft.check_parent(self.identity, [self.row], self.details, [{"id": "111"}])
        with self.assertRaisesRegex(ValueError, "scoped page ID differs"):
            draft.check_parent(self.identity, [self.row], dict(self.details, game_scoped_id="7"), self.files)

    def test_unknown_parent_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "required=1"):
            draft.check_parent(self.identity, [], self.details, self.files)

    def test_latest_range_is_preserved_and_wrong_file_is_rejected(self):
        definition = {"ranges": [{"target_mod_file": {"id": "400"}, "min_version": {"id": "500", "file": {"id": "400"}}, "max_version": None}]}
        self.assertEqual(draft.ranges([definition]), {"dependency_definitions": [{"ranges": [{"min_version_id": "500", "max_version_id": None}]}]})
        definition["ranges"][0]["min_version"]["file"]["id"] = "wrong"
        with self.assertRaisesRegex(ValueError, "minimum belongs"):
            draft.ranges([definition])
        with self.assertRaisesRegex(ValueError, "requirements are missing"):
            draft.ranges([])
