# Changelog

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
