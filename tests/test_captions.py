"""Tests for caption history, paragraph formatting and the sentence gap."""

from __future__ import annotations

import html
import unittest

from caption_english.captions import (
    FLUSH_MAX_SECONDS,
    FLUSH_QUIET_SECONDS,
    KOREAN_COLOR,
    BilingualCaptions,
    SENTENCE_GAP,
    CaptionBlock,
    format_bilingual,
    format_captions,
    history_capacity,
    split_complete,
    split_sentences,
    text_width_em,
    trim_blocks,
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


class SplitCompleteTests(unittest.TestCase):
    def test_single_complete_sentence(self) -> None:
        self.assertEqual(split_complete("We start at noon."), ("We start at noon.", ""))

    def test_sentences_and_unfinished_tail(self) -> None:
        self.assertEqual(
            split_complete("Welcome back. Ready? Today we are"),
            ("Welcome back. Ready?", "Today we are"),
        )

    def test_no_sentence_end(self) -> None:
        self.assertEqual(split_complete("Today we are talking"), ("", "Today we are talking"))
        self.assertEqual(split_complete("   "), ("", ""))

    def test_inline_periods_do_not_split(self) -> None:
        self.assertEqual(
            split_complete("Version 3.5 is on example.com and"),
            ("", "Version 3.5 is on example.com and"),
        )
        self.assertEqual(
            split_complete("Version 3.5 is out. See example.com"),
            ("Version 3.5 is out.", "See example.com"),
        )

    def test_closing_quote_stays_with_sentence(self) -> None:
        self.assertEqual(
            split_complete('He said "stop." Then he'), ('He said "stop."', "Then he")
        )
        self.assertEqual(split_complete("It was done (finally.)"), ("It was done (finally.)", ""))

    def test_ellipsis_ends_sentence(self) -> None:
        self.assertEqual(split_complete("Well… maybe"), ("Well…", "maybe"))

    def test_whitespace_is_collapsed(self) -> None:
        self.assertEqual(split_complete("  One   two.\n Three "), ("One two.", "Three"))


class SplitSentencesTests(unittest.TestCase):
    def test_sentences_and_tail(self) -> None:
        self.assertEqual(
            split_sentences("Welcome back. Ready? Version 3.5 is on example.com and"),
            ["Welcome back.", "Ready?", "Version 3.5 is on example.com and"],
        )

    def test_quotes_and_empty(self) -> None:
        self.assertEqual(split_sentences('He said "stop." Then (quietly.)'), ['He said "stop."', "Then (quietly.)"])
        self.assertEqual(split_sentences("  "), [])


def _block(i: int, english: str, korean: str | None = None) -> CaptionBlock:
    return CaptionBlock(id=i, english=english, korean=korean)


class BlockHistoryTests(unittest.TestCase):
    def test_korean_counts_wider_than_latin(self) -> None:
        self.assertGreater(text_width_em("안녕하세요"), 2 * text_width_em("hello"))
        # 80 Hangul wrap onto two 800 px lines at 22 px; 80 Latin letters fit on one
        wide = [_block(i, "x", "가" * 80) for i in range(200)]
        narrow = [_block(i, "x", "a" * 80) for i in range(200)]
        kept_wide, _ = trim_blocks(wide, 800, 300, 22)
        kept_narrow, _ = trim_blocks(narrow, 800, 300, 22)
        self.assertLess(len(kept_wide), len(kept_narrow))

    def test_bigger_overlay_keeps_more(self) -> None:
        # Long enough to wrap at 560 px but not at 1100 px
        english = "Hello there, this is a much longer test sentence that wraps on a narrow overlay."
        blocks = [_block(i, english, "안녕하세요, 이것은 좁은 화면에서 줄이 바뀌는 긴 테스트 문장입니다.") for i in range(300)]
        small, _ = trim_blocks(blocks, 560, 100, 22)
        self.assertGreater(len(trim_blocks(blocks, 1100, 100, 22)[0]), len(small))
        self.assertGreater(len(trim_blocks(blocks, 560, 350, 22)[0]), len(small))

    def test_bigger_font_keeps_fewer(self) -> None:
        blocks = [_block(i, "Hello there, this is a test sentence.", "안녕하세요 테스트") for i in range(300)]
        self.assertLess(
            len(trim_blocks(blocks, 800, 300, 40)[0]), len(trim_blocks(blocks, 800, 300, 22)[0])
        )

    def test_drops_only_oldest(self) -> None:
        blocks = [_block(i, f"Sentence {i}.", "문장") for i in range(300)]
        kept, dropped = trim_blocks(blocks, 800, 160, 22)
        self.assertLess(len(kept), len(blocks))
        self.assertEqual(kept, blocks[-len(kept) :])
        self.assertEqual(dropped, [b.id for b in blocks[: len(blocks) - len(kept)]])

    def test_keeps_everything_that_fits(self) -> None:
        blocks = [_block(0, "One.", "하나."), _block(1, "Two.")]
        self.assertEqual(trim_blocks(blocks, 800, 160, 22), (blocks, []))
        self.assertEqual(trim_blocks([], 800, 160, 22), ([], []))

    def test_never_drops_newest(self) -> None:
        blocks = [_block(0, "old"), _block(1, "x" * 5000, "가" * 2000)]
        self.assertEqual(trim_blocks(blocks, 320, 80, 72), ([blocks[1]], [0]))

    def test_full_overlay_is_filled(self) -> None:
        # Enough text is kept to cover the visible lines of a 761x308 overlay at 22 px
        blocks = [_block(i, "This is a fairly typical spoken sentence.", "이것은 꽤 전형적인 문장입니다.") for i in range(300)]
        kept, _ = trim_blocks(blocks, 761, 308, 22)
        self.assertGreaterEqual(len(kept) * 2, 308 // (22 * 1.2))


def _span(text: str) -> str:
    return f'<span foreground="{KOREAN_COLOR}">{text}</span>'


class BilingualFormatTests(unittest.TestCase):
    def test_blocks_in_order_with_korean_below(self) -> None:
        blocks = [_block(0, "Hello.", "안녕하세요."), _block(1, "Thanks.", "감사합니다.")]
        self.assertEqual(
            format_bilingual(blocks, "", html.escape),
            "\n".join(["Hello.", _span("안녕하세요."), "Thanks.", _span("감사합니다.")]),
        )

    def test_untranslated_block_is_english_only(self) -> None:
        blocks = [_block(0, "Hello.", "안녕하세요."), _block(1, "Not yet.")]
        self.assertEqual(
            format_bilingual(blocks, "", html.escape),
            "\n".join(["Hello.", _span("안녕하세요."), "Not yet."]),
        )

    def test_open_english_follows_last_block(self) -> None:
        blocks = [_block(0, "Hello.", "안녕하세요.")]
        self.assertEqual(
            format_bilingual(blocks, "and now we", html.escape),
            "\n".join(["Hello.", _span("안녕하세요."), "and now we"]),
        )
        self.assertEqual(format_bilingual([], "just started", html.escape), "just started")
        self.assertEqual(format_bilingual([], "", html.escape), "")

    def test_sentence_gaps_in_both_languages(self) -> None:
        blocks = [_block(0, "One. Two.", "하나. 둘.")]
        self.assertEqual(
            format_bilingual(blocks, "", html.escape),
            f"One.{G}Two.\n" + _span(f"하나.{G}둘."),
        )

    def test_text_is_escaped(self) -> None:
        blocks = [_block(0, 'a < b & "c" > d', "x < y & 'z'")]
        out = format_bilingual(blocks, "<b>not bold</b>", html.escape)
        self.assertEqual(
            out,
            "\n".join(
                [
                    "a &lt; b &amp; &quot;c&quot; &gt; d",
                    _span("x &lt; y &amp; &#x27;z&#x27;"),
                    "&lt;b&gt;not bold&lt;/b&gt;",
                ]
            ),
        )

    def test_empty_translation_adds_no_line(self) -> None:
        self.assertEqual(format_bilingual([_block(0, "Hmm.", "")], "", html.escape), "Hmm.")


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class BilingualCaptionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.submitted: list[tuple[int, str]] = []
        self.discarded: list[int] = []
        self.caps = BilingualCaptions(
            submit=lambda i, t: self.submitted.append((i, t)),
            discard=self.discarded.extend,
            clock=self.clock,
        )

    def test_complete_sentences_close_immediately(self) -> None:
        self.caps.add_final("Welcome back. Today we talk about audio.")
        self.assertEqual(self.submitted, [(0, "Welcome back. Today we talk about audio.")])
        self.assertEqual(self.caps.pending, "")

    def test_sentence_split_across_phrases_closes_once(self) -> None:
        self.caps.add_final("Hello. Today we are talking")
        self.assertEqual(self.submitted, [(0, "Hello.")])
        self.assertEqual(self.caps.pending, "Today we are talking")
        self.caps.add_final("about Linux audio. And then")
        self.assertEqual(
            self.submitted, [(0, "Hello."), (1, "Today we are talking about Linux audio.")]
        )
        self.assertEqual(self.caps.pending, "And then")

    def test_final_clears_partial(self) -> None:
        self.caps.set_partial("Hello wor")
        self.caps.add_final("Hello world.")
        self.assertEqual(self.caps.partial, "")
        self.caps.add_final("   ")
        self.assertEqual(len(self.submitted), 1)

    def test_quiet_flush_after_two_seconds(self) -> None:
        self.caps.add_final("And that is why we")
        self.clock.now += FLUSH_QUIET_SECONDS - 0.1
        self.assertFalse(self.caps.flush_due())
        self.clock.now += 0.2
        self.assertTrue(self.caps.flush_due())
        self.assertEqual(self.submitted, [(0, "And that is why we")])
        self.assertFalse(self.caps.flush_due())

    def test_partial_in_progress_blocks_quiet_flush(self) -> None:
        self.caps.add_final("And that is why we")
        self.caps.set_partial("decided to")
        self.clock.now += FLUSH_QUIET_SECONDS + 1
        self.assertFalse(self.caps.flush_due())
        self.caps.set_partial("")  # the partial was noise and got retracted
        self.assertTrue(self.caps.flush_due())

    def test_forced_flush_during_continuous_speech(self) -> None:
        self.caps.add_final("so we kept going")
        self.caps.set_partial("and going")
        self.clock.now += 3
        self.caps.add_final("and going")  # resets the quiet timer, not the age
        self.caps.set_partial("and")
        self.clock.now += FLUSH_MAX_SECONDS - 3 - 0.1
        self.assertFalse(self.caps.flush_due())
        self.clock.now += 0.2
        self.assertTrue(self.caps.flush_due())
        self.assertEqual(self.submitted, [(0, "so we kept going and going")])
        self.assertEqual(self.caps.partial, "and")

    def test_rest_after_a_sentence_has_its_own_age(self) -> None:
        self.caps.add_final("no end yet")
        self.clock.now += 6
        self.caps.add_final("here. New one")
        self.caps.set_partial("still")
        self.clock.now += FLUSH_MAX_SECONDS - 1
        self.assertFalse(self.caps.flush_due())

    def test_translation_attaches_to_its_block(self) -> None:
        self.caps.add_final("One. Two")
        self.caps.add_final("three.")
        self.assertTrue(self.caps.set_translation(1, "둘 셋."))
        self.assertTrue(self.caps.set_translation(0, "하나."))
        self.assertEqual(
            [(b.english, b.korean) for b in self.caps.blocks],
            [("One.", "하나."), ("Two three.", "둘 셋.")],
        )
        self.assertFalse(self.caps.set_translation(99, "없음"))

    def test_markup_shows_open_english_last(self) -> None:
        self.caps.add_final("Hello. And")
        self.caps.set_partial("then")
        self.caps.set_translation(0, "안녕.")
        self.assertEqual(
            self.caps.markup(html.escape), "Hello.\n" + _span("안녕.") + "\nAnd then"
        )

    def test_trim_discards_dropped_blocks(self) -> None:
        for i in range(300):
            self.caps.add_final(f"Sentence number {i}.")
        self.caps.trim(800, 160, 22)
        kept = [b.id for b in self.caps.blocks]
        self.assertEqual(kept[-1], 299)
        self.assertEqual(self.discarded, list(range(kept[0])))

    def test_stop_translating_keeps_building_blocks(self) -> None:
        self.caps.add_final("Before.")
        self.caps.stop_translating()
        self.caps.add_final("After.")
        self.caps.trim(320, 80, 72)
        self.assertEqual(self.submitted, [(0, "Before.")])
        self.assertEqual([b.english for b in self.caps.blocks][-1], "After.")
        self.assertEqual(self.discarded, [])


if __name__ == "__main__":
    unittest.main()
