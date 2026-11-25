#!/usr/bin/env python3
"""Measure live caption latency on a recording.

Plays an English recording into the speech engine at real-time pace (100 ms
blocks, like the audio capture does) and reports how long after each word is
spoken it first shows up in the captions, and when it becomes final text.
Word times come from an offline transcription of the same audio.

    .venv/bin/python scripts/bench_latency.py talk.mp3 [--model tiny.en] [--translate]

With --translate, final text also goes through the Korean translation path the
app uses (sentence blocks, then the translator), and the delay from a block's
English being complete to its Korean arriving is reported too.
"""

from __future__ import annotations

import argparse
import difflib
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from caption_english.audio import BLOCK_FRAMES, SAMPLE_RATE  # noqa: E402
from caption_english import translate  # noqa: E402
from caption_english.captions import BilingualCaptions  # noqa: E402
from caption_english.stt import SpeechToText  # noqa: E402


# Long enough for the 2 s quiet flush plus one translation
FLUSH_WAIT = 4.0


def load_audio(path: str, start: float, seconds: float) -> np.ndarray:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        sys.exit("ffmpeg is required: sudo apt install ffmpeg")
    raw = subprocess.run(
        [ffmpeg, "-loglevel", "error", "-ss", str(start), "-t", str(seconds), "-i", path,
         "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "-"],
        check=True,
        capture_output=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def first_seen(ref: list[str], events: list[tuple[float, str]]) -> list[float | None]:
    """Time each reference word first appears in the caption text."""
    seen: list[float | None] = [None] * len(ref)
    for t, text in events:
        matcher = difflib.SequenceMatcher(None, ref, words(text), autojunk=False)
        for a, _b, size in matcher.get_matching_blocks():
            if size < 2:
                continue  # single-word matches are too often spurious
            for k in range(a, a + size):
                if seen[k] is None:
                    seen[k] = t
    return seen


def summarize(ends: list[float], seen: list[float | None], audio_s: float) -> str:
    # Words in the last second may not be final before the run ends
    eligible = [(e, s) for e, s in zip(ends, seen) if e < audio_s - 1.0]
    lat = sorted(s - e for e, s in eligible if s is not None and s >= e - 0.3)
    if not lat:
        return "no words matched"
    p90 = lat[min(len(lat) - 1, int(len(lat) * 0.9))]
    return f"median {statistics.median(lat):.2f} s, p90 {p90:.2f} s ({len(lat)}/{len(eligible)} words)"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("audio", help="English speech recording (any format ffmpeg reads)")
    parser.add_argument("--model", default="base.en")
    parser.add_argument("--start", type=float, default=0.0, help="offset into the file (s)")
    parser.add_argument("--seconds", type=float, default=90.0, help="length to play (s)")
    parser.add_argument("--translate", action="store_true", help="also translate into Korean")
    parser.add_argument("--beam", type=int, default=translate.BEAM_SIZE, help="translation beam size")
    args = parser.parse_args()

    audio = load_audio(args.audio, args.start, args.seconds)
    audio_s = audio.size / SAMPLE_RATE
    print(f"Audio: {audio_s:.1f} s, model {args.model}")

    finals: list[str] = []
    partial = ""
    any_events: list[tuple[float, str]] = []
    final_events: list[tuple[float, str]] = []
    decodes: list[float] = []
    t0 = 0.0

    # Korean path: same block grouping as the app, guarded by one lock because
    # here the STT, translator and flush threads all touch it
    caps_lock = threading.Lock()
    block_done: dict[int, float] = {}
    korean_at: dict[int, float] = {}
    batch_times: list[tuple[int, float]] = []
    translator: translate.Translator | None = None
    caps: BilingualCaptions | None = None

    def on_text(text: str, is_final: bool) -> None:
        nonlocal partial
        t = time.monotonic() - t0
        if is_final:
            finals.append(text)
            partial = ""
            final_events.append((t, " ".join(finals)))
        else:
            partial = text
        any_events.append((t, " ".join([*finals, partial])))
        if caps is not None:
            with caps_lock:
                if is_final:
                    caps.add_final(text)
                else:
                    caps.set_partial(text)

    engine = SpeechToText(on_text=on_text, on_error=print, model_size=args.model)
    engine.load_model()
    model = engine._model  # noqa: SLF001

    print("Transcribing offline for reference word times…")
    segments, _info = model.transcribe(audio, language="en", word_timestamps=True, vad_filter=True)
    ref = [(tok, w.end) for seg in segments for w in seg.words for tok in words(w.word)]
    ref_words = [tok for tok, _end in ref]
    ref_ends = [end for _tok, end in ref]

    class TimedModel:
        def __getattr__(self, name: str):  # noqa: ANN204
            return getattr(model, name)

        def transcribe(self, samples, **kwargs):  # noqa: ANN001, ANN201
            start = time.monotonic()
            segs, info = model.transcribe(samples, **kwargs)
            segs = list(segs)
            decodes.append(time.monotonic() - start)
            return segs, info

    engine._model = TimedModel()  # noqa: SLF001

    stop_flush = threading.Event()
    if args.translate:
        translate.BEAM_SIZE = args.beam

        def on_korean(block_id: int, korean: str) -> None:
            korean_at[block_id] = time.monotonic() - t0
            with caps_lock:
                caps.set_translation(block_id, korean)  # type: ignore[union-attr]

        translator = translate.Translator(on_result=on_korean, on_error=print, on_status=print)
        translator.load_model()
        inner = translator._translate  # noqa: SLF001

        def timed_translate(texts: list[str]) -> list[str]:
            start = time.monotonic()
            out = inner(texts)
            batch_times.append((len(texts), time.monotonic() - start))
            return out

        translator._translate = timed_translate  # type: ignore[method-assign]  # noqa: SLF001

        def submit(block_id: int, english: str) -> None:
            block_done[block_id] = time.monotonic() - t0
            translator.submit(block_id, english)  # type: ignore[union-attr]

        caps = BilingualCaptions(submit=submit)

        def flush_loop() -> None:
            while not stop_flush.wait(0.25):
                with caps_lock:
                    caps.flush_due()  # type: ignore[union-attr]

        threading.Thread(target=flush_loop, daemon=True).start()
        print(f"Korean translation on (beam {args.beam})")

    print(f"Playing {audio_s:.0f} s in real time…")
    engine.start()
    if translator:
        translator.start()
    t0 = time.monotonic()
    noise = np.random.default_rng(0).normal(0, 0.001, SAMPLE_RATE * 3).astype(np.float32)
    stream = np.concatenate([audio, noise])  # trailing quiet lets the last phrase end
    for i in range(stream.size // BLOCK_FRAMES):
        delay = t0 + (i + 1) * BLOCK_FRAMES / SAMPLE_RATE - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        engine.feed_audio(stream[i * BLOCK_FRAMES : (i + 1) * BLOCK_FRAMES])
    time.sleep(1.5)
    engine.stop()
    if translator:
        time.sleep(FLUSH_WAIT)  # let the last unfinished sentence flush and translate
        stop_flush.set()
        translator.stop()
    wall = time.monotonic() - t0

    print()
    print("First appearance: ", summarize(ref_ends, first_seen(ref_words, any_events), audio_s))
    print("Final text:       ", summarize(ref_ends, first_seen(ref_words, final_events), audio_s))
    if decodes:
        print(
            f"Decodes:           {len(decodes)}, median {1000 * statistics.median(decodes):.0f} ms, "
            f"max {1000 * max(decodes):.0f} ms, busy {100 * sum(decodes) / wall:.0f}% of the time"
        )
    if args.translate:
        delays = sorted(korean_at[i] - block_done[i] for i in block_done if i in korean_at)
        missing = len(block_done) - len(delays)
        if delays:
            p90 = delays[min(len(delays) - 1, int(len(delays) * 0.9))]
            print(
                f"Korean delay:      median {statistics.median(delays):.2f} s, p90 {p90:.2f} s "
                f"({len(delays)} blocks, {missing} untranslated)"
            )
        if batch_times:
            per_block = [t / n for n, t in batch_times]
            print(
                f"Translations:      {len(batch_times)} batches, median {1000 * statistics.median(per_block):.0f} ms "
                f"per block, max batch {1000 * max(t for _n, t in batch_times):.0f} ms, "
                f"busy {100 * sum(t for _n, t in batch_times) / wall:.0f}% of the time"
            )
        print()
        for block in caps.blocks[-6:]:  # type: ignore[union-attr]
            print(f"  EN: {block.english}\n  KO: {block.korean}")


if __name__ == "__main__":
    main()
