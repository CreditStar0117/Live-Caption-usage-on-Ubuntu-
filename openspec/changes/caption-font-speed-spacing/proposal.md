# Proposal

## Why

Captions feel slow and are hard to read. Words appear about 1 s after they are spoken, and continuous speech stays unsettled for 7 s at the median (up to 12 s), so the line keeps rewriting itself. Sentences run together, separated by a single space. The caption text is a fixed 22 px, so users cannot make it larger or smaller. The overlay keeps only the last 6 phrases, so a tall overlay stays mostly empty and earlier captions vanish quickly.

## What Changes

- Add a user-controlled **caption font size** for the overlay, adjustable from the control window. The overlay applies it immediately, and the size is restored on the next launch.
- Separate sentences in the overlay with a **wide, fixed gap on the same line**. Captions stay one flowing paragraph, but each sentence boundary gets a clearly larger space than the space between words, and the gap scales with the font size.
- Make live captions **faster**:
  - shorten the time from a spoken word to its first appearance on screen
  - shorten the time until in-progress text settles into stable, final text, so long runs of continuous speech no longer stay unsettled for up to 12 s
- Keep **caption history until the overlay is full**, replacing the fixed 6-phrase limit. A larger overlay or smaller font shows more earlier text, and old text scrolls off the top only when newer text needs the space.
- Bound the CPU cost of faster captioning so it stays usable alongside video playback.
- Add a **speech model choice** in the control window:
  - **Accurate (`base.en`)**, the default and unchanged from today.
  - **Fast (`tiny.en`)**, which shows words sooner and uses about half the CPU but is less accurate on noisy audio. It downloads on first use.

  The choice is saved and applies the next time captioning starts.

## Capabilities

### New Capabilities

- (none)

### Modified Capabilities

- `caption-overlay`: adds user-controlled, persisted caption font size, a fixed visual gap between sentences, and caption history that fills the overlay.
- `speech-to-text`: adds latency targets for first appearance and for stable (final) text during continuous speech, bounds on recognition work, and a user-selectable accurate/fast speech model.

## Impact

- Code: `src/caption_english/stt.py` (decode cadence and phrase commit policy), `src/caption_english/overlay.py` (font size and sentence rendering), `src/caption_english/app.py` (font-size and model controls, caption assembly), `src/caption_english/config.py` (persisted `font_size`), and a new pure-Python caption-formatting helper.
- Config: `~/.config/caption-english/config.json` gains a `font_size` key, and the existing `model_size` key becomes user-selectable. Existing files without `font_size` load with the default (22 px), so no migration is needed.
- CPU: with the default model, recognition runs about twice as often during speech (measured decode busy 45% → 82%). It still runs one pass at a time and stops during silence.
- Tests: new and updated unit tests for config font-size clamping and persistence, sentence splitting and spacing, and the STT commit policy.
- Dependencies: no new packages. Picking Fast downloads the `tiny.en` model (~75 MB) once, through the existing faster-whisper download path.
- Docs: README sections on captions and overlay settings.
