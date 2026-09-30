"""Synthetic capture doubles: no audio device, no real audio."""

import threading
import time

FRAME = b"\x10\x00" * 4096


class FakeCapture:
    def __init__(self, track: str, frames: int = 5, fail: bool = False) -> None:
        self.track = track
        self.frames = frames
        self.fail = fail
        self.stopped = threading.Event()

    def start(self, sink) -> None:
        if self.fail:
            raise RuntimeError("DEVICE_FAILED")

        def run() -> None:
            for _ in range(self.frames):
                if self.stopped.is_set():
                    return
                sink(FRAME)
                time.sleep(0.01)

        threading.Thread(target=run, daemon=True).start()

    def stop(self) -> None:
        self.stopped.set()


def available() -> dict:
    return {"microphone": {"state": "available"}, "system": {"state": "available"}}
