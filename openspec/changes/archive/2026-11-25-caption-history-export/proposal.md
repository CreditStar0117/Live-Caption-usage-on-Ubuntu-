# Proposal

## Why

Captions disappear once they scroll out of the overlay. The overlay keeps only enough history to fill its window, so nothing that was said earlier in a talk, meeting or video can be read again or kept. Users want a record of what was said that they can review, search or share afterwards. Saving it as a plain text file keeps it on the user's own machine, in line with the app's promise that nothing leaves the computer.

## What Changes

- The app keeps a **full English caption history** for the whole app run. It is separate from the overlay's history and is not trimmed when captions scroll out of the overlay. It keeps growing across Stop and Start until the user clears it or quits the app.
- Only **final English text** goes into the history. Partial (in-progress) text is never recorded. **Korean translations are never recorded**, even when Korean translation is on.
- The history is grouped into **sentences**, each with the clock time it started, using the same sentence rules as the captions.
- A new **Caption history** section in the control window shows how many sentences have been recorded. It has a **Save history…** button that opens a file dialog to save the history as a UTF-8 `.txt` file, and a **Clear** button that asks for confirmation before emptying the history.
- The saved file has a short header with the save date and time. Each captioning session starts with a line giving its date, start time and audio source, followed by one `[HH:MM:SS] sentence` line per sentence. An unfinished sentence at the moment of saving is included as the last line.
- Saving works while captioning is running or stopped. Captioning is not interrupted, and the history is kept after saving.
- When the user closes the app with history that has not been saved, the app asks whether to **save, discard or cancel**, so a whole session is not lost by accident.
- If the file cannot be written, the control window shows the error in red and the history is kept.
- Nothing is written to disk unless the user saves. There is no automatic saving.

## Capabilities

### New Capabilities

- `caption-history`: recording the English caption history for the app run, and saving it to a text file. Covers what is recorded (final English only, grouped into timestamped sentences), how long it lasts, the file format, the save and clear controls, the prompt before quitting with unsaved history, and save errors.

### Modified Capabilities

None. The overlay, speech recognition and translation behave as before. The history reads the same final English text the overlay already gets.

## Impact

- **Code**
  - New `src/caption_english/history.py` (no GTK): the history store, sentence grouping with timestamps, the file text, the default file name and the file write.
  - `src/caption_english/app.py`: records final English in `_show_text` for both the English-only and two-language paths, adds the Caption history section to the control window, adds the save and clear dialogs, and asks before quitting.
- **Config**: none. The history is kept in memory only, and the last folder used for saving is remembered for the current app run only.
- **Dependencies**: none. `Gtk.FileDialog` and `Gtk.AlertDialog` need GTK 4.10 or newer. Ubuntu 24.04 ships GTK 4.14, which the app already uses.
- **Memory**: the history grows by roughly 100 bytes per sentence, which is about 1 MB for a full working day of speech. There is no cap.
- **Tests**: new `tests/test_history.py` covering sentence grouping across phrases, timestamps, session lines, English-only recording, clearing, the file text and writing the file.
- **Docs**: a README section on caption history, and a CHANGELOG entry.
