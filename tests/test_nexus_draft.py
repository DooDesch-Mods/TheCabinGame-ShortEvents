import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("nexus_draft", Path(__file__).resolve().parents[1] / "tools/nexus_draft.py")
draft = importlib.util.module_from_spec(spec)
spec.loader.exec_module(draft)

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
