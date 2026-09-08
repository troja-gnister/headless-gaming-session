#!/usr/bin/python3
"""Desktop apps share only a private persistent home and one Wayland socket."""
import os
from pathlib import Path
import subprocess
import sys
import secrets


def build_args(desktop_home, runtime, display, data_fds):
    inner_runtime = f"/run/user/{os.getuid()}"
    args = ["bwrap", "--unshare-all", "--unshare-user", "--disable-userns", "--new-session", "--die-with-parent",
            "--cap-drop", "ALL", "--clearenv", "--hostname", "gaming-desktop",
            "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin",
            "--symlink", "usr/sbin", "/sbin", "--symlink", "usr/lib", "/lib",
            "--symlink", "usr/lib64", "/lib64", "--proc", "/proc", "--dev", "/dev",
            "--tmpfs", "/tmp", "--dir", "/etc", "--dir", "/home",
            "--bind", str(desktop_home), "/home/desktop",
            "--dir", "/run", "--dir", "/run/user", "--perms", "0700", "--dir", inner_runtime]
    for source in ("/etc/fonts", "/etc/ld.so.cache", "/etc/localtime"):
        if Path(source).exists():
            args += ["--ro-bind", source, source]
    for destination, fd in data_fds.items():
        args += ["--ro-bind-data", str(fd), destination]
    if display:
        args += ["--ro-bind", str(runtime / display), f"{inner_runtime}/{display}"]
    values = {"HOME": "/home/desktop", "USER": "desktop", "LOGNAME": "desktop",
              "PATH": "/usr/bin:/bin", "SHELL": "/bin/bash", "LANG": "C.UTF-8",
              "XDG_RUNTIME_DIR": inner_runtime, "XDG_SESSION_TYPE": "wayland",
              "XDG_CURRENT_DESKTOP": "sway", "GDK_BACKEND": "wayland",
              "GTK_USE_PORTAL": "0", "GSETTINGS_BACKEND": "keyfile",
              "TERM": "xterm-256color", "NO_AT_BRIDGE": "1"}
    if display:
        values["WAYLAND_DISPLAY"] = display
    for key, value in values.items():
        args += ["--setenv", key, value]
    return args + ["--chdir", "/home/desktop"]


PROBE = '''import json, os, pathlib, sys
p=pathlib.Path
assert os.environ["HOME"] == "/home/desktop"
host_home = p(sys.argv[1])
if host_home != p("/home/desktop"):
    assert not host_home.exists(), "Host home is visible"
    assert not (p("/proc/1/root") / str(host_home).lstrip("/")).exists(), "Host home visible through proc"
for item in ("/mnt", "/media", "/root", "/proc/1/root/mnt", "/run/dbus/system_bus_socket", "/run/user/%s/bus" % os.getuid(), "/run/user/%s/headless-gaming/control.sock" % os.getuid()):
    assert not p(item).exists(), item
assert sorted(x.name for x in p("/home").iterdir()) == ["desktop"]
try:
    p("/usr/.headless-write-probe").write_text("must not write")
except OSError:
    pass
else:
    raise AssertionError("System programs are writable")
marker=p("/home/desktop/.sandbox-probe")
marker.write_text("private home write test")
assert marker.read_text() == "private home write test"
marker.unlink()
assert "SWAYSOCK" not in os.environ and "DBUS_SESSION_BUS_ADDRESS" not in os.environ
assert len(p("/proc/net/route").read_text().splitlines()) == 1, "Unexpected network route"
print(json.dumps({"sandbox": "passed", "home": os.environ["HOME"], "host_mounts": "hidden", "host_control_sockets": "hidden", "network": "isolated", "usr": "read-only"}))
'''


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "terminal"
    if action == "menu":
        choice = subprocess.run(["wmenu", "-p", "Private desktop"], input="Terminal\nFiles\nReturn to Gaming\n",
                                text=True, capture_output=True)
        value = choice.stdout.strip()
        if choice.returncode or value not in ("Terminal", "Files", "Return to Gaming"):
            return 0
        if value == "Return to Gaming":
            from sessionctl import request
            request("gaming")
            return 0
        action = {"Terminal": "terminal", "Files": "files"}[value]
    if action not in ("terminal", "files", "probe"):
        raise ValueError("Only terminal, files, menu, and probe are supported")
    desktop_home = Path.home() / ".local/share/headless-desktop-home"
    if desktop_home.is_symlink():
        raise ValueError("Desktop home must not be a symlink")
    desktop_home.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name in ("Documents", "Downloads", "Desktop"):
        (desktop_home / name).mkdir(exist_ok=True)
    runtime = Path(os.environ["XDG_RUNTIME_DIR"])
    display = os.environ.get("WAYLAND_DISPLAY", "") if action != "probe" else ""
    if action != "probe" and (not display or Path(display).name != display or not (runtime / display).is_socket()):
        raise ValueError("Expected the private Sway Wayland display socket")
    contents = {"/etc/passwd": f"desktop:x:{os.getuid()}:{os.getgid()}:Private Desktop:/home/desktop:/bin/bash\n",
                "/etc/group": f"desktop:x:{os.getgid()}:\n",
                "/etc/nsswitch.conf": "passwd: files\ngroup: files\nhosts: files\n",
                "/etc/machine-id": secrets.token_hex(16) + "\n"}
    data_fds = {}
    for name, content in contents.items():
        fd = os.memfd_create("desktop-config")
        os.write(fd, content.encode())
        os.lseek(fd, 0, os.SEEK_SET)
        data_fds[name] = fd
    args = build_args(desktop_home, runtime, display, data_fds)
    if action == "terminal":
        command = ["foot", "--app-id=headless-desktop", "--title=Private Desktop Terminal", "/bin/bash", "--noprofile"]
    elif action == "files":
        command = ["dbus-run-session", "--", "thunar", "/home/desktop"]
    else:
        command = ["python3", "-c", PROBE, str(Path.home())]
    try:
        return subprocess.run(args + ["--"] + command, pass_fds=tuple(data_fds.values()), close_fds=True).returncode
    finally:
        for fd in data_fds.values():
            os.close(fd)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as exc:
        sys.exit(f"Desktop sandbox: {exc}")
