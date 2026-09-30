"""Real-device Capture Agent smoke against a running AdVera stack (Windows).

WARNING: this records the default microphone and the system playback (loopback) for the
requested seconds. Run it only with consent. By default the meeting and its audio are deleted
afterwards (--keep keeps them); no audio is written anywhere else.

Optionally `--play FILE.wav` plays a synthetic smoke file on the default speaker during the
capture, so the system track carries speech (e.g. data/smoke/ca-two-speakers.wav).

Usage: python scripts/agent_smoke.py [--api http://localhost:18000] [--seconds 6] [--play F] [--keep]
"""

import argparse
import asyncio
import json
import sys
import threading
import wave

import httpx
import websockets
from agent.config import AgentConfig
from agent.remote import RemoteAgent


def play(path: str) -> None:
    import numpy as np
    import soundcard as sc

    with wave.open(path, "rb") as handle:
        rate = handle.getframerate()
        samples = np.frombuffer(handle.readframes(handle.getnframes()), dtype="<i2")
    sc.default_speaker().play(samples.astype(np.float32) / 32768.0, samplerate=rate)


async def next_event(ws, kind: str, timeout: float = 15) -> dict:
    while True:
        event = json.loads(await asyncio.wait_for(ws.recv(), timeout))
        if event["type"] == kind:
            return event


async def main(args) -> int:
    async with httpx.AsyncClient(base_url=args.api, timeout=30) as http:
        meeting = (await http.post("/api/meetings", json={"title": "Agent device smoke"})).json()
        agent = RemoteAgent(AgentConfig(args.api, agent_id="agent-smoke"))
        task = asyncio.create_task(agent.run())
        for _ in range(100):
            capabilities = (await http.get("/api/capture-agent/capabilities")).json()
            if capabilities["available"]:
                break
            await asyncio.sleep(0.1)
        print("capabilities:", capabilities["tracks"])
        tracks = [
            name for name, info in capabilities["tracks"].items() if info["state"] == "available"
        ]

        ws_url = args.api.replace("http", "ws", 1) + f"/ws/meetings/{meeting['id']}/audio"
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({"type": "start", "source": "agent"}))
            await next_event(ws, "audio.ready")
            response = await http.post(
                "/api/capture-agent/sessions", json={"meeting_id": meeting["id"], "tracks": tracks}
            )
            print("capture session:", response.status_code, response.json().get("state"))
            if response.status_code != 201:
                return 1
            if args.play:
                threading.Thread(target=play, args=(args.play,), daemon=True).start()
            await asyncio.sleep(args.seconds)
            await ws.send(json.dumps({"type": "stop"}))
            stopped = await next_event(ws, "audio.stopped")
            outcome = await asyncio.wait_for(ws.recv(), 15)
        print("tracks:", json.dumps(stopped["tracks"]))
        print("after stop:", outcome)
        print("dropped frames:", agent.diagnostics.snapshot()["tracks"])
        agent.shutdown()
        await asyncio.wait_for(task, 10)
        if not args.keep:
            await http.delete(f"/api/meetings/{meeting['id']}")
            print("meeting and audio deleted")
        else:
            print("meeting kept:", meeting["id"])
        ok = all(stopped["tracks"].get(track, {}).get("bytes", 0) > 0 for track in tracks)
        return 0 if ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", default="http://localhost:18000")
    parser.add_argument("--seconds", type=float, default=6)
    parser.add_argument("--play")
    parser.add_argument("--keep", action="store_true")
    sys.exit(asyncio.run(main(parser.parse_args())))
