# Design

## Context

Greenfield repo with no application code yet. Target is Ubuntu desktop (PipeWire/PulseAudio, X11 and Wayland). See proposal.md for motivation. Specs define audio capture, English speech-to-text, and a resizable caption overlay.

## Goals / Non-Goals

**Goals:**

- End-to-end local pipeline: audio → STT → always-on-top overlay with user-controlled width/height.
- Prefer offline speech recognition so captions work without a network.
- Persist overlay geometry (size; optionally position) across launches.
- Keep the first version installable and runnable on a typical Ubuntu desktop.

**Non-Goals:**

- Multi-language UI or non-English transcription in MVP.
- Cloud STT providers, speaker diarization, or translation.
- Full accessibility suite beyond live captions (e.g. custom TTS).
- Mobile or non-Linux platforms.

## Decisions

### 1. Application stack: Python + GTK 4

- **Choice:** Python 3 with GTK 4 (PyGObject) for the overlay and controls.
- **Rationale:** Native Ubuntu windowing, straightforward always-on-top and resize, low footprint vs Electron, good PipeWire/Pulse integration via GStreamer or `sounddevice`/`pulsectl`.
- **Alternatives:** Electron/Tauri (heavier, harder system-audio capture); Qt/PySide (also fine; GTK fits GNOME-first Ubuntu better).

### 2. Speech engine: faster-whisper (local)

- **Choice:** `faster-whisper` with a small English model (e.g. `base.en` or `small.en`) and streaming/chunked inference.
- **Rationale:** Local, English-focused models, acceptable latency on CPU; GPU optional later.
- **Alternatives:** `whisper.cpp` (C++ binding/CLI); Vosk (lighter, lower accuracy); cloud APIs (out of MVP scope).

### 3. Audio capture: PipeWire/Pulse monitor + mic

- **Choice:** Capture via PipeWire/PulseAudio monitor of the default sink for system audio, and the default source for microphone; user picks source in settings.
- **Rationale:** Matches Ubuntu defaults; monitor source is the standard way to caption “what you hear.”
- **Alternatives:** ALSA-only (fragile across distros); exclusive JACK (power-user only).

### 4. Overlay sizing model

- **Choice:** Interactive window resize (edges/corners) plus optional width/height fields or presets; clamp to min/max; save size in a user config file (e.g. XDG `~/.config/caption-english/`).
- **Rationale:** User asked for controllable width and height; drag-resize is natural, explicit controls help precision and accessibility.
- **Alternatives:** Size-only via settings dialog (less direct); percentage of screen only (less precise).

### 5. Process architecture

- **Choice:** Single process with async/worker thread for STT so the GTK UI stays responsive; audio frames queue into the recognizer; UI thread only updates caption text and geometry.
- **Rationale:** Simplest operational model for MVP; avoids multi-process IPC until needed.
- **Alternatives:** Separate STT daemon (better isolation later; more complexity now).

### 6. Packaging

- **Choice:** Runnable from source with a `requirements.txt` / venv first; optionally add a `.desktop` launcher; Flatpak/Snap deferred.
- **Rationale:** Fastest path to a working Ubuntu app; packaging can follow once behavior is solid.

## Risks / Trade-offs

- **[Wayland always-on-top / layer-shell]** → Use GTK APIs that work on X11; on Wayland, request appropriate layer/above hints where available and document session limitations.
- **[System-audio capture needs monitor source]** → Document enabling/monitoring default sink; fail with a clear error if unavailable.
- **[STT CPU latency / accuracy]** → Default to a small English model; allow model size config later; chunk audio for incremental updates.
- **[Model download size]** → First-run download of the Whisper model with progress/error messaging.
- **[Privacy]** → Keep audio and transcripts local by default; do not upload audio in MVP.

## Migration Plan

- N/A for greenfield. First release is a new install. Config lives under XDG paths so wiping it resets overlay size without reinstalling.

## Open Questions

- Exact min/max overlay pixel bounds (to be set during UI implementation from readability tests).
- Whether position (x/y) persistence ships in the same MVP as size (lean yes if cheap; not required by specs).
