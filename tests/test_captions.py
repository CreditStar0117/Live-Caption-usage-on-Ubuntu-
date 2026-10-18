"""Tests for caption history, paragraph formatting and the sentence gap."""

from __future__ import annotations

import unittest

from caption_english.captions import (
    SENTENCE_GAP,
    format_captions,
    history_capacity,
    trim_history,
)

G = SENTENCE_GAP


class HistoryTests(unittest.TestCase):
    def test_capacity_grows_with_overlay_size(self) -> None:
        small = history_capacity(560, 100, 22)
        self.assertGreater(history_capacity(1100, 100, 22), small)
        self.assertGreater(history_capacity(560, 350, 22), small)

    def test_capacity_shrinks_with_font_size(self) -> None:
        self.assertLess(history_capacity(800, 300, 40), history_capacity(800, 300, 22))

    def test_capacity_covers_a_full_overlay(self) -> None:
        # 761x308 at 22 px fits roughly 1000-1300 characters of English text
        self.assertGreaterEqual(history_capacity(761, 308, 22), 1300)

    def test_keeps_everything_under_capacity(self) -> None:
        phrases = ["One.", "Two.", "Three."]
        self.assertEqual(trim_history(phrases, 1000), phrases)
        self.assertEqual(trim_history([], 1000), [])

    def test_drops_only_oldest_beyond_capacity(self) -> None:
        phrases = [f"{i}" * 99 for i in range(10)]  # 100 characters each with a space
        kept = trim_history(phrases, 350)
        # Newest three hold 300 characters; the fourth crosses 350 and is kept
        self.assertEqual(kept, phrases[-4:])

    def test_never_drops_newest_phrase(self) -> None:
        phrases = ["old", "x" * 500]
        self.assertEqual(trim_history(phrases, 100), ["x" * 500])


class SentenceGapTests(unittest.TestCase):
    def test_gap_between_sentences(self) -> None:
        self.assertEqual(
            format_captions(["Welcome back. Today we talk about audio! Ready?"]),
            f"Welcome back.{G}Today we talk about audio!{G}Ready?",
        )

    def test_gap_between_final_phrases(self) -> None:
        self.assertEqual(
            format_captions(["Welcome back to the show.", "Today we talk about audio."]),
            f"Welcome back to the show.{G}Today we talk about audio.",
        )

    def test_sentence_split_across_phrases_uses_word_space(self) -> None:
        self.assertEqual(
            format_captions(["Today we are talking about", "Linux audio."]),
            "Today we are talking about Linux audio.",
        )

    def test_in_progress_partial_gets_gap(self) -> None:
        self.assertEqual(
            format_captions(["That is how it works.", "So let's get started"]),
            f"That is how it works.{G}So let's get started",
        )

    def test_empty_partial_adds_no_trailing_gap(self) -> None:
        self.assertEqual(format_captions(["Done here.", ""]), "Done here.")
        self.assertEqual(format_captions(["", ""]), "")
        self.assertEqual(format_captions([]), "")

    def test_inline_periods_are_not_boundaries(self) -> None:
        self.assertEqual(
            format_captions(["Version 3.5 is on example.com today."]),
            "Version 3.5 is on example.com today.",
        )

    def test_closing_quote_and_bracket_stay_with_sentence(self) -> None:
        self.assertEqual(
            format_captions(['He said "stop." Then (quietly.) he left.']),
            f'He said "stop."{G}Then (quietly.){G}he left.',
        )

    def test_ellipsis_ends_sentence(self) -> None:
        self.assertEqual(format_captions(["Well… Maybe."]), f"Well…{G}Maybe.")

    def test_whitespace_is_collapsed(self) -> None:
        self.assertEqual(
            format_captions(["  One   two.\n", "  Three  "]),
            f"One two.{G}Three",
        )


if __name__ == "__main__":
    unittest.main()
