# Headless gaming session for Fedora Server

One private Sway desktop, host Sunshine, and Gamescope + Flatpak Steam.
The physical DisplayPort monitor stays on the existing TTY. All streaming
uses Sway's `HEADLESS-1` output and Sunshine `capture = wlr`.

This folder is the complete source bundle: it can be copied or committed to
Git without exporting a configured host's files. Usernames, home paths, GPU
devices and trusted web origins are resolved or supplied at installation time.

## Supported systems

Designed and tested on Fedora Server 44, x86_64, with AMD Vulkan/RADV rendering
and Mesa VAAPI encoding. The target must support unprivileged user namespaces,
systemd user services, headless Sway and Sunshine's wlr capture backend.
Package sources are Fedora, RPM Fusion Free, the pvermeer/sunshine COPR and
Flathub. Vulkan rendering, VAAPI codec support and headless buffer sharing must
work on the target driver. Intel has not been validated; NVIDIA/NVENC requires
driver and encoder changes that this bundle does not configure automatically.

It is not a universal installer for every machine: other distributions,
non-VAAPI encoders (such as NVIDIA NVENC), and untested drivers need adaptation.
Remote package versions are not pinned, so this reproduces the configuration
and workflow rather than an identical operating-system image.

### Tested dependency versions

These versions describe the validated software stack; they are not package pins.

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

## Daily use

In Moonlight, launch **Desktop**. This tile serves either current session mode.
In Steam's library, launch **Switch to Desktop** (under non-Steam games / Session).
In Sway, click **Return to Gaming** in the bottom bar to start Gamescope/Steam.
This is a library shortcut, not an alteration of Steam's power menu.

The bar also has Terminal, Files and Applications. Sway's modifier is the
Windows/Super key: Super+Return opens a terminal, Super+D opens applications,
Super+E opens files, Super+Shift+G enters Gaming Mode, Super+Shift+D enters
Desktop Mode. Desktop windows stay on workspace 2 while gaming uses workspace 1.
Save game progress before switching; switching to Desktop stops Steam/games.

### Restricted desktop access

Terminal and Thunar run in bubblewrap and share a separate persistent home:
`~/.local/share/headless-desktop-home` on the host, displayed as `/home/desktop`
inside the desktop apps. Copy files into that folder from the host when needed.
They cannot browse the host user's home, `/mnt`, `/media`, other users'
homes, container data, or host process filesystem. System programs/libraries
under `/usr` and selected font/loader configuration are exposed read-only so
the apps can run. Temporary files and process/device views are private.

There is no network, host D-Bus, Sway IPC or session-control socket inside these
apps. `sudo`, host `systemctl`, mounting storage and remote filesystem access
are unavailable. Commands and applications launched from the terminal or Thunar
inherit the sandbox. The Applications menu deliberately offers only Terminal,
Files and Return to Gaming. Host control actions live in Sway's bar/keybindings.

This is a filesystem/process sandbox sharing the host kernel and the private
Sway Wayland socket, not a VM. Steam retains its existing Flatpak permissions;
these new restrictions apply to desktop apps. No extra host user is created.
The desktop home is kept on uninstall. To test the restrictions:
`python3 ~/.local/share/headless-gaming/desktop-sandbox.py probe`.

### Dynamic resolutions

Moonlight can request any resolution within configurable safety limits; there
is no resolution allowlist. The original 1280x720, 1920x1080, 3840x1080 and
1920x1200 choices remain useful client presets, not server restrictions.

Each **new Moonlight application launch** applies the requested resolution/FPS
immediately. In Gaming Mode, a changed mode restarts Gamescope/Steam; an identical
request keeps it running. **Save and close your game before launching with a
different mode**, since the restart also stops games. In Desktop Mode only Sway
is resized. No Desktop/Gaming round trip is required to apply a Moonlight mode.

**Resume** preserves the existing host session and does not rerun the preparation
command. Merely disconnecting and reconnecting can therefore retain the old host
resolution. To apply changed Moonlight settings, quit the current Moonlight app
session and launch **Desktop** again instead of choosing Resume.

`sessionctl.py status` reports both `resolution` and `pending_resolution`.
Only successfully applied modes are saved across service restarts. The service
starts in Gaming Mode on boot. No config editing is needed per resolution.

Default limits require even width/height (encoder compatibility), width
320–8192, height 200–8192, at most 33,177,600 pixels, and integer FPS 1–240.
These are safety ceilings, **not a guarantee that a GPU/codec/client supports
every combination**. Excessive resolutions or FPS can still overload encoding,
rendering or network capacity; unusual aspect ratios can affect game UI layout.
Odd dimensions are rejected explicitly, not silently rounded.

Optional overrides go in `~/.config/headless-gaming/limits.json` (or under
`$XDG_CONFIG_HOME`), outside this source bundle. Only the keys you want to change
are needed. The controller rereads this file on each resolution request, and
the installer preserves it. For example:

```json
{
  "max_width": 5120,
  "max_height": 2880,
  "max_pixels": 14745600,
  "max_fps": 144
}
```

Supported keys are `min_width`, `min_height`, `max_width`, `max_height`,
`max_pixels`, `min_fps`, `max_fps`; values must be positive integers.
Rejected requests include the requested dimensions/FPS and the failed limit
in the log. Invalid requests do not stop the game or replace a queued mode.

For an intentional immediate change from the host, after saving/closing games:

```bash
python3 ~/.local/share/headless-gaming/sessionctl.py resolution 2560 1440 144 --restart
```

The installed Sunshine prep command is `sessionctl.py resolution --restart`;
it reads `SUNSHINE_CLIENT_WIDTH`, `SUNSHINE_CLIENT_HEIGHT`, and
`SUNSHINE_CLIENT_FPS`. `--restart` explicitly permits stopping Steam/games when
the requested mode differs.

For manual host commands **without** `--restart`, the conservative queueing
behavior remains available: a changed mode waits while Gamescope is running
(even at Steam's menu). Switch to Desktop to apply it, then return to Gaming.
The latest valid manual request replaces the pending one; requesting the active
mode cancels it. Pending requests are in memory only. Normal Moonlight launches
use `--restart` and do not enter this queue.

## Reproduce on a fresh Fedora Server

Clone or copy this folder and enter it. Run as your trusted gaming user, not
root. Host provisioning uses sudo and installs the dependencies in packages.txt:

```bash
bash setup-system.sh
# Reboot, then log back in as the same user.
```

Select the target GPU and the exact HTTPS origins used to access Sunshine's
web interface. An origin includes the hostname or IP and port, without a path.
Multiple LAN/VPN origins are comma-separated. Enter machine settings when
prompted; they are not saved into this source folder:

```bash
ls -l /dev/dri/by-path/
read -r -p 'Gaming GPU render-device path: ' gaming_gpu
read -r -p 'Sunshine HTTPS origins (comma-separated, port 47990): ' gaming_origins
bash install.sh --gpu "$gaming_gpu" --origins "$gaming_origins" --dry-run
bash install.sh --gpu "$gaming_gpu" --origins "$gaming_origins"
bash verify.sh --live
```

Choose a render node belonging to the intended GPU, not its card node. The
installer substitutes the home path and uses the current user's UID. Render-node
numbers can change after hardware changes; prefer a stable `*-render` symlink
under `/dev/dri/by-path/` when available. The path is hardware-specific and must
be chosen again on a different machine.

After first Steam login, if no profile existed when installing, run
`bash install.sh --shortcut-only` to add the shortcut. It stops the private
session briefly while Steam's shortcut file is updated. Configure Sunshine's
web login and pair Moonlight through its UI. Certificates, passwords, pairings,
Steam accounts, games, and Proton prefixes are intentionally not bundled.

`setup-system.sh` enables the pvermeer/sunshine COPR, RPM Fusion Free, and
Flathub. Review that script before running on a new host. It installs the
dependencies in packages.txt, including the freeworld VAAPI codec driver,
adds the user to input/video/render, installs input rules, and enables lingering.
Input group membership grants access to host input devices: use a trusted
dedicated gaming account. The scripts never run Steam or Sway as root.

Network/firewall policy is site-specific and is not reset by this bundle.
If Fedora's packaged Sunshine firewalld service is present, allow it only in
the intended LAN/VPN zone (`sudo firewall-cmd --get-services` to check).
Ensure Moonlight can reach the server on the Sunshine ports; see upstream:
https://docs.lizardbyte.dev/projects/sunshine/latest/md_docs_2getting__started.html
The management UI uses HTTPS port 47990. CSRF origins and firewall access are
separate settings. Existing LAN/VPN CSRF origins are retained unless overridden.

## Install/update/rollback

Run `bash install.sh --gpu ...` again to deploy changes. With no `--origins`,
the existing allowed origins are preserved. It merges owned Sunshine keys and
the Desktop prep command, preserves other settings/apps and Steam shortcuts,
and adds only socket-directory and read-only client-folder Flatpak access.
It does not grant Steam arbitrary host execution permission.

Before changes, files are copied into
`~/.local/state/headless-gaming/backups/<timestamp>/`. This directory may contain
private configuration and belongs outside this source folder. The installer
prints its backup path. It restarts the private user service after deployment.

```bash
bash uninstall.sh
# Or restore a specific deployment:
read -r -p 'Deployment backup directory to restore: ' gaming_backup
bash uninstall.sh --backup "$gaming_backup"
```

Uninstall restores the previous user configuration (or removes package-owned
files on a fresh install), service enablement and Flatpak override snapshot.
It keeps another snapshot of the files it is replacing. It refuses to overwrite
manually changed configuration until reconciled. Steam's shortcut file is
restored as a snapshot, so later shortcut changes are retained only in the
recovery backup. Packages, repositories, host udev rule, group membership,
lingering, games, and saved data are retained. Removing those shared host
settings requires a separate decision; this script does not remove them.

When migrating an existing installation, review old udev rules and capabilities
separately. The host setup script supplies a 0660 input rule and does not add
CAP_SYS_ADMIN for wlr capture. Desktop sandboxes expose neither uinput nor host
control buses. Unrelated Steam Flatpak permissions are preserved.

## Files and responsibilities

| File | Purpose |
| --- | --- |
| controller.py | Owns Gamescope child, validates requests, switches workspaces |
| sessionctl.py | Fixed-command Unix socket client, usable from Steam Flatpak |
| bar.py | Clickable Swaybar actions |
| desktop-sandbox.py | Home-scoped terminal/file manager and fixed application menu |
| deploy.py, install.sh, uninstall.sh | Render, snapshot, deploy, restore |
| shortcuts.py | Preserve/merge Steam binary shortcuts while Steam is stopped |
| setup-system.sh, packages.txt | Host packages, repositories, input permissions |
| templates/ | Sway, service, udev source configurations |
| tests/, verify.sh | Automated and live checks |

The runtime scripts deploy to `~/.local/share/headless-gaming/`; configurations
deploy to the usual `~/.config/{sway,sunshine,systemd/user}/` paths. The source
folder is the reproducible bundle, not a relocated operating-system runtime.
No files outside this source folder are needed to deploy it, apart from the
listed dependencies and the target machine's installation settings.

## Troubleshooting

```bash
python3 ~/.local/share/headless-gaming/sessionctl.py status
python3 ~/.local/share/headless-gaming/sessionctl.py desktop
python3 ~/.local/share/headless-gaming/sessionctl.py gaming
python3 ~/.local/share/headless-gaming/sessionctl.py resolution 3840 1080 60
journalctl --user -u headless-game-stream.service -b --no-pager -n 150
tail -100 ~/.local/state/headless-gaming/gamescope.log
journalctl -t headless-gaming -b --no-pager -n 30
systemctl --user restart headless-game-stream.service
```

The controller's socket is `$XDG_RUNTIME_DIR/headless-gaming/control.sock`.
It is user-only, checks peer UID, and accepts status/desktop/gaming/resolution.
Normal switching keeps Sway/Sunshine alive. A whole-service restart disconnects
the stream. A Gamescope failure reveals Sway so you can retry Gaming Mode.
If the controller itself fails, restart the whole user service.

Use a keyboard/mouse or Moonlight's mouse emulation in Desktop Mode. Raw gamepad
buttons do not navigate Sway automatically after Steam Input exits.

## Verification

Run the local checks without changing a running session:

```bash
bash verify.sh
```

Check the installed service, current output, Flatpak permissions and desktop
sandbox restrictions:

```bash
bash verify.sh --live
```

For a full transition test, save and close games first. This test stops and
starts Steam, exercises all four resolutions, checks same-mode reconnects,
and launches the actual Steam library shortcut. It leaves Gaming Mode running
at 3840x1080, 60 Hz:

```bash
python3 tests/live_smoke.py --run
```

The focused dynamic-resolution test runs the installed Sunshine prep command
with Moonlight-style environment inputs and checks immediate mode application,
same-mode PID preservation, manual queueing, rejection of unsafe requests, and
a custom mode through Sway and Gamescope. It stops/starts Steam; close games
first. It restores the initial applied resolution:

```bash
python3 tests/live_resolution.py --run
```

Deployment, repeat installation, both desktop windows, the Steam shortcut,
all four resolutions and desktop sandbox restrictions have been exercised.
Live checks confirmed that Sway, Sunshine and the controller kept the same PIDs
through mode transitions and that only HEADLESS-1 was configured. Confirm the
visual layout and input behavior through Moonlight on your target machine.

A fresh Fedora installation has not been provisioned in a VM for validation,
and the rollback script has not been exercised against the running deployment.
Fedora, COPR, RPM Fusion, Steam and Flatpak updates can change compatibility.
