#!/usr/bin/env python3
import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.realpath(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def load_hearth(home):
    os.environ["HOME"] = home
    loader = importlib.machinery.SourceFileLoader("hearth_cli", os.path.join(HERE, "hearth"))
    spec = importlib.util.spec_from_loader("hearth_cli", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class HearthCliOpenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old_home = os.environ.get("HOME")
        self.addCleanup(self._restore_home)
        self.mod = load_hearth(self.tmp.name)

    def _restore_home(self):
        if self.old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self.old_home

    def test_open_summons_full_plugin_id(self):
        with mock.patch("subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="ok", stderr="")
            code = self.mod.cmd_open("")
        self.assertEqual(code, 0)
        run.assert_called_once()
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["omarchy-shell", "shell", "summon", "io.github.primo-marino.hearth", "{}"])
        self.assertEqual(kwargs.get("timeout"), 8)

    def test_open_returns_1_on_nonzero(self):
        with mock.patch("subprocess.run") as run:
            run.return_value = mock.Mock(returncode=1, stdout="", stderr="boom")
            code = self.mod.cmd_open("")
        self.assertEqual(code, 1)

    def test_open_returns_1_when_shell_missing(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError):
            code = self.mod.cmd_open("")
        self.assertEqual(code, 1)

    def test_open_returns_1_when_shell_returns_unknown(self):
        with mock.patch("subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="unknown", stderr="")
            code = self.mod.cmd_open("")
        self.assertEqual(code, 1)

    def test_open_room_writes_pending_and_summons(self):
        with mock.patch("subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="ok", stderr="")
            code = self.mod.main(["open", "--room", "kitchen"])
        self.assertEqual(code, 0)
        with open(self.mod.PENDING_ROOM, "r", encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), "kitchen")
        args, _ = run.call_args
        self.assertEqual(args[0], ["omarchy-shell", "shell", "summon", "io.github.primo-marino.hearth", "{}"])


class HearthCliActTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old_home = os.environ.get("HOME")
        self.addCleanup(self._restore_home)
        self.mod = load_hearth(self.tmp.name)

    def _restore_home(self):
        if self.old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self.old_home

    def test_act_ipc_ok_does_not_fall_back(self):
        with mock.patch.object(self.mod, "shell_running", return_value=True), \
             mock.patch.object(self.mod, "ipc", return_value=(0, json.dumps({"ok": True}))), \
             mock.patch.object(self.mod, "rest_act") as rest:
            code = self.mod.cmd_act("light.kitchen", "toggle")
        self.assertEqual(code, 0)
        rest.assert_not_called()

    def test_act_disconnected_falls_back_to_rest(self):
        reply = json.dumps({"ok": False, "error": "Disconnected from Home Assistant."})
        with mock.patch.object(self.mod, "shell_running", return_value=True), \
             mock.patch.object(self.mod, "ipc", return_value=(0, reply)), \
             mock.patch.object(self.mod, "rest_act", return_value={"ok": True}) as rest:
            code = self.mod.cmd_act("light.kitchen", "toggle")
        self.assertEqual(code, 0)
        rest.assert_called_once()
        args, _ = rest.call_args
        self.assertEqual(args[0], "light.kitchen")
        self.assertEqual(args[1], "toggle")

    def test_act_other_error_does_not_fall_back(self):
        reply = json.dumps({"ok": False, "error": "Call failed."})
        with mock.patch.object(self.mod, "shell_running", return_value=True), \
             mock.patch.object(self.mod, "ipc", return_value=(0, reply)), \
             mock.patch.object(self.mod, "rest_act") as rest:
            code = self.mod.cmd_act("light.kitchen", "toggle")
        self.assertEqual(code, 1)
        rest.assert_not_called()

    def test_act_ipc_timeout_does_not_fall_back(self):
        with mock.patch.object(self.mod, "shell_running", return_value=True), \
             mock.patch.object(self.mod, "ipc", return_value=(124, "ipc timeout")), \
             mock.patch.object(self.mod, "rest_act") as rest:
            code = self.mod.cmd_act("light.kitchen", "toggle")
        self.assertEqual(code, 1)
        rest.assert_not_called()


if __name__ == "__main__":
    unittest.main()
