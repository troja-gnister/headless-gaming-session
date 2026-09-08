#!/usr/bin/python3
"""Opt-in disruptive live test: stops Steam/games; leaves Gaming Mode active."""
import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sessionctl import request
from shortcuts import decode, paths, NAME


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Acknowledge this stops and starts the gaming session")
    args = parser.parse_args()
    if not args.run:
        parser.error("Use --run when no game progress needs preserving")
    sway_pid = command("systemctl", "--user", "show", "headless-game-stream.service", "-p", "MainPID", "--value")
    sunshine_pids = command("pgrep", "-x", "sunshine")
    controller_pid = request("status")["controller_pid"]
    ipc = f'{os.environ["XDG_RUNTIME_DIR"]}/sway-ipc.{os.getuid()}.{sway_pid}.sock'

    def outputs():
        return json.loads(command("swaymsg", "-s", ipc, "-t", "get_outputs", "-r"))

    def stable():
        assert command("systemctl", "--user", "show", "headless-game-stream.service", "-p", "MainPID", "--value") == sway_pid
        assert command("pgrep", "-x", "sunshine") == sunshine_pids
        assert request("status")["controller_pid"] == controller_pid
        assert [output["name"] for output in outputs()] == ["HEADLESS-1"]

    def wait_desktop():
        for _ in range(40):
            state = request("status")
            if state["state"] == "desktop" and state["gamescope_pid"] is None:
                return
            time.sleep(1)
        raise AssertionError("Desktop transition timed out")

    for width, height in [(1280, 720), (1920, 1080), (1920, 1200), (3840, 1080)]:
        request("desktop")
        wait_desktop()
        state = request("resolution", width=width, height=height, fps=60)
        assert state["state"] == "desktop" and state["gamescope_pid"] is None
        mode = outputs()[0]["current_mode"]
        assert (mode["width"], mode["height"], mode["refresh"]) == (width, height, 60000)
        started = request("gaming")
        pid = started["gamescope_pid"]
        assert pid is not None
        same = request("resolution", width=width, height=height, fps=60)
        assert same["gamescope_pid"] == pid
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        assert cmdline[cmdline.index(b"-W") + 1] == str(width).encode()
        assert cmdline[cmdline.index(b"-H") + 1] == str(height).encode()
        stable()
        print(f"PASS {width}x{height}@60: desktop resize, return to gaming, same-mode PID preserved", flush=True)
    # Allow Steam's UI and protocol handler to finish their final startup.
    time.sleep(20)
    shortcut_id = None
    for path in paths(Path.home()):
        if not path.exists():
            continue
        root = decode(path.read_bytes())
        for tag, key, shortcuts in root:
            if tag != 0 or key != b"shortcuts":
                continue
            for _, _, fields in shortcuts:
                if any(t == 1 and k.lower() == b"appname" and v == NAME.encode() for t, k, v in fields):
                    shortcut_id = next(struct.unpack("<I", v)[0] for t, k, v in fields if t == 2 and k == b"appid")
    assert shortcut_id is not None, "Steam shortcut missing"
    game_id = (shortcut_id << 32) | 0x02000000
    subprocess.run(["flatpak", "run", "com.valvesoftware.Steam", f"steam://rungameid/{game_id}"], timeout=20, check=True)
    wait_desktop()
    stable()
    print("PASS Steam library shortcut launched by steam://rungameid and reached Desktop Mode", flush=True)
    request("gaming")
    time.sleep(5)
    stable()
    result = request("status")
    assert result["gamescope_pid"] is not None and result["state"] == "gaming"
    print("PASS Sway, Sunshine and controller PIDs stayed unchanged; only HEADLESS-1 exists", flush=True)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
