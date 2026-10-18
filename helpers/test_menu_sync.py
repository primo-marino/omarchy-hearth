#!/usr/bin/env python3
import json
import os
import tempfile
import unittest
from pathlib import Path

import menu_sync


class MenuSyncTests(unittest.TestCase):
    def test_strip_jsonc_comments_and_trailing_commas(self):
        raw = '{\n  // hi\n  "personal.notes": {"label": "Notes"},\n}\n'
        parsed = menu_sync.parse_object(raw)
        self.assertEqual(parsed["personal.notes"]["label"], "Notes")

    def test_strip_jsonc_inline_line_comment(self):
        raw = '{"a": 1, // note\n "b": 2}'
        self.assertEqual(menu_sync.strip_jsonc(raw), '{"a": 1, \n "b": 2}')

    def test_strip_jsonc_single_line_block_comment(self):
        raw = '{"a": 1, /* note */ "b": 2}'
        self.assertEqual(menu_sync.strip_jsonc(raw), '{"a": 1,  "b": 2}')

    def test_strip_jsonc_multi_line_block_comment(self):
        raw = '{\n  /* line1\n     line2 */\n  "a": 1\n}'
        self.assertEqual(menu_sync.strip_jsonc(raw), '{\n  \n\n  "a": 1\n}')

    def test_strip_jsonc_keeps_double_slash_in_string(self):
        raw = '{"a": "http://x // not comment"}'
        self.assertEqual(menu_sync.strip_jsonc(raw), raw)

    def test_strip_jsonc_keeps_block_open_in_string(self):
        raw = '{"a": "/* not comment */"}'
        self.assertEqual(menu_sync.strip_jsonc(raw), raw)

    def test_strip_jsonc_keeps_comma_brace_in_string(self):
        raw = '{"a": "x, }"}'
        self.assertEqual(menu_sync.strip_jsonc(raw), raw)

    def test_strip_jsonc_trailing_comma_object(self):
        raw = '{"a": 1,}'
        self.assertEqual(menu_sync.strip_jsonc(raw), '{"a": 1}')

    def test_strip_jsonc_trailing_comma_array(self):
        raw = '{"a": [1, 2,]}'
        self.assertEqual(menu_sync.strip_jsonc(raw), '{"a": [1, 2]}')

    def test_strip_jsonc_escaped_quote_then_comment(self):
        raw = '{"a": "x\\" // not comment"}'
        self.assertEqual(menu_sync.strip_jsonc(raw), raw)

    def test_strip_jsonc_escaped_quote_then_real_comment(self):
        raw = '{"a": "x\\"", // real\n "b": 2}'
        self.assertEqual(menu_sync.strip_jsonc(raw), '{"a": "x\\"", \n "b": 2}')

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
            before = Path(path).read_text(encoding="utf-8")
            result = menu_sync.sync(
                tree={"hearth": {"label": "X"}},
                cli="/bin/true",
                menu_path=path,
                etag_path=os.path.join(tmp, "etag"),
            )
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"], "parse_failed")
            self.assertEqual(Path(path).read_text(encoding="utf-8"), before)

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
            text = Path(path).read_text(encoding="utf-8")
            data = menu_sync.parse_object(text)
            self.assertEqual(data["personal.notes"]["label"], "Notes")
            self.assertEqual(data["hearth"]["label"], "Hearth")
            self.assertIn("// keep me", text)

    def test_hearth_key_does_not_eat_hearthside(self):
        self.assertFalse(menu_sync.is_hearth_key("hearthside"))

    def test_unchanged_tree_does_not_clobber_user_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "omarchy-menu.jsonc")
            etag = os.path.join(tmp, "etag")
            menu_sync.sync(
                tree={"hearth": {"label": "Hearth"}},
                cli="/tmp/hearth",
                menu_path=path,
                etag_path=etag,
            )
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            data["personal.notes"] = {"label": "Keep me"}
            Path(path).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            result = menu_sync.sync(
                tree={"hearth": {"label": "Hearth"}},
                cli="/tmp/hearth",
                menu_path=path,
                etag_path=etag,
            )
            self.assertEqual(result.get("skipped"), "user_edit")
            self.assertFalse(result.get("wrote"))
            kept = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertEqual(kept["personal.notes"]["label"], "Keep me")

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
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            data["personal.notes"] = {"label": "Notes"}
            Path(path).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            result = menu_sync.sync(
                tree={"hearth": {"label": "Hearth"}, "hearth.open": {"label": "Open", "action": "x"}},
                cli="/tmp/hearth",
                menu_path=path,
                etag_path=etag,
            )
            self.assertTrue(result.get("ok"))
            merged = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertEqual(merged["personal.notes"]["label"], "Notes")
            self.assertIn("hearth.open", merged)

    def test_uninstall_drops_hearth_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "omarchy-menu.jsonc")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"personal.notes": {"label": "N"}, "hearth": {"label": "H"}}, f)
            menu_sync.sync(tree={}, cli="", menu_path=path, etag_path=os.path.join(tmp, "etag"))
            data = menu_sync.parse_object(Path(path).read_text(encoding="utf-8"))
            self.assertIn("personal.notes", data)
            self.assertNotIn("hearth", data)

    def test_header_comment_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "omarchy-menu.jsonc")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{\n  // header comment\n  "hearth": {"label": "H"},\n  "a": 1\n}\n')
            result = menu_sync.sync(
                tree={"hearth": {"label": "H2"}},
                cli="/tmp/hearth",
                menu_path=path,
                etag_path=os.path.join(tmp, "etag"),
            )
            self.assertTrue(result["ok"])
            text = Path(path).read_text(encoding="utf-8")
            self.assertIn("// header comment", text)
            self.assertIn('"a": 1', text)
            self.assertIn('"label": "H2"', text)

    def test_inline_comment_on_previous_member_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "omarchy-menu.jsonc")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{\n  "a": 1, // note about a\n  "hearth": {"label": "H"}\n}\n')
            result = menu_sync.sync(
                tree={"hearth": {"label": "H2"}},
                cli="/tmp/hearth",
                menu_path=path,
                etag_path=os.path.join(tmp, "etag"),
            )
            self.assertTrue(result["ok"])
            text = Path(path).read_text(encoding="utf-8")
            self.assertIn("// note about a", text)
            self.assertIn('"a": 1', text)
            self.assertIn('"label": "H2"', text)

    def test_uninstall_strict_json_stays_strict(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "omarchy-menu.jsonc")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"personal.notes": {"label": "N"}, "hearth": {"label": "H"}}, f)
            menu_sync.sync(tree={}, cli="", menu_path=path, etag_path=os.path.join(tmp, "etag"))
            text = Path(path).read_text(encoding="utf-8")
            data = json.loads(text)
            self.assertIn("personal.notes", data)
            self.assertNotIn("hearth", data)

    def test_sync_strict_json_stays_strict(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "omarchy-menu.jsonc")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"personal.notes": {"label": "N"}}, f)
            result = menu_sync.sync(
                tree={"hearth": {"label": "H"}},
                cli="/tmp/hearth",
                menu_path=path,
                etag_path=os.path.join(tmp, "etag"),
            )
            self.assertTrue(result["ok"])
            text = Path(path).read_text(encoding="utf-8")
            data = json.loads(text)
            self.assertIn("personal.notes", data)
            self.assertIn("hearth", data)

    def test_two_syncs_no_blank_line_buildup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "omarchy-menu.jsonc")
            etag = os.path.join(tmp, "etag")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{\n  "personal.notes": {"label": "Notes"}\n}\n')
            menu_sync.sync(
                tree={"hearth": {"label": "H1"}},
                cli="/tmp/hearth",
                menu_path=path,
                etag_path=etag,
            )
            first = Path(path).read_text(encoding="utf-8")
            menu_sync.sync(
                tree={"hearth": {"label": "H2"}},
                cli="/tmp/hearth",
                menu_path=path,
                etag_path=etag,
            )
            second = Path(path).read_text(encoding="utf-8")
            self.assertEqual(first.count("\n"), second.count("\n"))
            self.assertNotIn("\n\n\n", second)

    def test_uninstall_drops_trailing_comma_before_removed_hearth(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "omarchy-menu.jsonc")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{\n  "a": 1,\n  "hearth": {"label": "H"}\n}\n')
            menu_sync.sync(tree={}, cli="", menu_path=path, etag_path=os.path.join(tmp, "etag"))
            text = Path(path).read_text(encoding="utf-8")
            self.assertNotIn('"a": 1,', text)
            self.assertIn('"a": 1', text)
            data = menu_sync.parse_object(text)
            self.assertEqual(data, {"a": 1})

    def test_uninstall_keeps_original_trailing_comma(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "omarchy-menu.jsonc")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{\n  "a": 1,\n}\n')
            menu_sync.sync(tree={}, cli="", menu_path=path, etag_path=os.path.join(tmp, "etag"))
            text = Path(path).read_text(encoding="utf-8")
            self.assertIn('"a": 1,', text)
            data = menu_sync.parse_object(text)
            self.assertEqual(data, {"a": 1})

    def test_hearth_in_middle_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "omarchy-menu.jsonc")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{\n  "a": 1,\n  "hearth.old": {"label": "Old"},\n  "b": 2\n}\n')
            result = menu_sync.sync(
                tree={"hearth.new": {"label": "New"}},
                cli="/tmp/hearth",
                menu_path=path,
                etag_path=os.path.join(tmp, "etag"),
            )
            self.assertTrue(result["ok"])
            text = Path(path).read_text(encoding="utf-8")
            self.assertIn('"a": 1', text)
            self.assertIn('"b": 2', text)
            self.assertIn('"hearth.new"', text)
            self.assertNotIn('"hearth.old"', text)

    def test_second_sync_updates_hearth_keeps_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "omarchy-menu.jsonc")
            etag = os.path.join(tmp, "etag")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{\n  // keep me\n  "personal.notes": {"label": "Notes"}\n}\n')
            menu_sync.sync(
                tree={"hearth": {"label": "Hearth"}},
                cli="/tmp/hearth",
                menu_path=path,
                etag_path=etag,
            )
            result = menu_sync.sync(
                tree={"hearth": {"label": "Hearth2"}},
                cli="/tmp/hearth",
                menu_path=path,
                etag_path=etag,
            )
            self.assertTrue(result["ok"])
            text = Path(path).read_text(encoding="utf-8")
            self.assertIn("// keep me", text)
            self.assertIn('"label": "Hearth2"', text)

    def test_uninstall_keeps_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "omarchy-menu.jsonc")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{\n  // keep me\n  "personal.notes": {"label": "Notes"},\n  "hearth": {"label": "Hearth"}\n}\n')
            menu_sync.sync(tree={}, cli="", menu_path=path, etag_path=os.path.join(tmp, "etag"))
            text = Path(path).read_text(encoding="utf-8")
            self.assertIn("// keep me", text)
            self.assertNotIn("hearth", text)

    def test_hearthside_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "omarchy-menu.jsonc")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{\n  "hearthside": {"label": "Not Hearth"}\n}\n')
            result = menu_sync.sync(
                tree={"hearth": {"label": "Hearth"}},
                cli="/tmp/hearth",
                menu_path=path,
                etag_path=os.path.join(tmp, "etag"),
            )
            self.assertTrue(result["ok"])
            text = Path(path).read_text(encoding="utf-8")
            self.assertIn('"hearthside"', text)
            self.assertIn('"hearth"', text)

    def test_result_always_parses(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "omarchy-menu.jsonc")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{\n  "personal.notes": {"label": "Notes"}\n}\n')
            result = menu_sync.sync(
                tree={"hearth": {"label": "Hearth"}},
                cli="/tmp/hearth",
                menu_path=path,
                etag_path=os.path.join(tmp, "etag"),
            )
            self.assertTrue(result["ok"])
            text = Path(path).read_text(encoding="utf-8")
            parsed = menu_sync.parse_object(text)
            self.assertIsNotNone(parsed)
            self.assertIn("hearth", parsed)

    def test_last_member_trailing_comma(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "omarchy-menu.jsonc")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{\n  "personal.notes": {"label": "Notes"},\n}\n')
            result = menu_sync.sync(
                tree={"hearth": {"label": "Hearth"}},
                cli="/tmp/hearth",
                menu_path=path,
                etag_path=os.path.join(tmp, "etag"),
            )
            self.assertTrue(result["ok"])
            text = Path(path).read_text(encoding="utf-8")
            self.assertIn('"personal.notes"', text)
            self.assertIn('"hearth"', text)
            parsed = menu_sync.parse_object(text)
            self.assertIsNotNone(parsed)

    def test_only_hearth_keys_plus_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "omarchy-menu.jsonc")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{\n  // comment\n  "hearth": {"label": "Hearth"}\n}\n')
            result = menu_sync.sync(
                tree={"hearth": {"label": "Hearth2"}},
                cli="/tmp/hearth",
                menu_path=path,
                etag_path=os.path.join(tmp, "etag"),
            )
            self.assertTrue(result["ok"])
            text = Path(path).read_text(encoding="utf-8")
            parsed = menu_sync.parse_object(text)
            self.assertIsNotNone(parsed)
            self.assertEqual(parsed["hearth"]["label"], "Hearth2")


if __name__ == "__main__":
    unittest.main()
