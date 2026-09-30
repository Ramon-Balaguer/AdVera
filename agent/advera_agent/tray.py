"""Windows tray process (windows-agent-tray-autostart.md, agent-recording-notification.md).

The tray keeps the outbound connection running in a background asyncio loop. Starting the
tray or Windows never starts a recording: capture only begins on the backend's command.
"""

import asyncio
import logging
import threading

from PIL import Image, ImageDraw

from advera_agent import autostart, config
from advera_agent.diagnostics import Diagnostics
from advera_agent.remote import RemoteAgent

logger = logging.getLogger("advera.agent.tray")


def _icon_image(recording: bool = False) -> Image.Image:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((6, 6, 58, 58), fill=(59, 111, 216, 255))
    if recording:
        draw.ellipse((22, 22, 42, 42), fill=(192, 57, 43, 255))
    return image


class TrayApp:
    def __init__(self, cfg: config.AgentConfig | None = None) -> None:
        import pystray

        # An explicit configuration (for example from --backend-url) wins over the saved one.
        self.cfg = cfg
        self.pystray = pystray
        self.diagnostics = Diagnostics()
        self.loop = asyncio.new_event_loop()
        self.agent: RemoteAgent | None = None
        self.icon = pystray.Icon(
            "advera-agent", _icon_image(), "AdVera Capture Agent", self._menu()
        )

    def _menu(self):
        item = self.pystray.MenuItem
        return self.pystray.Menu(
            item(
                lambda _: f"Estado: {self.diagnostics.connection} / {self.diagnostics.session}",
                None,
                enabled=False,
            ),
            item("Configurar…", self._configure),
            item("Diagnóstico de tráfico", self._diagnostics),
            item(
                "Iniciar con Windows",
                self._toggle_autostart,
                checked=lambda _: autostart.is_enabled(),
                enabled=lambda _: config.load().configured,
            ),
            item("Salir", self._exit),
        )

    def _notify(self, message: str) -> None:
        try:
            self.icon.icon = _icon_image(recording=True)
            self.icon.notify(message, "AdVera")
        except Exception as error:  # a suppressed balloon never stops capture
            logger.warning("notification failed: %s", type(error).__name__)

    def _start_agent(self, cfg) -> None:
        if not cfg.configured:
            return
        self.agent = RemoteAgent(cfg, diagnostics=self.diagnostics, notify=self._notify)
        asyncio.run_coroutine_threadsafe(self.agent.run(), self.loop)

    def _restart_agent(self, cfg) -> None:
        if self.agent is not None:
            self.loop.call_soon_threadsafe(self.agent.shutdown)
        self._start_agent(cfg)

    def _configure(self, *_):
        from advera_agent.wizard import run_wizard

        threading.Thread(
            target=run_wizard, kwargs={"on_saved": self._restart_agent}, daemon=True
        ).start()

    def _diagnostics(self, *_):
        from advera_agent.wizard import show_diagnostics

        threading.Thread(target=show_diagnostics, args=(self.diagnostics,), daemon=True).start()

    def _toggle_autostart(self, *_):
        if autostart.is_enabled():
            autostart.disable()
        else:
            autostart.enable()

    def _exit(self, *_):
        if self.agent is not None:
            self.loop.call_soon_threadsafe(self.agent.shutdown)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.icon.stop()

    def run(self) -> None:
        threading.Thread(
            target=self.loop.run_forever, name="advera-agent-loop", daemon=True
        ).start()
        cfg = self.cfg or config.load()
        if cfg.configured:
            self._start_agent(cfg)
        else:
            self._configure()
        self.icon.run()
