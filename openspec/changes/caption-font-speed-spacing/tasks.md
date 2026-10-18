# Tasks

## 1. Persisted font size setting

- [x] 1.1 Add `font_size` (default 22, clamped 12–72 via `clamp_font_size`) to `AppConfig` in `config.py`. Parse it per field in `load_config` so a missing or invalid value falls back to 22 without resetting other settings. Add cases to `tests/test_config.py` (missing key, invalid value, out-of-range clamp, save/load round-trip) and verify `python -m unittest tests.test_config` passes

## 2. Sentence gap formatting

- [x] 2.1 Create `src/caption_english/captions.py` with `format_captions(phrases)`, which joins phrases, collapses whitespace, and puts EM SPACE + EN SPACE after `.`/`?`/`!`/`…` (plus closing quotes or brackets) when followed by whitespace. Add `tests/test_captions.py` covering multiple sentences, a sentence split across phrases with no punctuation, an in-progress partial, `3.5` and `example.com`, quotes after the period, and an empty partial. Verify `python -m unittest tests.test_captions` passes
- [x] 2.2 Use `format_captions([*finals, partial])` in `CaptionEnglishApp._show_text`, and verify in the running app that two spoken sentences show a visibly wider gap than word spacing on the same line

## 3. Overlay font size control

- [x] 3.1 Add a dedicated font-size `Gtk.CssProvider` (priority APPLICATION + 1) and `set_font_size(px)` to `CaptionOverlay`, and initialize it from config. Verify by launching the app that captions render at the saved size
- [x] 3.2 Add a "Caption text" frame with a "Font size" spin button (12–72, step 2) to `ControlWindow`, wired to a new `CaptionEnglishApp.apply_font_size` that clamps, applies and saves. Verify in the running app that changing it redraws existing caption text without clearing it, and that a relaunch restores the size in both the overlay and the spin button
- [x] 3.3 Update `README.md` with a "Caption text" section covering the font size control, its range and persistence, and the sentence gap. Verify the documented steps match the app

## 4. Faster speech-to-text

- [x] 4.1 In `stt.py`, set `STEP_SECONDS = 0.5` and add `SOFT_COMMIT_SECONDS = 5.0`. Change `MAX_PHRASE_SECONDS` to 10.0. Implement the commit policy: pause → commit all; at ≥5 s with ≥2 segments → commit all but the last, cutting at the last segment start snapped to the nearest VAD pause within 0.6 s; at ≥10 s → commit all. Update `test_long_phrase_keeps_unfinished_segment` and add tests for the soft commit, snap to pause, no snap when no pause is near, and the 10 s single-segment hard commit. Verify `python -m unittest tests.test_stt` passes
- [x] 4.2 Add the last-decode cache to `SpeechToText`: reuse when the speech end is unchanged (±0.15 s) and the cached decode saw ≥0.3 s past it; clear it on every buffer cut and on silence. Add tests that `transcribe` is not called again on a reuse, is called when the tail was too short or new speech arrived, and that the cache is cleared after a commit. Verify `python -m unittest tests.test_stt` passes
- [x] 4.3 Add `scripts/bench_latency.py <audio-file> [model]`. It decodes any ffmpeg-readable file to 16 kHz mono and feeds `SpeechToText` in real time. It reports median and p90 latency to first appearance and to final text, decode time, and decode busy %. Run it on a ≥60 s English recording and verify that with `base.en` the median first appearance is ≤0.9 s and the median final latency is clearly below the old 7 s. Document the command in the README "Tests" section

## 5. Speech model choice

- [x] 5.1 Add a `model_choices(current)` helper (Accurate `base.en`, Fast `tiny.en`, plus the current value if it is neither). Cover it with a unit test, and verify `python -m unittest tests.test_config` passes
- [x] 5.2 Add a "Speech model" `Gtk.DropDown` to `ControlWindow` that is disabled while captioning, saves `model_size` on change, and warms an already-downloaded model in the background via `preload_model`. Verify in the running app that choosing Fast and pressing Start shows the download/loading status and then captions, and that the choice survives a relaunch
- [x] 5.3 Update the README "Captions" section: refresh rate (about twice a second), finished sentences settling while the speaker keeps talking, and the Accurate/Fast model choice including the one-time `tiny.en` download. Verify the text matches app behavior

## 6. Caption history fills the overlay

- [x] 6.1 Add `history_capacity(width, height, font_px)` and `trim_history(phrases, capacity)` to `captions.py`. `trim_history` keeps the newest phrases until their total length reaches the capacity, including the phrase that crosses it, and never drops the newest phrase. Add tests that capacity grows with overlay size and shrinks with font size, and that trimming drops only the oldest phrases beyond capacity. Verify `python -m unittest tests.test_captions` passes
- [x] 6.2 Replace `MAX_CAPTION_PHRASES` in `CaptionEnglishApp._show_text` with `trim_history`, using the current overlay size and font size from config. Verify in the running app that a tall overlay (for example 1100×350) fills to the top with earlier captions before old text scrolls away, with the newest line visible at the bottom
- [x] 6.3 Update the README "Overlay size" section: a larger overlay or smaller font keeps more caption history on screen. Verify the text matches app behavior

## 7. Integration checks

- [x] 7.1 Run the full suite with `python -m unittest discover -s tests -v` and verify all tests pass
- [ ] 7.2 Manual acceptance with system audio playing an English video:
  - captions appear noticeably faster than before
  - the overlay fills to the top with earlier captions before old text scrolls away
  - sentences are separated by the wide gap
  - the font size changes live and persists
  - Fast mode works after a restart
  - stopping and starting again still works with no errors in the log

## Workflow follow-up

- Archive the change with `/opsx:archive` after implementation and review are complete. This syncs the `caption-overlay` and `speech-to-text` deltas into `openspec/specs/`.
