"""Tests for XDG config load/save and size/font clamps."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from caption_english.config import (
    DEFAULT_FONT_SIZE,
    MAX_FONT_SIZE,
    MAX_HEIGHT,
    MAX_WIDTH,
    MIN_FONT_SIZE,
    MIN_HEIGHT,
    MIN_WIDTH,
    AppConfig,
    clamp_font_size,
    clamp_size,
    load_config,
    model_choices,
    save_config,
)


def _write_config(tmp: str, data: dict) -> None:
    path = Path(tmp) / "caption-english" / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class ClampTests(unittest.TestCase):
    def test_clamp_within_range(self) -> None:
        self.assertEqual(clamp_size(800, 160), (800, 160))

    def test_clamp_below_min(self) -> None:
        w, h = clamp_size(10, 10)
        self.assertEqual(w, MIN_WIDTH)
        self.assertEqual(h, MIN_HEIGHT)

    def test_clamp_above_max(self) -> None:
        w, h = clamp_size(99999, 99999)
        self.assertEqual(w, MAX_WIDTH)
        self.assertEqual(h, MAX_HEIGHT)

    def test_font_size_clamp(self) -> None:
        self.assertEqual(clamp_font_size(30), 30)
        self.assertEqual(clamp_font_size(4), MIN_FONT_SIZE)
        self.assertEqual(clamp_font_size(500), MAX_FONT_SIZE)


class ConfigPersistTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}):
                cfg = AppConfig(overlay_width=640, overlay_height=120, audio_source="mic")
                save_config(cfg)
                path = Path(tmp) / "caption-english" / "config.json"
                self.assertTrue(path.exists())
                loaded = load_config()
                self.assertEqual(loaded.overlay_width, 640)
                self.assertEqual(loaded.overlay_height, 120)
                self.assertEqual(loaded.audio_source, "mic")
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(data["overlay_width"], 640)

    def test_font_size_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}):
                save_config(AppConfig(font_size=40))
                self.assertEqual(load_config().font_size, 40)

    def test_font_size_out_of_range_is_clamped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}):
                _write_config(tmp, {"font_size": 200})
                self.assertEqual(load_config().font_size, MAX_FONT_SIZE)
                _write_config(tmp, {"font_size": 1})
                self.assertEqual(load_config().font_size, MIN_FONT_SIZE)

    def test_missing_font_size_uses_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}):
                # A config saved before font size existed
                _write_config(tmp, {"overlay_width": 700, "audio_source": "mic"})
                cfg = load_config()
                self.assertEqual(cfg.font_size, DEFAULT_FONT_SIZE)
                self.assertEqual(cfg.overlay_width, 700)
                self.assertEqual(cfg.audio_source, "mic")

    def test_invalid_font_size_keeps_other_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}):
                for bad in ("huge", None, [30], {"px": 30}):
                    _write_config(tmp, {"font_size": bad, "overlay_width": 700})
                    cfg = load_config()
                    self.assertEqual(cfg.font_size, DEFAULT_FONT_SIZE, bad)
                    self.assertEqual(cfg.overlay_width, 700, bad)


class ModelChoiceTests(unittest.TestCase):
    def test_offered_models(self) -> None:
        expected = [("base.en", "Accurate (base.en)"), ("tiny.en", "Fast (tiny.en)")]
        self.assertEqual(model_choices("base.en"), expected)
        self.assertEqual(model_choices("tiny.en"), expected)
        self.assertEqual(model_choices(""), expected)

    def test_other_saved_model_is_kept(self) -> None:
        choices = model_choices("small.en")
        self.assertEqual(choices[-1], ("small.en", "small.en"))
        self.assertEqual(len(choices), 3)

    def test_default_model_is_accurate(self) -> None:
        self.assertEqual(AppConfig().model_size, "base.en")


if __name__ == "__main__":
    unittest.main()
