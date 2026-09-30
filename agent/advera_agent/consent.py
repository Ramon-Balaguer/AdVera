"""Local consent before a remote start (QA/Security review, ADR 0019).

The backend can ask the agent to record from anywhere the API is reachable, so the agent asks
the person at the machine first. A dialog that nobody answers counts as a refusal. Without a
way to ask (headless console run) the start is refused unless the operator opted in with
`consent = "always"` in the configuration or `--allow-remote-recording` for that run.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger("advera.agent.consent")

ASK_TIMEOUT_SECONDS = 30
TRACK_LABELS = {"microphone": "el micrófono", "system": "el audio del sistema"}

# Called with the requested tracks; returns True when the person accepts.
Confirm = Callable[[list[str]], Awaitable[bool]]


def describe(tracks: list[str]) -> str:
    return " y ".join(TRACK_LABELS.get(track, track) for track in tracks)


def ask_with_dialog(tracks: list[str]) -> bool:
    """Blocking Tk dialog that closes itself (= refusal) after ASK_TIMEOUT_SECONDS."""
    import tkinter
    from tkinter import ttk

    answer = {"value": False}
    root = tkinter.Tk()
    root.title("AdVera")
    root.attributes("-topmost", True)
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=16)
    frame.pack()
    ttk.Label(
        frame,
        text=f"AdVera quiere grabar {describe(tracks)} de este equipo.\n¿Permitirlo?",
        justify="left",
    ).pack(anchor="w")
    buttons = ttk.Frame(frame)
    buttons.pack(anchor="e", pady=(12, 0))

    def choose(value: bool) -> None:
        answer["value"] = value
        root.destroy()

    ttk.Button(buttons, text="Permitir", command=lambda: choose(True)).pack(side="left", padx=4)
    deny = ttk.Button(buttons, text="Denegar", command=lambda: choose(False))
    deny.pack(side="left", padx=4)
    deny.focus_set()
    root.protocol("WM_DELETE_WINDOW", lambda: choose(False))
    root.after(ASK_TIMEOUT_SECONDS * 1000, lambda: choose(False))
    root.mainloop()
    return answer["value"]


async def ask_in_thread(tracks: list[str]) -> bool:
    try:
        return await asyncio.to_thread(ask_with_dialog, tracks)
    except Exception as error:  # no display, Tk missing…: refuse rather than record
        logger.warning("consent dialog unavailable: %s", type(error).__name__)
        return False
