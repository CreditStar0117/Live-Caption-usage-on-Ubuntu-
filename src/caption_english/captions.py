"""Caption text: history kept for the overlay, and paragraph formatting."""

from __future__ import annotations

import math
import re
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

# EM SPACE + EN SPACE: a 1.5 em gap that scales with the font size. Both are
# line-break class BA (no break before), so a wrapped line never starts with it.
SENTENCE_GAP = "  "

_WHITESPACE = re.compile(r"\s+")
# . ? ! or … (plus closing quotes/brackets) followed by whitespace ends a
# sentence; "3.5" or "example.com" have no whitespace after the period.
_SENTENCE_END = re.compile(r"([.?!…][\"'”’)\]]*) (?=\S)")
# The same sentence end, also accepted at the end of the text
_SENTENCE_END_ANYWHERE = re.compile(r"[.?!…][\"'”’)\]]*(?=\s|$)")

# Smallest average character width and line height (in em) measured across
# common UI fonts, so the estimate errs toward keeping more text, not less
_CHAR_WIDTH_EM = 0.33
_LINE_HEIGHT_EM = 1.14
# History beyond one full overlay: covers wrap waste at line ends and resizes
_HISTORY_MARGIN = 1.5
# Hangul and other East Asian wide characters, on the small side for the same reason
_WIDE_CHAR_WIDTH_EM = 0.9


def history_capacity(width: int, height: int, font_px: int) -> int:
    """Characters of caption text needed to fill an overlay of this size."""
    per_line = width / (_CHAR_WIDTH_EM * font_px)
    lines = height / (_LINE_HEIGHT_EM * font_px)
    return int(per_line * lines * _HISTORY_MARGIN)


def trim_history(phrases: list[str], capacity: int) -> list[str]:
    """Drop the oldest phrases that are not needed to fill *capacity* characters."""
    total = 0
    for i in range(len(phrases) - 1, -1, -1):
        total += len(phrases[i]) + 1
        if total >= capacity:
            return phrases[i:]
    return phrases


def format_captions(phrases: list[str]) -> str:
    """Join final phrases and the in-progress text for display."""
    text = _WHITESPACE.sub(" ", " ".join(phrases)).strip()
    return _SENTENCE_END.sub(lambda m: m.group(1) + SENTENCE_GAP, text)


def split_complete(text: str) -> tuple[str, str]:
    """Split *text* after its last sentence end into (complete sentences, unfinished rest)."""
    text = _WHITESPACE.sub(" ", text).strip()
    last = None
    for last in _SENTENCE_END_ANYWHERE.finditer(text):
        pass
    if last is None:
        return "", text
    return text[: last.end()].strip(), text[last.end() :].strip()


def split_sentences(text: str) -> list[str]:
    """Sentences of *text*; a trailing unfinished sentence is kept as the last item."""
    text = _WHITESPACE.sub(" ", text).strip()
    sentences: list[str] = []
    start = 0
    for m in _SENTENCE_END_ANYWHERE.finditer(text):
        sentences.append(text[start : m.end()].strip())
        start = m.end()
    if text[start:].strip():
        sentences.append(text[start:].strip())
    return sentences


@dataclass
class CaptionBlock:
    """Final English caption text and, once translated, its Korean."""

    id: int
    english: str
    korean: str | None = None


def text_width_em(text: str) -> float:
    """Estimated width of *text* in em, counting East Asian wide characters as wide."""
    return sum(
        _WIDE_CHAR_WIDTH_EM if unicodedata.east_asian_width(c) in ("W", "F") else _CHAR_WIDTH_EM
        for c in text
    )


def _wrapped_lines(text: str, width: int, font_px: int) -> int:
    return max(1, math.ceil(text_width_em(text) * font_px / max(1, width)))


def block_lines(block: CaptionBlock, width: int, font_px: int) -> int:
    """Lines a block takes on the overlay: its English, then its Korean on new lines."""
    lines = _wrapped_lines(block.english, width, font_px)
    if block.korean:
        lines += _wrapped_lines(block.korean, width, font_px)
    return lines


def trim_blocks(
    blocks: list[CaptionBlock], width: int, height: int, font_px: int
) -> tuple[list[CaptionBlock], list[int]]:
    """Keep the newest blocks needed to fill the overlay; return (kept, dropped ids)."""
    budget = height / (_LINE_HEIGHT_EM * font_px) * _HISTORY_MARGIN
    total = 0
    for i in range(len(blocks) - 1, -1, -1):
        total += block_lines(blocks[i], width, font_px)
        if total >= budget:
            return blocks[i:], [b.id for b in blocks[:i]]
    return blocks, []


# Warm amber: easy to tell from the white English on the dark overlay
KOREAN_COLOR = "#ffd27a"


def format_bilingual(
    blocks: list[CaptionBlock], open_english: str, escape: Callable[[str], str]
) -> str:
    """Pango markup: each block's English with its Korean below, then the open English."""
    lines: list[str] = []
    for block in blocks:
        lines.append(escape(format_captions([block.english])))
        korean = format_captions([block.korean or ""])
        if korean:
            lines.append(f'<span foreground="{KOREAN_COLOR}">{escape(korean)}</span>')
    open_text = format_captions([open_english])
    if open_text:
        lines.append(escape(open_text))
    return "\n".join(lines)


# An unfinished sentence is translated as it is after this much quiet...
FLUSH_QUIET_SECONDS = 2.0
# ...or once it has waited this long, even while the speaker keeps talking
FLUSH_MAX_SECONDS = 8.0


class BilingualCaptions:
    """Final English grouped into sentence blocks for translation, plus the open English.

    Runs on one thread (the GTK main loop); *submit* hands a block to the translator.
    """

    def __init__(
        self,
        submit: Callable[[int, str], None],
        discard: Callable[[list[int]], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._submit = submit
        self._discard = discard
        self._clock = clock
        self.blocks: list[CaptionBlock] = []
        # Final English whose sentence is not finished yet, and the partial text
        self.pending = ""
        self.partial = ""
        self._next_id = 0
        self._last_final_at = 0.0
        self._pending_since = 0.0

    def stop_translating(self) -> None:
        """Keep building blocks, but send no more of them for translation."""
        self._submit = lambda _id, _text: None
        self._discard = None

    def add_final(self, text: str) -> None:
        self.partial = ""
        text = _WHITESPACE.sub(" ", text).strip()
        if not text:
            return
        now = self._clock()
        self._last_final_at = now
        if not self.pending:
            self._pending_since = now
        complete, rest = split_complete(f"{self.pending} {text}")
        if complete:
            self._close(complete)
            self._pending_since = now
        self.pending = rest

    def set_partial(self, text: str) -> None:
        self.partial = text

    def flush_due(self) -> bool:
        """Close the unfinished sentence when it has waited long enough; True if it did."""
        if not self.pending:
            return False
        now = self._clock()
        quiet = not self.partial.strip() and now - self._last_final_at >= FLUSH_QUIET_SECONDS
        if quiet or now - self._pending_since >= FLUSH_MAX_SECONDS:
            self._close(self.pending)
            self.pending = ""
            return True
        return False

    def set_translation(self, block_id: int, korean: str) -> bool:
        for block in reversed(self.blocks):
            if block.id == block_id:
                block.korean = korean
                return True
        return False  # already scrolled out of the history

    def trim(self, width: int, height: int, font_px: int) -> None:
        self.blocks, dropped = trim_blocks(self.blocks, width, height, font_px)
        if dropped and self._discard:
            self._discard(dropped)

    def markup(self, escape: Callable[[str], str]) -> str:
        return format_bilingual(self.blocks, f"{self.pending} {self.partial}", escape)

    def _close(self, english: str) -> None:
        block = CaptionBlock(self._next_id, english)
        self._next_id += 1
        self.blocks.append(block)
        self._submit(block.id, english)
