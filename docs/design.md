# Private gaming and desktop session

Approved design, 2026-09-08. One persistent headless Sway compositor and
Sunshine instance serve Moonlight. A user-owned Unix socket controller manages
Gamescope/Flatpak Steam. Gaming and desktop are workspaces of the same Sway;
the physical DRM connectors are never configured by this software.

Gaming -> Desktop stops Gamescope/Steam and reveals workspace 2. Desktop ->
Gaming starts Gamescope at the most recent requested resolution. Desktop
windows are retained on workspace 2. Only Gamescope is automatically fullscreen.
The Sway bar offers return-to-gaming, terminal, files, and a fixed action menu.
Mod+Shift+G returns to gaming; Mod+Shift+D switches to desktop.

Moonlight app preparation sends width, height and FPS to the controller.
Allowed sizes: 1280x720, 1920x1080, 3840x1080, 1920x1200. FPS: integer 30-240.
Same-mode reconnect preserves the running game. Changed mode restarts Gaming
Mode; in Desktop Mode it only resizes Sway. Application prep runs on a fresh
Moonlight app launch, not necessarily on Resume.

Flatpak receives access to the controller socket directory and a read-only
client script. Steam's non-Steam shortcut uses Python in its existing runtime.
No host-command D-Bus permission is needed. The server accepts only fixed
operations, validates dimensions, checks peer UID, serializes transitions,
tracks its own child process, and closes descriptors when spawning children.

Desktop access constraint added by user: terminal and file manager must not
access host data outside home. A dedicated desktop home at
~/.local/share/headless-desktop-home is mounted as /home/desktop in bubblewrap.
Both apps and all descendants share this home. /usr and selected library/font
configuration are read-only; /tmp, /dev and /proc are private. Host home,
storage mounts, host processes, system/session D-Bus, Sway IPC, controller socket
and network are hidden. One Wayland socket is shared for display/input. Every
bar action and keyboard binding uses the same sandbox launcher. Application
menu choices are a fixed allowlist. No unrestricted run-command launcher exists.
This changes desktop app access only; Steam retains its existing Flatpak access.

Installer renders user/GPU-specific templates, merges owned Sunshine keys,
preserves unrelated apps/settings, and backs up modified files. Pairing and
account secrets remain outside the source bundle. Rollback restores the
deployment backup. Package removal is not part of uninstall.

Verification: parser/validation/socket tests, syntax, deployment dry run,
idempotent installation, live output and window inspection, Flatpak client
access, both transitions, all four modes, same-mode PID retention, and
unchanged Sway/Sunshine PIDs during transitions.
