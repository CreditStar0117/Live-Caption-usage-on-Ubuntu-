# Tasks

## 1. Translation setting and dependencies

- [x] 1.1 Add `translate_korean: bool = False` to `AppConfig` in `config.py`. Parse it on its own in `load_config` so a missing or invalid value falls back to `False` without resetting other settings, and keep it in `clamped()`. Add cases to `tests/test_config.py` (missing key, invalid value, save/load round-trip, pre-translation config file). Verify `python -m unittest tests.test_config` passes
- [x] 1.2 Add `ctranslate2>=4.0`, `tokenizers>=0.13` and `huggingface_hub>=0.13` to `pyproject.toml` `dependencies` and `requirements.txt`, and add `fonts-noto-cjk` to the apt comment in `requirements.txt`. Verify `.venv/bin/pip install -e .` succeeds and installs nothing new

## 2. Sentence blocks, history and two-language text (pure helpers)

- [x] 2.1 Add `split_complete(text) -> (complete, rest)` to `captions.py`. It cuts after the last sentence end, using the same punctuation and closing-quote rule as `_SENTENCE_END` and also accepting the end of the string. Add `tests/test_captions.py` cases: a single complete sentence, two sentences plus an unfinished tail, no sentence end, `3.5` and `example.com` not splitting, a closing quote after the period, and an ellipsis. Verify `python -m unittest tests.test_captions` passes
- [x] 2.2 Add `CaptionBlock(id, english, korean)` and `trim_blocks(blocks, width, height, font_px)` per design D7: em-width estimate, with East Asian wide or fullwidth characters at 0.9 em, at least one line each for English and Korean, a 1.5× margin, and newest kept first. It returns the kept blocks and the dropped ids. Add tests that Korean text counts as wider than the same number of Latin characters, that a bigger overlay keeps more blocks, that a bigger font keeps fewer, that the newest block is never dropped, and that only the oldest are dropped. Verify `python -m unittest tests.test_captions` passes
- [x] 2.3 Add `format_bilingual(blocks, open_english, escape) -> str` per design D6. For each block it writes the English through `format_captions`, then a newline and the Korean in `<span foreground="#ffd27a">` (omitted while `korean is None`), with blocks separated by newlines and the open English last. Everything is escaped through the injected `escape`. Add tests for: block order, an untranslated block shown English-only, open English after the last block, sentence gaps inside English and Korean, and escaping of `<`, `>`, `&` and quotes in both languages (using `html.escape` as a stand-in). Verify `python -m unittest tests.test_captions` passes

## 3. Translation engine

- [x] 3.1 Create `src/caption_english/translate.py` with constants (repo id, pinned revision `302d78f00e6fdb50a1064059df7c392b735e9d05`, allow patterns, `eng_Latn`/`kor_Hang`, thread counts, beam size, batch size 16) and pure helpers. `source_tokens(tokenizer, text)` returns `["eng_Latn", *pieces, "</s>"]`. `decode_hypothesis(tokenizer, tokens)` drops the `kor_Hang` prefix and decodes with `skip_special_tokens=True`. Add `tests/test_translate.py` using a small fake tokenizer to check the source framing and that the prefix and special tokens are removed. Verify `python -m unittest tests.test_translate` passes
- [x] 3.2 Add `model_dir()`, `is_translation_model_downloaded()` and `load_model()` with the module-level model cache and lock (design D8):
  - `CAPTION_ENGLISH_TRANSLATION_MODEL` overrides the location.
  - When the model is on disk, loading uses `local_files_only=True`.
  - Status messages are "Downloading translation model (~620 MB, first use only)…", "Loading translation model…" and "Korean translation ready".
  - Failures raise `TranslationError`.

  Test with `snapshot_download` and `ctranslate2.Translator` patched: the env override skips the download, a downloaded model makes no non-local call, and a download failure raises `TranslationError`. Verify `python -m unittest tests.test_translate` passes
- [x] 3.3 Add the `Translator` worker per design D3: `start/stop/submit/discard`, a drain-and-batch loop, `inter_threads=1, intra_threads=2`, `max_decoding_length` scaled to the source length, and the `on_result/on_error/on_status` callbacks. Results come back in submission order, discarded ids are skipped, and an exception in `translate_batch` reports `on_error` once and stops the worker. Test with a fake `ctranslate2.Translator`:
  - several queued blocks go out in one batch, in order
  - discarded ids are never translated
  - items submitted before the model is loaded are translated once it is ready
  - an error is reported and no further results follow
  - `stop()` drops queued items and joins the thread

  Verify `python -m unittest tests.test_translate` passes
- [x] 3.4 Load the real model once (`.venv/bin/python -c` with `Translator.load_model()` and one sentence) and verify that a sample sentence such as "The meeting starts at three o'clock tomorrow." comes back as Korean, and that a second run makes no network request (run it with `HF_HUB_OFFLINE=1`)

## 4. Overlay rendering

- [x] 4.1 Add `CaptionOverlay.set_caption_markup(markup)` (idle-scheduled `Gtk.Label.set_markup`), keeping `set_caption_text` for translation-off mode. Verify in the running app that a markup string with English, an amber Korean line and a long overflowing history renders Hangul without empty boxes, keeps the newest line visible at the bottom, and redraws both languages when the font size changes

## 5. App wiring and control window

- [x] 5.1 Add a "Korean translation" row to `ControlWindow` with a `Gtk.Switch` bound to `translate_korean` and saved on change, plus a dedicated translation status label that uses the `error` CSS class for errors. Make the switch insensitive while captioning in `set_running`, and update the hint text to mention the one-time translation download. On activate, warm the translator in the background when it is enabled and already downloaded. Verify in the running app that the switch persists across a relaunch and is locked while captioning
- [x] 5.2 In `start_captioning`, when translation is enabled, start a `translation-boot` thread alongside `_boot` that loads and starts a `Translator` with session-guarded callbacks (design D4). Stop it in `stop_captioning`. Verify in the running app, with the model cache temporarily moved away, that English captions appear while the status line shows the translation download, and that Korean begins once it is ready
- [x] 5.3 Change `_show_text` for translation mode (design D5):
  - Final English goes into `_pending`, `split_complete` closes blocks, each block is `submit`ted, and history is trimmed with `trim_blocks` (calling `discard` on dropped ids).
  - Rendering uses `format_bilingual` with `GLib.markup_escape_text`.
  - Add `_show_translation(session, block_id, korean)` to fill in a block.
  - Add the 250 ms flush timer: no partial in progress and ≥2 s since the last final, or pending text older than 8 s.
  - Leave the translation-off path unchanged.

  Move the block and flush state handling into a GTK-free helper class in `captions.py` so it can be unit tested. Test it with a fake clock and submit function: sentences close immediately, a split sentence closes after the second phrase, the 2 s flush happens and is blocked by a partial, the 8 s forced flush works, and translations attach to the right block. Verify `python -m unittest tests.test_captions` passes
- [x] 5.4 Handle translator errors per design D9: show the red translation status, stop the translator for the session, keep English captioning and the Korean already shown, and do not call `_fail_stop`. Verify in the running app, with `CAPTION_ENGLISH_TRANSLATION_MODEL` pointing at an empty directory, that the error shows in red while English captions continue, and that a Stop followed by Start with a valid model translates again
- [x] 5.5 Add a "Korean translation" section to `README.md`:
  - how to turn it on, and that it applies at the next Start
  - the one-time ~620 MB download and the offline use that follows
  - the two-language layout, with Korean appearing after each sentence completes
  - that English captions are not slowed down
  - the NLLB-200 CC-BY-NC 4.0 non-commercial license
  - `CAPTION_ENGLISH_TRANSLATION_MODEL` and the `ct2-transformers-converter` command for a local model

  Also add `fonts-noto-cjk` to the apt install line. Verify the documented steps match the app

## 6. Latency benchmark

- [x] 6.1 Add a `--translate` option to `scripts/bench_latency.py`. It feeds final text through the same block helper and `Translator` as the app, and reports the median and p90 delay from block completion to Korean, plus translation time per block, next to the existing English latency figures. Run it on a ≥60 s English recording with `base.en` and verify:
  - the English median first appearance stays ≤0.9 s with translation on
  - the Korean median delay is ≤2 s

  Compare `beam_size` 1 and 2, keep the faster one that meets both targets, and record the numbers in design.md. (Result: both met the targets; beam 2 was kept despite being 0.04 s slower, because beam 1 mistranslated a sentence. See design D11.) Document the option in the README "Caption latency benchmark" section

## 7. Integration checks

- [x] 7.1 Run the full suite with `python -m unittest discover -s tests -v` and verify all tests pass
- [x] 7.2 Manual acceptance with system audio playing an English video and translation on (verified by feeding an English video's audio straight into the running app in place of capture, which this change does not touch; see design D11 for numbers):
  - each English block gets amber Korean underneath, and partial text stays English-only
  - English captions are as quick as with translation off
  - the overlay fills with two-language history and scrolls correctly
  - Stop during translation leaves no Korean in the next session
  - with the network disabled, translation still works after the first download
  - turning translation off restores the plain English overlay
- [x] 7.3 Add a `1.1.0` entry to `CHANGELOG.md` and bump `version` in `pyproject.toml`. Verify `openspec validate live-korean-translation --strict` passes

## Workflow follow-up

- Archive the change with `/opsx:archive` after acceptance, which syncs the `caption-translation` and `caption-overlay` deltas into `openspec/specs/`.
