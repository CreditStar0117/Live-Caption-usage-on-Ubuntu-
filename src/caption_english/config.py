"""XDG config for overlay size, caption text, audio source and model preferences."""

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
MIN_FONT_SIZE = 12
MAX_FONT_SIZE = 72
DEFAULT_FONT_SIZE = 22
DEFAULT_MODEL = "base.en"
# Speech models offered in the control window: (model name, label)
MODEL_CHOICES = (
    (DEFAULT_MODEL, "Accurate (base.en)"),
    ("tiny.en", "Fast (tiny.en)"),
)


def clamp_size(width: int, height: int) -> tuple[int, int]:
    w = max(MIN_WIDTH, min(MAX_WIDTH, int(width)))
    h = max(MIN_HEIGHT, min(MAX_HEIGHT, int(height)))
    return w, h


def clamp_font_size(size: int) -> int:
    return max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, int(size)))


def model_choices(current: str) -> list[tuple[str, str]]:
    """Offered models, plus *current* if it is another (e.g. hand-edited) model."""
    choices = list(MODEL_CHOICES)
    if current and current not in dict(choices):
        choices.append((current, current))
    return choices


def _parse_font_size(value: object) -> int:
    # Parsed on its own so a bad value does not reset the other settings
    try:
        return clamp_font_size(int(value))  # type: ignore[call-overload]
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_FONT_SIZE


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
    model_size: str = DEFAULT_MODEL
    overlay_visible: bool = True
    font_size: int = DEFAULT_FONT_SIZE

    def clamped(self) -> AppConfig:
        w, h = clamp_size(self.overlay_width, self.overlay_height)
        return AppConfig(
            overlay_width=w,
            overlay_height=h,
            overlay_x=self.overlay_x,
            overlay_y=self.overlay_y,
            audio_source=self.audio_source if self.audio_source in ("mic", "system", "both") else "system",
            model_size=self.model_size or DEFAULT_MODEL,
            overlay_visible=bool(self.overlay_visible),
            font_size=clamp_font_size(self.font_size),
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
            model_size=data.get("model_size", DEFAULT_MODEL),
            overlay_visible=bool(data.get("overlay_visible", True)),
            font_size=_parse_font_size(data.get("font_size", DEFAULT_FONT_SIZE)),
        )
        return cfg.clamped()
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return AppConfig().clamped()


def save_config(cfg: AppConfig) -> None:
    cfg = cfg.clamped()
    path = config_path()
    path.write_text(json.dumps(asdict(cfg), indent=2) + "\n", encoding="utf-8")
