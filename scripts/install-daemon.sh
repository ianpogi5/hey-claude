#!/usr/bin/env bash
# Install the heyclauded systemd user unit + D-Bus activation file,
# pointing at this checkout's venv. Re-run after moving the checkout.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
bin="$root/.venv/bin/heyclauded"

if [ ! -x "$bin" ]; then
    echo "error: $bin not found — run: .venv/bin/pip install -e ." >&2
    exit 1
fi

unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
dbus_dir="${XDG_DATA_HOME:-$HOME/.local/share}/dbus-1/services"
mkdir -p "$unit_dir" "$dbus_dir"

sed "s|@HEYCLAUDED@|$bin|" "$root/systemd/hey-claude.service.in" \
    > "$unit_dir/hey-claude.service"
sed "s|@HEYCLAUDED@|$bin|" "$root/systemd/org.kdc.HeyClaude.service.in" \
    > "$dbus_dir/org.kdc.HeyClaude.service"

systemctl --user daemon-reload
# dbus-broker (Fedora) won't see a new activatable service without a reload
busctl --user call org.freedesktop.DBus /org/freedesktop/DBus \
    org.freedesktop.DBus ReloadConfig >/dev/null || true

cat <<EOF
Installed:
  $unit_dir/hey-claude.service
  $dbus_dir/org.kdc.HeyClaude.service

The daemon now starts on demand (D-Bus activation) — any call wakes it:
  gdbus call --session --dest org.kdc.HeyClaude \\
      --object-path /org/kdc/HeyClaude --method org.kdc.HeyClaude.Toggle

Manual control:
  systemctl --user start|stop|status hey-claude
EOF
