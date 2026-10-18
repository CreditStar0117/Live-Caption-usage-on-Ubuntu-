"""Audio capture for microphone, system playback monitor, or both."""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHANNELS = 1
BLOCK_MS = 100
BLOCK_FRAMES = SAMPLE_RATE * BLOCK_MS // 1000
# A running stream that delivers nothing for this long is treated as disconnected
STALL_SECONDS = 3.0
# How long a freshly started parec may take to fail on a bad source
PAREC_STARTUP_CHECK_SECONDS = 0.3
# PipeWire/Pulse silently move a stream elsewhere (e.g. to the mic) when its
# source is missing or removed, so parec streams verify where they are attached.
ATTACHMENT_WAIT_SECONDS = 1.0
ATTACHMENT_CHECK_SECONDS = 1.0

AudioCallback = Callable[[np.ndarray], None]
ErrorCallback = Callable[[str], None]


class CaptureSource(str, Enum):
    MIC = "mic"
    SYSTEM = "system"
    BOTH = "both"


class CaptureError(Exception):
    """Raised when audio capture cannot start or fails."""


@dataclass
class DeviceInfo:
    name: str
    index: int | str | None
    # "portaudio" (sounddevice) or "pulse" (parec, addressed by source name)
    backend: str = "portaudio"


def _pulse_default_monitor() -> str | None:
    try:
        import pulsectl
    except ImportError as exc:
        raise CaptureError("pulsectl is required for system audio capture") from exc

    try:
        with pulsectl.Pulse("caption-english") as pulse:
            server = pulse.server_info()
            sink_name = server.default_sink_name
            if not sink_name:
                return None
            # Prefer "<sink>.monitor" naming used by Pulse/PipeWire
            monitor = f"{sink_name}.monitor"
            sources = pulse.source_list()
            for src in sources:
                if src.name == monitor:
                    return monitor
                if getattr(src, "monitor_of_sink_name", None) == sink_name:
                    return src.name
            # Fallback: any monitor source
            for src in sources:
                if ".monitor" in (src.name or ""):
                    return src.name
    except pulsectl.PulseError as exc:
        raise CaptureError(f"Cannot connect to PipeWire/PulseAudio: {exc}") from exc
    return None


def _import_sounddevice():
    try:
        import sounddevice as sd
    except OSError as exc:
        raise CaptureError(
            "PortAudio library not found. Install libportaudio2 "
            "(sudo apt install libportaudio2) or use scripts/run.sh "
            "which loads the bundled local library."
        ) from exc
    return sd


def resolve_input_device(source: CaptureSource) -> DeviceInfo:
    """Resolve a capture device for the requested source."""
    if source == CaptureSource.MIC:
        sd = _import_sounddevice()
        try:
            default = sd.default.device
            # sounddevice may return (input, output), _InputOutputPair, or int
            idx: int | None
            try:
                idx = int(default[0])  # type: ignore[index]
            except (TypeError, ValueError, IndexError, KeyError):
                try:
                    idx = int(default)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    idx = None
            if idx is None or idx < 0:
                for i, dev in enumerate(sd.query_devices()):
                    if int(dev.get("max_input_channels", 0)) >= 1:
                        return DeviceInfo(name=str(dev.get("name")), index=i)
                raise CaptureError("No microphone input device is available")
            dev = sd.query_devices(idx)
            return DeviceInfo(name=str(dev.get("name")), index=idx)
        except CaptureError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise CaptureError(f"Cannot open microphone: {exc}") from exc

    if source in (CaptureSource.SYSTEM, CaptureSource.BOTH):
        monitor = _pulse_default_monitor()
        if not monitor:
            raise CaptureError(
                "System playback monitor not found. Ensure PipeWire/PulseAudio "
                "is running and a default sink exists."
            )
        # Ubuntu's PortAudio is built with ALSA only and cannot open Pulse
        # sources by name, so the monitor is recorded with parec instead.
        return DeviceInfo(name=monitor, index=monitor, backend="pulse")

    raise CaptureError(f"Unknown capture source: {source}")


def _attached_source(pulse: Any, pid: int) -> str | None:
    """Name of the source the recording stream of process *pid* is attached to."""
    for output in pulse.source_output_list():
        if output.proplist.get("application.process.id") == str(pid):
            return pulse.source_info(output.source).name
    return None


class ParecStream:
    """Record a PipeWire/PulseAudio source through ``parec`` (sounddevice-like API)."""

    def __init__(
        self,
        source_name: str,
        on_block: AudioCallback,
        on_finished: ErrorCallback,
        check_attachment: bool = True,
    ) -> None:
        self._source_name = source_name
        self._on_block = on_block
        self._on_finished = on_finished
        self._check_attachment = check_attachment
        self._proc: subprocess.Popen[bytes] | None = None
        self._thread: threading.Thread | None = None
        self._watch_stop = threading.Event()
        self._stopping = False
        self._lost = False

    def start(self) -> None:
        parec = shutil.which("parec")
        if parec is None:
            raise CaptureError(
                "parec not found. Install it with: sudo apt install pulseaudio-utils"
            )
        self._proc = subprocess.Popen(
            [
                parec,
                f"--device={self._source_name}",
                "--format=float32le",
                f"--rate={SAMPLE_RATE}",
                f"--channels={CHANNELS}",
                "--raw",
                f"--latency-msec={BLOCK_MS}",
                "--client-name=caption-english",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            self._proc.wait(timeout=PAREC_STARTUP_CHECK_SECONDS)
        except subprocess.TimeoutExpired:
            pass  # still running: the source opened
        else:
            detail = self._read_stderr() or f"exit code {self._proc.returncode}"
            raise CaptureError(f"Cannot record '{self._source_name}': {detail}")
        if self._check_attachment:
            self._verify_attachment_on_start()
        self._thread = threading.Thread(target=self._reader, name="parec-reader", daemon=True)
        self._thread.start()
        if self._check_attachment:
            threading.Thread(
                target=self._watch_attachment, name="parec-watch", daemon=True
            ).start()

    def _verify_attachment_on_start(self) -> None:
        import pulsectl

        assert self._proc is not None
        deadline = time.monotonic() + ATTACHMENT_WAIT_SECONDS
        with pulsectl.Pulse("caption-english-check") as pulse:
            while time.monotonic() < deadline:
                attached = _attached_source(pulse, self._proc.pid)
                if attached is None:
                    time.sleep(0.1)  # stream not registered yet
                    continue
                if attached != self._source_name:
                    self.stop()
                    raise CaptureError(
                        f"Cannot record '{self._source_name}': the audio device is not available"
                    )
                return

    def _watch_attachment(self) -> None:
        import pulsectl

        proc = self._proc
        assert proc is not None
        try:
            with pulsectl.Pulse("caption-english-watch") as pulse:
                while not self._watch_stop.wait(ATTACHMENT_CHECK_SECONDS):
                    attached = _attached_source(pulse, proc.pid)
                    if attached is not None and attached != self._source_name:
                        self._report_lost(
                            f"Audio device '{self._source_name}' is no longer available"
                        )
                        return
        except pulsectl.PulseError as exc:
            if not self._stopping:
                self._report_lost(f"Lost connection to PipeWire/PulseAudio: {exc}")

    def _report_lost(self, message: str) -> None:
        # Stop forwarding audio that now comes from some other device
        self._lost = True
        if not self._stopping:
            self._on_finished(message)

    def _read_stderr(self) -> str:
        if self._proc is None or self._proc.stderr is None:
            return ""
        return self._proc.stderr.read().decode(errors="replace").strip()

    def _reader(self) -> None:
        proc = self._proc
        assert proc is not None and proc.stdout is not None
        block_bytes = BLOCK_FRAMES * 4
        while True:
            data = proc.stdout.read(block_bytes)
            if len(data) < block_bytes:
                break
            if not self._lost:
                self._on_block(np.frombuffer(data, dtype=np.float32).copy())
        if not self._stopping and not self._lost:
            proc.wait()
            detail = self._read_stderr() or f"exit code {proc.returncode}"
            self._on_finished(f"System audio stream ended unexpectedly ({detail})")

    def stop(self) -> None:
        self._stopping = True
        self._watch_stop.set()
        proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=2.0)
        self._thread = None

    def close(self) -> None:
        if self._proc is not None:
            for pipe in (self._proc.stdout, self._proc.stderr):
                if pipe is not None:
                    pipe.close()
        self._proc = None


class _Mixer:
    """Sum two capture streams block-by-block into one mono signal."""

    # If one input lags this far behind, pass the other through alone
    MAX_BACKLOG = SAMPLE_RATE // 2

    def __init__(self, on_audio: AudioCallback) -> None:
        self._on_audio = on_audio
        self._lock = threading.Lock()
        self._pending = [np.zeros(0, dtype=np.float32), np.zeros(0, dtype=np.float32)]

    def feed(self, slot: int, samples: np.ndarray) -> None:
        with self._lock:
            self._pending[slot] = np.concatenate([self._pending[slot], samples])
            a, b = self._pending
            n = min(a.size, b.size)
            if n:
                out = np.clip(a[:n] + b[:n], -1.0, 1.0)
                self._pending = [a[n:], b[n:]]
            elif self._pending[slot].size > self.MAX_BACKLOG:
                out = self._pending[slot]
                self._pending[slot] = np.zeros(0, dtype=np.float32)
            else:
                return
        self._on_audio(out)


class AudioCapture:
    """Capture mono float32 audio at 16 kHz and push frames to a callback."""

    def __init__(
        self,
        on_audio: AudioCallback,
        on_error: ErrorCallback | None = None,
    ) -> None:
        self._on_audio = on_audio
        self._on_error = on_error
        self._stream: Any = None
        self._stream_b: Any = None
        self._lock = threading.Lock()
        self._running = False
        self._source: CaptureSource | None = None
        self._mixer: _Mixer | None = None
        self._last_frame: list[float] = []
        self._watchdog_stop = threading.Event()
        self._failed = False

    @property
    def running(self) -> bool:
        return self._running

    @property
    def source(self) -> CaptureSource | None:
        return self._source

    def start(self, source: CaptureSource | str = CaptureSource.SYSTEM) -> None:
        if isinstance(source, str):
            source = CaptureSource(source)
        with self._lock:
            if self._running:
                self._stop_unlocked()
            self._failed = False
            try:
                if source == CaptureSource.BOTH:
                    self._start_both_unlocked()
                else:
                    device = resolve_input_device(source)
                    self._last_frame = [time.monotonic()]
                    self._stream = self._open_stream(device, 0)
                    self._stream.start()
                self._source = source
                self._running = True
                self._start_watchdog()
                logger.info("Audio capture started (%s)", source.value)
            except CaptureError:
                self._stop_unlocked()
                raise
            except Exception as exc:  # noqa: BLE001
                self._stop_unlocked()
                msg = f"Failed to start audio capture: {exc}"
                raise CaptureError(msg) from exc

    def stop(self) -> None:
        with self._lock:
            self._stop_unlocked()

    def _stop_unlocked(self) -> None:
        self._running = False
        self._watchdog_stop.set()
        for attr in ("_stream", "_stream_b"):
            stream = getattr(self, attr, None)
            if stream is not None:
                try:
                    stream.stop()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    stream.close()
                except Exception:  # noqa: BLE001
                    pass
                setattr(self, attr, None)
        was_running = self._source is not None
        self._source = None
        self._mixer = None
        if was_running:
            logger.info("Audio capture stopped")

    def _start_both_unlocked(self) -> None:
        mic = resolve_input_device(CaptureSource.MIC)
        sys_dev = resolve_input_device(CaptureSource.SYSTEM)
        self._mixer = _Mixer(self._on_audio)
        self._last_frame = [time.monotonic(), time.monotonic()]
        self._stream = self._open_stream(mic, 0)
        self._stream_b = self._open_stream(sys_dev, 1)
        self._stream.start()
        self._stream_b.start()

    def _deliver(self, slot: int, samples: np.ndarray) -> None:
        """Route one block from stream *slot* to the consumer (runs on audio threads)."""
        try:
            mono = np.asarray(samples, dtype=np.float32)
            if mono.ndim > 1:
                mono = mono.mean(axis=1)
            self._last_frame[slot] = time.monotonic()
            mixer = self._mixer
            if mixer is not None:
                mixer.feed(slot, mono.copy())
            else:
                self._on_audio(mono.copy())
        except Exception as exc:  # noqa: BLE001
            self._emit_error(f"Audio processing error: {exc}")

    def _on_stream_finished(self, message: str) -> None:
        if self._running:
            self._emit_error(message)

    def _open_stream(self, device: DeviceInfo, slot: int) -> Any:
        if device.backend == "pulse":
            return ParecStream(
                str(device.index),
                on_block=lambda block: self._deliver(slot, block),
                on_finished=self._on_stream_finished,
            )

        sd = _import_sounddevice()

        def callback(indata, frames, time_info, status):  # noqa: ANN001, ARG001
            if status:
                # PortAudio only reports over/underflow here; neither is fatal
                logger.debug("Audio status: %s", status)
            self._deliver(slot, indata)

        try:
            return sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="float32",
                blocksize=BLOCK_FRAMES,
                device=device.index,
                callback=callback,
                finished_callback=lambda: self._on_stream_finished(
                    f"Audio device '{device.name}' stopped unexpectedly"
                ),
            )
        except Exception as exc:  # noqa: BLE001
            raise CaptureError(
                f"Cannot open audio device '{device.name}': {exc}"
            ) from exc

    def _start_watchdog(self) -> None:
        self._watchdog_stop = threading.Event()
        threading.Thread(
            target=self._watchdog,
            args=(self._watchdog_stop,),
            name="audio-watchdog",
            daemon=True,
        ).start()

    def _watchdog(self, stop_event: threading.Event) -> None:
        while not stop_event.wait(0.5):
            now = time.monotonic()
            if any(now - last > STALL_SECONDS for last in self._last_frame):
                self._emit_error(
                    "Audio device stopped delivering audio (was it disconnected?)"
                )
                return

    def _emit_error(self, message: str) -> None:
        # Report once per session; the owner stops capture from its own thread
        if self._failed:
            return
        self._failed = True
        logger.error(message)
        if self._on_error:
            try:
                self._on_error(message)
            except Exception:  # noqa: BLE001
                logger.exception("Error callback failed")
