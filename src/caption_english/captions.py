"""Caption text: history kept for the overlay, and paragraph formatting."""

from __future__ import annotations

import re

# EM SPACE + EN SPACE: a 1.5 em gap that scales with the font size. Both are
# line-break class BA (no break before), so a wrapped line never starts with it.
SENTENCE_GAP = "  "

_WHITESPACE = re.compile(r"\s+")
# . ? ! or … (plus closing quotes/brackets) followed by whitespace ends a
# sentence; "3.5" or "example.com" have no whitespace after the period.
_SENTENCE_END = re.compile(r"([.?!…][\"'”’)\]]*) (?=\S)")

# Smallest average character width and line height (in em) measured across
# common UI fonts, so the estimate errs toward keeping more text, not less
_CHAR_WIDTH_EM = 0.33
_LINE_HEIGHT_EM = 1.14
# History beyond one full overlay: covers wrap waste at line ends and resizes
_HISTORY_MARGIN = 1.5


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
