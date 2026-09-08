#!/usr/bin/bash
set -euo pipefail
bundle_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s "$bundle_dir/tests" -v
bash -n "$bundle_dir/install.sh" "$bundle_dir/uninstall.sh" "$bundle_dir/setup-system.sh"
if [[ ${1:-} == --live ]]; then
    systemctl --user is-active headless-game-stream.service
    python3 "$HOME/.local/share/headless-gaming/sessionctl.py" status
    python3 "$HOME/.local/share/headless-gaming/desktop-sandbox.py" probe
    session_pid=$(systemctl --user show headless-game-stream.service -p MainPID --value)
    swaymsg -s "$XDG_RUNTIME_DIR/sway-ipc.$(id -u).$session_pid.sock" -t get_outputs -r
    flatpak override --user --show com.valvesoftware.Steam
    id
    ls -l /dev/uinput /dev/uhid
fi
