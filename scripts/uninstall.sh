#!/usr/bin/env bash
# Remove what scripts/install.sh installed. Settings and downloaded models are kept
# (see the messages at the end for where they are).
set -euo pipefail

DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="${DATA}/caption-english"
LAUNCHER="${HOME}/.local/bin/caption-english"
DESKTOP_DIR="${DATA}/applications"
DESKTOP_FILE="${DESKTOP_DIR}/caption-english.desktop"

rm -rf "${APP_DIR}"
rm -f "${LAUNCHER}" "${DESKTOP_FILE}"
update-desktop-database "${DESKTOP_DIR}" 2>/dev/null || true

echo "Removed Caption English."
echo "Kept your settings: ${XDG_CONFIG_HOME:-$HOME/.config}/caption-english/"
echo "Kept downloaded models (shared with other apps): ~/.cache/huggingface/hub/"
