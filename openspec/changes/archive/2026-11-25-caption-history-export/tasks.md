# Tasks

## 1. History store (pure helpers)

- [x] 1.1 Create `src/caption_english/history.py` with `HistorySentence`, `HistorySession` and `CaptionHistory` (injectable `datetime` clock), per design D1 and D2:
  - `start_session(source)`, `add_final(text)`, `end_session()` and `clear()`
  - sentence grouping with `split_complete` and `split_sentences` from `captions.py`, where the first sentence is timed at `pending_since` and later ones at `now`
  - `sentence_count`, which includes pending text
  - `revision`, `mark_saved(revision)` and `has_unsaved` (D5)

  Add `tests/test_history.py` with a fake clock covering:
  - a sentence split across two phrases is timed at the first phrase
  - two sentences in one phrase become two sentences
  - `end_session` closes pending text, and the next session starts a new sentence
  - empty or whitespace-only finals are ignored
  - the count includes pending text
  - `clear` during an open session keeps a fresh session for later captions
  - `has_unsaved` stays correct across saves, new captions and clears

  Verify `python -m unittest tests.test_history` passes
- [x] 1.2 Add `CaptionHistory.transcript(saved_at)` and `default_filename(now)` per design D3:
  - a header, then one `--- Session started … (<source> audio) ---` line per session followed by `[HH:MM:SS] text` lines
  - a blank line between sessions and a trailing `\n`
  - sessions with no sentences left out
  - pending text written last without consuming it
  - the name `caption-history-YYYY-MM-DD-HHMMSS.txt`

  Add tests that compare the exact text for two sessions, an empty session left out, pending text included and still pending afterwards, and a Unicode sentence. Verify `python -m unittest tests.test_history` passes
- [x] 1.3 Add `write_transcript(path, text)` per design D4: an `O_EXCL` temporary file in the same folder created with mode `0o666` (umask applied), `fsync`, the mode copied from an existing target, `os.replace`, and the temporary file removed on any `OSError` before re-raising. Add tests in a `tempfile.TemporaryDirectory`:
  - a new file is written as UTF-8
  - an existing file is replaced and keeps its mode
  - a failure from a patched `os.write` keeps the old content and leaves no `.tmp` file
  - a missing folder raises `OSError`

  Verify `python -m unittest tests.test_history` passes

## 2. Recording in the app

- [x] 2.1 In `app.py`, create `self.history = CaptionHistory()` in `CaptionEnglishApp.__init__`, call `history.start_session(self.config.audio_source)` in `start_captioning` and `history.end_session()` in `stop_captioning`, and call `history.add_final(text)` for final text in `_show_text` after the session check and before the translation branch (design D2). Leave `_show_translation` untouched. Verify `python -m unittest discover -s tests` passes. Then run the app with translation on, caption an English video for a minute, and check in a debugger or log line that the history holds only English sentences, including ones that have scrolled off the overlay

## 3. Control window and dialogs

- [x] 3.1 Add the "Caption history" frame to `ControlWindow` between Translation and the actions row (design D6): a summary label, **Save history…** and **Clear…** buttons that are insensitive while the history is empty, and an error label styled like `set_translation_status`. Add `update_history(count, saved_name)` and `set_history_error(text)`, and call `update_history` from `_show_text`, after a save and after a clear. On GTK older than 4.10, show the D10 note and keep both buttons insensitive. Verify in the running app that the count rises while captioning, the buttons are enabled only once something is recorded, and the buttons stay usable while captioning
- [x] 3.2 Add the save flow (design D7):
  - a `Gtk.FileDialog` suggesting `default_filename(datetime.now())` in the last-used folder, else XDG Documents, else home, with a `*.txt` filter
  - on success: `write_transcript`, `mark_saved(revision)`, remember the folder and update the summary
  - `DISMISSED` or `CANCELLED` is ignored
  - any other `GLib.Error`, an `OSError` or a non-local `Gio.File` is shown with `set_history_error`

  Verify in the running app:
  - saving during captioning writes the expected format and captioning continues
  - cancelling writes nothing
  - saving to a read-only folder (for example `/`) shows a red error and keeps the history
  - the second save opens in the same folder
- [x] 3.3 Add the clear flow (design D8): a `Gtk.AlertDialog` with Cancel (the default and cancel button) and Clear, whose detail line gives the sentence count and whether it is unsaved. Verify in the running app that Escape and Cancel keep the history, Clear empties it and leaves the overlay as it is, and captions recorded after clearing appear under a new session line in the next save
- [x] 3.4 Add the close prompt (design D9):
  - a `_quit()` helper
  - `_on_control_close` returns `True` and shows Cancel, Discard and Save… when `has_unsaved`
  - a `_closing_prompt` guard against repeated close requests
  - Save… quits only after a successful write

  Verify in the running app:
  - closing with unsaved history asks first
  - Cancel keeps captioning running
  - Discard quits without writing
  - Save… followed by cancelling the file dialog stays open
  - Save… followed by a read-only folder shows the error and stays open
  - Save… to a valid folder writes the file and quits
  - closing straight after a save, or with an empty history, quits without asking
- [x] 3.5 Add a "Caption history" section to `README.md`: what is recorded (final English only, never Korean or partial text), that the history lasts until Clear or quit and is never written without saving, the file format with a short example, that times are approximate (when text became final), the close prompt, and that saving needs GTK 4.10 or newer. Extend the **Privacy** section to say that history stays in memory unless saved. Verify the documented steps match the app

## 4. Integration checks

- [x] 4.1 Run the full suite with `python -m unittest discover -s tests -v` and verify all tests pass
- [x] 4.2 Manual acceptance in the running app:
  - two sessions (system audio, then mic) with a Stop in between appear in one saved file, each under its own session line
  - with translation on, the saved file contains no Hangul (check with `grep -P '[\x{AC00}-\x{D7A3}]' file` returning nothing)
  - shrinking the overlay or raising the font size mid-session does not remove earlier sentences from the saved file
  - an unfinished sentence at Stop is saved on its own line
  - English captions appear as quickly as before (spot-check with `scripts/bench_latency.py`, whose median first appearance should stay at or under 0.9 s)
- [x] 4.3 Add a `1.2.0` entry to `CHANGELOG.md` and bump `version` in `pyproject.toml`. Verify `openspec validate caption-history-export --strict` passes

## Workflow follow-up

- Archive the change with `/opsx:archive` after acceptance, which syncs the `caption-history` spec into `openspec/specs/`.
