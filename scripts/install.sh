#!/usr/bin/env bash
# Install Caption English for the current user, independent of this checkout:
#   ~/.local/share/caption-english/venv   the app and its Python libraries
#   ~/.local/bin/caption-english          command that starts the app
#   ~/.local/share/applications/...       Applications-menu entry
# Run it again to upgrade. Remove with scripts/uninstall.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="${DATA}/caption-english"
VENV="${APP_DIR}/venv"
BIN_DIR="${HOME}/.local/bin"
LAUNCHER="${BIN_DIR}/caption-english"
DESKTOP_DIR="${DATA}/applications"
DESKTOP_FILE="${DESKTOP_DIR}/caption-english.desktop"

# grep without -q reads all input, so the producer never dies of SIGPIPE under pipefail
has_portaudio() { ldconfig -p | grep 'libportaudio\.so\.2' >/dev/null; }

# System packages the app needs but pip cannot provide
missing=()
python3 -c 'import venv, ensurepip' 2>/dev/null || missing+=(python3-venv)
python3 -c 'import gi; gi.require_version("Gtk", "4.0"); from gi.repository import Gtk' 2>/dev/null \
  || missing+=(python3-gi gir1.2-gtk-4.0)
command -v parec >/dev/null || missing+=(pulseaudio-utils)
if ! has_portaudio && [[ ! -d "${ROOT}/.local-libs" ]]; then
  missing+=(libportaudio2)
fi
if (( ${#missing[@]} )); then
  echo "Missing system packages. Install them, then run this script again:" >&2
  echo "  sudo apt install ${missing[*]}" >&2
  exit 1
fi
fc-list :lang=ko family | grep . >/dev/null \
  || echo "Note: no Korean font found; for Korean translation run: sudo apt install fonts-noto-cjk"

echo "Creating the app environment in ${VENV}…"
mkdir -p "${APP_DIR}"
# --system-site-packages: Ubuntu's PyGObject/GTK 4 come from apt, not pip
python3 -m venv --clear --system-site-packages "${VENV}"
"${VENV}/bin/pip" install --quiet --upgrade pip
echo "Installing Caption English and its libraries (this can take a few minutes)…"
# A regular (non-editable) install: the app keeps working if this checkout moves
"${VENV}/bin/pip" install --quiet "${ROOT}"

# PortAudio fetched without sudo by scripts/fetch-portaudio.sh
rm -rf "${APP_DIR}/lib"
if [[ -d "${ROOT}/.local-libs/x86_64-linux-gnu" ]] && ! has_portaudio; then
  cp -a "${ROOT}/.local-libs/x86_64-linux-gnu" "${APP_DIR}/lib"
fi

mkdir -p "${BIN_DIR}"
cat > "${LAUNCHER}" <<EOF
#!/usr/bin/env bash
# Start Caption English (installed by scripts/install.sh)
if [[ -d "${APP_DIR}/lib" ]]; then
  export LD_LIBRARY_PATH="${APP_DIR}/lib\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
fi
exec "${VENV}/bin/caption-english" "\$@"
EOF
chmod +x "${LAUNCHER}"

mkdir -p "${DESKTOP_DIR}"
# Absolute Exec path: ~/.local/bin is not on the desktop session's PATH everywhere
sed "s|^Exec=.*|Exec=\"${LAUNCHER}\"|" "${ROOT}/packaging/caption-english.desktop" > "${DESKTOP_FILE}"
update-desktop-database "${DESKTOP_DIR}" 2>/dev/null || true

version="$("${VENV}/bin/python" -c 'import caption_english; print(caption_english.__version__)')"
echo
echo "Installed Caption English ${version}."
echo "  Open it from the Applications menu (search \"Caption English\"),"
echo "  or run: ${LAUNCHER}"
