"""GTK application: control panel + overlay + capture/STT wiring."""

from __future__ import annotations

import logging
import os
import sys
import threading
from datetime import datetime
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from caption_english.audio import AudioCapture, CaptureError, CaptureSource
from caption_english import translate
from caption_english.captions import (
    BilingualCaptions,
    format_captions,
    history_capacity,
    trim_history,
)
from caption_english.config import (
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
from caption_english.history import (
    CaptionHistory,
    default_filename,
    history_summary,
    write_transcript,
)
from caption_english.overlay import CaptionOverlay
from caption_english.stt import SpeechEngineError, SpeechToText, preload_model
from caption_english.translate import TranslationError, Translator

logger = logging.getLogger(__name__)

# How often an unfinished sentence is checked for translation (ms)
FLUSH_CHECK_MS = 250
TRANSLATION_OFF = "Off. English captions only."
TRANSLATION_NEXT_START = "Korean appears under each English sentence from the next Start."
# The save and confirm dialogs need GTK 4.10 (Ubuntu 22.04 ships 4.6)
HAS_DIALOGS = hasattr(Gtk, "FileDialog") and hasattr(Gtk, "AlertDialog")
HISTORY_NEEDS_GTK = "Saving history needs GTK 4.10 or newer."


def _sentences(count: int) -> str:
    return f"{count} sentence" if count == 1 else f"{count} sentences"


def _documents_folder() -> str:
    documents = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS)
    if documents and os.path.isdir(documents):
        return documents
    return GLib.get_home_dir()


def _dialog_dismissed(exc: GLib.Error) -> bool:
    quark = Gtk.dialog_error_quark()
    return exc.matches(quark, Gtk.DialogError.DISMISSED) or exc.matches(
        quark, Gtk.DialogError.CANCELLED
    )


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

        # Speech model: accuracy vs speed
        model_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        model_row.append(Gtk.Label(label="Speech model:", xalign=0.0))
        choices = model_choices(app.config.model_size)
        self._models = [name for name, _label in choices]
        self.model_combo = Gtk.DropDown.new_from_strings([label for _name, label in choices])
        self.model_combo.set_selected(self._models.index(app.config.model_size))
        self.model_combo.connect("notify::selected", self._on_model_changed)
        model_row.append(self.model_combo)
        root.append(model_row)

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

        # Caption text controls
        text_frame = Gtk.Frame(label="Caption text")
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        text_box.set_margin_top(8)
        text_box.set_margin_bottom(8)
        text_box.set_margin_start(8)
        text_box.set_margin_end(8)
        text_frame.set_child(text_box)

        font_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        font_row.append(Gtk.Label(label="Font size", xalign=0.0, width_chars=8))
        self.font_adj = Gtk.Adjustment(
            value=app.config.font_size,
            lower=MIN_FONT_SIZE,
            upper=MAX_FONT_SIZE,
            step_increment=2,
            page_increment=8,
        )
        self.font_spin = Gtk.SpinButton(adjustment=self.font_adj, climb_rate=1, digits=0)
        self.font_spin.set_hexpand(True)
        self.font_spin.connect(
            "value-changed", lambda spin: app.apply_font_size(int(spin.get_value()))
        )
        font_row.append(self.font_spin)
        font_row.append(Gtk.Label(label="px"))
        text_box.append(font_row)
        root.append(text_frame)

        # Korean translation
        tr_frame = Gtk.Frame(label="Translation")
        tr_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        tr_box.set_margin_top(8)
        tr_box.set_margin_bottom(8)
        tr_box.set_margin_start(8)
        tr_box.set_margin_end(8)
        tr_frame.set_child(tr_box)

        tr_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        tr_label = Gtk.Label(label="Korean translation", xalign=0.0)
        tr_label.set_hexpand(True)
        tr_row.append(tr_label)
        self.translate_switch = Gtk.Switch(active=app.config.translate_korean)
        self.translate_switch.set_valign(Gtk.Align.CENTER)
        self.translate_switch.connect(
            "notify::active", lambda sw, _p: app.set_translate_korean(sw.get_active())
        )
        tr_row.append(self.translate_switch)
        tr_box.append(tr_row)

        self.translation_status = Gtk.Label(
            label=TRANSLATION_NEXT_START if app.config.translate_korean else TRANSLATION_OFF,
            xalign=0.0,
            wrap=True,
        )
        self.translation_status.add_css_class("dim-label")
        tr_box.append(self.translation_status)
        root.append(tr_frame)

        # English caption history for this app run
        hist_frame = Gtk.Frame(label="Caption history")
        hist_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        hist_box.set_margin_top(8)
        hist_box.set_margin_bottom(8)
        hist_box.set_margin_start(8)
        hist_box.set_margin_end(8)
        hist_frame.set_child(hist_box)

        hist_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.history_summary = Gtk.Label(
            label=history_summary(0, None), xalign=0.0, wrap=True
        )
        self.history_summary.set_hexpand(True)
        hist_row.append(self.history_summary)
        self.save_history_btn = Gtk.Button(label="Save history…")
        self.save_history_btn.set_sensitive(False)
        self.save_history_btn.connect("clicked", lambda *_: app.save_history())
        hist_row.append(self.save_history_btn)
        self.clear_history_btn = Gtk.Button(label="Clear…")
        self.clear_history_btn.set_sensitive(False)
        self.clear_history_btn.connect("clicked", lambda *_: app.clear_history())
        hist_row.append(self.clear_history_btn)
        hist_box.append(hist_row)

        self.history_error = Gtk.Label(xalign=0.0, wrap=True)
        if HAS_DIALOGS:
            self.history_error.add_css_class("error")
            self.history_error.set_visible(False)
        else:
            self.history_error.set_text(HISTORY_NEEDS_GTK)
            self.history_error.add_css_class("dim-label")
        hist_box.append(self.history_error)
        root.append(hist_frame)

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
            label=(
                "The first start with each speech model downloads it (local, English). "
                f"Korean translation downloads its model (~{translate.DOWNLOAD_MB} MB) "
                "the first time it is used. Everything runs on this computer."
            ),
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

    def _on_model_changed(self, *_args) -> None:  # noqa: ANN001
        selected = self.model_combo.get_selected()
        if 0 <= selected < len(self._models):
            self.app_ref.set_model(self._models[selected])

    def set_status(self, text: str, error: bool = False) -> None:
        def _set() -> bool:
            self.status.set_text(text)
            if error:
                self.status.add_css_class("error")
            else:
                self.status.remove_css_class("error")
            return False

        GLib.idle_add(_set)

    def set_translation_status(self, text: str, error: bool = False) -> None:
        def _set() -> bool:
            self.translation_status.set_text(text)
            if error:
                self.translation_status.remove_css_class("dim-label")
                self.translation_status.add_css_class("error")
            else:
                self.translation_status.remove_css_class("error")
                self.translation_status.add_css_class("dim-label")
            return False

        GLib.idle_add(_set)

    def set_running(self, running: bool) -> None:
        def _set() -> bool:
            self.start_btn.set_sensitive(not running)
            self.stop_btn.set_sensitive(running)
            self.source_combo.set_sensitive(not running)
            self.model_combo.set_sensitive(not running)
            self.translate_switch.set_sensitive(not running)
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

    def update_history(self, count: int, saved_name: str | None) -> None:
        """Show the history size; call on the GTK thread."""
        self.history_summary.set_text(history_summary(count, saved_name))
        self.save_history_btn.set_sensitive(HAS_DIALOGS and count > 0)
        self.clear_history_btn.set_sensitive(HAS_DIALOGS and count > 0)

    def set_history_error(self, text: str) -> None:
        """Show a save error in red, or hide it with an empty text; call on the GTK thread."""
        if not HAS_DIALOGS:
            return
        self.history_error.set_text(text)
        self.history_error.set_visible(bool(text))

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
        # Set while a session captions with Korean translation
        self.translator: Translator | None = None
        self._bilingual: BilingualCaptions | None = None
        self._flush_timer: int | None = None
        # Final English for the whole app run, saved only when the user asks
        self.history = CaptionHistory()
        self._history_folder: str | None = None
        self._history_saved_name: str | None = None
        # Set while the "save before quitting?" prompt or its save dialog is open
        self._closing_prompt = False

    def do_activate(self) -> None:  # noqa: N802
        if self.control is None:
            self.control = ControlWindow(self)
            self.control.connect("close-request", self._on_control_close)
            self.overlay = CaptionOverlay(
                width=self.config.overlay_width,
                height=self.config.overlay_height,
                on_size_changed=self._on_overlay_resized,
                font_size=self.config.font_size,
            )
            self.overlay.connect("close-request", self._on_overlay_close)
            if self.config.overlay_visible:
                self.overlay.show_overlay()
            else:
                self.overlay.hide_overlay()
            self.control.set_overlay_button_label(self.overlay.is_overlay_visible())
            self._preload_model()
            if self.config.translate_korean:
                self._preload_translation()
        self.control.present()

    def _preload_model(self) -> None:
        # Warm the model cache so Start is quick (only if already downloaded)
        threading.Thread(
            target=preload_model,
            args=(self.config.model_size,),
            name="model-preload",
            daemon=True,
        ).start()

    def _preload_translation(self) -> None:
        # Warm the translation model so Korean starts quickly (only if already downloaded)
        threading.Thread(
            target=translate.preload_model, name="translation-preload", daemon=True
        ).start()

    def _on_control_close(self, *_args) -> bool:  # noqa: ANN001
        if HAS_DIALOGS and self.history.has_unsaved:
            # Keep the window (and captioning) until the user decides
            if not self._closing_prompt:
                self._closing_prompt = True
                self._ask_before_quit()
            return True
        self._quit()
        return False

    def _quit(self) -> None:
        self.stop_captioning()
        self._persist_config()
        self.quit()

    def _ask_before_quit(self) -> None:
        count = self.history.sentence_count
        dialog = Gtk.AlertDialog(
            message="Save caption history before quitting?",
            detail=f"{_sentences(count)} of English captions have not been saved. "
            "They are lost if you quit without saving.",
            buttons=["Cancel", "Discard", "Save…"],
            cancel_button=0,
            default_button=2,
            modal=True,
        )
        dialog.choose(self.control, None, self._on_quit_chosen)

    def _on_quit_chosen(self, dialog: Gtk.AlertDialog, result: Gio.AsyncResult) -> None:
        try:
            choice = dialog.choose_finish(result)
        except GLib.Error:
            choice = 0
        if choice == 2:
            self.save_history(quit_after=True)
        elif choice == 1:
            self._quit()
        else:
            self._closing_prompt = False

    def _refresh_history(self) -> None:
        if self.control:
            saved = None if self.history.has_unsaved else self._history_saved_name
            self.control.update_history(self.history.sentence_count, saved)

    def save_history(self, quit_after: bool = False) -> None:
        """Ask where to save the English caption history, then write it there."""
        if not HAS_DIALOGS or self.control is None:
            return
        dialog = Gtk.FileDialog(title="Save caption history", modal=True)
        dialog.set_initial_name(default_filename(datetime.now()))
        dialog.set_initial_folder(
            Gio.File.new_for_path(self._history_folder or _documents_folder())
        )
        text_files = Gtk.FileFilter(name="Text files (*.txt)")
        text_files.add_suffix("txt")
        all_files = Gtk.FileFilter(name="All files")
        all_files.add_pattern("*")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(text_files)
        filters.append(all_files)
        dialog.set_filters(filters)
        dialog.set_default_filter(text_files)
        dialog.save(self.control, None, self._on_save_chosen, quit_after)

    def _on_save_chosen(
        self, dialog: Gtk.FileDialog, result: Gio.AsyncResult, quit_after: bool
    ) -> None:
        try:
            gfile = dialog.save_finish(result)
        except GLib.Error as exc:
            if not _dialog_dismissed(exc):
                self._history_save_failed(f"Could not save history: {exc.message}")
            self._closing_prompt = False
            return
        path = gfile.get_path() if gfile else None
        if not path:
            self._history_save_failed("Could not save history: choose a folder on this computer.")
            return
        # Written synchronously, so nothing is recorded between these two lines
        revision = self.history.revision
        try:
            write_transcript(path, self.history.transcript(datetime.now()))
        except OSError as exc:
            reason = exc.strerror or str(exc)
            self._history_save_failed(f"Could not save {os.path.basename(path)}: {reason}")
            return
        self.history.mark_saved(revision)
        self._history_folder = os.path.dirname(path)
        self._history_saved_name = os.path.basename(path)
        logger.info("Saved caption history to %s", path)
        if self.control:
            self.control.set_history_error("")
        self._refresh_history()
        if quit_after:
            self._quit()

    def _history_save_failed(self, message: str) -> None:
        logger.error(message)
        # A failed save while quitting keeps the app open
        self._closing_prompt = False
        if self.control:
            self.control.set_history_error(message)

    def clear_history(self) -> None:
        """Empty the caption history once the user confirms."""
        count = self.history.sentence_count
        if not HAS_DIALOGS or self.control is None or count == 0:
            return
        detail = f"{_sentences(count)} will be removed."
        if self.history.has_unsaved:
            detail += " They have not been saved." if count > 1 else " It has not been saved."
        dialog = Gtk.AlertDialog(
            message="Clear caption history?",
            detail=detail,
            buttons=["Cancel", "Clear"],
            cancel_button=0,
            default_button=0,
            modal=True,
        )
        dialog.choose(self.control, None, self._on_clear_chosen)

    def _on_clear_chosen(self, dialog: Gtk.AlertDialog, result: Gio.AsyncResult) -> None:
        try:
            choice = dialog.choose_finish(result)
        except GLib.Error:
            return
        if choice != 1:
            return
        self.history.clear()
        self._history_saved_name = None
        if self.control:
            self.control.set_history_error("")
        self._refresh_history()

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

    def set_model(self, model: str) -> None:
        """Choose the speech model; it is used from the next Start."""
        if not model or model == self.config.model_size:
            return
        self.config.model_size = model
        self._persist_config()
        self._preload_model()

    def set_translate_korean(self, on: bool) -> None:
        """Turn Korean translation on or off; it applies from the next Start."""
        if on == self.config.translate_korean:
            return
        self.config.translate_korean = on
        self._persist_config()
        if self.control:
            self.control.set_translation_status(
                TRANSLATION_NEXT_START if on else TRANSLATION_OFF
            )
        if on:
            self._preload_translation()

    def apply_overlay_size(self, width: int, height: int) -> None:
        w, h = clamp_size(width, height)
        self.config.overlay_width = w
        self.config.overlay_height = h
        if self.overlay:
            self.overlay.set_size_px(w, h)
        self._persist_config()

    def apply_font_size(self, px: int) -> None:
        px = clamp_font_size(px)
        if px == self.config.font_size:
            return
        self.config.font_size = px
        if self.overlay:
            self.overlay.set_font_size(px)
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
        self._bilingual = None
        self.history.start_session(source.value)
        if self.overlay:
            self.overlay.set_caption_text("")
        if self.control:
            self.control.set_status("Starting…")
            self.control.set_running(True)
        if self.config.translate_korean:
            self._start_translation(session)

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

    def _start_translation(self, session: int) -> None:
        """Load the translator next to captioning; English never waits for it."""
        translator = Translator(
            on_result=lambda block_id, korean: GLib.idle_add(
                self._show_translation, session, block_id, korean
            ),
            on_error=lambda msg: GLib.idle_add(self._translation_failed, session, msg),
            on_status=lambda msg: self._on_translation_status(session, msg),
        )
        self.translator = translator
        # Blocks finished while the model loads wait in the translator's queue
        self._bilingual = BilingualCaptions(submit=translator.submit, discard=translator.discard)
        self._flush_timer = GLib.timeout_add(FLUSH_CHECK_MS, self._flush_tick, session)

        def _boot() -> None:
            try:
                translator.load_model()
                translator.start()  # does nothing if captioning stopped meanwhile
            except TranslationError as exc:
                GLib.idle_add(self._translation_failed, session, str(exc))
            except Exception as exc:  # noqa: BLE001
                GLib.idle_add(
                    self._translation_failed, session, f"Failed to start translation: {exc}"
                )

        threading.Thread(target=_boot, name="translation-boot", daemon=True).start()

    def _stop_translation(self) -> None:
        if self._flush_timer is not None:
            GLib.source_remove(self._flush_timer)
            self._flush_timer = None
        if self.translator:
            # Joining an in-flight translation can take a moment: do it off the UI
            # thread. The session number already discards its results.
            translator, self.translator = self.translator, None
            threading.Thread(target=translator.stop, name="translation-stop", daemon=True).start()

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
        self._stop_translation()
        # An unfinished sentence stays on its own, apart from the next session
        self.history.end_session()
        if self.control:
            self.control.set_running(False)
            self.control.set_status("Stopped")

    def _show_text(self, session: int, text: str, is_final: bool) -> bool:
        if session != self._session:
            return False
        if is_final:
            # Every final English phrase, in both modes; Korean never comes through here
            self.history.add_final(text)
            self._refresh_history()
        if self._bilingual is not None:
            if is_final:
                self._bilingual.add_final(text)
            else:
                self._bilingual.set_partial(text)
            self._render_bilingual()
            return False
        if is_final:
            self._finals.append(text)
            # Keep enough history to fill the overlay; older text scrolls away
            capacity = history_capacity(
                self.config.overlay_width, self.config.overlay_height, self.config.font_size
            )
            self._finals = trim_history(self._finals, capacity)
            self._partial = ""
        else:
            self._partial = text
        if self.overlay:
            self.overlay.set_caption_text(format_captions([*self._finals, self._partial]))
        return False

    def _render_bilingual(self) -> None:
        assert self._bilingual is not None
        # Keep enough two-language history to fill the overlay; older blocks scroll away
        self._bilingual.trim(
            self.config.overlay_width, self.config.overlay_height, self.config.font_size
        )
        if self.overlay:
            self.overlay.set_caption_markup(self._bilingual.markup(GLib.markup_escape_text))

    def _show_translation(self, session: int, block_id: int, korean: str) -> bool:
        if session != self._session or self._bilingual is None:
            return False
        if self._bilingual.set_translation(block_id, korean):
            self._render_bilingual()
        return False

    def _flush_tick(self, session: int) -> bool:
        if session != self._session or self._bilingual is None:
            return False
        if self._bilingual.flush_due():
            self._render_bilingual()
        return True

    def _on_translation_status(self, session: int, message: str) -> None:
        if self.control and session == self._session:
            self.control.set_translation_status(message)

    def _translation_failed(self, session: int, message: str) -> bool:
        """Show the error and keep English captioning; Korean stays off this session."""
        if session != self._session:
            return False
        logger.error(message)
        if self.translator:
            # The worker has already ended; stopping it only releases the queue
            translator, self.translator = self.translator, None
            threading.Thread(target=translator.stop, name="translation-stop", daemon=True).start()
        if self._bilingual is not None:
            self._bilingual.stop_translating()
        if self.control:
            self.control.set_translation_status(f"Error: {message}", error=True)
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
