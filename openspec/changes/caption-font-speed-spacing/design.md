# Design

## Context

See proposal.md (Why) for motivation, and the `caption-overlay` and `speech-to-text` delta specs for requirements.

Current pipeline:
- `parec` or PortAudio delivers 100 ms blocks to `SpeechToText`.
- A worker thread re-decodes the whole in-progress phrase with faster-whisper every 1.0 s of new audio.
- A phrase becomes final after 0.5 s of trailing silence, as measured by Silero VAD, or when it reaches 12 s.
- `app._show_text` joins finals and the partial with single spaces into one `Gtk.Label`.
- The overlay CSS hard-codes `font-size: 22px`.

Measurements on this machine (i7-11700, `base.en` int8) used 90 s of continuous English speech fed in real time:

| Variant | Word first appears (median / p90) | Word final (median / p90) | Decode busy | Drift vs offline |
|---|---|---|---|---|
| Current (1 s step, 12 s max) | 1.04 / 1.63 s | 7.0 / 11.6 s | 45% | 2.6% |
| 0.5 s step only | 0.90 / 1.51 s | 7.0 / 11.4 s | 89% | 6.2% |
| **Prototype of this design, `base.en`** | **0.79 / 1.40 s** | **3.8 / 6.1 s** | **82%** | **5.2%** |
| Prototype of this design, `tiny.en` | 0.62 / 0.93 s | 4.1 / 7.0 s | 49% | 4.9% |

Capture adds only about 100 ms of buffering. A whole decode takes about 0.4 s whatever the input length: faster-whisper pads every window to 30 s, and the encoder accounts for about 80% of the time.

## Goals / Non-Goals

**Goals:**
- Lower first-appearance and finalization latency, as specified, without new dependencies.
- Keep decoding single-flight and skip it whenever it cannot change the result.
- Keep sentence formatting and config parsing in pure-Python units that are testable without GTK.

**Non-Goals:**
- No GPU or CUDA path, no other STT engines, no change to audio capture.
- No word-level timestamps or LocalAgreement-style streaming. Both would need a deeper rewrite. The phrase/commit model is kept.
- No per-sentence line layout. The user chose same-line spacing.
- No font family, color or theme controls. Only the size changes.

## Decisions

### D1. Decode every 0.5 s of new audio (was 1.0 s)
The worker already drains the whole queue before each pass, so a pass that takes longer than 0.5 s is followed immediately by one covering all new audio. That behavior satisfies "Recognition slower than refresh rate". Halving the step alone gave only about 0.14 s, but together with D2 and D3 the median first appearance drops from 1.04 s to 0.79 s.
- *Alternative:* decode back-to-back with no minimum step. Rejected: CPU use stays near 100% during speech for a gain of about 0.1 s.

### D2. Soft commit at 5 s, hard commit at 10 s (was a single 12 s forced cut)
When the phrase is at least 5 s long and Whisper returned two or more segments, all but the last segment become final. The buffer is cut at the start of the last segment, which is usually a sentence boundary. At 10 s the whole phrase becomes final. Shorter phrases also keep each decode's context small, so the median decoded audio drops from 6.4 s to 3.5 s.
- *Alternative:* the 0.5 s step with a 6 s forced cut. It gave similar latency, but it cuts mid-word when there is only one segment.

### D3. Snap forced cuts to a VAD pause
A Whisper segment's start time can be off by a few hundred milliseconds. The cut therefore moves to the midpoint of the nearest gap between VAD speech regions within ±0.6 s, if one exists. The cut lands in silence, so no word is split or transcribed twice.

### D4. Reuse the last decode when no new speech arrived
The engine caches the last result as `(speech_end, buffer_duration, segments)`. When the next VAD pass reports the same speech end (±0.15 s), and the cached decode already saw at least 0.3 s past it, the engine reuses the cached segments. This usually happens during the 0.5 s pause that ends a phrase. The phrase then becomes final without another 0.4 s pass, which saves CPU and finalizes sooner. Requiring that tail guards against Whisper's habit of leaving the last word out of a buffer that ends right at the word. The cache is cleared whenever the buffer is cut.

### D5. Model choice reuses `config.model_size`
The control window gets a `Gtk.DropDown` with two entries: "Accurate (base.en)" and "Fast (tiny.en)". If config.json names another model, for example a hand-edited `small.en`, that model is listed as a third entry so the setting is not silently lost.
- The dropdown is disabled while captioning, like the audio source picker.
- On change, the app saves the config and warms the model in the background if it is already downloaded, using the existing `preload_model`.
- First-use download goes through the existing `load_model` status path ("Downloading speech model…").

### D6. Sentence gap: EM SPACE + EN SPACE (1.5 em) instead of markup
A new pure function `format_captions(phrases: list[str]) -> str`, in `caption_english/captions.py`, does three things:
1. Joins finals and the partial with single spaces.
2. Collapses whitespace.
3. Replaces the whitespace after sentence-ending punctuation with `"  "`.

The boundary regex is `[.!?…]` plus optional closing quotes or brackets, then whitespace. A period that is not followed by whitespace, as in `3.5` or `example.com`, is not a boundary.

Measured with Pango, the gap is exactly 1.5 em: 33 px at 22 px and 60 px at 40 px, about 6× a word space. It scales with the font automatically. Unicode line-break class BA (no break before) means a wrapped line never begins with the gap; this was verified over a range of wrap widths.
- *Alternative:* Pango markup `letter_spacing` on a normal space. Rejected: it needs pt/px conversion and markup escaping of untrusted transcript text.
- *Alternative:* one label per sentence. Rejected: the user chose a flowing paragraph.

### D7. Font size through a dedicated CSS provider
`CaptionOverlay` owns a second `Gtk.CssProvider` that holds only `label.caption-text { font-size: Npx; }`. It is added at `STYLE_PROVIDER_PRIORITY_APPLICATION + 1`, and `set_font_size(px)` reloads it. The label keeps its text, so a resize does not clear captions. The old scroll-to-bottom handler set the scroll position while the viewport was still being laid out, so the overlay kept showing the oldest lines whenever text overflowed. Rendering checks found this both after text growth and after a font change. The handler now scrolls once layout finishes (an idle callback), so the newest line stays visible after reflow.
- The control window gets a "Font size" `Gtk.SpinButton` with range 12–72 and step 2, in a "Caption text" frame. It saves immediately, as the size controls do.
- *Alternative:* a Pango size attribute on the label. Rejected: CSS already styles the label, and two sources of truth would conflict.

### D8a. Caption history sized to the overlay (replaces the 6-phrase limit)
The app used to keep the last 6 final phrases. Since D2, phrases are at most about 5 s long, so 6 of them fill only a few lines of a tall overlay. The app now keeps final phrases, newest first, until their total length reaches the overlay's capacity. It drops older phrases only beyond that point.

Capacity, in a pure function `history_capacity(width, height, font_px)` in `captions.py`, is:

    (width / (0.33 × font)) × (height / (1.14 × font)) × 1.5

The 0.33 em character width and 1.14 em line height are the smallest values measured with Pango across Sans, Ubuntu and Cantarell, so the estimate leans toward too much text rather than too little. The 1.5× margin covers wrap waste at line ends and a later resize. Overflow is harmless: the scroller keeps the newest line in view, and older text sits above the visible area.

The app reads the overlay size and font size from config, which follows drag-resizes, the size spins and the font spin.

Measured Pango layout cost per update is 1 ms for 2k characters (a 761×308 overlay at 22 px) and 27 ms for 60k characters (the 2400×900 maximum at 12 px), at most twice a second.
- *Alternative:* unlimited history. Rejected: layout cost and memory grow for the whole session.
- *Alternative:* measure real overflow in the overlay and trim to it. Rejected: it is exact, but it needs a layout pass before trimming and couples the overlay back to the app's phrase list.

### D8. Config parsing per field for `font_size`
`AppConfig.font_size` defaults to 22, with `clamp_font_size()` bounding it to 12–72. `load_config` parses `font_size` in its own try/except, so a bad value falls back to 22 without resetting the other settings. A missing key also gives 22, so older config files load unchanged.

## Risks / Trade-offs

- **[CPU during speech roughly doubles with base.en (45% → 82% decode busy)]** → Silence and reused decodes skip recognition entirely. Fast (`tiny.en`) is offered at about 49%. Passes never overlap.
- **[Shorter phrases give Whisper less context (drift vs offline 2.6% → 5.2% on the sample)]** → D3 avoids split words. Most differences are function words ("is" vs "or"). If accuracy complaints come in, the soft-commit threshold is a single constant to raise.
- **[Abbreviations such as "Mr. Smith" get a sentence gap]** → Accepted. Whisper rarely emits mid-sentence abbreviations with periods, and a wrong gap only affects spacing.
- **[Latency targets depend on hardware]** → The spec scopes them to the default model on a typical 8-core desktop CPU. The benchmark harness (see tasks) makes them repeatable.
- **[`tiny.en` is noticeably worse on noisy audio, accents and music]** → It is opt-in, labeled "Fast", and base.en stays the default.

## Migration Plan

No data migration. The new `font_size` key is written on the next save, and older config files load with defaults. To roll back, revert the commit. An older build ignores the unknown `font_size` key: `load_config` reads known keys only.
