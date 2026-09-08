#!/usr/bin/python3
"""Opt-in live resolution test: stops Steam; restores the initial applied mode."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sessionctl import request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Acknowledge that Steam/games will stop")
    if not parser.parse_args().run:
        parser.error("Save and close games, then use --run")
    initial = request("status")
    if initial["state"] != "gaming" or initial.get("pending_resolution"):
        raise RuntimeError("Start in Gaming Mode without a pending resolution")
    original = initial["resolution"]
    target = (2560, 1440, 60) if original != [2560, 1440, 60] else (3440, 1440, 60)
    sway_pid = subprocess.check_output(["systemctl", "--user", "show", "headless-game-stream.service", "-p", "MainPID", "--value"], text=True).strip()
    sunshine_pids = subprocess.check_output(["pgrep", "-x", "sunshine"], text=True)
    ipc = f'{os.environ["XDG_RUNTIME_DIR"]}/sway-ipc.{os.getuid()}.{sway_pid}.sock'
    client = Path.home() / ".local/share/headless-gaming/sessionctl.py"

    def prep(mode):
        env = dict(os.environ, **dict(zip(("SUNSHINE_CLIENT_WIDTH", "SUNSHINE_CLIENT_HEIGHT", "SUNSHINE_CLIENT_FPS"), map(str, mode))))
        return subprocess.run([sys.executable, str(client), "resolution"], env=env, text=True, capture_output=True, timeout=55)

    def outputs():
        return json.loads(subprocess.check_output(["swaymsg", "-s", ipc, "-t", "get_outputs", "-r"], text=True))

    try:
        result = prep(target)
        assert result.returncode == 0, result.stderr
        state = json.loads(result.stdout)
        assert state["gamescope_pid"] == initial["gamescope_pid"]
        assert state["resolution"] == original and state["pending_resolution"] == list(target)
        rejected = prep((8192, 8192, 60))
        assert rejected.returncode != 0 and "8192x8192@60" in rejected.stderr
        assert request("status")["gamescope_pid"] == initial["gamescope_pid"]
        assert request("status")["pending_resolution"] == list(target)
        print("PASS Moonlight prep accepted a custom mode without restarting; unsafe mode rejected without changing state", flush=True)
        request("desktop")
        for _ in range(40):
            state = request("status")
            if state["state"] == "desktop" and state["resolution"] == list(target):
                break
            time.sleep(0.5)
        assert state["resolution"] == list(target) and state["pending_resolution"] is None
        mode = outputs()[0]["current_mode"]
        assert (mode["width"], mode["height"], mode["refresh"]) == (target[0], target[1], target[2] * 1000)
        state = request("gaming")
        pid = state["gamescope_pid"]
        assert pid is not None
        argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        assert argv[argv.index(b"-w") + 1] == str(target[0]).encode()
        assert argv[argv.index(b"-h") + 1] == str(target[1]).encode()
        assert json.loads(prep(target).stdout)["gamescope_pid"] == pid
        assert request("status")["controller_pid"] == initial["controller_pid"]
        assert subprocess.check_output(["pgrep", "-x", "sunshine"], text=True) == sunshine_pids
        assert [output["name"] for output in outputs()] == ["HEADLESS-1"]
        print("PASS queued custom mode applied to Sway and Gamescope; same-mode reconnect preserved PID; only HEADLESS-1 exists", flush=True)
    finally:
        state = request("resolution", width=original[0], height=original[1], fps=original[2], restart=True)
        if state["state"] != "gaming":
            state = request("gaming")
        assert state["resolution"] == original and state["pending_resolution"] is None
        print("Restored original mode: " + json.dumps(state), flush=True)


if __name__ == "__main__":
    main()
