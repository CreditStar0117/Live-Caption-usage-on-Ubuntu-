#!/usr/bin/env bash
# Launch Caption English with local PortAudio (if not installed system-wide).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LIBDIR="${ROOT}/.local-libs/x86_64-linux-gnu"
if [[ -d "$LIBDIR" ]]; then
  # Ensure unversioned soname symlink exists for ctypes discovery
  if [[ -e "$LIBDIR/libportaudio.so.2" && ! -e "$LIBDIR/libportaudio.so" ]]; then
    ln -sf libportaudio.so.2 "$LIBDIR/libportaudio.so"
  fi
  export LD_LIBRARY_PATH="${LIBDIR}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
# Prefer project venv
if [[ -x "${ROOT}/.venv/bin/caption-english" ]]; then
  exec "${ROOT}/.venv/bin/caption-english" "$@"
fi
exec python3 -m caption_english "$@"
