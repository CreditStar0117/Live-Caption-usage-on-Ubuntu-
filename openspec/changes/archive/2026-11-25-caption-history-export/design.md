# Design

## Context

See proposal.md (Why) for motivation, and the `caption-history` delta spec for requirements.

How captions reach the app today:
- `SpeechToText` sends `(text, is_final)` through `GLib.idle_add` to `CaptionEnglishApp._show_text`, which runs on the GTK thread. A session counter (`self._session`) turns callbacks from a stopped session into no-ops.
- With translation off, `_show_text` keeps `self._finals`, trimmed with `history_capacity`/`trim_history`. With translation on, `BilingualCaptions` keeps sentence blocks, trimmed with `trim_blocks`. Both drop old text on purpose, so neither can serve as a full record.
- Korean text arrives only through `_show_translation`, never through `_show_text`.
- `captions.py` already has the sentence rules: `split_complete(text)` and `split_sentences(text)`, built on the same sentence-end pattern as the overlay's gaps.
- Final phrases do not line up with sentences. A final phrase can end mid-sentence or hold several sentences (see the live-korean-translation design, Context).
- Closing the control window calls `_on_control_close`, which stops captioning, saves the config and quits. Closing the overlay only hides it.
- The app runs on GTK 4.14 here (Ubuntu 24.04). `Gtk.FileDialog` and `Gtk.AlertDialog` exist from GTK 4.10.

## Goals / Non-Goals

**Goals:**
- One full English record per app run, independent of the overlay's trimming and of the translation mode.
- History logic, file text and file writing testable without GTK.
- No effect on caption latency: recording is a few string operations per final phrase on the GTK thread.

**Non-Goals:**
- Automatic or periodic saving, or recovering history after a crash. The user chose manual saving only.
- Saving Korean, partial text, or audio.
- Other file formats (SRT, VTT, JSON, Markdown) or per-word timing.
- Viewing or searching the history inside the app.
- Keeping history across app restarts.
- Asking about unsaved history when the app ends other than by closing the control window (Ctrl+C in a terminal, logout, `kill`).

## Decisions

### D1. A GTK-free `CaptionHistory` in a new `history.py`
`src/caption_english/history.py` holds the data and logic:

- `HistorySentence(time: datetime, text: str)`
- `HistorySession(started: datetime, source: str, sentences: list[HistorySentence])`
- `CaptionHistory(clock: Callable[[], datetime] = datetime.now)`, with:
  - `start_session(source)`: appends a new, empty session.
  - `add_final(text)`: groups final text into sentences (D2).
  - `end_session()`: closes any unfinished sentence (D2).
  - `clear()`: empties everything. If a session is open, a fresh one starts at the clear time with the same source, so captions that follow still have a session line.
  - `sentence_count`: complete sentences, plus one when an unfinished sentence is pending.
  - `has_unsaved`, `mark_saved(revision)` and `revision` (D5).
  - `transcript(saved_at) -> str`: the file text (D3).

The class runs only on the GTK thread, so it needs no lock.

It is a separate class, not an extension of `BilingualCaptions`, for three reasons. `BilingualCaptions` exists only while translation is on, its blocks are trimmed to the overlay, and its flush timing (2 s quiet, 8 s max) is tuned for translation latency. The history needs none of that.

### D2. Sentence grouping and timestamps
`add_final(text)` at clock time `now`:
1. Normalize whitespace. Ignore empty text.
2. If nothing is pending, set `pending_since = now`.
3. Run `split_complete(f"{pending} {text}")` to get `(complete, rest)`.
4. Split `complete` with `split_sentences`. The first sentence gets `pending_since`, because its first words became final then. Any further sentences get `now`, because they began in this phrase.
5. Set `pending = rest`. If `rest` is non-empty and `complete` was non-empty, set `pending_since = now`.

`end_session()` turns any pending text into a sentence at `pending_since`, so it is never joined with the next session's first words (spec: "Unfinished sentence when captioning stops").

A sentence's time is when its first words *became final*. That is about 0.5 s after the phrase ended for short phrases, and up to about 10 s after speech started for long ones. Using the speech time itself would need audio timestamps from `SpeechToText`, which it does not expose. The README says that times are approximate.

Recording happens in `_show_text`, right after the session check and before the translation branch:

```python
if is_final:
    self.history.add_final(text)
```

This runs the same way in English-only and two-language mode. Korean never passes through `_show_text`, so it cannot be recorded. `start_captioning` calls `history.start_session(self.config.audio_source)` and `stop_captioning` calls `history.end_session()`. `_fail_stop` goes through `stop_captioning`, so a session that stops on an error is closed the same way.

### D3. File text
```
Caption English caption history
Saved 2026-11-25 14:30:12

--- Session started 2026-11-25 14:02:55 (system audio) ---
[14:03:01] Welcome back to the show.
[14:03:04] Today we talk about Linux audio.

--- Session started 2026-11-25 14:20:40 (mic audio) ---
[14:20:43] Can everyone hear me?
[14:20:47] Let's get started
```
- UTF-8 without BOM, `\n` line endings, and a trailing newline.
- Sessions with no sentences are left out.
- A pending, unfinished sentence is written as the last line, at `pending_since`. It is not removed from pending, so later words still join it.
- Sentence text is written as it was recognized. The overlay's em-space sentence gap is not used.
- The audio source label is `system`, `mic` or `both`, as in the control window.

`default_filename(now)` returns `caption-history-2026-11-25-143012.txt`. Including the seconds means two saves in the same minute do not suggest the same name.

### D4. Writing the file safely
`write_transcript(path, text)` writes to a temporary file in the target's folder, then replaces the target:
- The temporary name is `.<name>.<random>.tmp`. It is created with `os.open(..., O_WRONLY | O_CREAT | O_EXCL, 0o666)`, so the user's umask sets its permissions just as for any new file.
- After `write`, `flush` and `os.fsync`, `os.replace` moves it over the target. If the target already exists, its permission bits are copied to the temporary file first.
- On any `OSError`, the temporary file is removed and the error is raised again. The existing file is never left half written (spec: "Overwriting an existing file fails").

The text is generated and written synchronously on the GTK thread. A full day is about 1 MB, which writes in milliseconds. This also means no new captions can be added between taking the text and marking it saved.

### D5. Saved state
`revision` increases on every `add_final` that changes the history. `end_session` does not increase it: the saved text already shows pending text as a sentence at the same time, so closing it leaves the file text unchanged, and a save made just before Stop still counts as saved. A save records the revision it wrote with `mark_saved(revision)`. `has_unsaved` is `revision != saved_revision and sentence_count > 0`. A clear resets both counters, which leaves nothing unsaved.

### D6. Control window: Caption history section
A new `Gtk.Frame(label="Caption history")` sits between Translation and the Start/Stop row. It contains:
- A summary label: "Nothing recorded yet", "12 sentences, not saved", or "12 sentences, saved to caption-history-….txt".
- **Save history…** and **Clear…** buttons. Both are insensitive while the history is empty. Neither is locked while captioning.
- A status label for save errors. It uses the `error` CSS class, in the same way as the translation status (live-korean-translation D9). The main status line belongs to captioning, which would overwrite a save error.

`_show_text` calls `control.update_history(count, saved_name)` after recording. It already runs on the GTK thread, so no `idle_add` is needed.

### D7. Save dialog
The dialog is a `Gtk.FileDialog` used with `save(parent, None, callback)`:
- The initial name comes from `default_filename(datetime.now())`.
- The initial folder is the folder last saved to in this run. Otherwise it is the XDG Documents folder (`GLib.get_user_special_dir(DIRECTORY_DOCUMENTS)`) if that exists, and the home folder if not.
- It has a "Text files (*.txt)" filter and an "All files" filter.
- The name is kept exactly as the user typed it. No `.txt` is added.
- GTK itself asks before overwriting an existing file.

In the callback, `save_finish` raises `GLib.Error`. `Gtk.DialogError.DISMISSED` or `CANCELLED` means the user cancelled, and nothing happens. Any other error is shown as a save error. A `Gio.File` without a local path (`get_path()` is `None`) is reported as "Choose a folder on this computer".

On success, the app records the folder, calls `mark_saved`, updates the summary and clears the error label.

### D8. Clear confirmation
A `Gtk.AlertDialog` asks "Clear caption history?" with buttons **Cancel** and **Clear**. Cancel is the cancel and default button, so pressing Enter or Escape keeps the history. The detail line says "N sentences will be removed." and adds "They have not been saved." when `has_unsaved` is true. The overlay is not touched.

### D9. Asking before quitting
`_on_control_close` now does the following:
- When `history.has_unsaved` is false, it behaves as today: stop, save the config, quit.
- When it is true, it returns `True`, which keeps the window open, and shows a `Gtk.AlertDialog`: "Save caption history before quitting?" with buttons **Cancel**, **Discard** and **Save…**. Cancel is the cancel button and Save is the default button.
  - **Save…** opens the save dialog (D7) with `quit_after=True`. The app quits only once the file has been written. A cancelled dialog or a write error leaves the app open, and a write error is shown in red.
  - **Discard** quits.
  - **Cancel** does nothing, and captioning keeps running.
- A `_closing_prompt` flag ignores repeated close requests while the prompt or save dialog is open.

Quitting is moved into one `_quit()` helper (stop captioning, save the config, `self.quit()`) so every path does the same thing.

### D10. GTK version
`Gtk.FileDialog` and `Gtk.AlertDialog` need GTK 4.10 or newer. There is no fallback to the deprecated `Gtk.FileChooserNative` or `Gtk.MessageDialog`. On older GTK (Ubuntu 22.04 ships 4.6), the history section shows "Saving history needs GTK 4.10 or newer". Save and Clear are then unavailable, the close prompt is skipped, and the rest of the app works as before. The README states the requirement.

Alternative considered: implementing both dialog APIs. That roughly doubles the dialog code for a release no longer in use on the target machine. It can be added later without changing the spec.

### D11. Tests
New `tests/test_history.py`, using a fake clock that returns fixed `datetime`s:
- A sentence split across two phrases is timed at the first phrase.
- Two sentences in one phrase become two sentences.
- `end_session` closes the pending text, and the next session's first words start a new sentence.
- Empty and whitespace-only finals are ignored.
- `sentence_count` counts pending text.
- The transcript has the header, session lines, `[HH:MM:SS]` lines and a trailing newline, leaves out empty sessions, and includes pending text without consuming it.
- `clear` during an open session keeps a session for later captions.
- `has_unsaved` and `mark_saved` across saves, new captions and clears.
- `default_filename`.
- `write_transcript` against a temporary folder:
  - it writes a new file
  - it replaces an existing file and keeps its mode
  - a failing write, simulated by patching `os.write`, leaves the old content and no `.tmp` file
  - a missing folder raises `OSError`

The GTK wiring (dialogs, close prompt) is checked by hand in the running app.

## Risks / Trade-offs

- [A crash or `kill` loses the unsaved history] → This follows from the user's choice of manual saving. The close prompt covers the usual way of quitting. Automatic saving can be added later as a separate change.
- [Times show when text became final, not exactly when it was spoken (up to about 10 s later for long phrases)] → The README says that times are approximate. They are accurate enough to find a moment in a recording.
- [A session that runs past midnight shows `[00:00:05]` after `[23:59:58]`, with no date change] → The session line carries the date. This is rare, and the time order still reads correctly.
- [History grows without limit] → About 100 bytes per sentence, or about 1 MB for a full day. This is negligible next to the speech model.
- [GTK older than 4.10 cannot save] → It is stated in the README and in the control window, and the rest of the app is unaffected (D10).
- [A modal prompt on close could surprise users who never save] → It appears only when there is unsaved history. Discard is one click away.

## Migration Plan

No settings or files change. Older config files load unchanged. Rolling back means reverting the release, and no data needs migrating.
