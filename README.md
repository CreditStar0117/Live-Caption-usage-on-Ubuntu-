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
- First run downloads a local Whisper model (`base.en`, ~150 MB). The optional Fast model, `tiny.en` (~75 MB), downloads the first time you use it. Audio and text stay on your machine.

## Install

```bash
git clone https://github.com/CreditStar0117/Live-Caption-usage-on-Ubuntu-.git
cd Live-Caption-usage-on-Ubuntu-
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

Press **Start**. Captions appear in the overlay as you hear them. The current phrase refreshes about twice a second and settles into final text when the speaker pauses. If the speaker keeps talking, finished sentences still settle after about 5 seconds, and no text stays unsettled for more than about 10 seconds. Earlier captions stay on screen until the overlay is full (see **Overlay size**). Press **Stop** to end captioning.

### Speech model

Choose the model under **Speech model** before pressing **Start**. The picker is locked while captioning.

- **Accurate (base.en)** is the default. On an 8-core desktop CPU, words usually appear about 0.8 s after they are spoken.
- **Fast (tiny.en)** shows words sooner (about 0.6 s) and uses about half the CPU, but makes more mistakes with noisy audio, accents or music. It downloads (~75 MB) the first time you start with it. The control window shows the download status.

The choice is saved and used on the next launch.

If audio capture or the speech model fails (no output device, device unplugged, broken model), the control window shows the error in red and captioning stops. Fix the cause and press **Start** again.

### Always on top (X11 / Wayland)

The overlay asks the window manager to keep it above other windows. On a GNOME **Wayland** session the app runs through XWayland automatically (`GDK_BACKEND=x11`) because Wayland has no always-on-top request for apps. To force native Wayland anyway, launch with `GDK_BACKEND=wayland`; the overlay will then behave like a normal window.

### Overlay size

- Drag the overlay window edges/corners to resize.
- Or set **Width** / **Height** (and presets) in the control window.
- Earlier captions stay on screen until the overlay is full. A larger overlay or smaller font keeps more history visible, and the oldest lines scroll off the top only when new text needs the space. The newest line is always visible at the bottom. Pressing **Start** again begins with an empty overlay.
- Size is saved under `~/.config/caption-english/config.json` and restored on next launch.

### Caption text

- Set **Font size** (12–72 px, default 22) in the control window’s **Caption text** box. The overlay redraws the current captions at the new size right away. The newest line stays in view.
- The font size is saved with the overlay size and restored on next launch.
- Sentences stay in one flowing paragraph, but each one ending in `.`, `?`, `!` or `…` is followed by a fixed wide gap (1.5× the font size) instead of a single space. Periods inside words or numbers, such as `3.5` or `example.com`, do not add a gap.

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

### Caption latency benchmark

`scripts/bench_latency.py` plays an English recording into the speech engine at real-time speed. It reports how long after each word is spoken the word first appears in the captions, and when it becomes final text. It needs `ffmpeg`, takes any format ffmpeg reads, and plays 90 s by default:

```bash
.venv/bin/python scripts/bench_latency.py talk.mp3                 # default model (base.en)
.venv/bin/python scripts/bench_latency.py talk.mp3 --model tiny.en --start 30 --seconds 60
```

On an 8-core desktop CPU with `base.en`, expect a median of about 0.8 s to first appearance and about 4 s to final text during continuous speech.

## Privacy

Transcription runs locally via `faster-whisper`. No audio is uploaded by this app.
