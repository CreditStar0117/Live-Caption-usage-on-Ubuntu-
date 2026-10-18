"""CLI entry: python -m caption_english"""

from __future__ import annotations

import os
import sys


def main(argv: list[str] | None = None) -> int:
    # GNOME on Wayland has no always-on-top API for apps; under XWayland the
    # overlay can use the X11 "above" hint. Must be set before GTK loads.
    if os.environ.get("XDG_SESSION_TYPE") == "wayland" and os.environ.get("DISPLAY"):
        os.environ.setdefault("GDK_BACKEND", "x11")

    from caption_english.app import run

    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
