"""Run the real Capture Agent against a running stack with SYNTHETIC captures.

No microphone or loopback is touched: each track produces a modulated tone in real time, so
the whole chain (agent -> backend -> browser waveforms) can be exercised without recording
anyone. Stop with Ctrl+C.

Usage: python scripts/agent_synthetic.py [--api http://localhost:18000]
"""

import argparse
import asyncio
import math
import threading
import time

import numpy as np
from agent.config import AgentConfig
from agent.remote import RemoteAgent

RATE = 16_000
FRAME = 4096


class ToneCapture:
    def __init__(self, track: str) -> None:
        self.track = track
        self.stop_event = threading.Event()

    def start(self, sink) -> None:
        frequency = 220.0 if self.track == "microphone" else 330.0

        def run() -> None:
            index = 0
            while not self.stop_event.is_set():
                t = (np.arange(FRAME) + index * FRAME) / RATE
                envelope = 0.15 + 0.12 * math.sin(index / 3.0)
                samples = envelope * np.sin(2 * np.pi * frequency * t)
                sink((samples * 32767).astype("<i2").tobytes())
                index += 1
                time.sleep(FRAME / RATE)  # real time

        threading.Thread(target=run, daemon=True).start()

    def stop(self) -> None:
        self.stop_event.set()


async def main(api: str) -> None:
    agent = RemoteAgent(
        AgentConfig(api, agent_id="agent-synthetic"),
        capture_factory=ToneCapture,
        capabilities=lambda: {
            "microphone": {"state": "available"},
            "system": {"state": "available"},
        },
    )
    await agent.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", default="http://localhost:18000")
    try:
        asyncio.run(main(parser.parse_args().api))
    except KeyboardInterrupt:
        pass
