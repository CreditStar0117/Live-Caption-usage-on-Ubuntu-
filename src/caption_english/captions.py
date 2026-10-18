"""Caption text formatting: one paragraph with a fixed gap between sentences."""

from __future__ import annotations

import re

# EM SPACE + EN SPACE: a 1.5 em gap that scales with the font size. Both are
# line-break class BA (no break before), so a wrapped line never starts with it.
SENTENCE_GAP = "  "

_WHITESPACE = re.compile(r"\s+")
# . ? ! or … (plus closing quotes/brackets) followed by whitespace ends a
# sentence; "3.5" or "example.com" have no whitespace after the period.
_SENTENCE_END = re.compile(r"([.?!…][\"'”’)\]]*) (?=\S)")


def format_captions(phrases: list[str]) -> str:
    """Join final phrases and the in-progress text for display."""
    text = _WHITESPACE.sub(" ", " ".join(phrases)).strip()
    return _SENTENCE_END.sub(lambda m: m.group(1) + SENTENCE_GAP, text)
