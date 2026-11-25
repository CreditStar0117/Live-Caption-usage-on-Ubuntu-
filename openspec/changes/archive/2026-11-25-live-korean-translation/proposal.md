# Proposal

## Why

Caption English shows only English text. Korean-speaking users who follow English talks, meetings or videos need the meaning in Korean while it is being said. Whisper cannot help here: its built-in translation only produces English. So the app needs its own translation step, and it must run on the user's machine to keep the app's promise that no audio or text leaves the computer.

## What Changes

- Add **live English→Korean translation**, off by default and turned on with a **Korean translation** switch in the control window. The switch is saved between launches and, like the speech model picker, is locked while captioning.
- Translation runs **locally and offline** with a separate translation model (NLLB-200 distilled 600M, int8, run with CTranslate2). The model downloads once (about 620 MB) the first time translation is used, and the control window shows the download status.
- Only **final English text** is translated. The text is translated a whole sentence at a time, so the Korean reads naturally and does not keep changing.
- When translation is on, the overlay shows **each block of English captions with its Korean translation directly under it**. The in-progress English (partial text, and final text whose sentence is not finished yet) shows without Korean until its sentence is complete and translated.
- English captions **never wait** for translation. They keep their current latency, including while the translation model is downloading or loading. Korean appears a moment later.
- If the translation model cannot be downloaded, loaded or run, the control window shows the error in red. **English captioning keeps running**, and Korean translation is off until the next Start.
- The overlay's caption history accounts for the Korean lines and the wider Hangul characters, so a full overlay still shows its newest English and Korean at the bottom.
- Turning translation off gives exactly today's behavior.

## Capabilities

### New Capabilities

- `caption-translation`: optional on-device translation of final English captions into Korean. Covers the on/off setting and its persistence, the offline model and its first-use download, translating whole sentences, keeping English captions independent of translation speed, and reporting translation errors.

### Modified Capabilities

- `caption-overlay`: adds a two-language layout. Each English caption block is shown with its Korean translation underneath, captions that are still in progress stay English-only, and the history that fills the overlay includes the Korean lines.

## Impact

- **Code**
  - New `src/caption_english/translate.py`: the translation engine and its worker thread, model download and loading.
  - `src/caption_english/captions.py`: groups final text into sentence blocks, trims history, and builds the two-language overlay text.
  - `src/caption_english/app.py`: the translation switch and wiring.
  - `src/caption_english/overlay.py`: styled two-language text.
  - `src/caption_english/config.py`: a new saved setting.
- **Config**: `~/.config/caption-english/config.json` gains a `translate_korean` key (default `false`). Older files load unchanged, so no migration is needed.
- **Dependencies**: no new Python packages need installing. `ctranslate2`, `tokenizers` and `huggingface_hub` are already installed as dependencies of faster-whisper. They become direct dependencies in `pyproject.toml` and `requirements.txt`. Korean text needs a Hangul font (`fonts-noto-cjk`, normally present on Ubuntu desktop), which is added to the README's apt list.
- **Model and license**: the translation model downloads about 620 MB, once, to the Hugging Face cache. NLLB-200 is licensed **CC-BY-NC 4.0 (non-commercial only)**. This is fine for personal use, but it must be stated in the README and revisited before any commercial distribution.
- **CPU and memory**: one short translation runs for each finished sentence, and only while speech is being captioned. The translator adds about 1 GB of RAM while loaded. Its thread count is capped so it does not slow down speech recognition.
- **Tests**: new unit tests for sentence blocks, history trimming with Hangul, overlay text escaping, the translation worker (with a fake model) and the new config key. The latency benchmark gains a translation timing option.
- **Docs**: a README section on Korean translation, plus an updated control-window hint.
