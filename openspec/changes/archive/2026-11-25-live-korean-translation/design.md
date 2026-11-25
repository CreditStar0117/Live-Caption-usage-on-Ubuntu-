# Design

## Context

See proposal.md (Why) for motivation, and the `caption-translation` and `caption-overlay` delta specs for requirements.

How captioning works today:
- `SpeechToText` runs faster-whisper (CTranslate2, CPU int8, 4 threads by default) on its own worker thread.
- It sends `(text, is_final)` results through `GLib.idle_add` to `CaptionEnglishApp._show_text`, which runs on the GTK thread.
- `_show_text` keeps `self._finals` (a list of final phrase strings) and `self._partial`, trims the finals with `history_capacity`/`trim_history`, and renders them with `format_captions` into one plain-text `Gtk.Label` in the overlay.
- A session counter (`self._session`) makes callbacks from a stopped session no-ops.
- A pipeline error calls `_fail_stop`, which stops everything and shows the status in red.

Constraints found on this machine:
- These packages are already in the venv as faster-whisper dependencies: `ctranslate2` 4.8.3, `tokenizers` 0.23.3, `huggingface_hub`. `sentencepiece` and `transformers` are not installed.
- Noto CJK fonts, which include Korean, are installed and picked up by fontconfig.
- Whisper's `task="translate"` only produces English. A separate machine-translation model is therefore required.

Final phrases do not line up with sentences. The STT engine finalizes after a 0.5 s pause, at a Whisper segment boundary once the phrase reaches 5 s, or with a hard cut at 10 s. So a final phrase can end mid-sentence or hold several sentences.

## Goals / Non-Goals

**Goals:**
- English→Korean translation on the CPU, with no new pip packages and no network use after the one-time download.
- English caption latency unchanged. Translation is a separate consumer of final text and never sits in the speech path.
- Translation logic testable without GTK and without downloading the real model.

**Non-Goals:**
- Any target language other than Korean, a language picker, or non-English speech. The engine takes the target language code as a parameter so these stay possible later, but the UI offers only Korean.
- Translating partial text.
- Cloud translation engines, GPU support, or a translation model picker.
- Renaming the app, which is still "Caption English".
- Toggling translation in the middle of a session. The switch applies at Start, like the speech model picker.

## Decisions

### D1. Model: NLLB-200 distilled 600M, int8, pre-converted for CTranslate2
The model is loaded from the Hugging Face repo `JustFrederik/nllb-200-distilled-600M-ct2-int8`. The download is pinned to revision `302d78f00e6fdb50a1064059df7c392b735e9d05` and filtered to `model.bin`, `config.json`, `shared_vocabulary.txt` and `tokenizer.json`, about 640 MB in all. CTranslate2 runs it as a `ctranslate2.Translator`.

Why:
- It ships `tokenizer.json`, so `tokenizers` (already installed) handles tokenization. No new packages are needed.
- It is already int8, about 620 MB, and runs on the same runtime as faster-whisper.
- Its English→Korean quality is clearly better than the MIT-licensed alternative.

Alternatives considered:

| Option | Why not |
|---|---|
| M2M100 418M (`michaelfeil/ct2fast-m2m100_418M`, MIT) | 970 MB, has no `tokenizer.json` so it would need `sentencepiece`, and its Korean is weaker. It is the fallback if the license becomes a problem (see Risks). |
| Opus-MT `Helsinki-NLP/opus-mt-tc-big-en-ko` (CC-BY 4.0, 418 MB) | No CTranslate2 conversion is published. Converting needs `transformers` and `torch` (several GB), or the project would have to host converted weights. |
| NLLB-200 distilled 1.3B | Better quality, but about 2× slower per sentence and about 1.4 GB to download. Revisit if the 600M quality is not good enough. |
| Whisper `task="translate"` | Produces English only. |
| Cloud APIs | Rejected by the user, because text would leave the machine. |

**License:** NLLB-200's license is CC-BY-NC 4.0. The README states this. See Risks.

**Override:** setting the environment variable `CAPTION_ENGLISH_TRANSLATION_MODEL` to a local directory containing a CTranslate2 NLLB model skips the download. This covers the pinned repo disappearing, and offline installs.

### D2. Tokenization and decoding with `tokenizers`
`Tokenizer.from_file(tokenizer.json)` loads the tokenizer. Each block is encoded with `add_special_tokens=False`, then the NLLB source sequence is built by hand: `["eng_Latn", *pieces, "</s>"]`.

Translation runs as:

```
translate_batch(sources, target_prefix=[["kor_Hang"]] * n, beam_size=2,
                max_input_length=256, max_decoding_length=<about 2× the source tokens + 16>)
```

For each hypothesis, the leading `kor_Hang` is dropped, the tokens are converted with `token_to_id`, and `tokenizer.decode(ids, skip_special_tokens=True)` produces the text.

- Building the frame by hand avoids depending on the tokenizer's post-processor, which carries whatever source language was configured at conversion time.
- The decoding-length cap stops runaway repetition on very short or odd inputs.
- `beam_size=2` is the starting point. The benchmark (task 7) decides between 1 and 2.
- Each block is split into sentences, and each sentence is a separate item in the same batch. The Korean is then joined back per block. With the real model, a two-sentence input ("Welcome back to the show. Today we talk about Linux audio.") lost its first sentence entirely; translated per sentence, both survive. If the model drops a sentence's final `.`, `?`, `!` or `…`, the English sentence's mark is copied over, because the overlay puts its sentence gap only after that punctuation.

### D3. A separate translation worker thread, batched, one pass at a time
A new `caption_english/translate.py` holds a `Translator` class modeled on `SpeechToText`:
- `load_model()` downloads if needed and loads the model, reporting status through `on_status`.
- `start()`, `stop()`, `submit(block_id, text)` and `discard(block_ids)`.
- Callbacks: `on_result(block_id, korean)`, `on_error(msg)` and `on_status(msg)`.

The worker:
- Blocks on a queue, then drains it, as the STT worker does, and translates everything queued in one `translate_batch` call (up to 16 blocks) in spoken order.
- Skips ids that the app discarded because they were trimmed from history. This keeps a backlog built up during the first-use download from translating text that is no longer on screen.
- Waits until the model is loaded before taking items. Blocks submitted during the download wait in the queue (spec: "Sentences finished during the download").

The CTranslate2 translator is created with `inter_threads=1, intra_threads=2`. Whisper keeps its 4 threads, so the two together fit on the 8-core target, and translating a sentence never takes CPU away from a Whisper decode for long.

Loaded models are cached at module level, like `stt._models`. The app warms the model in the background when translation is enabled and the model is already on disk, as `_preload_model` already does for Whisper.

Alternatives considered:
- *Translate on the STT worker after each final.* Rejected: it adds translation time to English latency.
- *Translate on the GTK thread.* Rejected: it blocks the UI.
- *A process pool.* Rejected: the extra complexity buys nothing, because CTranslate2 releases the GIL.

### D4. Start-up runs in parallel with English captioning
`start_captioning` keeps its existing `_boot` thread for capture and STT. When translation is enabled, a second `translation-boot` thread runs `Translator.load_model()` and `start()`. A slow or failed translation load therefore never delays or stops English captions (spec: "Translation does not delay English captions").

Both boots carry the session number. Their results go through `GLib.idle_add` and are ignored if the session changed. `stop_captioning` stops the translator and bumps the session, so late results are dropped (spec: "Stopping discards pending translations").

### D5. Sentence blocks are built on the GTK thread, in pure helpers
New pure functions and data in `captions.py`:
- `CaptionBlock(id, english, korean: str | None)`.
- `split_complete(text) -> (complete, rest)`. It cuts after the last sentence end, using the same boundary rule as `_SENTENCE_END`, extended to also accept the end of the string. `rest` is the unfinished tail.

How `_show_text` handles a final when translation is active:
1. Append the final to `self._pending`, the final English not yet in a block.
2. Run `split_complete` on it.
3. If `complete` is non-empty, it becomes a new block and is `submit`ted.
4. `self._pending` becomes `rest`.

Flushing an unfinished tail:
- A 250 ms GLib timer checks pending text. When no partial is in progress and at least 2.0 s have passed since the last final, the pending text becomes a block as it is.
- Pending text older than 8 s is flushed even while speech continues, so a long unpunctuated stretch still gets Korean.
- This satisfies "Unfinished sentence when the speaker stops" and keeps Korean from lagging without limit.

With translation off, none of this runs. `_show_text` keeps today's code path exactly (spec: "Translation off").

Alternatives considered:
- *Translate each final phrase as it arrives.* Rejected: a sentence split across phrases is translated as fragments, which gives poor Korean.
- *Translate the whole history again each time.* Rejected: it is wasteful, and Korean already shown would change.

### D6. Two-language rendering with escaped Pango markup
`format_bilingual(blocks, open_english) -> str` returns Pango markup:
- Each block's English goes through `format_captions` for the sentence gaps, then `GLib.markup_escape_text` (passed in as `escape` so tests need no GTK).
- The Korean, also formatted with `format_captions` and escaped, goes in `<span foreground="#ffd27a">` on the next line. This is a warm amber, with good contrast on the overlay's near-black background.
- Blocks are separated by a newline. The open English (pending plus partial) follows the last block, with no Korean.

`CaptionOverlay` gets `set_caption_markup(markup)` alongside `set_caption_text`, and uses `Gtk.Label.set_markup`.
- The font size still comes from the CSS provider, so it applies to Korean as well.
- Hangul glyphs come from fontconfig fallback to Noto Sans CJK. No CSS font change is needed.
- The existing scroll-to-newest handler runs on the adjustment's `changed` signal, so it keeps working.

Escaping is mandatory: transcripts and translations are untrusted text and can contain `<` or `&`.
- *Alternative:* one `Gtk.Label` per block in a `Gtk.Box`. Rejected: it needs a rewrite of the scrolling and reflow logic, which currently assumes a single label, to gain nothing over markup.

### D7. History trimming by estimated line count
In translation mode, history is trimmed with `trim_blocks(blocks, width, height, font_px)` instead of the character-count capacity:
- Each block's English and Korean are measured in em units: `_CHAR_WIDTH_EM = 0.33` for most characters, and 0.9 em for East Asian wide or fullwidth characters (`unicodedata.east_asian_width` in `{"W", "F"}`).
- The measurement is converted to wrapped lines: `ceil(width_em × font / width)`, at least 1 line each, since every block starts a new line.
- Blocks are kept newest first until the lines reach `height / (1.14 × font) × 1.5`.
- The underestimated widths make the trim err toward keeping more text, as the existing helper does (spec: "Two-language history fills the overlay").
- Ids of trimmed blocks are passed to `Translator.discard`.

Translation-off mode keeps `history_capacity`/`trim_history` unchanged.

### D8. Download, offline use and privacy
`is_translation_model_downloaded()` checks each model file with `hf_hub_download(..., local_files_only=True)`. When the files are present, loading also uses `local_files_only=True`, so a normal start makes no network request at all. When they are missing, each file is downloaded at the pinned revision with `hf_hub_download`, on the translation-boot thread. `snapshot_download` is not used: it downloads through a thread pool that Python waits for at exit, so quitting the app during a first-use download would hang until the download finished. Status messages are:
- "Downloading translation model (~620 MB, first use only)…"
- "Loading translation model…"
- "Korean translation ready"

Only model files are fetched. Caption text is never part of any request (spec: "On-device translation").

### D9. A separate translation status line and non-fatal errors
The control window gets a "Korean translation" `Gtk.Switch` row with its own status label beneath it.
- Translation status never overwrites the main captioning status. If it shared the main label, "Captioning (system audio)…" from `_finish_boot` would hide "Downloading translation model…".
- Translation errors use the same red `error` CSS class.
- On a translator error, the app: shows the error on that label, stops the translator for the session, clears pending translation state, and keeps rendering English. Korean already shown stays. It does **not** call `_fail_stop`.
- The switch is insensitive while captioning, matching the source and model pickers.

### D10. Configuration and dependencies
- `AppConfig.translate_korean: bool = False` is parsed independently, so a bad value does not reset other settings, as `font_size` already works. No migration is needed.
- `pyproject.toml` and `requirements.txt` list `ctranslate2>=4.0`, `tokenizers>=0.13` and `huggingface_hub>=0.13` directly. They are already installed, but the app now imports them itself.
- The README apt line gains `fonts-noto-cjk`.

### D11. Measured results (task 6.1)
Measured on this machine (16 threads, `base.en`, a 90 s English conversation from 20 s in, fed in real time with `scripts/bench_latency.py --translate`):

| Run | English first appearance (median / p90) | English final (median / p90) | Korean after block complete (median / p90) | Translation time per block | Translator busy |
|---|---|---|---|---|---|
| Translation off | 0.70 / 1.00 s | 2.55 / 4.86 s | – | – | – |
| **Beam 2 (kept)** | **0.76 / 1.11 s** | **2.85 / 5.03 s** | **0.44 / 0.92 s** | **435 ms** | **10%** |
| Beam 1 | 0.68 / 1.04 s | 2.77 / 5.23 s | 0.40 / 0.73 s | 379 ms | 7% |

- Both beam sizes meet the specs: English first appearance stays within 0.9 s at the median, and Korean appears within 2 s.
- The English difference between runs (0.68–0.76 s) is within run-to-run variation.
- **Beam 2 is kept** although beam 1 is slightly faster. Beam 1 mistranslated "Yes, we eat fish." as "어서 먹어요" ("Go ahead and eat"), while beam 2 gave "그래, 우리는 물고기를 먹습니다." Its cost is about 0.04 s per block, well inside the target.
- The worst Whisper decode rose from 0.6 s to 1.8 s while a translation batch ran. This is an occasional spike, not a trend; the p90 first appearance rose by only 0.1 s.

## Risks / Trade-offs

- **[License] NLLB-200 is CC-BY-NC 4.0 (non-commercial only).** → It is stated in the README next to the feature. The `Translator` keeps model-specific framing (language codes, source and target framing) in one place, so switching to M2M100 (MIT, plus `sentencepiece`) is a contained change if the project ever needs commercial use.
- **[Supply] The model comes from a third-party conversion repo that could change or disappear.** → The revision is pinned to an exact commit. `CAPTION_ENGLISH_TRANSLATION_MODEL` accepts a locally converted model, and the README documents `ct2-transformers-converter --model facebook/nllb-200-distilled-600M --quantization int8`.
- **[Quality] Korean quality is moderate, and speech-recognition errors carry into the translation.** → Translating whole sentences (D5) avoids fragment translations. Beam size 2. The README sets expectations. The 1.3B model is a possible later step.
- **[CPU] Translation competes with Whisper.** → It is capped at 2 threads, runs one pass at a time and only on final text. The benchmark checks that English latency stays within the `speech-to-text` spec (median ≤ 0.9 s) with translation on.
- **[Memory] About 1 GB more RAM while the translator is loaded.** → It is loaded only when translation is on.
- **[Disk/network] The first use downloads about 640 MB, and the first start shows Korean late.** → The status line explains the wait, and English works meanwhile.
- **[Rendering] Markup injection or broken text from unescaped transcript characters.** → Everything is escaped (D6), with unit tests for `<`, `>`, `&` and quotes.
- **[Rendering] No Hangul font on minimal installs.** → `fonts-noto-cjk` is in the README apt list. A rendering check is part of verification.
- **[Latency] Unfinished sentences wait up to 2 s, or up to 8 s during continuous speech, before translation.** → This is an accepted trade-off for whole-sentence quality. Whisper usually punctuates, so most blocks close right away.

## Migration Plan

- No data migration. Existing configs load with translation off.
- Rollback: turn the switch off, which restores today's behavior exactly. To reclaim disk space, delete `~/.cache/huggingface/hub/models--JustFrederik--nllb-200-distilled-600M-ct2-int8`.
- Release as a minor version (1.1.0) with a CHANGELOG entry.

## Open Questions

- The exact Korean color and block spacing. These are tuned during the rendering check, within D6.
