"""Local English speech-to-text via faster-whisper."""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from caption_english.audio import SAMPLE_RATE

logger = logging.getLogger(__name__)

TextCallback = Callable[[str, bool], None]  # text, is_final
ErrorCallback = Callable[[str], None]
StatusCallback = Callable[[str], None]

# Re-decode the current phrase after this much new audio (partial results)
STEP_SECONDS = 1.0
# A phrase is final once this much silence follows its last word...
END_SILENCE_SECONDS = 0.5
# ...or once it grows this long (bounds latency and CPU per decode)
MAX_PHRASE_SECONDS = 12.0
# Audio kept while idle so the first word of the next phrase is not clipped
PREROLL_SECONDS = 0.3
# RMS below this is treated as silence and never sent to the model
SILENCE_RMS = 0.008
# Whisper's own hallucination guard for non-speech segments
NO_SPEECH_PROB = 0.6
LOW_AVG_LOGPROB = -1.0

_models: dict[str, Any] = {}
_models_lock = threading.Lock()


@dataclass
class SttResult:
    text: str
    is_final: bool


@dataclass
class _Segment:
    start: float
    end: float
    text: str


class SpeechEngineError(Exception):
    """Raised when the speech engine cannot load or run."""


def is_model_downloaded(model_size: str) -> bool:
    try:
        from faster_whisper.utils import download_model

        download_model(model_size, local_files_only=True)
        return True
    except Exception:  # noqa: BLE001
        return False


def preload_model(model_size: str) -> None:
    """Load a model that is already on disk into the shared cache (no download)."""
    if model_size in _models or not is_model_downloaded(model_size):
        return
    try:
        SpeechToText(on_text=lambda _t, _f: None, model_size=model_size).load_model()
    except SpeechEngineError:
        pass  # reported again, to the user, when captioning starts


def is_silence(samples: np.ndarray, threshold: float = SILENCE_RMS) -> bool:
    """Return True when the buffer is below the silence RMS threshold."""
    if samples.size == 0:
        return True
    rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float32)))) + 1e-12)
    return rms < threshold


class SpeechToText:
    """Worker-thread phrase transcription with partial and final results."""

    def __init__(
        self,
        on_text: TextCallback,
        on_error: ErrorCallback | None = None,
        on_status: StatusCallback | None = None,
        model_size: str = "base.en",
    ) -> None:
        self._on_text = on_text
        self._on_error = on_error
        self._on_status = on_status
        self._model_size = model_size
        self._model = None
        self._queue: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=300)
        self._buffer = np.zeros(0, dtype=np.float32)
        self._thread: threading.Thread | None = None
        self._running = False
        # Audio fed before start() is queued so speech during model load is kept
        self._stopped = False
        self._lock = threading.Lock()
        self._last_partial = ""

    @property
    def running(self) -> bool:
        return self._running

    @property
    def model_loaded(self) -> bool:
        return self._model is not None

    def load_model(self) -> None:
        """Load (and download on first run) the Whisper model. Call before start()."""
        if self._model_size not in _models:
            # Report before taking the lock: a background preload may hold it
            if is_model_downloaded(self._model_size):
                self._status(f"Loading speech model ({self._model_size})…")
            else:
                self._status(f"Downloading speech model ({self._model_size}, first run only)…")
        with _models_lock:
            model = _models.get(self._model_size)
            if model is None:
                try:
                    from faster_whisper import WhisperModel

                    # CPU int8 is a good default for Ubuntu laptops
                    model = WhisperModel(self._model_size, device="cpu", compute_type="int8")
                except Exception as exc:  # noqa: BLE001
                    msg = f"Failed to load speech model '{self._model_size}': {exc}"
                    logger.exception(msg)
                    raise SpeechEngineError(msg) from exc
                _models[self._model_size] = model
                logger.info("Loaded Whisper model %s", self._model_size)
        self._model = model
        self._status("Speech model ready")

    def start(self) -> None:
        if self._model is None:
            raise SpeechEngineError(
                "Speech model is not loaded. Load it before starting captioning."
            )
        with self._lock:
            if self._running:
                return
            self._running = True
            self._buffer = np.zeros(0, dtype=np.float32)
            self._last_partial = ""
            self._thread = threading.Thread(target=self._worker, name="stt-worker", daemon=True)
            self._thread.start()
            logger.info("STT worker started")

    def stop(self) -> None:
        with self._lock:
            self._running = False
            self._stopped = True
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=5.0)
        self._thread = None
        # Drain queue
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._buffer = np.zeros(0, dtype=np.float32)
        logger.info("STT worker stopped")

    def feed_audio(self, samples: np.ndarray) -> None:
        if self._stopped:
            return
        block = np.asarray(samples, dtype=np.float32)
        try:
            self._queue.put_nowait(block)
        except queue.Full:
            # Fell far behind (e.g. a long first-run download): keep the newest audio
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(block)
            except queue.Full:
                pass

    def _worker(self) -> None:
        step = int(SAMPLE_RATE * STEP_SECONDS)
        new_samples = 0
        while self._running:
            try:
                item = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            # Take everything queued so a slow decode never falls further behind
            items = [item]
            while True:
                try:
                    items.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            if any(i is None for i in items):
                break
            self._buffer = np.concatenate([self._buffer, *items])
            new_samples += sum(i.size for i in items)
            if new_samples >= step:
                new_samples = 0
                self._process_buffer()

    def _process_buffer(self) -> None:
        """Decode the current phrase and emit a partial or final result."""
        assert self._model is not None
        preroll = int(SAMPLE_RATE * PREROLL_SECONDS)
        if is_silence(self._buffer):
            logger.debug("Skipping silent audio")
            self._end_phrase_without_speech(preroll)
            return
        try:
            speech = self._speech_regions(self._buffer)
            segments = self._transcribe(self._buffer) if speech else []
        except Exception as exc:  # noqa: BLE001
            msg = f"Speech recognition failed: {exc}"
            logger.exception(msg)
            self._emit_error(msg)
            return
        if not speech:
            self._end_phrase_without_speech(preroll)
            return

        duration = self._buffer.size / SAMPLE_RATE
        # Judge the phrase end from the VAD, not Whisper timestamps: Whisper
        # often leaves the last words of a buffer untranscribed until later.
        speech_end = speech[-1][1]
        if duration - speech_end >= END_SILENCE_SECONDS:
            commit, cut = segments, speech_end
        elif duration >= MAX_PHRASE_SECONDS:
            if len(segments) > 1 and duration < MAX_PHRASE_SECONDS * 1.5:
                # Forced cut while still talking: keep the unfinished segment
                commit, cut = segments[:-1], segments[-1].start
            else:
                commit, cut = segments, duration
        else:
            commit, cut = None, 0.0

        if commit is not None:
            # No pre-roll here: audio before the cut is already transcribed
            self._buffer = self._buffer[int(cut * SAMPLE_RATE) :]
            text = _join(commit)
            had_partial = bool(self._last_partial)
            self._last_partial = ""
            if text:
                self._on_text(text, True)
            elif had_partial:
                self._on_text("", False)  # e.g. a cough: retract the partial
            return

        text = _join(segments)
        if text != self._last_partial:
            self._last_partial = text
            self._on_text(text, False)

    def _end_phrase_without_speech(self, preroll: int) -> None:
        self._buffer = self._buffer[-preroll:]
        if self._last_partial:
            # A partial was shown but the audio turned out to be noise: retract it
            self._last_partial = ""
            self._on_text("", False)

    def _speech_regions(self, audio: np.ndarray) -> list[tuple[float, float]]:
        """Speech (start, end) times in seconds, from faster-whisper's Silero VAD."""
        from faster_whisper.vad import VadOptions, get_speech_timestamps

        options = VadOptions(min_silence_duration_ms=300, speech_pad_ms=100)
        return [
            (r["start"] / SAMPLE_RATE, r["end"] / SAMPLE_RATE)
            for r in get_speech_timestamps(audio, options)
        ]

    def _transcribe(self, audio: np.ndarray) -> list[_Segment]:
        segments, _info = self._model.transcribe(
            audio,
            language="en",
            vad_filter=True,
            beam_size=1,
            best_of=1,
            condition_on_previous_text=False,
        )
        result: list[_Segment] = []
        for seg in segments:
            text = (seg.text or "").strip()
            if not text:
                continue
            if seg.no_speech_prob > NO_SPEECH_PROB and seg.avg_logprob < LOW_AVG_LOGPROB:
                continue
            result.append(_Segment(float(seg.start), float(seg.end), text))
        return result

    def _emit_error(self, message: str) -> None:
        if self._on_error:
            try:
                self._on_error(message)
            except Exception:  # noqa: BLE001
                logger.exception("STT error callback failed")

    def _status(self, message: str) -> None:
        logger.info(message)
        if self._on_status:
            try:
                self._on_status(message)
            except Exception:  # noqa: BLE001
                logger.exception("STT status callback failed")


def _join(segments: list[_Segment]) -> str:
    return " ".join(s.text for s in segments).strip()
