# Changelog

## [1.2.0] - 2026-11-25

Keep and save what was said: a full English caption history you can save as a text file.

### Added

- **Caption history**: everything captioned in English while the app is open is kept, including captions that have scrolled off the overlay. It carries on across Stop and Start, and the control window shows how many sentences it holds. Only final English text is recorded, never in-progress text or Korean translations.
- **Save history…** writes the history to a UTF-8 text file you choose, with one `[HH:MM:SS] sentence` line per sentence and a line for each session's start time and audio source. Saving works while captioning and does not interrupt it. A failed save shows in red, keeps the history and never leaves a half-written file.
- **Clear…** empties the history after asking.
- Closing the app with unsaved history asks whether to save, discard or cancel.
- Saving and clearing need GTK 4.10 or newer.

## [1.1.0] - 2026-11-25

Live Korean translation of the English captions, run on your own computer.

### Added

- **Korean translation** switch in the control window, off by default and saved between launches. When it is on, each block of English captions is shown with its Korean translation underneath, in amber.
- Translation runs offline with NLLB-200 distilled 600M (int8, CTranslate2). The model (about 620 MB) downloads once, the first time translation is used, and the control window shows the download status. The model's license is CC-BY-NC 4.0 (non-commercial use only).
- Whole sentences are translated once they are complete, so the Korean does not keep changing. English captions are never delayed by translation.
- Translation errors show in red in the control window's Translation box while English captioning continues.
- `CAPTION_ENGLISH_TRANSLATION_MODEL` points the app at a locally converted translation model instead of downloading one.
- `scripts/bench_latency.py --translate` measures how long Korean takes to appear.

## [1.0.0] - 2026-10-18

First release of Caption English: live English captions for Ubuntu, transcribed locally with Whisper.

### Added

- Live captions from system audio, the microphone, or both, in an always-on-top overlay.
- Adjustable overlay size and font size (12–72 px). Both are saved between launches.
- Faster captions: words appear about 0.8 s after they are spoken (was about 1 s), and text settles in about 4 s during continuous speech (was about 7 s).
- A wide, fixed gap between sentences, on the same line.
- Caption history that fills the overlay. Old text scrolls away only when new text needs the space.
- Speech model choice: Accurate (`base.en`, default) or Fast (`tiny.en`).

### Fixed

- The overlay always shows the newest caption line when the text is longer than the overlay.
