# Compatibility and validation

The current implementation has been exercised on Fedora Server 44, x86_64,
with AMD RADV rendering and Mesa VAAPI encoding. These are software compatibility
notes, not a machine configuration or an OS image.

| Dependency | Tested version |
| --- | --- |
| Sunshine (pvermeer COPR) | 2026.516.143833-4.fc44 |
| Sway | 1.11-3.fc44 |
| Gamescope | 3.16.25-1.fc44 |
| Flatpak | 1.18.2-1.fc44 |
| Steam runtime | org.freedesktop.Platform 25.08 |
| PipeWire | 1.6.8-1.fc44 |
| WirePlumber | 0.5.14-1.fc44 |
| mesa-va-drivers-freeworld | 26.1.8-1.fc44 |
| foot | 1.27.0-1.fc44 |
| Thunar | 4.20.9-1.fc44 |
| wmenu | 0.2.0-3.fc44 |
| bubblewrap | 0.12.0-1.fc44 |
| dbus-daemon | 1.16.2-1.fc44 |

Select the target machine's render device when installing. A stable symlink
under `/dev/dri/by-path/` is preferable to a potentially changing renderD number.
Sunshine captures HEADLESS-1 through wlr and uses VAAPI encoding. Vulkan,
VAAPI codec support and headless buffer sharing must work on the target driver.
Intel has not been validated. An NVIDIA/NVENC deployment requires driver and
encoder changes; this bundle does not configure it automatically.

Verified:

- Installed from this bundle; reran installer successfully as an upgrade.
- Existing LAN and VPN CSRF origins preserved.
- Only HEADLESS-1 exists in Sway; physical display connectors are not configured.
- Flatpak socket client works with only the added narrow filesystem permissions.
- Actual Steam non-Steam shortcut launched through its steam://rungameid URI
  and caused Gaming -> Desktop.
- Restricted foot terminal and Thunar both appeared as ordinary Sway windows.
- Private home is writable, host mounts/home and control sockets are hidden,
  system programs are read-only, and network namespace has no host routes.
- All four modes passed desktop resize -> gaming launch -> same-mode reconnect.
- Gamescope command-line dimensions matched Sway's actual output mode.
- Sway, Sunshine and controller PIDs stayed unchanged across transitions.
- The live smoke test leaves Gaming Mode at 3840x1080@60.

Run `bash verify.sh` for the local tests. `bash verify.sh --live` checks the
installed service and sandbox. The optional disruptive test
`python3 tests/live_smoke.py --run` repeats mode transitions, launches the Steam
shortcut, and leaves Gaming Mode at 3840x1080@60. Save games before running it.

Scope of verification: current-host deployment, upgrade and live transitions
were exercised. A fresh Fedora installation was not provisioned in a VM, and
the rollback script was not used to revert this working deployment. The user
can confirm the visual layout and pointer/controller ergonomics through
Moonlight; the live checks observed Sway windows and actual process transitions.

When migrating an existing installation, review old udev rules and capabilities
separately. The host setup script supplies a 0660 input rule and does not add
CAP_SYS_ADMIN for wlr capture. Desktop sandboxes expose neither uinput nor host
control buses. The user installer preserves unrelated Steam Flatpak permissions.
