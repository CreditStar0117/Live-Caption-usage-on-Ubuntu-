"""Tests for the local translation engine, with a fake tokenizer and fake CTranslate2 model."""

from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from caption_english import translate
from caption_english.translate import (
    EOS,
    SOURCE_LANG,
    TARGET_LANG,
    TranslationError,
    Translator,
    _keep_sentence_end,
    decode_hypothesis,
    source_tokens,
)

SPECIAL = {"<s>", "</s>", "<pad>", SOURCE_LANG, TARGET_LANG}


class FakeTokenizer:
    """Whitespace tokenizer with "▁" word pieces and an on-demand vocabulary."""

    def __init__(self) -> None:
        self.vocab: dict[str, int] = {}
        self.tokens: list[str] = []
        for tok in sorted(SPECIAL):
            self.token_to_id(tok)

    def encode(self, text: str, add_special_tokens: bool = True) -> SimpleNamespace:
        assert not add_special_tokens, "the framing is built by hand"
        return SimpleNamespace(tokens=["▁" + w for w in text.split()])

    def token_to_id(self, token: str) -> int:
        if token not in self.vocab:
            self.vocab[token] = len(self.tokens)
            self.tokens.append(token)
        return self.vocab[token]

    def decode(self, ids: list[int], skip_special_tokens: bool = False) -> str:
        toks = [self.tokens[i] for i in ids]
        if skip_special_tokens:
            toks = [t for t in toks if t not in SPECIAL]
        return "".join(toks).replace("▁", " ")


class FakeModel:
    """Translates each word to "ko:<word>" and records every batch."""

    def __init__(self, fail: bool = False, delay: float = 0.0) -> None:
        self.batches: list[list[list[str]]] = []
        self.kwargs: list[dict] = []
        self.fail = fail
        self.delay = delay
        self.gate = threading.Event()
        self.gate.set()

    def translate_batch(self, sources, target_prefix, **kwargs):  # noqa: ANN001, ANN201
        self.gate.wait(5)
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise RuntimeError("boom")
        self.batches.append(sources)
        self.kwargs.append({"target_prefix": target_prefix, **kwargs})
        return [
            SimpleNamespace(
                hypotheses=[[TARGET_LANG, *("▁ko:" + t.lstrip("▁") for t in src[1:-1]), EOS]]
            )
            for src in sources
        ]


class FramingTests(unittest.TestCase):
    def test_source_framing(self) -> None:
        tok = FakeTokenizer()
        self.assertEqual(
            source_tokens(tok, "Hello there."), [SOURCE_LANG, "▁Hello", "▁there.", EOS]
        )

    def test_long_input_is_capped(self) -> None:
        tokens = source_tokens(FakeTokenizer(), "word " * 1000)
        self.assertEqual(len(tokens), translate.MAX_INPUT_TOKENS)
        self.assertEqual((tokens[0], tokens[-1]), (SOURCE_LANG, EOS))

    def test_decode_drops_prefix_and_special_tokens(self) -> None:
        tok = FakeTokenizer()
        self.assertEqual(
            decode_hypothesis(tok, [TARGET_LANG, "▁안녕", "하세요", "▁세계", EOS]),
            "안녕하세요 세계",
        )
        self.assertEqual(decode_hypothesis(tok, []), "")


class SentenceEndTests(unittest.TestCase):
    def test_missing_end_mark_is_copied(self) -> None:
        self.assertEqual(_keep_sentence_end("Good morning.", "안녕하세요"), "안녕하세요.")
        self.assertEqual(_keep_sentence_end("Are you there?", "거기 있어요"), "거기 있어요?")
        self.assertEqual(_keep_sentence_end('He said "stop."', "그는 멈추라고"), "그는 멈추라고.")

    def test_existing_or_no_end_mark_is_kept(self) -> None:
        self.assertEqual(_keep_sentence_end("Good morning.", "안녕하세요!"), "안녕하세요!")
        self.assertEqual(_keep_sentence_end("so we kept", "그래서 우리는"), "그래서 우리는")
        self.assertEqual(_keep_sentence_end("Hello.", ""), "")


class Collector:
    def __init__(self) -> None:
        self.results: list[tuple[int, str]] = []
        self.errors: list[str] = []
        self.done = threading.Event()
        self.expect = 0

    def on_result(self, block_id: int, text: str) -> None:
        self.results.append((block_id, text))
        if len(self.results) >= self.expect:
            self.done.set()

    def on_error(self, message: str) -> None:
        self.errors.append(message)
        self.done.set()


def _translator(model: FakeModel, collector: Collector) -> Translator:
    t = Translator(on_result=collector.on_result, on_error=collector.on_error)
    with mock.patch.object(translate, "load_model", return_value=(model, FakeTokenizer())):
        t.load_model()
    return t


class WorkerTests(unittest.TestCase):
    def test_queued_blocks_go_in_one_batch_in_order(self) -> None:
        model, c = FakeModel(), Collector()
        c.expect = 3
        t = _translator(model, c)
        # Submitted before start: they wait, then leave as one batch
        t.submit(0, "one")
        t.submit(1, "two")
        t.submit(2, "three")
        t.start()
        self.assertTrue(c.done.wait(5))
        t.stop()
        self.assertEqual(c.results, [(0, "ko:one"), (1, "ko:two"), (2, "ko:three")])
        self.assertEqual(len(model.batches), 1)
        kw = model.kwargs[0]
        self.assertEqual(kw["target_prefix"], [[TARGET_LANG]] * 3)
        self.assertEqual(kw["beam_size"], translate.BEAM_SIZE)
        self.assertGreater(kw["max_decoding_length"], 3)

    def test_each_sentence_is_translated_separately(self) -> None:
        model, c = FakeModel(), Collector()
        c.expect = 2
        t = _translator(model, c)
        t.submit(0, "Welcome back. Today we talk.")
        t.submit(1, "Short one")
        t.start()
        self.assertTrue(c.done.wait(5))
        t.stop()
        # Three sentences go out as three sources in one batch...
        self.assertEqual(
            model.batches,
            [[
                [SOURCE_LANG, "▁Welcome", "▁back.", EOS],
                [SOURCE_LANG, "▁Today", "▁we", "▁talk.", EOS],
                [SOURCE_LANG, "▁Short", "▁one", EOS],
            ]],
        )
        # ...and come back joined per block
        self.assertEqual(
            c.results, [(0, "ko:Welcome ko:back. ko:Today ko:we ko:talk."), (1, "ko:Short ko:one")]
        )

    def test_items_submitted_before_model_ready_are_translated(self) -> None:
        model, c = FakeModel(), Collector()
        c.expect = 1
        t = Translator(on_result=c.on_result, on_error=c.on_error)
        t.submit(7, "early")  # model still downloading
        with mock.patch.object(translate, "load_model", return_value=(model, FakeTokenizer())):
            t.load_model()
        t.start()
        self.assertTrue(c.done.wait(5))
        t.stop()
        self.assertEqual(c.results, [(7, "ko:early")])

    def test_discarded_blocks_are_not_translated(self) -> None:
        model, c = FakeModel(), Collector()
        c.expect = 2
        t = _translator(model, c)
        for i, text in enumerate(["a", "b", "c", "d"]):
            t.submit(i, text)
        t.discard([0, 2])
        t.start()
        self.assertTrue(c.done.wait(5))
        t.stop()
        self.assertEqual(c.results, [(1, "ko:b"), (3, "ko:d")])
        self.assertEqual(model.batches, [[[SOURCE_LANG, "▁b", EOS], [SOURCE_LANG, "▁d", EOS]]])

    def test_large_backlog_is_split_into_batches(self) -> None:
        model, c = FakeModel(), Collector()
        n = translate.MAX_BATCH + 3
        c.expect = n
        t = _translator(model, c)
        for i in range(n):
            t.submit(i, f"w{i}")
        t.start()
        self.assertTrue(c.done.wait(5))
        t.stop()
        self.assertEqual([r[0] for r in c.results], list(range(n)))
        self.assertEqual([len(b) for b in model.batches], [translate.MAX_BATCH, 3])

    def test_blank_text_is_not_submitted(self) -> None:
        model, c = FakeModel(), Collector()
        c.expect = 1
        t = _translator(model, c)
        t.submit(0, "   ")
        t.submit(1, "real")
        t.start()
        self.assertTrue(c.done.wait(5))
        t.stop()
        self.assertEqual(c.results, [(1, "ko:real")])

    def test_error_is_reported_once_and_stops_results(self) -> None:
        model, c = FakeModel(fail=True), Collector()
        t = _translator(model, c)
        t.submit(0, "one")
        t.start()
        self.assertTrue(c.done.wait(5))
        t.submit(1, "two")
        time.sleep(0.4)
        t.stop()
        self.assertEqual(len(c.errors), 1)
        self.assertIn("boom", c.errors[0])
        self.assertEqual(c.results, [])
        self.assertFalse(t.running)

    def test_stop_drops_queued_and_in_flight_items(self) -> None:
        model, c = FakeModel(), Collector()
        model.gate.clear()  # hold the first translation in flight
        t = _translator(model, c)
        t.submit(0, "in flight")
        t.start()
        time.sleep(0.4)
        t.submit(1, "queued")
        stopper = threading.Thread(target=t.stop)
        stopper.start()
        time.sleep(0.1)
        model.gate.set()
        stopper.join(5)
        self.assertFalse(stopper.is_alive())
        self.assertEqual(c.results, [])
        t.submit(2, "after stop")
        self.assertTrue(t._queue.empty())  # noqa: SLF001

    def test_start_requires_model(self) -> None:
        t = Translator(on_result=lambda _i, _t: None)
        with self.assertRaises(TranslationError):
            t.start()


class LoadModelTests(unittest.TestCase):
    def setUp(self) -> None:
        translate._models.clear()  # noqa: SLF001
        self.addCleanup(translate._models.clear)  # noqa: SLF001
        self.ct2 = mock.patch("ctranslate2.Translator", return_value="ct2-model")
        self.tok = mock.patch("tokenizers.Tokenizer.from_file", return_value="tokenizer")
        self.ct2_mock = self.ct2.start()
        self.tok.start()
        self.addCleanup(self.ct2.stop)
        self.addCleanup(self.tok.stop)

    def _model_files(self, root: str) -> Path:
        path = Path(root)
        for name in translate.MODEL_FILES:
            (path / name).write_text("x")
        return path

    def test_env_override_skips_download(self) -> None:
        statuses: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            self._model_files(tmp)
            with (
                mock.patch.dict(os.environ, {translate.MODEL_ENV: tmp}),
                mock.patch("huggingface_hub.hf_hub_download") as snap,
            ):
                model = translate.load_model(statuses.append)
        snap.assert_not_called()
        self.assertEqual(model, ("ct2-model", "tokenizer"))
        self.assertEqual(self.ct2_mock.call_args.args[0], tmp)
        self.assertEqual(self.ct2_mock.call_args.kwargs["intra_threads"], translate.INTRA_THREADS)
        self.assertEqual(statuses, ["Loading translation model…", "Korean translation ready"])

    def test_downloaded_model_makes_only_local_calls(self) -> None:
        statuses: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            self._model_files(tmp)
            env = {k: v for k, v in os.environ.items() if k != translate.MODEL_ENV}
            with (
                mock.patch.dict(os.environ, env, clear=True),
                mock.patch(
                    "huggingface_hub.hf_hub_download",
                    side_effect=lambda _repo, name, **_kw: str(Path(tmp) / name),
                ) as snap,
            ):
                translate.load_model(statuses.append)
                # Cached: a second load does no lookups at all
                calls = snap.call_count
                translate.load_model()
                self.assertEqual(snap.call_count, calls)
        self.assertEqual(
            {c.args[1] for c in snap.call_args_list}, set(translate.MODEL_FILES)
        )
        for call in snap.call_args_list:
            self.assertTrue(call.kwargs["local_files_only"])
            self.assertEqual(call.kwargs["revision"], translate.REVISION)
        self.assertEqual(statuses[0], "Loading translation model…")

    def test_missing_model_is_downloaded(self) -> None:
        statuses: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            self._model_files(tmp)

            def snapshot(_repo: str, name: str, *, local_files_only: bool, **_kwargs) -> str:  # noqa: ANN003
                if local_files_only:
                    raise FileNotFoundError("not cached")
                return str(Path(tmp) / name)

            env = {k: v for k, v in os.environ.items() if k != translate.MODEL_ENV}
            with (
                mock.patch.dict(os.environ, env, clear=True),
                mock.patch("huggingface_hub.hf_hub_download", side_effect=snapshot) as snap,
            ):
                translate.load_model(statuses.append)
        self.assertIn(False, [c.kwargs["local_files_only"] for c in snap.call_args_list])
        self.assertTrue(statuses[0].startswith("Downloading translation model"))

    def test_download_failure_raises_translation_error(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != translate.MODEL_ENV}
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch("huggingface_hub.hf_hub_download", side_effect=OSError("offline")),
        ):
            with self.assertRaises(TranslationError) as ctx:
                translate.load_model()
        self.assertIn("offline", str(ctx.exception))
        self.assertFalse(translate._models)  # noqa: SLF001

    def test_empty_override_dir_raises_translation_error(self) -> None:
        self.ct2_mock.side_effect = RuntimeError("Unable to open file 'model.bin'")
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {translate.MODEL_ENV: tmp}):
                self.assertFalse(translate.is_translation_model_downloaded())
                with self.assertRaises(TranslationError):
                    translate.load_model()


if __name__ == "__main__":
    unittest.main()
