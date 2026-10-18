"""Audio capture unit tests (mocked devices)."""

from __future__ import annotations

import stat
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from caption_english import audio as audio_mod
from caption_english.audio import (
    BLOCK_FRAMES,
    AudioCapture,
    CaptureError,
    CaptureSource,
    DeviceInfo,
    ParecStream,
)


class ResolveDeviceTests(unittest.TestCase):
    def test_mic_picks_first_input_when_default_invalid(self) -> None:
        fake_devices = [
            {"name": "out", "max_input_channels": 0, "hostapi": 0},
            {"name": "Mic", "max_input_channels": 1, "hostapi": 0},
        ]
        sd = mock.MagicMock()
        sd.default.device = (-1, -1)
        sd.query_devices.return_value = fake_devices

        with mock.patch.dict("sys.modules", {"sounddevice": sd}):
            info = audio_mod.resolve_input_device(CaptureSource.MIC)
            self.assertEqual(info.index, 1)
            self.assertIn("Mic", info.name)
            self.assertEqual(info.backend, "portaudio")

    def test_system_requires_monitor(self) -> None:
        with mock.patch(
            "caption_english.audio._pulse_default_monitor",
            return_value=None,
        ):
            with self.assertRaises(CaptureError):
                audio_mod.resolve_input_device(CaptureSource.SYSTEM)

    def test_system_uses_pulse_monitor_by_name(self) -> None:
        with mock.patch(
            "caption_english.audio._pulse_default_monitor",
            return_value="speakers.monitor",
        ):
            info = audio_mod.resolve_input_device(CaptureSource.SYSTEM)
        self.assertEqual(info, DeviceInfo("speakers.monitor", "speakers.monitor", "pulse"))


class AudioCaptureLifecycleTests(unittest.TestCase):
    def test_start_stop_mic_with_mock_stream(self) -> None:
        frames: list[np.ndarray] = []
        errors: list[str] = []

        capture = AudioCapture(on_audio=frames.append, on_error=errors.append)

        mock_stream = mock.MagicMock()
        with mock.patch.object(capture, "_open_stream", return_value=mock_stream):
            with mock.patch(
                "caption_english.audio.resolve_input_device",
                return_value=DeviceInfo(name="mic", index=0),
            ):
                capture.start(CaptureSource.MIC)
                self.assertTrue(capture.running)
                mock_stream.start.assert_called_once()
                capture.stop()
                self.assertFalse(capture.running)
                mock_stream.stop.assert_called()
                mock_stream.close.assert_called()
        self.assertEqual(errors, [])

    def test_source_selection_uses_chosen_path(self) -> None:
        capture = AudioCapture(on_audio=lambda _x: None)
        opened: list[DeviceInfo] = []

        def fake_resolve(source: CaptureSource) -> DeviceInfo:
            if source == CaptureSource.MIC:
                return DeviceInfo("mic", 3)
            return DeviceInfo("speakers.monitor", "speakers.monitor", "pulse")

        def fake_open(device: DeviceInfo, _slot: int) -> mock.MagicMock:
            opened.append(device)
            return mock.MagicMock()

        with mock.patch("caption_english.audio.resolve_input_device", side_effect=fake_resolve):
            with mock.patch.object(capture, "_open_stream", side_effect=fake_open):
                for source in ("mic", "system", "both"):
                    opened.clear()
                    capture.start(source)
                    self.assertEqual(capture.source, CaptureSource(source))
                    names = [d.name for d in opened]
                    expected = {
                        "mic": ["mic"],
                        "system": ["speakers.monitor"],
                        "both": ["mic", "speakers.monitor"],
                    }[source]
                    self.assertEqual(names, expected)
                    capture.stop()

    def test_start_failure_leaves_stopped(self) -> None:
        capture = AudioCapture(on_audio=lambda _x: None)
        with mock.patch(
            "caption_english.audio.resolve_input_device",
            side_effect=CaptureError("No device"),
        ):
            with self.assertRaises(CaptureError):
                capture.start(CaptureSource.MIC)
        self.assertFalse(capture.running)

    def test_stalled_stream_reports_error_once(self) -> None:
        errors: list[str] = []
        got_error = threading.Event()

        def on_error(msg: str) -> None:
            errors.append(msg)
            got_error.set()

        capture = AudioCapture(on_audio=lambda _x: None, on_error=on_error)
        with mock.patch.object(audio_mod, "STALL_SECONDS", 0.2):
            with mock.patch.object(capture, "_open_stream", return_value=mock.MagicMock()):
                with mock.patch(
                    "caption_english.audio.resolve_input_device",
                    return_value=DeviceInfo(name="mic", index=0),
                ):
                    capture.start(CaptureSource.MIC)
                    self.assertTrue(got_error.wait(3.0))
                    time.sleep(0.6)
                    capture.stop()
        self.assertEqual(len(errors), 1)
        self.assertIn("stopped delivering audio", errors[0])


class MixerTests(unittest.TestCase):
    def test_both_sources_are_summed_not_interleaved(self) -> None:
        out: list[np.ndarray] = []
        mixer = audio_mod._Mixer(out.append)  # noqa: SLF001
        mixer.feed(0, np.full(1600, 0.1, dtype=np.float32))
        self.assertEqual(out, [])  # waits for the other stream
        mixer.feed(1, np.full(1600, 0.2, dtype=np.float32))
        self.assertEqual(len(out), 1)
        np.testing.assert_allclose(out[0], 0.3, rtol=1e-5)

    def test_lagging_source_does_not_block(self) -> None:
        out: list[np.ndarray] = []
        mixer = audio_mod._Mixer(out.append)  # noqa: SLF001
        for _ in range(6):
            mixer.feed(0, np.full(1600, 0.1, dtype=np.float32))
        self.assertEqual(sum(o.size for o in out), 9600)


class ParecStreamTests(unittest.TestCase):
    def _fake_parec(self, tmp: str, body: str) -> str:
        path = Path(tmp) / "parec"
        path.write_text("#!/usr/bin/env python3\nimport sys\n" + body)
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
        return str(path)

    def test_bad_source_fails_on_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = self._fake_parec(
                tmp, "sys.stderr.write('Stream error: No such entity\\n'); sys.exit(1)\n"
            )
            stream = ParecStream("nope.monitor", lambda _b: None, lambda _m: None, False)
            with mock.patch("caption_english.audio.shutil.which", return_value=fake):
                with self.assertRaises(CaptureError) as ctx:
                    stream.start()
            self.assertIn("No such entity", str(ctx.exception))
            stream.close()

    def test_blocks_delivered_and_unexpected_end_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Two 100 ms float32 blocks, then the "device" goes away
            fake = self._fake_parec(
                tmp,
                "import time\n"
                f"sys.stdout.buffer.write(b'\\x00' * {BLOCK_FRAMES * 4 * 2}); sys.stdout.flush()\n"
                "time.sleep(0.5)\n"
                "sys.stderr.write('Connection terminated\\n'); sys.exit(1)\n",
            )
            blocks: list[np.ndarray] = []
            finished = threading.Event()
            messages: list[str] = []

            def on_finished(msg: str) -> None:
                messages.append(msg)
                finished.set()

            stream = ParecStream("x.monitor", blocks.append, on_finished, False)
            with mock.patch("caption_english.audio.shutil.which", return_value=fake):
                stream.start()
            self.assertTrue(finished.wait(5.0))
            stream.stop()
            stream.close()
        self.assertEqual([b.size for b in blocks], [BLOCK_FRAMES, BLOCK_FRAMES])
        self.assertIn("ended unexpectedly", messages[0])
        self.assertIn("Connection terminated", messages[0])

    def test_stop_does_not_report_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = self._fake_parec(tmp, "import time\ntime.sleep(30)\n")
            messages: list[str] = []
            stream = ParecStream("x.monitor", lambda _b: None, messages.append, False)
            with mock.patch("caption_english.audio.shutil.which", return_value=fake):
                stream.start()
            stream.stop()
            stream.close()
        self.assertEqual(messages, [])

    def _pulse_mock(self, attached: list[str | None]) -> mock.MagicMock:
        pulsectl = mock.MagicMock()
        pulsectl.PulseError = RuntimeError
        names = iter(attached)
        patcher = mock.patch(
            "caption_english.audio._attached_source", side_effect=lambda *_: next(names, attached[-1])
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return pulsectl

    def test_stream_redirected_to_other_device_fails_on_start(self) -> None:
        # PipeWire attaches a stream for a missing source to some other device
        pulsectl = self._pulse_mock(["other.monitor"])
        with tempfile.TemporaryDirectory() as tmp:
            fake = self._fake_parec(tmp, "import time\ntime.sleep(30)\n")
            stream = ParecStream("gone.monitor", lambda _b: None, lambda _m: None)
            with mock.patch.dict("sys.modules", {"pulsectl": pulsectl}):
                with mock.patch("caption_english.audio.shutil.which", return_value=fake):
                    with self.assertRaises(CaptureError) as ctx:
                        stream.start()
            stream.close()
        self.assertIn("not available", str(ctx.exception))

    def test_stream_moved_mid_session_reports_device_lost(self) -> None:
        pulsectl = self._pulse_mock(["x.monitor", "x.monitor", "mic.input"])
        finished = threading.Event()
        messages: list[str] = []

        def on_finished(msg: str) -> None:
            messages.append(msg)
            finished.set()

        with tempfile.TemporaryDirectory() as tmp:
            fake = self._fake_parec(tmp, "import time\ntime.sleep(30)\n")
            stream = ParecStream("x.monitor", lambda _b: None, on_finished)
            with mock.patch.object(audio_mod, "ATTACHMENT_CHECK_SECONDS", 0.05):
                with mock.patch.dict("sys.modules", {"pulsectl": pulsectl}):
                    with mock.patch("caption_english.audio.shutil.which", return_value=fake):
                        stream.start()
                    self.assertTrue(finished.wait(3.0))
            stream.stop()
            stream.close()
        self.assertEqual(len(messages), 1)
        self.assertIn("no longer available", messages[0])


if __name__ == "__main__":
    unittest.main()
