import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import subprocess
import importlib.util

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller import Controller, validate_mode
from deploy import merge_conf, stop_session, payload
from shortcuts import decode, encode, update

spec = importlib.util.spec_from_file_location("desktop_sandbox", Path(__file__).resolve().parents[1] / "desktop-sandbox.py")
sandbox = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sandbox)


class FakeController(Controller):
    def __init__(self, directory, state="gaming"):
        self.mode = (1920, 1080, 120)
        self.state = state
        self.events = []
        self.error = None
        self.mode_file = Path(directory) / "resolution.json"

    def status(self):
        return {"ok": True, "state": self.state, "resolution": self.mode}

    def resize(self, mode):
        self.events.append(("resize", mode))

    def stop_game(self):
        self.events.append("stop")

    def start_game(self):
        self.events.append("start")
        self.state = "gaming"

    def sway(self, command):
        self.events.append(command)


class SessionTests(unittest.TestCase):
    def test_rendering_uses_only_target_installation_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            for username, gpu in (("player-a", "/dev/dri/renderD140"), ("player-b", "/dev/dri/renderD150")):
                home = Path(directory) / username
                install = home / ".local/share/headless-gaming"
                origins = f"https://{username}.example.invalid:47990"
                with patch("deploy.HOME_DIR", home), patch("deploy.INSTALL", install):
                    files = payload(gpu, origins)
                self.assertTrue(all(path.is_relative_to(home) for path in files))
                conf = files[home / ".config/sunshine/sunshine.conf"].decode()
                self.assertIn(f"adapter_name = {gpu}", conf)
                self.assertIn(origins, conf)
                sway = files[home / ".config/sway/config.headless"].decode()
                self.assertIn(str(install), sway)
                self.assertNotIn("@INSTALL@", sway)
                unit = files[home / ".config/systemd/user/headless-game-stream.service"].decode()
                self.assertIn(gpu, unit)
                self.assertNotIn("@GPU@", unit)

    def test_sandbox_runtime_uses_current_uid(self):
        with patch("os.getuid", return_value=23456):
            args = sandbox.build_args(Path("/private/home"), Path("/run/user/23456"), "wayland-7", {})
        self.assertIn("/run/user/23456/wayland-7", args)
        self.assertNotIn("/run/user/1000", args)

    def test_fresh_install_does_not_stop_missing_service(self):
        with patch("deploy.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "not-found\n")), patch("deploy.run") as stop:
            stop_session()
            stop.assert_not_called()

    def test_existing_service_is_stopped_before_update(self):
        with patch("deploy.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "loaded\n")), patch("deploy.run") as stop:
            stop_session()
            stop.assert_called_once_with("systemctl", "--user", "stop", "headless-game-stream.service")
    def test_desktop_mount_policy(self):
        args = sandbox.build_args(Path("/private/home"), Path("/run/user/1000"), "wayland-1", {})
        self.assertIn("--unshare-all", args)
        self.assertIn("--unshare-user", args)
        self.assertIn("--disable-userns", args)
        self.assertNotIn("--share-net", args)
        self.assertNotIn("--dev-bind", args)
        binds = [(args[i+1], args[i+2]) for i, arg in enumerate(args) if arg == "--bind"]
        self.assertEqual(binds, [("/private/home", "/home/desktop")])
        self.assertNotIn("SWAYSOCK", args)
        self.assertNotIn("DBUS_SESSION_BUS_ADDRESS", args)

    def test_all_desktop_launches_are_sandboxed(self):
        root = Path(__file__).resolve().parents[1]
        config = (root / "templates/config.headless").read_text()
        for action in ("terminal", "files", "menu"):
            self.assertIn("exec $desktop " + action, config)
        for forbidden in ("exec foot", "exec thunar", "exec wmenu-run"):
            self.assertNotIn(forbidden, config)
    def test_four_modes(self):
        for w, h in [(1280, 720), (1920, 1080), (3840, 1080), (1920, 1200)]:
            self.assertEqual(validate_mode(str(w), str(h), "60"), (w, h, 60))

    def test_invalid_modes_do_not_reach_commands(self):
        for values in [("1920;reboot", 1080, 60), (0, 0, 60), (1920, 1080, 0),
                       (1920, 1080, 241), (1920, 1080, "60.0"), (True, 1080, 60),
                       ("１９２０", 1080, 60)]:
            with self.assertRaises(ValueError):
                validate_mode(*values)

    def test_same_resolution_keeps_game(self):
        with tempfile.TemporaryDirectory() as directory:
            ctrl = FakeController(directory)
            ctrl.dispatch(dict(command="resolution", width=1920, height=1080, fps=120))
            self.assertEqual(ctrl.events, [])

    def test_changed_gaming_resolution_restarts_once(self):
        with tempfile.TemporaryDirectory() as directory:
            ctrl = FakeController(directory)
            ctrl.dispatch(dict(command="resolution", width=3840, height=1080, fps=60))
            self.assertEqual(ctrl.events, ["stop", ("resize", (3840, 1080, 60)), "start"])
            self.assertEqual(json.loads(ctrl.mode_file.read_text()), [3840, 1080, 60])

    def test_desktop_resize_does_not_launch_game(self):
        with tempfile.TemporaryDirectory() as directory:
            ctrl = FakeController(directory, "desktop")
            ctrl.dispatch(dict(command="resolution", width=1920, height=1200, fps=60))
            self.assertEqual(ctrl.events, [("resize", (1920, 1200, 60))])
            self.assertEqual(ctrl.state, "desktop")

    def test_failed_new_game_restores_previous_output(self):
        with tempfile.TemporaryDirectory() as directory:
            ctrl = FakeController(directory)
            def fail():
                raise RuntimeError("startup failed")
            ctrl.start_game = fail
            with self.assertRaises(RuntimeError):
                ctrl.dispatch(dict(command="resolution", width=1280, height=720, fps=60))
            self.assertEqual(ctrl.mode, (1920, 1080, 120))
            self.assertEqual(ctrl.state, "desktop")
            self.assertIn(("resize", (1920, 1080, 120)), ctrl.events)

    def test_unknown_operation_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            ctrl = FakeController(directory)
            with self.assertRaises(ValueError):
                ctrl.dispatch({"command": "exec", "args": "reboot"})
            self.assertEqual(ctrl.events, [])

    def test_conf_merge_keeps_unrelated_settings_and_is_idempotent(self):
        old = "# mine\nbitrate = 20000\ncapture = kms\ncapture = x11\n"
        merged = merge_conf(old, {"capture": "wlr", "output_name": "HEADLESS-1"})
        self.assertIn("bitrate = 20000", merged)
        self.assertIn("# mine", merged)
        self.assertEqual(merged.count("capture ="), 1)
        self.assertEqual(merged, merge_conf(merged, {"capture": "wlr", "output_name": "HEADLESS-1"}))

    def test_shortcut_roundtrip_preserves_other_entries(self):
        old_fields = [(1, b"AppName", b"Other game"), (2, b"appid", struct.pack("<I", 12345)),
                      (0, b"tags", [(1, b"0", b"Favorite")])]
        original = encode([(0, b"shortcuts", [(0, b"0", old_fields)])])
        self.assertEqual(encode(decode(original)), original)
        changed = update(original, Path("/example/install"))
        self.assertEqual(decode(changed)[0][2][0][2], old_fields)
        self.assertEqual(changed, update(changed, Path("/example/install")))
        self.assertEqual(len(decode(changed)[0][2]), 2)

    def test_unknown_vdf_type_refuses_change(self):
        with self.assertRaises(ValueError):
            update(b"\x05unknown\0data\x08", Path("/example/install"))


if __name__ == "__main__":
    unittest.main()
