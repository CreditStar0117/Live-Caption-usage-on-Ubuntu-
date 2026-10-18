"""Always-on-top caption overlay with controllable size and font size."""

from __future__ import annotations

import logging
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from caption_english import x11
from caption_english.config import (
    DEFAULT_FONT_SIZE,
    MIN_HEIGHT,
    MIN_WIDTH,
    clamp_font_size,
    clamp_size,
)

logger = logging.getLogger(__name__)

SizeCallback = Callable[[int, int], None]


class CaptionOverlay(Gtk.Window):
    """Caption window that stays above other windows."""

    def __init__(
        self,
        width: int = 800,
        height: int = 160,
        on_size_changed: SizeCallback | None = None,
        font_size: int = DEFAULT_FONT_SIZE,
    ) -> None:
        super().__init__(title="Live Caption")
        self._on_size_changed = on_size_changed
        self._width, self._height = clamp_size(width, height)
        self._size_idle: int | None = None

        self.set_decorated(True)
        self.set_resizable(True)
        self.set_default_size(self._width, self._height)
        self.set_size_request(MIN_WIDTH, MIN_HEIGHT)

        css = Gtk.CssProvider()
        css.load_from_data(
            b"""
            window.caption-overlay {
              background-color: rgba(12, 12, 14, 0.88);
            }
            label.caption-text {
              color: #f5f5f5;
              padding: 12px 16px;
            }
            """
        )
        display = Gdk.Display.get_default()
        Gtk.StyleContext.add_provider_for_display(
            display, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        # Font size lives in its own provider so changing it leaves the rest alone
        self._font_css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            display, self._font_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1
        )
        self._font_size = DEFAULT_FONT_SIZE
        self.set_font_size(font_size)
        self.add_css_class("caption-overlay")

        self._label = Gtk.Label(
            label="Captions will appear here…",
            wrap=True,
            wrap_mode=Pango.WrapMode.WORD_CHAR,
            justify=Gtk.Justification.LEFT,
            xalign=0.0,
            yalign=1.0,
            selectable=False,
        )
        self._label.add_css_class("caption-text")
        self._label.set_hexpand(True)
        self._label.set_vexpand(True)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_child(self._label)
        self.set_child(scroller)
        # Keep the newest caption line in view as text grows or reflows
        self._vadj = scroller.get_vadjustment()
        self._scroll_idle: int | None = None
        self._vadj.connect("changed", self._on_content_size_changed)

        # GTK 4 keeps default-width/height in sync with user resizes (content size)
        self.connect("notify::default-width", self._on_default_size_notify)
        self.connect("notify::default-height", self._on_default_size_notify)
        # The WM drops _NET_WM_STATE when a window is unmapped, so re-apply on every map
        self.connect("map", lambda *_: GLib.timeout_add(150, self._apply_keep_above))

    def _apply_keep_above(self) -> bool:
        surface = self.get_surface()
        get_xid = getattr(surface, "get_xid", None)
        if get_xid is None or not x11.set_keep_above(get_xid()):
            logger.warning("Always-on-top is not supported in this session (needs X11/XWayland)")
        return False

    def _on_content_size_changed(self, *_args) -> None:  # noqa: ANN001
        # "changed" fires while the viewport is being allocated, and a value set
        # then is not drawn until the next allocation: scroll once layout is done
        if self._scroll_idle is None:
            self._scroll_idle = GLib.idle_add(self._scroll_to_newest)

    def _scroll_to_newest(self) -> bool:
        self._scroll_idle = None
        self._vadj.set_value(self._vadj.get_upper() - self._vadj.get_page_size())
        return False

    def _on_default_size_notify(self, *_args) -> None:  # noqa: ANN001
        # width and height notify separately; handle them together once idle
        if self._size_idle is None:
            self._size_idle = GLib.idle_add(self._sync_size_from_window)

    def _sync_size_from_window(self) -> bool:
        self._size_idle = None
        raw_w, raw_h = self.get_default_size()
        if raw_w <= 0 or raw_h <= 0:
            return False
        w, h = clamp_size(raw_w, raw_h)
        if (w, h) != (raw_w, raw_h):
            # Dragged past the maximum: snap back into the supported range
            self.set_default_size(w, h)
        if (w, h) != (self._width, self._height):
            self._width, self._height = w, h
            if self._on_size_changed:
                self._on_size_changed(w, h)
        return False

    @property
    def caption_width(self) -> int:
        return self._width

    @property
    def caption_height(self) -> int:
        return self._height

    @property
    def font_size(self) -> int:
        return self._font_size

    def set_font_size(self, px: int) -> None:
        """Apply a caption font size in pixels; the current text is kept and reflowed."""
        self._font_size = clamp_font_size(px)
        self._font_css.load_from_data(
            f"label.caption-text {{ font-size: {self._font_size}px; }}".encode()
        )

    def set_caption_text(self, text: str) -> None:
        def _set() -> bool:
            self._label.set_text(text or "")
            return False

        GLib.idle_add(_set)

    def set_size_px(self, width: int, height: int) -> None:
        w, h = clamp_size(width, height)
        self._width, self._height = w, h
        self.set_default_size(w, h)
        if self._on_size_changed:
            self._on_size_changed(w, h)

    def show_overlay(self) -> None:
        self.present()

    def hide_overlay(self) -> None:
        self.set_visible(False)

    def is_overlay_visible(self) -> bool:
        return bool(self.get_visible())
