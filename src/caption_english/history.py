"""English caption history for the app run, and saving it as a text file.

GTK-free: the app feeds it final English text on the GTK thread.
"""

from __future__ import annotations

import contextlib
import os
import re
import secrets
import stat
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from caption_english.captions import split_complete, split_sentences

_WHITESPACE = re.compile(r"\s+")

TRANSCRIPT_TITLE = "Caption English caption history"


@dataclass
class HistorySentence:
    """One English sentence and the local time its first words became final."""

    time: datetime
    text: str


@dataclass
class HistorySession:
    """One captioning session: when it started, its audio source and its sentences."""

    started: datetime
    source: str
    sentences: list[HistorySentence] = field(default_factory=list)


class CaptionHistory:
    """Final English captions grouped into timestamped sentences, per session.

    Runs on one thread (the GTK main loop), so it needs no lock.
    """

    def __init__(self, clock: Callable[[], datetime] = datetime.now) -> None:
        self._clock = clock
        self.sessions: list[HistorySession] = []
        self._open = False
        # Final English whose sentence is not finished yet
        self.pending = ""
        self._pending_since: datetime | None = None
        self._revision = 0
        self._saved_revision = 0

    @property
    def revision(self) -> int:
        """Bumped on every change to the recorded text; a save stores the one it wrote."""
        return self._revision

    @property
    def sentence_count(self) -> int:
        count = sum(len(s.sentences) for s in self.sessions)
        return count + (1 if self.pending else 0)

    @property
    def has_unsaved(self) -> bool:
        return self.sentence_count > 0 and self._revision != self._saved_revision

    def mark_saved(self, revision: int) -> None:
        self._saved_revision = revision

    def start_session(self, source: str) -> None:
        self.end_session()
        self.sessions.append(HistorySession(self._clock(), source))
        self._open = True

    def end_session(self) -> None:
        """Close the session; an unfinished sentence becomes a sentence of its own.

        The saved text already shows pending text as a sentence at the same time,
        so this is not a change: a save just before Stop stays a save.
        """
        if self.pending:
            assert self._pending_since is not None
            self.sessions[-1].sentences.append(
                HistorySentence(self._pending_since, self.pending)
            )
            self.pending = ""
            self._pending_since = None
        self._open = False

    def add_final(self, text: str) -> None:
        text = _WHITESPACE.sub(" ", text).strip()
        if not text:
            return
        if not self._open:
            self.start_session("unknown")
        now = self._clock()
        if not self.pending:
            self._pending_since = now
        complete, rest = split_complete(f"{self.pending} {text}")
        if complete:
            session = self.sessions[-1]
            for i, sentence in enumerate(split_sentences(complete)):
                # The first sentence began with the pending words, later ones in this phrase
                started = self._pending_since if i == 0 else now
                assert started is not None
                session.sentences.append(HistorySentence(started, sentence))
            if rest:
                self._pending_since = now
        self.pending = rest
        if not rest:
            self._pending_since = None
        self._revision += 1

    def clear(self) -> None:
        """Empty the history; an open session carries on as a fresh one from now."""
        source = self.sessions[-1].source if self._open and self.sessions else None
        self.sessions = []
        self.pending = ""
        self._pending_since = None
        self._open = False
        self._revision = 0
        self._saved_revision = 0
        if source is not None:
            self.start_session(source)

    def transcript(self, saved_at: datetime) -> str:
        """The saved file's text; an unfinished sentence is included but stays pending."""
        parts = [f"{TRANSCRIPT_TITLE}\nSaved {saved_at:%Y-%m-%d %H:%M:%S}\n"]
        for index, session in enumerate(self.sessions):
            sentences = list(session.sentences)
            is_last = index == len(self.sessions) - 1
            if is_last and self.pending and self._pending_since is not None:
                sentences.append(HistorySentence(self._pending_since, self.pending))
            if not sentences:
                continue
            lines = [
                f"--- Session started {session.started:%Y-%m-%d %H:%M:%S} "
                f"({session.source} audio) ---"
            ]
            lines += [f"[{s.time:%H:%M:%S}] {s.text}" for s in sentences]
            parts.append("\n".join(lines) + "\n")
        return "\n".join(parts)


def default_filename(now: datetime) -> str:
    """Suggested file name; the seconds keep two saves in a minute apart."""
    return f"caption-history-{now:%Y-%m-%d-%H%M%S}.txt"


def history_summary(count: int, saved_name: str | None) -> str:
    """Control-window line: how much is recorded and whether it is saved."""
    if count == 0:
        return "Nothing recorded yet"
    noun = "sentence" if count == 1 else "sentences"
    if saved_name:
        return f"{count} {noun}, saved to {saved_name}"
    return f"{count} {noun}, not saved"


def write_transcript(path: str | os.PathLike[str], text: str) -> None:
    """Write *text* as UTF-8 to *path*; a failed write never leaves a half-written file."""
    target = os.path.abspath(os.fspath(path))
    folder, name = os.path.split(target)
    tmp = os.path.join(folder, f".{name}.{secrets.token_hex(4)}.tmp")
    # 0o666 lets the user's umask set the permissions, as for any new file
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    try:
        try:
            data = memoryview(text.encode("utf-8"))
            while data:
                written = os.write(fd, data)
                data = data[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            mode = stat.S_IMODE(os.stat(target).st_mode)
        except FileNotFoundError:
            pass
        else:
            os.chmod(tmp, mode)
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
