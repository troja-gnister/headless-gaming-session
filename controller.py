#!/usr/bin/python3
"""Own the gaming child; Sway and Sunshine outlive all mode transitions."""
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import time

MODES = {(1280, 720), (1920, 1080), (3840, 1080), (1920, 1200)}


def validate_mode(width, height, fps):
    values = (width, height, fps)
    if any(not str(v).isascii() or not str(v).isdigit() for v in values):
        raise ValueError("Width, height and FPS must be positive integers")
    w, h, rate = map(int, values)
    if (w, h) not in MODES or not 30 <= rate <= 240:
        raise ValueError("Allowed: 1280x720, 1920x1080, 3840x1080, 1920x1200; FPS 30-240")
    return w, h, rate


class Controller:
    def __init__(self):
        self.runtime = Path(os.environ["XDG_RUNTIME_DIR"]) / "headless-gaming"
        self.runtime.mkdir(mode=0o700, exist_ok=True)
        self.endpoint = self.runtime / "control.sock"
        self.state_dir = Path.home() / ".local/state/headless-gaming"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.mode_file = self.state_dir / "resolution.json"
        self.mode = (1920, 1080, 120)
        if self.mode_file.exists():
            try:
                self.mode = validate_mode(*json.loads(self.mode_file.read_text()))
            except (ValueError, TypeError):
                pass
        self.gamescope = None
        self.desktop_opened = False
        self.state = "desktop"
        self.error = None

    def sway(self, command):
        result = subprocess.run(["swaymsg", "-r", command], check=True, capture_output=True, text=True, timeout=8)
        if any(not entry.get("success", False) for entry in json.loads(result.stdout)):
            raise RuntimeError(f"Sway rejected {command}: {result.stdout}")

    def resize(self, mode):
        w, h, fps = mode
        self.sway(f"output HEADLESS-1 mode {w}x{h}@{fps}Hz")

    def running(self):
        return self.gamescope is not None and self.gamescope.poll() is None

    def stop_game(self):
        if self.running():
            self.gamescope.terminate()
            try:
                self.gamescope.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(self.gamescope.pid, signal.SIGKILL)
                self.gamescope.wait(timeout=5)
        # Flatpak/Proton may have separate sessions. This installation owns the
        # dedicated user's Steam instance, and must stop it before relaunching.
        subprocess.run(["flatpak", "kill", "com.valvesoftware.Steam"], capture_output=True, timeout=10)
        self.gamescope = None

    def start_game(self):
        if self.running():
            self.sway("workspace number 1")
            return
        self.sway("workspace number 1")
        w, h, fps = self.mode
        with (self.state_dir / "gamescope.log").open("a") as log:
            self.gamescope = subprocess.Popen([
                "gamescope", "-e", "-w", str(w), "-h", str(h), "-W", str(w), "-H", str(h),
                "-r", str(fps), "--force-grab-cursor", "--", "flatpak", "run",
                "com.valvesoftware.Steam", "-gamepadui"],
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True, close_fds=True)
        time.sleep(2)
        if not self.running():
            raise RuntimeError("Gamescope exited; inspect ~/.local/state/headless-gaming/gamescope.log")
        self.state = "gaming"
        self.error = None

    def desktop(self):
        self.stop_game()
        self.state = "desktop"
        self.sway("workspace number 2")
        if not self.desktop_opened:
            sandbox = Path(__file__).with_name("desktop-sandbox.py")
            self.sway(f'exec /usr/bin/python3 "{sandbox}" terminal')
            self.desktop_opened = True

    def status(self):
        return {"ok": True, "state": self.state, "resolution": list(self.mode),
                "gamescope_pid": self.gamescope.pid if self.running() else None,
                "controller_pid": os.getpid(), "error": self.error}

    def dispatch(self, data):
        command = data.get("command")
        if command == "status":
            return self.status()
        if command == "desktop":
            self.desktop()
        elif command == "gaming":
            self.resize(self.mode)
            self.start_game()
        elif command == "resolution":
            new_mode = validate_mode(data.get("width"), data.get("height"), data.get("fps"))
            if new_mode != self.mode:
                previous = self.mode
                was_gaming = self.state == "gaming"
                if was_gaming:
                    self.stop_game()
                try:
                    self.resize(new_mode)
                    self.mode = new_mode
                    if was_gaming:
                        self.start_game()
                except Exception:
                    self.mode = previous
                    self.resize(previous)
                    self.state = "desktop"
                    self.sway("workspace number 2")
                    raise
                temp = self.mode_file.with_suffix(".tmp")
                temp.write_text(json.dumps(self.mode) + "\n")
                temp.replace(self.mode_file)
        else:
            raise ValueError("Unknown session command")
        return self.status()

    def serve(self):
        # flock protects against a duplicate controller without unlinking the
        # live server's socket. All subprocess descriptors are closed at exec.
        import fcntl
        with (self.runtime / "controller.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.endpoint.unlink(missing_ok=True)
            with socket.socket(socket.AF_UNIX) as server:
                server.bind(str(self.endpoint))
                os.chmod(self.endpoint, 0o600)
                server.listen(8)
                server.settimeout(1)
                self.resize(self.mode)
                try:
                    self.start_game()
                except Exception as exc:
                    self.error = str(exc)
                    self.state = "desktop"
                while True:
                    if self.state == "gaming" and not self.running():
                        self.state = "desktop"
                        self.error = "Gamescope exited; desktop recovery available"
                        self.sway("workspace number 2")
                    try:
                        connection, _ = server.accept()
                    except socket.timeout:
                        continue
                    with connection:
                        connection.settimeout(5)
                        _, uid, _ = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                        if uid != os.getuid():
                            continue
                        try:
                            with connection.makefile("rb") as stream:
                                raw = stream.readline(4097)
                            if len(raw) > 4096:
                                raise ValueError("Request too large")
                            data = json.loads(raw)
                            if not isinstance(data, dict):
                                raise ValueError("Expected a command object")
                            # Ack desktop first: the client may be the Steam
                            # shortcut that the transition itself terminates.
                            if data.get("command") == "desktop":
                                connection.sendall(b'{"ok":true,"queued":"desktop"}\n')
                                time.sleep(0.3)
                                self.dispatch(data)
                            else:
                                result = self.dispatch(data)
                                connection.sendall(json.dumps(result).encode() + b"\n")
                        except Exception as exc:
                            self.error = str(exc)
                            print(f"session: {exc}", flush=True)
                            try:
                                connection.sendall(json.dumps({"ok": False, "error": str(exc)}).encode() + b"\n")
                            except OSError:
                                pass


if __name__ == "__main__":
    Controller().serve()
