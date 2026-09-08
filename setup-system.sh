#!/usr/bin/bash
# Run as the intended gaming user. Requires sudo and network access.
set -euo pipefail
bundle_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if (( EUID == 0 )); then
    echo 'Run this as the gaming user, not root.' >&2
    exit 1
fi
sudo dnf install -y dnf-plugins-core
sudo dnf copr enable -y pvermeer/sunshine
fedora_release=$(rpm -E %fedora)
if ! rpm -q rpmfusion-free-release >/dev/null; then
    sudo dnf install -y "https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-${fedora_release}.noarch.rpm"
fi
mapfile -t gaming_packages < <(sed '/^#/d; /^$/d' "$bundle_dir/packages.txt")
# The freeworld VAAPI package replaces Fedora's codec-limited driver package.
if rpm -q mesa-va-drivers >/dev/null && ! rpm -q mesa-va-drivers-freeworld >/dev/null; then
    sudo dnf swap -y mesa-va-drivers mesa-va-drivers-freeworld
fi
sudo dnf install -y "${gaming_packages[@]}"
sudo flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
sudo flatpak install -y flathub com.valvesoftware.Steam
sudo usermod -aG input,video,render "$(id -un)"
sudo install -m 0644 "$bundle_dir/templates/99-z-headless-gaming.rules" /etc/udev/rules.d/99-z-headless-gaming.rules
sudo modprobe uinput
sudo modprobe uhid
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=misc
sudo udevadm trigger --subsystem-match=input
sudo loginctl enable-linger "$(id -un)"
echo 'Host provisioning complete. Reboot before the user install so its manager has the new groups.'
echo 'Sunshine wlr capture does not require adding CAP_SYS_ADMIN. Package-provided capabilities are left as installed.'
