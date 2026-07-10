#!/usr/bin/env bash
# Install (or update) the hey-claude GNOME Shell extension for this user.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
uuid="hey-claude@kdc.org"
dest="${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions/$uuid"

mkdir -p "$dest"
cp -r "$root/extension/." "$dest/"
glib-compile-schemas "$dest/schemas"

echo "Installed to $dest"

if gnome-extensions enable "$uuid" 2>/dev/null; then
    echo "Extension enabled."
    echo "If the icon doesn't appear, log out and back in (Wayland can't reload the shell)."
else
    echo "Enable failed — the running shell hasn't seen the new extension yet."
    echo "Log out and back in, then run: gnome-extensions enable $uuid"
fi
