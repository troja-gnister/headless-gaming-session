#!/usr/bin/python3
"""Repeatable user deployment, snapshot rollback, and offline Steam shortcut."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.parse import urlsplit
from shortcuts import paths as shortcut_paths, update as update_shortcut

SOURCE = Path(__file__).resolve().parent
HOME_DIR = Path.home()
INSTALL = HOME_DIR / ".local/share/headless-gaming"
STATE = HOME_DIR / ".local/state/headless-gaming"
SERVICE = "headless-game-stream.service"


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def stop_session():
    result = subprocess.run(["systemctl", "--user", "show", SERVICE, "-p", "LoadState", "--value"],
                            check=True, capture_output=True, text=True)
    if result.stdout.strip() != "not-found":
        run("systemctl", "--user", "stop", SERVICE)


def render(text, gpu):
    return text.replace("@INSTALL@", str(INSTALL)).replace("@GPU@", gpu)


def merge_conf(text, settings):
    remaining = dict(settings)
    lines = []
    seen = set()
    for line in text.splitlines():
        key = line.split("=", 1)[0].strip()
        if key in settings:
            if key not in seen:
                lines.append(f"{key} = {settings[key]}")
                seen.add(key)
            remaining.pop(key, None)
        else:
            lines.append(line)
    lines.extend(f"{key} = {value}" for key, value in remaining.items())
    return "\n".join(lines) + "\n"


def payload(gpu, origins):
    files = {}
    for name in ("controller.py", "sessionctl.py", "bar.py", "desktop-sandbox.py"):
        files[INSTALL / name] = (SOURCE / name).read_bytes()
    files[HOME_DIR / ".config/sway/config.headless"] = render((SOURCE / "templates/config.headless").read_text(), gpu).encode()
    files[HOME_DIR / ".config/systemd/user" / SERVICE] = render((SOURCE / "templates" / SERVICE).read_text(), gpu).encode()
    conf = HOME_DIR / ".config/sunshine/sunshine.conf"
    existing = conf.read_text() if conf.exists() else ""
    if not origins:
        origins = next((line.split("=", 1)[1].strip() for line in existing.splitlines()
                        if line.split("=", 1)[0].strip() == "csrf_allowed_origins"), "")
    if not origins:
        raise ValueError("Supply --origins with your LAN/VPN HTTPS origins on a fresh install")
    for origin in origins.split(","):
        parsed = urlsplit(origin.strip())
        if parsed.scheme != "https" or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username:
            raise ValueError(f"Expected an HTTPS origin without path: {origin}")
    files[conf] = merge_conf(existing, {"capture": "wlr", "output_name": "HEADLESS-1", "encoder": "vaapi",
                                     "adapter_name": gpu, "csrf_allowed_origins": origins}).encode()
    apps_path = HOME_DIR / ".config/sunshine/apps.json"
    apps = json.loads(apps_path.read_text()) if apps_path.exists() else {"apps": []}
    desktop = next((app for app in apps["apps"] if app.get("name") == "Desktop"), None)
    if desktop is None:
        desktop = {"name": "Desktop", "image-path": "desktop.png"}
        apps["apps"].append(desktop)
    prep = [step for step in desktop.get("prep-cmd", [])
            if "sunshine-mode-switch" not in step.get("do", "") and "headless-gaming/sessionctl.py" not in step.get("do", "")]
    prep.append({"do": f'/usr/bin/python3 "{INSTALL}/sessionctl.py" resolution --restart', "undo": ""})
    desktop["prep-cmd"] = prep
    files[apps_path] = (json.dumps(apps, indent=2) + "\n").encode()
    for name, title, action in (("return-to-gaming", "Return to Gaming Mode", "gaming"),
                                ("switch-to-desktop", "Switch to Desktop", "desktop")):
        files[HOME_DIR / f".local/share/applications/headless-{name}.desktop"] = (
            f'[Desktop Entry]\nType=Application\nName={title}\nExec=/usr/bin/python3 "{INSTALL}/sessionctl.py" {action}\n'
            'Icon=applications-games\nTerminal=false\nCategories=Game;\n').encode()
    override = HOME_DIR / ".local/share/flatpak/overrides/com.valvesoftware.Steam"
    # Let Flatpak merge permissions using its own tool after the snapshot.
    files[override] = None
    return files


def snapshot(files):
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup = STATE / "backups" / time.strftime("%Y%m%d-%H%M%S")
    backup.mkdir(parents=True, mode=0o700)
    manifest = {"files": [], "enabled": subprocess.run(["systemctl", "--user", "is-enabled", SERVICE], capture_output=True).returncode == 0,
                "active": subprocess.run(["systemctl", "--user", "is-active", SERVICE], capture_output=True).returncode == 0}
    for index, path in enumerate(files):
        if path.is_symlink():
            raise ValueError(f"Refusing to overwrite symlink {path}")
        record = {"path": str(path), "backup": None}
        if path.exists():
            name = f"{index}.original"
            shutil.copy2(path, backup / name)
            record["backup"] = name
        manifest["files"].append(record)
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return backup, manifest


def replace_file(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".headless-tmp")
    temp.write_bytes(content)
    os.chmod(temp, 0o644)
    temp.replace(path)


def install(args):
    if not args.gpu or not Path(args.gpu).is_char_device():
        raise ValueError("--gpu must name your gaming GPU's render device; inspect /dev/dri/by-path/*-render")
    files = payload(args.gpu, args.origins)
    if args.dry_run:
        print("Would back up and deploy:\n" + "\n".join(map(str, files)))
        print("Would stop the private session, merge Steam shortcut, add narrow Flatpak filesystem access, enable and start service.")
        return
    for binary in ("sway", "sunshine", "gamescope", "foot", "thunar", "wmenu", "flatpak", "swaybar", "bwrap", "dbus-run-session"):
        if not shutil.which(binary):
            raise ValueError(f"Missing dependency {binary}; see packages.txt / setup-system.sh")
    run("flatpak", "info", "com.valvesoftware.Steam", stdout=subprocess.DEVNULL)
    # Validate every existing shortcut before stopping the working service.
    for path in shortcut_paths(HOME_DIR):
        files[path] = update_shortcut(path.read_bytes() if path.exists() else b"", INSTALL)
    backup, manifest = snapshot(files)
    print(f"Rollback backup: {backup}", flush=True)
    stop_session()
    subprocess.run(["flatpak", "kill", "com.valvesoftware.Steam"], capture_output=True)
    time.sleep(1)
    # Re-read after Steam is stopped, since shutdown may flush shortcuts.vdf.
    for path in shortcut_paths(HOME_DIR):
        record = next(item for item in manifest["files"] if item["path"] == str(path))
        if path.exists():
            record["backup"] = record["backup"] or f"shortcut-{path.parent.parent.name}.original"
            shutil.copy2(path, backup / record["backup"])
        files[path] = update_shortcut(path.read_bytes() if path.exists() else b"", INSTALL)
    try:
        for path, content in files.items():
            if content is not None:
                replace_file(path, content)
        (Path(os.environ["XDG_RUNTIME_DIR"]) / "headless-gaming").mkdir(mode=0o700, exist_ok=True)
        run("flatpak", "override", "--user", "--filesystem=xdg-run/headless-gaming", f"--filesystem={INSTALL}:ro", "com.valvesoftware.Steam")
        for record in manifest["files"]:
            path = Path(record["path"])
            record["installed_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        (backup / "manifest.json").write_text(json.dumps(manifest, indent=2))
        (STATE / "latest-backup").write_text(str(backup) + "\n")
        run("systemctl", "--user", "daemon-reload")
        run("systemctl", "--user", "enable", "--now", SERVICE)
    except Exception:
        (backup / "manifest.json").write_text(json.dumps(manifest, indent=2))
        print(f"Deployment failed; restore with: ./uninstall.sh --backup {backup}", file=sys.stderr)
        raise
    print("Installed. Steam library shortcut: Switch to Desktop. Desktop bar: Return to Gaming.")
    if not shortcut_paths(HOME_DIR):
        print("Log in to Steam once, then run ./install.sh --shortcut-only to add the shortcut.")


def rollback(args):
    backup = Path(args.backup) if args.backup else Path((STATE / "latest-backup").read_text().strip())
    manifest = json.loads((backup / "manifest.json").read_text())
    for item in manifest["files"]:
        path = Path(item["path"])
        if not path.is_relative_to(HOME_DIR) or path == HOME_DIR:
            raise ValueError("Invalid rollback target")
        if path.exists() and item.get("installed_sha256") and hashlib.sha256(path.read_bytes()).hexdigest() != item["installed_sha256"]:
            # Steam legitimately updates timestamps in its own shortcut DB.
            if path.name != "shortcuts.vdf":
                raise ValueError(f"Changed since deployment: {path}. Save/reconcile it before rollback.")
    stop_session()
    subprocess.run(["flatpak", "kill", "com.valvesoftware.Steam"], capture_output=True)
    # Keep a recovery copy of current files, including any Steam shortcut changes.
    snapshot([Path(item["path"]) for item in manifest["files"]])
    for item in manifest["files"]:
        path = Path(item["path"])
        if item["backup"]:
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup / item["backup"], path)
        else:
            path.unlink(missing_ok=True)
    run("systemctl", "--user", "daemon-reload")
    if manifest["enabled"]:
        run("systemctl", "--user", "enable", SERVICE)
    else:
        subprocess.run(["systemctl", "--user", "disable", SERVICE], capture_output=True)
    if manifest["active"]:
        run("systemctl", "--user", "start", SERVICE)
    print(f"Restored {backup}. Packages and host udev/group configuration retained.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpu")
    parser.add_argument("--origins")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--backup")
    parser.add_argument("--shortcut-only", action="store_true")
    args = parser.parse_args()
    if os.getuid() == 0:
        parser.error("Run as the gaming user, not root. setup-system.sh handles privileged provisioning.")
    if args.rollback:
        rollback(args)
    elif args.shortcut_only:
        stop_session()
        subprocess.run(["flatpak", "kill", "com.valvesoftware.Steam"], capture_output=True)
        files = {path: update_shortcut(path.read_bytes() if path.exists() else b"", INSTALL) for path in shortcut_paths(HOME_DIR)}
        if not files:
            raise ValueError("No Steam profile found; log in first")
        snapshot(files)
        for path, content in files.items():
            replace_file(path, content)
        run("systemctl", "--user", "start", SERVICE)
    else:
        install(args)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        sys.exit(f"Deployment error: {exc}")
