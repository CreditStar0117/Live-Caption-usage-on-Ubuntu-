# Caption English

Live English captions for Ubuntu. Captures microphone or system audio, transcribes locally with Whisper, and shows text in an always-on-top overlay whose **width** and **height** you control.

## Requirements (Ubuntu)

```bash
sudo apt update
sudo apt install -y \
  python3 python3-venv python3-pip python3-gi \
  gir1.2-gtk-4.0 \
  pipewire-pulse pulseaudio-utils \
  libportaudio2
```

- **PipeWire/PulseAudio** must be running (default on modern Ubuntu).
- System-audio captions record the default output’s **monitor** source with `parec` (from `pulseaudio-utils`). The microphone is read through PortAudio (`libportaudio2`).
- First run downloads a local Whisper model (`base.en`, ~150 MB). Audio and text stay on your machine.

## Install

```bash
cd Caption-English
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
pip install -e .
```

`--system-site-packages` is required so the venv can import Ubuntu’s `python3-gi` / GTK 4.

## Run

```bash
source .venv/bin/activate
# If libportaudio2 is not installed system-wide, use the helper:
./scripts/run.sh
# or, with system PortAudio:
caption-english
# or:
python -m caption_english
```

If you see `PortAudio library not found`, either install it (`sudo apt install libportaudio2`) or, without sudo, fetch a local copy and launch through the helper:

```bash
./scripts/fetch-portaudio.sh   # puts libportaudio under .local-libs/
./scripts/run.sh
```

### Captions

Press **Start**. Captions appear in the overlay as you hear them: the current phrase is refreshed about once a second and settles once the speaker pauses. The last few phrases stay on screen. Press **Stop** to end captioning.

If audio capture or the speech model fails (no output device, device unplugged, broken model), the control window shows the error in red and captioning stops. Fix the cause and press **Start** again.

### Always on top (X11 / Wayland)

The overlay asks the window manager to keep it above other windows. On a GNOME **Wayland** session the app runs through XWayland automatically (`GDK_BACKEND=x11`) because Wayland has no always-on-top request for apps. To force native Wayland anyway, launch with `GDK_BACKEND=wayland`; the overlay will then behave like a normal window.

### Overlay size

- Drag the overlay window edges/corners to resize.
- Or set **Width** / **Height** (and presets) in the control window.
- Size is saved under `~/.config/caption-english/config.json` and restored on next launch.

### Audio source

Choose **system**, **mic**, or **both** in the control window before starting.

## Desktop launcher

```bash
./scripts/install-desktop.sh
```

This installs `~/.local/share/applications/caption-english.desktop`, pointing at `scripts/run.sh` in this checkout (so the venv is used without activating it). Remove that file to uninstall the launcher.

Then launch **Caption English** from the app menu or:

```bash
gtk-launch caption-english
```

## Tests

```bash
source .venv/bin/activate
pip install -e .
python -m unittest discover -s tests -v
```

## Privacy

Transcription runs locally via `faster-whisper`. No audio is uploaded by this app.
