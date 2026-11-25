# Caption English

Live English captions for Ubuntu. Captures microphone or system audio, transcribes locally with Whisper, and shows text in an always-on-top overlay whose **width** and **height** you control. Optionally translates the captions into **Korean**, also on your own computer.

## Requirements (Ubuntu)

```bash
sudo apt update
sudo apt install -y \
  python3 python3-venv python3-pip python3-gi \
  gir1.2-gtk-4.0 \
  pipewire-pulse pulseaudio-utils \
  libportaudio2 fonts-noto-cjk
```

- **PipeWire/PulseAudio** must be running (default on modern Ubuntu).
- System-audio captions record the default output’s **monitor** source with `parec` (from `pulseaudio-utils`). The microphone is read through PortAudio (`libportaudio2`).
- First run downloads a local Whisper model (`base.en`, ~150 MB). The optional Fast model, `tiny.en` (~75 MB), downloads the first time you use it. Audio and text stay on your machine.
- `fonts-noto-cjk` provides the Korean (Hangul) font for translated captions. Ubuntu desktop installs it by default.

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

### Korean translation

Turn on **Korean translation** in the control window's **Translation** box, then press **Start**. The switch is locked while captioning and is saved for the next launch. It is off by default.

- The overlay shows each block of English captions with its Korean translation directly underneath, in amber. English that is still in progress, or a sentence that is not finished yet, shows in English only until its sentence is complete.
- Korean is translated a whole sentence at a time, so it does not keep changing. It usually appears a second or two after the sentence ends. A sentence the speaker leaves unfinished is translated anyway after about 2 seconds of quiet, or after 8 seconds during non-stop speech.
- English captions are never slowed down by translation, including while the translation model downloads or loads.
- The first start with translation on downloads the translation model (~620 MB) to `~/.cache/huggingface/`. The **Translation** box shows the download status, and English captions run meanwhile. After that, translation works offline. Caption text is never sent anywhere.
- If the translation model cannot be downloaded, loaded or run, the **Translation** box shows the error in red. English captioning continues, and translation stays off until you press **Stop** and **Start** again.
- Translation adds about 1 GB of memory use while it is on.

The translation model is [NLLB-200 distilled 600M](https://huggingface.co/facebook/nllb-200-distilled-600M) by Meta, converted for CTranslate2 (`JustFrederik/nllb-200-distilled-600M-ct2-int8`, pinned to one revision). **Its license is CC-BY-NC 4.0: non-commercial use only.**

To use a model you converted yourself, for example when offline or if the pinned repository goes away, point `CAPTION_ENGLISH_TRANSLATION_MODEL` at its directory:

```bash
pip install transformers torch sentencepiece   # only needed for the conversion
ct2-transformers-converter --model facebook/nllb-200-distilled-600M \
  --quantization int8 --copy_files tokenizer.json --output_dir ~/nllb-600m-ct2
CAPTION_ENGLISH_TRANSLATION_MODEL=~/nllb-600m-ct2 ./scripts/run.sh
```

### Caption history

The app keeps everything it captions in English while it is open, including captions that have already scrolled off the overlay. The **Caption history** box in the control window shows how many sentences it holds.

- Only final English text is recorded. Text still in progress is not, and Korean translations never are, even with **Korean translation** on.
- The history carries on across **Stop** and **Start**. It is emptied only when you press **Clear…** (which asks first) or quit the app.
- Nothing is written to disk until you press **Save history…**. It opens a file dialog suggesting a name such as `caption-history-2026-11-25-143012.txt` in your Documents folder. You can save while captioning, and captioning carries on.
- If you close the app with history that has not been saved, it asks whether to **Save…**, **Discard** or **Cancel**.
- If the file cannot be written, the error shows in red in the **Caption history** box and the history is kept. Saving over an existing file never leaves it half written.

The saved file is UTF-8 plain text, with one line per sentence and a line for each **Start**:

```
Caption English caption history
Saved 2026-11-25 14:30:12

--- Session started 2026-11-25 14:02:55 (system audio) ---
[14:03:01] Welcome back to the show.
[14:03:04] Today we talk about Linux audio.

--- Session started 2026-11-25 14:20:40 (mic audio) ---
[14:20:43] Can everyone hear me?
```

Times are approximate. They show when a sentence's first words became final text, which is usually about half a second after they were spoken, and up to about 10 seconds later in long, unbroken speech. A sentence still unfinished when you save is included as the last line.

Saving and clearing need GTK 4.10 or newer (Ubuntu 23.04 and later). On older GTK the history box says so, and the rest of the app works as before.

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

Add `--translate` to also run the Korean translation path the app uses. It reports how long after a sentence completes its Korean arrives, the translation time per block, and the last few English/Korean pairs (`--beam 1` tries the faster, less accurate beam size):

```bash
.venv/bin/python scripts/bench_latency.py talk.mp3 --translate
```

With translation on, English captions keep the same latency, and Korean typically arrives about 0.5 s after each sentence completes.

## Privacy

Transcription runs locally via `faster-whisper`, and Korean translation runs locally via CTranslate2. No audio or caption text is uploaded by this app. The network is used only to download models the first time they are needed. The caption history stays in memory and is written to disk only when you save it, to the file you choose.
