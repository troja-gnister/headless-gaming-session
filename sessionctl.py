#!/usr/bin/python3
"""Small fixed-command client; also runs inside Steam's Flatpak runtime."""
import json
import os
from pathlib import Path
import socket
import sys
import syslog


def request(command, **params):
    endpoint = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "headless-gaming/control.sock"
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(50)
        connection.connect(str(endpoint))
        connection.sendall(json.dumps({"command": command, **params}).encode() + b"\n")
        with connection.makefile("rb") as stream:
            result = json.loads(stream.readline(65536))
    if not result.get("ok"):
        raise RuntimeError(result.get("error", "Session command failed"))
    return result


def main():
    args = sys.argv[1:]
    command = args.pop(0) if args else "status"
    params = {}
    if command == "resolution":
        restart = bool(args and args[-1] == "--restart")
        if restart:
            args.pop()
            if len(args) != 3:
                raise ValueError("--restart requires explicit WIDTH HEIGHT FPS; it stops Steam and games")
        values = args or [os.environ.get(f"SUNSHINE_CLIENT_{key}", "") for key in ("WIDTH", "HEIGHT", "FPS")]
        if len(values) != 3:
            raise ValueError("resolution requires WIDTH HEIGHT FPS")
        params = dict(zip(("width", "height", "fps"), values))
        if restart:
            params["restart"] = True
        syslog.openlog("headless-gaming")
        syslog.syslog(syslog.LOG_NOTICE, "Resolution request: " + json.dumps(params))
    elif args:
        raise ValueError("Unexpected arguments")
    print(json.dumps(request(command, **params), indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"headless-gaming: {exc}", file=sys.stderr)
        sys.exit(1)
