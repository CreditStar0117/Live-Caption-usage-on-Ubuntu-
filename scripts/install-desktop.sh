#!/usr/bin/env bash
# Add Caption English (this checkout) to the Applications menu.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$DEST"
# Launch through run.sh so the project venv and local PortAudio are used
sed "s|^Exec=.*|Exec=\"${ROOT}/scripts/run.sh\"|" \
  "${ROOT}/packaging/caption-english.desktop" > "${DEST}/caption-english.desktop"
update-desktop-database "$DEST" 2>/dev/null || true
echo "Installed ${DEST}/caption-english.desktop"
