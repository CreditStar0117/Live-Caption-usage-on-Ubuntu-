#!/usr/bin/env bash
# Download Ubuntu libportaudio2 into .local-libs (no sudo required).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cd "$TMP"
apt-get download libportaudio2
dpkg-deb -x libportaudio2_*.deb extract
mkdir -p "${ROOT}/.local-libs"
cp -a extract/usr/lib/. "${ROOT}/.local-libs/"
LIBDIR="${ROOT}/.local-libs/x86_64-linux-gnu"
if [[ -e "$LIBDIR/libportaudio.so.2" && ! -e "$LIBDIR/libportaudio.so" ]]; then
  ln -sf libportaudio.so.2 "$LIBDIR/libportaudio.so"
fi
echo "Installed PortAudio under ${ROOT}/.local-libs"
