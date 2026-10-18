"""GTK application: control panel + overlay + capture/STT wiring."""

from __future__ import annotations

import logging
import sys
import threading
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from caption_english.audio import AudioCapture, CaptureError, CaptureSource
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
from caption_english.overlay import CaptionOverlay
from caption_english.stt import SpeechEngineError, SpeechToText, preload_model

logger = logging.getLogger(__name__)

# Final phrases kept on the overlay (older text scrolls away)
MAX_CAPTION_PHRASES = 6


class ControlWindow(Gtk.ApplicationWindow):
    def __init__(self, app: "CaptionEnglishApp") -> None:
        super().__init__(application=app, title="Caption English")
        self.app_ref = app
        self._syncing_spins = False
        self.set_default_size(420, 360)
        self.set_resizable(True)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(16)
        root.set_margin_bottom(16)
        root.set_margin_start(16)
        root.set_margin_end(16)
        self.set_child(root)

        title = Gtk.Label(label="Live Caption", xalign=0.0)
        title.add_css_class("title-1")
        root.append(title)

        self.status = Gtk.Label(label="Ready", xalign=0.0, wrap=True)
        self.status.add_css_class("dim-label")
        root.append(self.status)

        # Audio source
        src_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        src_row.append(Gtk.Label(label="Audio source:", xalign=0.0))
        self.source_combo = Gtk.DropDown.new_from_strings(["system", "mic", "both"])
        # Map current config
        sources = ["system", "mic", "both"]
        try:
            self.source_combo.set_selected(sources.index(app.config.audio_source))
        except ValueError:
            self.source_combo.set_selected(0)
        self.source_combo.connect("notify::selected", self._on_source_changed)
        src_row.append(self.source_combo)
        root.append(src_row)

        # Size controls
        size_frame = Gtk.Frame(label="Overlay size")
        size_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        size_box.set_margin_top(8)
        size_box.set_margin_bottom(8)
        size_box.set_margin_start(8)
        size_box.set_margin_end(8)
        size_frame.set_child(size_box)

        w_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        w_row.append(Gtk.Label(label="Width", xalign=0.0, width_chars=8))
        self.width_adj = Gtk.Adjustment(
            value=app.config.overlay_width,
            lower=MIN_WIDTH,
            upper=MAX_WIDTH,
            step_increment=10,
            page_increment=50,
        )
        self.width_spin = Gtk.SpinButton(adjustment=self.width_adj, climb_rate=1, digits=0)
        self.width_spin.set_hexpand(True)
        self.width_spin.connect("value-changed", self._on_size_spin)
        w_row.append(self.width_spin)
        size_box.append(w_row)

        h_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        h_row.append(Gtk.Label(label="Height", xalign=0.0, width_chars=8))
        self.height_adj = Gtk.Adjustment(
            value=app.config.overlay_height,
            lower=MIN_HEIGHT,
            upper=MAX_HEIGHT,
            step_increment=10,
            page_increment=50,
        )
        self.height_spin = Gtk.SpinButton(adjustment=self.height_adj, climb_rate=1, digits=0)
        self.height_spin.set_hexpand(True)
        self.height_spin.connect("value-changed", self._on_size_spin)
        h_row.append(self.height_spin)
        size_box.append(h_row)

        presets = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for label, w, h in (("Compact", 560, 100), ("Default", 800, 160), ("Wide", 1100, 200)):
            btn = Gtk.Button(label=label)
            btn.connect("clicked", self._make_preset_handler(w, h))
            presets.append(btn)
        size_box.append(presets)
        root.append(size_frame)

        # Actions
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.start_btn = Gtk.Button(label="Start")
        self.start_btn.add_css_class("suggested-action")
        self.start_btn.connect("clicked", lambda *_: app.start_captioning())
        actions.append(self.start_btn)

        self.stop_btn = Gtk.Button(label="Stop")
        self.stop_btn.set_sensitive(False)
        self.stop_btn.connect("clicked", lambda *_: app.stop_captioning())
        actions.append(self.stop_btn)

        self.toggle_overlay_btn = Gtk.Button(label="Hide overlay")
        self.toggle_overlay_btn.connect("clicked", lambda *_: app.toggle_overlay())
        actions.append(self.toggle_overlay_btn)
        root.append(actions)

        hint = Gtk.Label(
            label="First start downloads the Whisper model (local, English).",
            wrap=True,
            xalign=0.0,
        )
        hint.add_css_class("dim-label")
        root.append(hint)

    def _make_preset_handler(self, w: int, h: int):
        def _handler(*_args):  # noqa: ANN001
            self.width_spin.set_value(w)
            self.height_spin.set_value(h)
            self.app_ref.apply_overlay_size(w, h)

        return _handler

    def _on_size_spin(self, *_args) -> None:  # noqa: ANN001
        if self._syncing_spins:
            return
        w = int(self.width_spin.get_value())
        h = int(self.height_spin.get_value())
        self.app_ref.apply_overlay_size(w, h)

    def _on_source_changed(self, *_args) -> None:  # noqa: ANN001
        selected = self.source_combo.get_selected()
        sources = ["system", "mic", "both"]
        if 0 <= selected < len(sources):
            self.app_ref.set_audio_source(sources[selected])

    def set_status(self, text: str, error: bool = False) -> None:
        def _set() -> bool:
            self.status.set_text(text)
            if error:
                self.status.add_css_class("error")
            else:
                self.status.remove_css_class("error")
            return False

        GLib.idle_add(_set)

    def set_running(self, running: bool) -> None:
        def _set() -> bool:
            self.start_btn.set_sensitive(not running)
            self.stop_btn.set_sensitive(running)
            self.source_combo.set_sensitive(not running)
            return False

        GLib.idle_add(_set)

    def sync_size_spins(self, width: int, height: int) -> None:
        def _set() -> bool:
            self._syncing_spins = True
            try:
                self.width_spin.set_value(width)
                self.height_spin.set_value(height)
            finally:
                self._syncing_spins = False
            return False

        GLib.idle_add(_set)

    def set_overlay_button_label(self, visible: bool) -> None:
        def _set() -> bool:
            self.toggle_overlay_btn.set_label("Hide overlay" if visible else "Show overlay")
            return False

        GLib.idle_add(_set)


class CaptionEnglishApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id="org.captionenglish.LiveCaption")
        self.config: AppConfig = load_config()
        self.control: ControlWindow | None = None
        self.overlay: CaptionOverlay | None = None
        self.capture: AudioCapture | None = None
        self.stt: SpeechToText | None = None
        self._captioning = False
        # Bumped on every start/stop so late callbacks from an old session are ignored
        self._session = 0
        self._finals: list[str] = []
        self._partial = ""
        self._size_save_timeout: int | None = None

    def do_activate(self) -> None:  # noqa: N802
        if self.control is None:
            self.control = ControlWindow(self)
            self.control.connect("close-request", self._on_control_close)
            self.overlay = CaptionOverlay(
                width=self.config.overlay_width,
                height=self.config.overlay_height,
                on_size_changed=self._on_overlay_resized,
            )
            self.overlay.connect("close-request", self._on_overlay_close)
            if self.config.overlay_visible:
                self.overlay.show_overlay()
            else:
                self.overlay.hide_overlay()
            self.control.set_overlay_button_label(self.overlay.is_overlay_visible())
            # Warm the model cache so Start is quick (only if already downloaded)
            threading.Thread(
                target=preload_model,
                args=(self.config.model_size,),
                name="model-preload",
                daemon=True,
            ).start()
        self.control.present()

    def _on_control_close(self, *_args) -> bool:  # noqa: ANN001
        self.stop_captioning()
        self._persist_config()
        self.quit()
        return False

    def _on_overlay_close(self, *_args) -> bool:  # noqa: ANN001
        # Hide instead of destroy so show/hide still works
        if self.overlay:
            self.overlay.hide_overlay()
            self.config.overlay_visible = False
            self._persist_config()
            if self.control:
                self.control.set_overlay_button_label(False)
        return True  # prevent destroy

    def set_audio_source(self, source: str) -> None:
        if source in ("mic", "system", "both"):
            self.config.audio_source = source  # type: ignore[assignment]
            self._persist_config()

    def apply_overlay_size(self, width: int, height: int) -> None:
        w, h = clamp_size(width, height)
        self.config.overlay_width = w
        self.config.overlay_height = h
        if self.overlay:
            self.overlay.set_size_px(w, h)
        self._persist_config()

    def _on_overlay_resized(self, width: int, height: int) -> None:
        self.config.overlay_width = width
        self.config.overlay_height = height
        if self.control:
            self.control.sync_size_spins(width, height)
        # Debounce disk writes
        if self._size_save_timeout is not None:
            GLib.source_remove(self._size_save_timeout)
        self._size_save_timeout = GLib.timeout_add(400, self._persist_config_timeout)

    def _persist_config_timeout(self) -> bool:
        self._size_save_timeout = None
        self._persist_config()
        return False

    def _persist_config(self) -> None:
        try:
            save_config(self.config)
        except OSError as exc:
            logger.error("Failed to save config: %s", exc)

    def toggle_overlay(self) -> None:
        if not self.overlay:
            return
        if self.overlay.is_overlay_visible():
            self.overlay.hide_overlay()
            self.config.overlay_visible = False
        else:
            self.overlay.set_size_px(self.config.overlay_width, self.config.overlay_height)
            self.overlay.show_overlay()
            self.config.overlay_visible = True
        self._persist_config()
        if self.control:
            self.control.set_overlay_button_label(self.overlay.is_overlay_visible())

    def start_captioning(self) -> None:
        if self._captioning:
            return
        self._session += 1
        session = self._session
        source = CaptureSource(self.config.audio_source)
        self._finals = []
        self._partial = ""
        if self.overlay:
            self.overlay.set_caption_text("")
        if self.control:
            self.control.set_status("Starting…")
            self.control.set_running(True)

        def _boot() -> None:
            stt = SpeechToText(
                on_text=lambda text, final: GLib.idle_add(self._show_text, session, text, final),
                on_error=lambda msg: self._on_pipeline_error(session, msg),
                on_status=lambda msg: self._on_status(session, msg),
                model_size=self.config.model_size,
            )
            capture = AudioCapture(
                on_audio=stt.feed_audio,
                on_error=lambda msg: self._on_pipeline_error(session, msg),
            )
            try:
                # Open the audio device first so capture begins right away;
                # frames queue up in the STT engine until the model is ready.
                capture.start(source)
                stt.load_model()
                stt.start()
            except (CaptureError, SpeechEngineError) as exc:
                self._abort_boot(session, capture, stt, str(exc))
                return
            except Exception as exc:  # noqa: BLE001
                self._abort_boot(session, capture, stt, f"Failed to start: {exc}")
                return
            GLib.idle_add(self._finish_boot, session, capture, stt)

        threading.Thread(target=_boot, name="caption-boot", daemon=True).start()

    def _abort_boot(
        self, session: int, capture: AudioCapture, stt: SpeechToText, message: str
    ) -> None:
        capture.stop()
        stt.stop()
        self._on_pipeline_error(session, message)

    def _finish_boot(self, session: int, capture: AudioCapture, stt: SpeechToText) -> bool:
        if session != self._session:
            # Stopped (or restarted) while the model was loading
            capture.stop()
            stt.stop()
            return False
        self.capture = capture
        self.stt = stt
        self._captioning = True
        if self.control:
            self.control.set_status(f"Captioning ({self.config.audio_source} audio)…")
        return False

    def stop_captioning(self) -> None:
        self._session += 1
        self._captioning = False
        if self.capture:
            try:
                self.capture.stop()
            except Exception:  # noqa: BLE001
                logger.exception("Error stopping capture")
            self.capture = None
        if self.stt:
            try:
                self.stt.stop()
            except Exception:  # noqa: BLE001
                logger.exception("Error stopping STT")
            self.stt = None
        if self.control:
            self.control.set_running(False)
            self.control.set_status("Stopped")

    def _show_text(self, session: int, text: str, is_final: bool) -> bool:
        if session != self._session:
            return False
        if is_final:
            self._finals.append(text)
            del self._finals[:-MAX_CAPTION_PHRASES]
            self._partial = ""
        else:
            self._partial = text
        if self.overlay:
            self.overlay.set_caption_text(" ".join([*self._finals, self._partial]).strip())
        return False

    def _on_status(self, session: int, message: str) -> None:
        if self.control and session == self._session:
            self.control.set_status(message)

    def _on_pipeline_error(self, session: int, message: str) -> None:
        logger.error(message)
        # Ensure we leave a clean stopped state (on the GTK thread)
        GLib.idle_add(self._fail_stop, session, message)

    def _fail_stop(self, session: int, message: str) -> bool:
        if session != self._session:
            return False
        self.stop_captioning()
        if self.control:
            self.control.set_status(f"Error: {message}", error=True)
        return False


def run(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = CaptionEnglishApp()
    return int(app.run(argv if argv is not None else sys.argv))
