"""Native audio capture: `microphone` and `system` as independent tracks (ADR 0005, 0010).

- microphone: default input device through PortAudio/`sounddevice`
  (agent-microphone-waveform.md). SoundCard rejects some microphones' mix formats.
- system: default speaker's WASAPI loopback through `soundcard`
  (windows-wasapi-loopback-system-track.md). Stereo is downmixed to mono.

Both produce PCM s16le, mono, 16 kHz frames of FRAME_SAMPLES samples. Frames are never
written to disk or logs by the agent.
"""

import logging
import sys
import threading
from collections.abc import Callable
from typing import Literal, Protocol

import numpy as np

logger = logging.getLogger("advera.agent.capture")

Track = Literal["microphone", "system"]
SAMPLE_RATE = 16_000
FRAME_SAMPLES = 4096  # 256 ms
FrameSink = Callable[[bytes], None]


def to_pcm16(samples: np.ndarray) -> bytes:
    """Float32 [-1, 1] mono or multi-channel samples -> mono PCM s16le bytes."""
    data = np.asarray(samples, dtype=np.float32)
    if data.ndim == 2:
        data = data.mean(axis=1)  # downmix, never mix across tracks
    data = np.clip(data, -1.0, 1.0)
    return (data * 32767.0).astype("<i2").tobytes()


def rms(pcm: bytes) -> float:
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    return float(np.sqrt(np.mean(samples**2))) if samples.size else 0.0


class TrackCapture(Protocol):
    track: Track

    def start(self, sink: FrameSink) -> None: ...

    def stop(self) -> None: ...


class MicrophoneCapture:
    track: Track = "microphone"

    def __init__(self) -> None:
        self._stream = None

    def start(self, sink: FrameSink) -> None:
        import sounddevice as sd

        def callback(indata, frames, time_info, status) -> None:
            sink(bytes(indata))  # buffer objects become concrete bytes (agent-pcm-e2e-delivery-fix)

        self._stream = sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=FRAME_SAMPLES,
            callback=callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None


class SystemLoopbackCapture:
    track: Track = "system"

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._running = threading.Event()
        self.error: str | None = None

    def start(self, sink: FrameSink) -> None:
        ready = threading.Event()

        def run() -> None:
            import soundcard as sc

            try:
                _com_initialize()
                speaker = sc.default_speaker()
                loopback = sc.get_microphone(id=str(speaker.name), include_loopback=True)
                with loopback.recorder(samplerate=SAMPLE_RATE, channels=1) as recorder:
                    ready.set()
                    while self._running.is_set():
                        sink(to_pcm16(recorder.record(numframes=FRAME_SAMPLES)))
            except Exception as error:
                self.error = type(error).__name__
                logger.warning("system capture stopped: %s", self.error)
                ready.set()

        self._running.set()
        self._thread = threading.Thread(target=run, name="advera-system-capture", daemon=True)
        self._thread.start()
        ready.wait(timeout=5)
        if self.error:
            raise RuntimeError(self.error)

    def stop(self) -> None:
        self._running.clear()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None


def _com_initialize() -> None:
    """SoundCard/Media Foundation needs COM initialized in the capture thread."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.ole32.CoInitializeEx(None, 0x0)


def probe() -> dict[str, dict[str, str]]:
    """Report each track's state: available, device_unavailable, unsupported or error."""
    capabilities: dict[str, dict[str, str]] = {}
    if sys.platform != "win32":
        # Only the Windows adapters are implemented; other platforms stay honest.
        return {
            "microphone": {"state": "not_verified"},
            "system": {"state": "not_verified"},
        }
    try:
        import sounddevice as sd

        device = sd.query_devices(kind="input")
        capabilities["microphone"] = {"state": "available", "device": str(device["name"])[:80]}
    except ImportError:
        capabilities["microphone"] = {"state": "unsupported"}
    except Exception:
        capabilities["microphone"] = {"state": "device_unavailable"}
    try:
        import soundcard as sc

        speaker = sc.default_speaker()
        loopback = sc.get_microphone(id=str(speaker.name), include_loopback=True)
        capabilities["system"] = {"state": "available", "device": str(loopback.name)[:80]}
    except ImportError:
        capabilities["system"] = {"state": "unsupported"}
    except Exception:
        capabilities["system"] = {"state": "device_unavailable"}
    return capabilities


def create_capture(track: Track) -> TrackCapture:
    return MicrophoneCapture() if track == "microphone" else SystemLoopbackCapture()
