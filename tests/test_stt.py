"""Speech-to-text silence, streaming, and error handling tests."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np

from caption_english import stt as stt_mod
from caption_english.audio import SAMPLE_RATE
from caption_english.stt import SILENCE_RMS, SpeechEngineError, SpeechToText, is_silence


def _seg(start: float, end: float, text: str) -> SimpleNamespace:
    return SimpleNamespace(start=start, end=end, text=text, no_speech_prob=0.0, avg_logprob=-0.2)


def _engine(
    segments_per_call: list[list[SimpleNamespace]],
    speech_per_call: list[list[tuple[float, float]]] | None = None,
) -> tuple[SpeechToText, list]:
    """Engine with a mocked Whisper model and VAD (speech regions in seconds)."""
    emitted: list[tuple[str, bool]] = []
    stt = SpeechToText(on_text=lambda t, f: emitted.append((t, f)))
    stt._model = mock.MagicMock()  # noqa: SLF001
    stt._model.transcribe.side_effect = [(iter(s), None) for s in segments_per_call]  # noqa: SLF001
    if speech_per_call is None:
        speech_per_call = [[(s[0].start, s[-1].end)] if s else [] for s in segments_per_call]
    stt._speech_regions = mock.MagicMock(side_effect=speech_per_call)  # noqa: SLF001
    return stt, emitted


def _speech(seconds: float) -> np.ndarray:
    return np.full(int(SAMPLE_RATE * seconds), 0.2, dtype=np.float32)


class SilenceTests(unittest.TestCase):
    def test_zero_buffer_is_silence(self) -> None:
        self.assertTrue(is_silence(np.zeros(1600, dtype=np.float32)))

    def test_loud_buffer_is_not_silence(self) -> None:
        loud = np.ones(1600, dtype=np.float32) * 0.2
        self.assertFalse(is_silence(loud))

    def test_near_threshold(self) -> None:
        quiet = np.ones(1600, dtype=np.float32) * (SILENCE_RMS * 0.5)
        self.assertTrue(is_silence(quiet))


class StreamingTests(unittest.TestCase):
    def test_silent_buffer_does_not_emit_text(self) -> None:
        stt, emitted = _engine([])
        stt._buffer = np.zeros(SAMPLE_RATE * 2, dtype=np.float32)  # noqa: SLF001
        stt._process_buffer()  # noqa: SLF001
        stt._model.transcribe.assert_not_called()  # noqa: SLF001
        stt._speech_regions.assert_not_called()  # noqa: SLF001
        self.assertEqual(emitted, [])
        # Only the pre-roll is kept while idle
        self.assertLessEqual(stt._buffer.size, int(SAMPLE_RATE * stt_mod.PREROLL_SECONDS))  # noqa: SLF001

    def test_noise_without_speech_does_not_emit_text(self) -> None:
        stt, emitted = _engine([], speech_per_call=[[]])
        stt._buffer = _speech(1.5)  # noqa: SLF001
        stt._process_buffer()  # noqa: SLF001
        stt._model.transcribe.assert_not_called()  # noqa: SLF001
        self.assertEqual(emitted, [])

    def test_partial_then_final(self) -> None:
        stt, emitted = _engine(
            [
                [_seg(0.1, 0.9, "Ask not")],
                [_seg(0.1, 1.2, "Ask not what your country")],
            ],
            speech_per_call=[[(0.1, 1.0)], [(0.1, 1.3)]],
        )
        stt._buffer = _speech(1.0)  # noqa: SLF001
        stt._process_buffer()  # noqa: SLF001
        self.assertEqual(emitted, [("Ask not", False)])

        stt._buffer = _speech(2.0)  # noqa: SLF001
        stt._process_buffer()  # noqa: SLF001  (0.7 s of trailing silence)
        self.assertEqual(emitted[-1], ("Ask not what your country", True))
        # Audio up to the end of the phrase is dropped
        kept = stt._buffer.size / SAMPLE_RATE  # noqa: SLF001
        self.assertAlmostEqual(kept, 2.0 - 1.3, places=2)

    def test_no_final_while_vad_still_hears_speech(self) -> None:
        # Whisper has not transcribed the last word yet, but the VAD hears it:
        # finalizing now would drop that word.
        stt, emitted = _engine(
            [[_seg(0.2, 2.3, "And so my fellow Americans")]],
            speech_per_call=[[(0.2, 2.3), (3.2, 4.0)]],
        )
        stt._buffer = _speech(4.0)  # noqa: SLF001
        stt._process_buffer()  # noqa: SLF001
        self.assertEqual(emitted, [("And so my fellow Americans", False)])
        self.assertEqual(stt._buffer.size, SAMPLE_RATE * 4)  # noqa: SLF001

    def test_long_phrase_keeps_unfinished_segment(self) -> None:
        stt, emitted = _engine(
            [[_seg(0.0, 6.0, "First sentence."), _seg(6.2, 12.0, "Second still going")]]
        )
        stt._buffer = _speech(stt_mod.MAX_PHRASE_SECONDS)  # noqa: SLF001
        stt._process_buffer()  # noqa: SLF001
        self.assertEqual(emitted, [("First sentence.", True)])
        kept = stt._buffer.size / SAMPLE_RATE  # noqa: SLF001
        self.assertAlmostEqual(kept, 12.0 - 6.2, places=2)

    def test_hallucinated_non_speech_segment_dropped(self) -> None:
        bogus = SimpleNamespace(
            start=0.0, end=1.0, text="Thank you.", no_speech_prob=0.9, avg_logprob=-1.5
        )
        stt, emitted = _engine([[bogus]])
        stt._buffer = _speech(1.0)  # noqa: SLF001
        stt._process_buffer()  # noqa: SLF001
        self.assertEqual(emitted, [])


class EngineTests(unittest.TestCase):
    def test_start_without_model_errors(self) -> None:
        stt = SpeechToText(on_text=lambda t, f: None)
        with self.assertRaises(SpeechEngineError):
            stt.start()

    def test_load_model_failure_raises(self) -> None:
        stt = SpeechToText(on_text=lambda t, f: None, model_size="no-such-model")
        with mock.patch(
            "faster_whisper.WhisperModel",
            side_effect=RuntimeError("missing"),
        ):
            with self.assertRaises(SpeechEngineError):
                stt.load_model()
        self.assertFalse(stt.model_loaded)

    def test_audio_fed_before_start_is_kept_until_stop(self) -> None:
        stt = SpeechToText(on_text=lambda t, f: None)
        stt.feed_audio(np.ones(1600, dtype=np.float32))  # model still loading
        self.assertEqual(stt._queue.qsize(), 1)  # noqa: SLF001
        stt.stop()
        stt.feed_audio(np.ones(1600, dtype=np.float32))
        self.assertEqual(stt._queue.qsize(), 0)  # noqa: SLF001

    def test_recognition_failure_reports_error(self) -> None:
        errors: list[str] = []
        stt = SpeechToText(on_text=lambda t, f: None, on_error=errors.append)
        stt._model = mock.MagicMock()  # noqa: SLF001
        stt._model.transcribe.side_effect = RuntimeError("boom")  # noqa: SLF001
        stt._speech_regions = lambda _audio: [(0.0, 1.0)]  # noqa: SLF001
        stt._buffer = _speech(1.0)  # noqa: SLF001
        stt._process_buffer()  # noqa: SLF001
        self.assertEqual(len(errors), 1)
        self.assertIn("boom", errors[0])


if __name__ == "__main__":
    unittest.main()
