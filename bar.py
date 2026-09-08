#!/usr/bin/python3
"""Swaybar click targets; only fixed commands are executed."""
import json
import select
import subprocess
import sys
import time
from pathlib import Path
from sessionctl import request

print('{"version":1,"click_events":true}', flush=True)
print('[', flush=True)
first = True
while True:
    items = [{"name": "gaming", "full_text": "  Return to Gaming  ", "color": "#90ee90"},
             {"name": "terminal", "full_text": "  Terminal  "},
             {"name": "files", "full_text": "  Files  "},
             {"name": "apps", "full_text": "  Applications  "},
             {"full_text": time.strftime("  %a %H:%M  ")}]
    print(("" if first else ",") + json.dumps(items), flush=True)
    first = False
    if select.select([sys.stdin], [], [], 5)[0]:
        line = sys.stdin.readline().strip().lstrip(",")
        if not line:
            break
        try:
            click = json.loads(line)
            name = click.get("name")
            if name == "gaming":
                request("gaming")
            elif name in ("terminal", "files", "apps"):
                action = {"terminal": "terminal", "files": "files", "apps": "menu"}[name]
                subprocess.Popen(["python3", str(Path(__file__).with_name("desktop-sandbox.py")), action],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (ValueError, RuntimeError, OSError, AttributeError):
            pass
