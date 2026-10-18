# Tasks

## 1. Project scaffolding

- [x] 1.1 Create Python package layout (`src/caption_english/`, entrypoint module, `pyproject.toml` or `requirements.txt`) and verify `python -c "import caption_english"` works from the project venv
- [x] 1.2 Add runtime dependencies (PyGObject/GTK 4 notes, faster-whisper, audio capture libs) and verify `pip install -r requirements.txt` (or equivalent) succeeds in a clean venv
- [x] 1.3 Add a README with Ubuntu prerequisites (PipeWire/Pulse, GTK, model download) and verify the documented install steps can be followed from a fresh clone

## 2. Audio capture

- [x] 2.1 Implement start/stop capture for the default microphone and verify start begins a stream and stop releases the device (manual or unit test with a mock device)
- [x] 2.2 Implement system-playback capture via PipeWire/Pulse monitor of the default sink and verify playing a test tone is received when system audio is selected
- [x] 2.3 Add audio source selection (mic / system / both when available) and verify switching sources before start uses the chosen path
- [x] 2.4 Surface capture failures (missing device, permission denied, disconnect) as user-visible errors and verify a forced failure shows an error and leaves captioning stopped

## 3. Speech-to-text

- [x] 3.1 Integrate faster-whisper with a small English model (`base.en` or `small.en`), including first-run model load/download with progress or clear error, and verify the model loads successfully once
- [x] 3.2 Implement chunked/streaming transcription from the audio queue on a worker thread and verify spoken English test audio yields English text within a few seconds
- [x] 3.3 Handle silence/non-speech without inventing text and verify a silent buffer does not append fake captions
- [x] 3.4 Propagate STT engine failures to the UI and verify a missing/broken model shows an error and does not leave captioning appearing active

## 4. Caption overlay (width & height)

- [x] 4.1 Build an always-on-top GTK overlay window that displays the latest caption text and verify text updates when new transcription results arrive
- [x] 4.2 Enable interactive resize (edges/corners) with min/max clamps and verify dragging changes width and height within bounds
- [x] 4.3 Add explicit width/height controls (numeric fields and/or presets) and verify setting values updates the overlay size
- [x] 4.4 Persist and restore overlay width/height under XDG config and verify relaunch opens at the last saved size
- [x] 4.5 Implement show/hide overlay without quitting the app and verify hide removes visibility and show restores the overlay at the saved size

## 5. App controls & integration

- [x] 5.1 Wire Start/Stop Live Caption across capture → STT → overlay and verify a full session captions system or mic audio end-to-end
- [x] 5.2 Add a simple settings surface for audio source and overlay size and verify changes apply as specified
- [x] 5.3 Add a `.desktop` launcher (optional but recommended) and verify it appears/runs on Ubuntu from the Applications menu or `gtk-launch`

## 6. Integration checks

- [x] 6.1 Manual acceptance: start captioning, speak or play English audio, confirm captions appear; resize width/height by drag and by controls; restart app and confirm size restored
- [x] 6.2 Manual failure paths: deny/remove audio device and break STT path; confirm errors are shown and captioning does not silently hang

## Workflow follow-up

- Archive the change with `/opsx-archive` after review and implementation are complete.
- Sync specs into `openspec/specs/` if archiving does not already apply them per project practice.
