"""XDG config for overlay size and audio source preferences."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

AudioSource = Literal["mic", "system", "both"]

MIN_WIDTH = 320
MAX_WIDTH = 2400
MIN_HEIGHT = 80
MAX_HEIGHT = 900
DEFAULT_WIDTH = 800
DEFAULT_HEIGHT = 160


def clamp_size(width: int, height: int) -> tuple[int, int]:
    w = max(MIN_WIDTH, min(MAX_WIDTH, int(width)))
    h = max(MIN_HEIGHT, min(MAX_HEIGHT, int(height)))
    return w, h


def config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    path = base / "caption-english"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return config_dir() / "config.json"


@dataclass
class AppConfig:
    overlay_width: int = DEFAULT_WIDTH
    overlay_height: int = DEFAULT_HEIGHT
    overlay_x: int | None = None
    overlay_y: int | None = None
    audio_source: AudioSource = "system"
    model_size: str = "base.en"
    overlay_visible: bool = True

    def clamped(self) -> AppConfig:
        w, h = clamp_size(self.overlay_width, self.overlay_height)
        return AppConfig(
            overlay_width=w,
            overlay_height=h,
            overlay_x=self.overlay_x,
            overlay_y=self.overlay_y,
            audio_source=self.audio_source if self.audio_source in ("mic", "system", "both") else "system",
            model_size=self.model_size or "base.en",
            overlay_visible=bool(self.overlay_visible),
        )


def load_config() -> AppConfig:
    path = config_path()
    if not path.exists():
        return AppConfig().clamped()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cfg = AppConfig(
            overlay_width=int(data.get("overlay_width", DEFAULT_WIDTH)),
            overlay_height=int(data.get("overlay_height", DEFAULT_HEIGHT)),
            overlay_x=data.get("overlay_x"),
            overlay_y=data.get("overlay_y"),
            audio_source=data.get("audio_source", "system"),
            model_size=data.get("model_size", "base.en"),
            overlay_visible=bool(data.get("overlay_visible", True)),
        )
        return cfg.clamped()
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return AppConfig().clamped()


def save_config(cfg: AppConfig) -> None:
    cfg = cfg.clamped()
    path = config_path()
    path.write_text(json.dumps(asdict(cfg), indent=2) + "\n", encoding="utf-8")
