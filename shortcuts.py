#!/usr/bin/python3
"""Add/remove one Steam shortcut while preserving existing binary VDF records.

Steam must be stopped by the caller. Unknown VDF types fail closed before any
write. No Steam account credentials or other configuration is modified.
"""
from pathlib import Path
import struct
import zlib

NAME = "Switch to Desktop"


def decode(blob):
    position = 0

    def cstring():
        nonlocal position
        end = blob.index(b"\0", position)
        value = blob[position:end]
        position = end + 1
        return value

    def object_():
        nonlocal position
        entries = []
        while position < len(blob):
            tag = blob[position]
            position += 1
            if tag == 8:
                return entries
            key = cstring()
            if tag == 0:
                value = object_()
            elif tag == 1:
                value = cstring()
            elif tag in (2, 3, 4, 6, 7, 10):
                size = 8 if tag in (7, 10) else 4
                value = blob[position:position + size]
                if len(value) != size:
                    raise ValueError("Truncated VDF scalar")
                position += size
            else:
                raise ValueError(f"Unsupported VDF type {tag}; existing shortcut file left untouched")
            entries.append((tag, key, value))
        raise ValueError("Missing VDF object terminator")

    result = object_()
    if position != len(blob):
        raise ValueError("Unexpected trailing bytes in VDF")
    return result


def encode(entries):
    result = bytearray()
    for tag, key, value in entries:
        result.extend(bytes([tag]) + key + b"\0")
        result.extend(encode(value) if tag == 0 else value + (b"\0" if tag == 1 else b""))
    return bytes(result) + b"\x08"


def update(blob, install_dir):
    entries = decode(blob) if blob else [(0, b"shortcuts", [])]
    root = next((v for t, k, v in entries if t == 0 and k == b"shortcuts"), None)
    if root is None:
        raise ValueError("Missing shortcuts root")
    for _, _, fields in root:
        if any(t == 1 and k.lower() == b"appname" and v == NAME.encode() for t, k, v in fields):
            # This package owns only its own named shortcut.
            fields[:] = shortcut_fields(install_dir)
            return encode(entries)
    index = str(max([int(k) for _, k, _ in root if k.isdigit()], default=-1) + 1).encode()
    root.append((0, index, shortcut_fields(install_dir)))
    return encode(entries)


def shortcut_fields(install_dir):
    exe = '"/usr/bin/python3"'
    appid = zlib.crc32((exe + NAME).encode()) | 0x80000000
    strings = {"AppName": NAME, "Exe": exe, "StartDir": f'"{install_dir}"',
               "icon": "", "ShortcutPath": "", "LaunchOptions": f'"{install_dir}/sessionctl.py" desktop',
               "DevkitGameID": ""}
    fields = [(2, b"appid", struct.pack("<I", appid))]
    fields += [(1, k.encode(), v.encode()) for k, v in strings.items()]
    fields += [(2, k.encode(), struct.pack("<I", v)) for k, v in {
        "IsHidden": 0, "AllowDesktopConfig": 1, "AllowOverlay": 0,
        "OpenVR": 0, "Devkit": 0, "LastPlayTime": 0}.items()]
    fields.append((0, b"tags", [(1, b"0", b"Session")]))
    return fields


def paths(home):
    userdata = home / ".var/app/com.valvesoftware.Steam/.local/share/Steam/userdata"
    return [profile / "config/shortcuts.vdf" for profile in userdata.glob("*") if profile.name.isdigit()]
