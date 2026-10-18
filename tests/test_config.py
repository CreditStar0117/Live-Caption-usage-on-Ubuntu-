"""Tests for XDG config load/save and size clamps."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from caption_english.config import (
    MAX_HEIGHT,
    MAX_WIDTH,
    MIN_HEIGHT,
    MIN_WIDTH,
    AppConfig,
    clamp_size,
    load_config,
    save_config,
)


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


if __name__ == "__main__":
    unittest.main()
