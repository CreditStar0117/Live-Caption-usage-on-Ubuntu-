"""Tests for the English caption history, its file text and the file write."""

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from caption_english.history import (
    CaptionHistory,
    default_filename,
    history_summary,
    write_transcript,
)

T0 = datetime(2026, 11, 25, 14, 2, 55)


class FakeClock:
    def __init__(self, start: datetime = T0) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> datetime:
        self.now += timedelta(seconds=seconds)
        return self.now


def _sentences(history: CaptionHistory) -> list[tuple[datetime, str]]:
    return [(s.time, s.text) for session in history.sessions for s in session.sentences]


class GroupingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.history = CaptionHistory(clock=self.clock)
        self.history.start_session("system")

    def test_sentence_split_across_phrases_is_timed_at_first_phrase(self) -> None:
        t1 = self.clock.advance(5)
        self.history.add_final("The meeting starts")
        self.assertEqual(_sentences(self.history), [])
        self.clock.advance(3)
        self.history.add_final("at three o'clock.")
        self.assertEqual(_sentences(self.history), [(t1, "The meeting starts at three o'clock.")])
        self.assertEqual(self.history.pending, "")

    def test_two_sentences_in_one_phrase(self) -> None:
        t1 = self.clock.advance(1)
        self.history.add_final("Welcome back to the show. Today we talk about Linux audio.")
        self.assertEqual(
            _sentences(self.history),
            [(t1, "Welcome back to the show."), (t1, "Today we talk about Linux audio.")],
        )

    def test_later_sentences_are_timed_at_their_phrase(self) -> None:
        t1 = self.clock.advance(1)
        self.history.add_final("First part")
        t2 = self.clock.advance(4)
        self.history.add_final("ends here. Second one")
        t3 = self.clock.advance(2)
        self.history.add_final("is done.")
        self.assertEqual(
            _sentences(self.history),
            [(t1, "First part ends here."), (t2, "Second one is done.")],
        )
        self.assertLess(t2, t3)

    def test_end_session_closes_pending_and_next_session_starts_fresh(self) -> None:
        t1 = self.clock.advance(1)
        self.history.add_final("No full stop here")
        self.history.end_session()
        self.assertEqual(_sentences(self.history), [(t1, "No full stop here")])
        self.history.start_session("mic")
        t2 = self.clock.advance(10)
        self.history.add_final("new words.")
        self.assertEqual(self.history.sessions[1].source, "mic")
        self.assertEqual(
            [(s.time, s.text) for s in self.history.sessions[1].sentences],
            [(t2, "new words.")],
        )

    def test_empty_and_whitespace_finals_are_ignored(self) -> None:
        revision = self.history.revision
        self.history.add_final("")
        self.history.add_final("   \n ")
        self.assertEqual(self.history.sentence_count, 0)
        self.assertEqual(self.history.revision, revision)

    def test_whitespace_is_normalized(self) -> None:
        self.history.add_final("  Hello\n   there.  ")
        self.assertEqual(_sentences(self.history)[0][1], "Hello there.")

    def test_count_includes_pending(self) -> None:
        self.history.add_final("One. Two")
        self.assertEqual(self.history.sentence_count, 2)
        self.history.add_final("continues.")
        self.assertEqual(self.history.sentence_count, 2)

    def test_final_without_open_session_still_recorded(self) -> None:
        history = CaptionHistory(clock=self.clock)
        history.add_final("Hello.")
        self.assertEqual(history.sentence_count, 1)


class ClearAndSavedStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.history = CaptionHistory(clock=self.clock)

    def test_clear_during_open_session_keeps_a_fresh_session(self) -> None:
        self.history.start_session("both")
        self.history.add_final("Old text. Unfinished")
        cleared_at = self.clock.advance(60)
        self.history.clear()
        self.assertEqual(self.history.sentence_count, 0)
        self.assertEqual(self.history.pending, "")
        self.assertEqual(len(self.history.sessions), 1)
        self.assertEqual(self.history.sessions[0].started, cleared_at)
        self.assertEqual(self.history.sessions[0].source, "both")
        self.history.add_final("New text.")
        self.assertEqual(_sentences(self.history)[0][1], "New text.")

    def test_clear_while_stopped_leaves_no_session(self) -> None:
        self.history.start_session("system")
        self.history.add_final("Text.")
        self.history.end_session()
        self.history.clear()
        self.assertEqual(self.history.sessions, [])

    def test_has_unsaved_across_saves_captions_and_clears(self) -> None:
        self.assertFalse(self.history.has_unsaved)
        self.history.start_session("system")
        self.assertFalse(self.history.has_unsaved)  # an empty session is nothing to lose
        self.history.add_final("One.")
        self.assertTrue(self.history.has_unsaved)
        self.history.mark_saved(self.history.revision)
        self.assertFalse(self.history.has_unsaved)
        self.history.add_final("Two")
        self.assertTrue(self.history.has_unsaved)
        self.history.mark_saved(self.history.revision)
        saved_text = self.history.transcript(T0)
        self.history.end_session()  # the saved text already had the pending sentence
        self.assertEqual(self.history.transcript(T0), saved_text)
        self.assertFalse(self.history.has_unsaved)
        self.history.clear()
        self.assertFalse(self.history.has_unsaved)

    def test_save_of_older_revision_stays_unsaved(self) -> None:
        self.history.start_session("system")
        self.history.add_final("One.")
        written = self.history.revision
        self.history.add_final("Two.")
        self.history.mark_saved(written)
        self.assertTrue(self.history.has_unsaved)


class TranscriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.history = CaptionHistory(clock=self.clock)

    def test_two_sessions_and_empty_session_left_out(self) -> None:
        self.history.start_session("system")
        self.clock.advance(6)
        self.history.add_final("Welcome back to the show.")
        self.clock.advance(3)
        self.history.add_final("Today we talk about Linux audio.")
        self.history.end_session()
        self.clock.advance(60)
        self.history.start_session("mic")  # no captions: left out
        self.history.end_session()
        self.clock.now = datetime(2026, 11, 25, 14, 20, 40)
        self.history.start_session("mic")
        self.clock.advance(3)
        self.history.add_final("Can everyone hear me?")
        self.history.end_session()
        text = self.history.transcript(datetime(2026, 11, 25, 14, 30, 12))
        self.assertEqual(
            text,
            "Caption English caption history\n"
            "Saved 2026-11-25 14:30:12\n"
            "\n"
            "--- Session started 2026-11-25 14:02:55 (system audio) ---\n"
            "[14:03:01] Welcome back to the show.\n"
            "[14:03:04] Today we talk about Linux audio.\n"
            "\n"
            "--- Session started 2026-11-25 14:20:40 (mic audio) ---\n"
            "[14:20:43] Can everyone hear me?\n",
        )

    def test_pending_included_without_consuming_it(self) -> None:
        self.history.start_session("system")
        self.clock.advance(2)
        self.history.add_final("Done. Let's get started")
        text = self.history.transcript(T0)
        self.assertTrue(text.endswith("[14:02:57] Done.\n[14:02:57] Let's get started\n"))
        self.assertEqual(self.history.pending, "Let's get started")
        self.history.add_final("now.")
        self.assertEqual(_sentences(self.history)[-1][1], "Let's get started now.")

    def test_unicode_sentence(self) -> None:
        self.history.start_session("system")
        self.history.add_final("Café “déjà vu” — naïve.")
        self.assertIn("] Café “déjà vu” — naïve.\n", self.history.transcript(T0))

    def test_default_filename(self) -> None:
        self.assertEqual(
            default_filename(datetime(2026, 11, 25, 14, 30, 12)),
            "caption-history-2026-11-25-143012.txt",
        )

    def test_summary(self) -> None:
        self.assertEqual(history_summary(0, None), "Nothing recorded yet")
        self.assertEqual(history_summary(1, None), "1 sentence, not saved")
        self.assertEqual(history_summary(12, "a.txt"), "12 sentences, saved to a.txt")


class WriteTranscriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _leftovers(self) -> list[str]:
        return [p.name for p in self.dir.iterdir() if p.name.endswith(".tmp")]

    def test_writes_new_file_as_utf8(self) -> None:
        path = self.dir / "history.txt"
        write_transcript(path, "Héllo — “world”\n")
        self.assertEqual(path.read_bytes(), "Héllo — “world”\n".encode("utf-8"))
        self.assertEqual(self._leftovers(), [])

    def test_new_file_follows_umask(self) -> None:
        old = os.umask(0o027)
        try:
            path = self.dir / "history.txt"
            write_transcript(path, "x\n")
        finally:
            os.umask(old)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)

    def test_replaces_existing_file_and_keeps_mode(self) -> None:
        path = self.dir / "history.txt"
        path.write_text("old\n", encoding="utf-8")
        path.chmod(0o604)
        write_transcript(path, "new\n")
        self.assertEqual(path.read_text(encoding="utf-8"), "new\n")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o604)
        self.assertEqual(self._leftovers(), [])

    def test_failed_write_keeps_old_content_and_no_temp_file(self) -> None:
        path = self.dir / "history.txt"
        path.write_text("old\n", encoding="utf-8")
        with mock.patch("caption_english.history.os.write", side_effect=OSError(28, "No space")):
            with self.assertRaises(OSError):
                write_transcript(path, "new\n")
        self.assertEqual(path.read_text(encoding="utf-8"), "old\n")
        self.assertEqual(self._leftovers(), [])

    def test_missing_folder_raises(self) -> None:
        with self.assertRaises(OSError):
            write_transcript(self.dir / "missing" / "history.txt", "x\n")


if __name__ == "__main__":
    unittest.main()
