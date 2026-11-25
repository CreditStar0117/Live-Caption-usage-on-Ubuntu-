"""Local English→Korean translation of final captions (NLLB-200 via CTranslate2)."""

from __future__ import annotations

import logging
import os
import queue
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from caption_english.captions import split_sentences

logger = logging.getLogger(__name__)

ResultCallback = Callable[[int, str], None]  # block id, Korean text
ErrorCallback = Callable[[str], None]
StatusCallback = Callable[[str], None]

# NLLB-200 distilled 600M, already converted to CTranslate2 int8 (CC-BY-NC 4.0).
# Pinned to one commit so a change upstream cannot swap the model under users.
REPO_ID = "JustFrederik/nllb-200-distilled-600M-ct2-int8"
REVISION = "302d78f00e6fdb50a1064059df7c392b735e9d05"
MODEL_FILES = ["model.bin", "config.json", "shared_vocabulary.txt", "tokenizer.json"]
DOWNLOAD_MB = 620
# A local CTranslate2 NLLB model directory; skips the download
MODEL_ENV = "CAPTION_ENGLISH_TRANSLATION_MODEL"

SOURCE_LANG = "eng_Latn"
TARGET_LANG = "kor_Hang"
EOS = "</s>"

# Whisper uses 4 threads; 2 more keeps both within an 8-core CPU
INTRA_THREADS = 2
BEAM_SIZE = 2
# Blocks translated together when several finished during one translation
MAX_BATCH = 16
MAX_INPUT_TOKENS = 256

_models: dict[str, tuple[Any, Any]] = {}
_models_lock = threading.Lock()


class TranslationError(Exception):
    """Raised when the translation model cannot be downloaded, loaded or run."""


def source_tokens(tokenizer: Any, text: str, src_lang: str = SOURCE_LANG) -> list[str]:
    """NLLB source sequence for *text*: language code, pieces, end of sentence."""
    pieces = tokenizer.encode(text, add_special_tokens=False).tokens
    return [src_lang, *pieces[: MAX_INPUT_TOKENS - 2], EOS]


def decode_hypothesis(tokenizer: Any, tokens: list[str], target_lang: str = TARGET_LANG) -> str:
    """Text of a translated token sequence, without the language prefix or special tokens."""
    if tokens and tokens[0] == target_lang:
        tokens = tokens[1:]
    ids = [tokenizer.token_to_id(t) for t in tokens]
    return tokenizer.decode([i for i in ids if i is not None], skip_special_tokens=True).strip()


_SENTENCE_ENDS = ".?!…"


def _keep_sentence_end(english: str, korean: str) -> str:
    """Give the Korean the English sentence's end mark when the model dropped it.

    The overlay puts its wide sentence gap only after sentence-ending punctuation.
    """
    end = english.rstrip("\"'”’)] ")[-1:]
    if korean and end and end in _SENTENCE_ENDS and korean.rstrip("\"'”’)] ")[-1:] not in _SENTENCE_ENDS:
        return korean + end
    return korean


def _override_dir() -> Path | None:
    value = os.environ.get(MODEL_ENV)
    return Path(value).expanduser() if value else None


def _has_model_files(path: Path) -> bool:
    return (path / "model.bin").is_file() and (path / "tokenizer.json").is_file()


def model_dir(download: bool = False) -> Path:
    """Directory holding the translation model; downloads it first when *download* is set."""
    override = _override_dir()
    if override is not None:
        return override
    import huggingface_hub

    # One file at a time on the calling (daemon) thread: snapshot_download uses a
    # thread pool that Python joins at exit, so quitting mid-download would hang
    paths = [
        Path(
            huggingface_hub.hf_hub_download(
                REPO_ID, name, revision=REVISION, local_files_only=not download
            )
        )
        for name in MODEL_FILES
    ]
    path = paths[0].parent
    if not _has_model_files(path):
        raise FileNotFoundError(f"Translation model files are missing in {path}")
    return path


def is_translation_model_downloaded() -> bool:
    try:
        return _has_model_files(model_dir(download=False))
    except Exception:  # noqa: BLE001
        return False


def _model_key() -> str:
    override = _override_dir()
    return str(override) if override is not None else f"{REPO_ID}@{REVISION}"


def load_model(on_status: StatusCallback | None = None) -> tuple[Any, Any]:
    """Load (and on first use download) the model; returns (translator, tokenizer)."""

    def status(message: str) -> None:
        logger.info(message)
        if on_status:
            on_status(message)

    key = _model_key()
    if key not in _models:
        # Report before taking the lock: a background preload may hold it
        downloaded = is_translation_model_downloaded()
        if downloaded:
            status("Loading translation model…")
        else:
            status(f"Downloading translation model (~{DOWNLOAD_MB} MB, first use only)…")
    with _models_lock:
        model = _models.get(key)
        if model is None:
            try:
                path = model_dir(download=not is_translation_model_downloaded())
                import ctranslate2
                from tokenizers import Tokenizer

                translator = ctranslate2.Translator(
                    str(path),
                    device="cpu",
                    compute_type="int8",
                    inter_threads=1,
                    intra_threads=INTRA_THREADS,
                )
                tokenizer = Tokenizer.from_file(str(path / "tokenizer.json"))
            except Exception as exc:  # noqa: BLE001
                msg = f"Failed to load translation model: {exc}"
                logger.exception(msg)
                raise TranslationError(msg) from exc
            model = (translator, tokenizer)
            _models[key] = model
            logger.info("Loaded translation model from %s", path)
    status("Korean translation ready")
    return model


def preload_model() -> None:
    """Load a translation model that is already on disk into the cache (no download)."""
    if _model_key() in _models or not is_translation_model_downloaded():
        return
    try:
        load_model()
    except TranslationError:
        pass  # reported again, to the user, when captioning starts


class Translator:
    """Worker thread that translates caption blocks, a batch at a time, in order."""

    def __init__(
        self,
        on_result: ResultCallback,
        on_error: ErrorCallback | None = None,
        on_status: StatusCallback | None = None,
    ) -> None:
        self._on_result = on_result
        self._on_error = on_error
        self._on_status = on_status
        self._model: tuple[Any, Any] | None = None
        # Blocks submitted before the model is ready wait here
        self._queue: queue.Queue[tuple[int, str] | None] = queue.Queue()
        self._discarded: set[int] = set()
        # Highest block id taken off the queue; discarding those does nothing
        self._taken_upto = -1
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._running = False
        self._stopped = False

    @property
    def running(self) -> bool:
        return self._running

    def load_model(self) -> None:
        """Load (and download on first use) the model. Call before start()."""
        self._model = load_model(self._status)

    def start(self) -> None:
        if self._model is None:
            raise TranslationError("Translation model is not loaded.")
        with self._lock:
            if self._running or self._stopped:
                return
            self._running = True
            self._thread = threading.Thread(
                target=self._worker, name="translate-worker", daemon=True
            )
            self._thread.start()

    def submit(self, block_id: int, text: str) -> None:
        if not self._stopped and text.strip():
            self._queue.put((block_id, text))

    def discard(self, block_ids: list[int]) -> None:
        """Skip these blocks if they are still waiting (they left the caption history)."""
        with self._lock:
            self._discarded.update(i for i in block_ids if i > self._taken_upto)

    def stop(self) -> None:
        with self._lock:
            self._running = False
            self._stopped = True
        self._queue.put(None)
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=5.0)
        self._thread = None
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def _worker(self) -> None:
        while self._running:
            try:
                item = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            items = [item]
            while True:
                try:
                    items.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            if any(i is None for i in items):
                break
            with self._lock:
                wanted = [i for i in items if i is not None and i[0] not in self._discarded]
                taken = [i[0] for i in items if i is not None]
                self._discarded.difference_update(taken)
                self._taken_upto = max(self._taken_upto, *taken)
            for start in range(0, len(wanted), MAX_BATCH):
                batch = wanted[start : start + MAX_BATCH]
                try:
                    korean = self._translate([text for _id, text in batch])
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Translation failed")
                    self._running = False
                    self._emit_error(f"Korean translation failed: {exc}")
                    return
                if not self._running:
                    return  # stopped while translating: drop the result
                for (block_id, _text), text in zip(batch, korean):
                    self._on_result(block_id, text)

    def _translate(self, texts: list[str]) -> list[str]:
        assert self._model is not None
        # NLLB tends to drop a sentence when given several at once: translate each
        # sentence on its own (all in one batch) and join them back per block
        groups = [split_sentences(t) or [t] for t in texts]
        sentences = [sentence for group in groups for sentence in group]
        korean = iter(self._translate_sentences(sentences))
        return [
            " ".join(_keep_sentence_end(en, next(korean)) for en in group).strip()
            for group in groups
        ]

    def _translate_sentences(self, texts: list[str]) -> list[str]:
        assert self._model is not None
        translator, tokenizer = self._model
        sources = [source_tokens(tokenizer, t) for t in texts]
        longest = max(len(s) for s in sources)
        results = translator.translate_batch(
            sources,
            target_prefix=[[TARGET_LANG]] * len(sources),
            beam_size=BEAM_SIZE,
            max_input_length=MAX_INPUT_TOKENS,
            # Bounds runaway repetition on odd inputs; Korean needs about as many tokens
            max_decoding_length=2 * longest + 16,
        )
        return [decode_hypothesis(tokenizer, r.hypotheses[0]) for r in results]

    def _emit_error(self, message: str) -> None:
        if self._on_error:
            try:
                self._on_error(message)
            except Exception:  # noqa: BLE001
                logger.exception("Translation error callback failed")

    def _status(self, message: str) -> None:
        if self._on_status:
            try:
                self._on_status(message)
            except Exception:  # noqa: BLE001
                logger.exception("Translation status callback failed")
