#!/usr/bin/env python3
import json
import os
import tempfile
import unittest

import menu_sync


class MenuSyncTests(unittest.TestCase):
    def test_strip_jsonc_comments_and_trailing_commas(self):
        raw = '{\n  // hi\n  "personal.notes": {"label": "Notes"},\n}\n'
        parsed = menu_sync.parse_object(raw)
        self.assertEqual(parsed["personal.notes"]["label"], "Notes")

    def test_parse_fail_is_none(self):
        self.assertIsNone(menu_sync.parse_object("{not json"))

    def test_merge_only_hearth_keys(self):
        existing = {
            "personal.notes": {"label": "Notes"},
            "hearth.rooms.old": {"label": "Gone"},
        }
        tree = {
            "hearth": {"label": "Hearth"},
            "hearth.open": {"label": "Open", "action": "x"},
            "personal.notes": {"label": "should not land from tree"},
        }
        merged = menu_sync.merge_hearth(existing, tree)
        self.assertEqual(merged["personal.notes"]["label"], "Notes")
        self.assertIn("hearth", merged)
        self.assertIn("hearth.open", merged)
        self.assertNotIn("hearth.rooms.old", merged)

    def test_is_hearth_key(self):
        self.assertTrue(menu_sync.is_hearth_key("hearth"))
        self.assertTrue(menu_sync.is_hearth_key("hearth.open"))
        self.assertFalse(menu_sync.is_hearth_key("hearthside"))
        self.assertFalse(menu_sync.is_hearth_key("personal.hearth"))

    def test_sync_fail_closed_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "omarchy-menu.jsonc")
            with open(path, "w", encoding="utf-8") as f:
                f.write("{ nope")
            before = open(path).read()
            result = menu_sync.sync(
                tree={"hearth": {"label": "X"}},
                cli="/bin/true",
                menu_path=path,
                etag_path=os.path.join(tmp, "etag"),
            )
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"], "parse_failed")
            self.assertEqual(open(path).read(), before)

    def test_sync_writes_and_preserves(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "omarchy-menu.jsonc")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{\n  // keep me\n  "personal.notes": {"label": "Notes"}\n}\n')
            result = menu_sync.sync(
                tree={"hearth": {"icon": "x", "label": "Hearth"}, "hearth.open": {"label": "Open", "action": "true"}},
                cli="/tmp/hearth",
                menu_path=path,
                etag_path=os.path.join(tmp, "etag"),
                bak_path=os.path.join(tmp, "omarchy-menu.jsonc.bak"),
            )
            self.assertTrue(result["ok"])
            self.assertTrue(result["wrote"])
            data = json.loads(open(path).read())
            self.assertEqual(data["personal.notes"]["label"], "Notes")
            self.assertEqual(data["hearth"]["label"], "Hearth")
            self.assertNotIn("//", open(path).read())

    def test_hearth_key_does_not_eat_hearthside(self):
        self.assertFalse(menu_sync.is_hearth_key("hearthside"))

    def test_user_edit_still_merges_hearth_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "omarchy-menu.jsonc")
            etag = os.path.join(tmp, "etag")
            menu_sync.sync(
                tree={"hearth": {"label": "Hearth"}},
                cli="/tmp/hearth",
                menu_path=path,
                etag_path=etag,
            )
            data = json.loads(open(path).read())
            data["personal.notes"] = {"label": "Notes"}
            open(path, "w").write(json.dumps(data, indent=2) + "\n")
            result = menu_sync.sync(
                tree={"hearth": {"label": "Hearth"}, "hearth.open": {"label": "Open", "action": "x"}},
                cli="/tmp/hearth",
                menu_path=path,
                etag_path=etag,
            )
            self.assertTrue(result.get("ok"))
            merged = json.loads(open(path).read())
            self.assertEqual(merged["personal.notes"]["label"], "Notes")
            self.assertIn("hearth.open", merged)

    def test_uninstall_drops_hearth_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "omarchy-menu.jsonc")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"personal.notes": {"label": "N"}, "hearth": {"label": "H"}}, f)
            menu_sync.sync(tree={}, cli="", menu_path=path, etag_path=os.path.join(tmp, "etag"))
            data = json.loads(open(path).read())
            self.assertIn("personal.notes", data)
            self.assertNotIn("hearth", data)


if __name__ == "__main__":
    unittest.main()
