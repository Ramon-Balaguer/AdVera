"""Configuration wizard (agent-configuration-wizard.md).

One backend URL field. Saving and Windows autostart registration are enabled only after the
backend passes the AdVera health contract. Opening the wizard never starts a recording.
"""

import threading
import tkinter as tk
from tkinter import ttk

from agent import autostart, config

MESSAGES = {
    "INVALID_URL": "URL no válida. Usa http(s)://servidor:puerto",
    "CREDENTIALS_IN_URL": "La URL no puede contener credenciales.",
    "UNREACHABLE": "No se pudo conectar con el servidor.",
    "HTTP_ERROR": "El servidor respondió con un error.",
    "INCOMPATIBLE": "El servidor no es un backend de AdVera compatible.",
}


def run_wizard(on_saved=None) -> None:
    current = config.load()
    root = tk.Tk()
    root.title("AdVera · Configuración del agente")
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=16)
    frame.grid()

    ttk.Label(frame, text="URL del backend de AdVera").grid(column=0, row=0, sticky="w")
    url = tk.StringVar(value=current.backend_url or "http://localhost:8000")
    entry = ttk.Entry(frame, textvariable=url, width=48)
    entry.grid(column=0, row=1, columnspan=3, pady=(4, 8), sticky="we")

    status = tk.StringVar(
        value="Estado: " + ("configurado" if current.configured else "sin configurar")
    )
    autostart_state = tk.StringVar()

    def refresh_autostart() -> None:
        autostart_state.set(
            "Inicio con Windows: " + ("registrado" if autostart.is_enabled() else "no registrado")
        )

    refresh_autostart()
    validated: dict[str, str] = {}

    def validate() -> None:
        save_button.state(["disabled"])
        status.set("Comprobando…")

        def work() -> None:
            try:
                normalized = config.normalize_url(url.get())
                config.check_health(normalized)
            except config.ConfigError as error:
                message = MESSAGES.get(error.code, error.code)  # bind before `error` is cleared
                root.after(0, lambda: status.set(message))
                return
            validated["url"] = normalized
            root.after(
                0, lambda: (status.set("Backend disponible ✔"), save_button.state(["!disabled"]))
            )

        threading.Thread(target=work, daemon=True).start()

    def save() -> None:
        if "url" not in validated:
            return
        current.backend_url = validated["url"]
        current.last_health = "ok"
        config.save(current)
        autostart.enable()
        refresh_autostart()
        status.set("Configuración guardada")
        if on_saved:
            on_saved(current)

    def unregister() -> None:
        autostart.disable()
        refresh_autostart()

    ttk.Button(frame, text="Comprobar", command=validate).grid(column=0, row=2, sticky="w")
    save_button = ttk.Button(frame, text="Guardar y registrar inicio", command=save)
    save_button.grid(column=1, row=2, sticky="w", padx=8)
    save_button.state(["disabled"])
    ttk.Button(frame, text="Desregistrar inicio", command=unregister).grid(
        column=2, row=2, sticky="e"
    )
    ttk.Label(frame, textvariable=status).grid(
        column=0, row=3, columnspan=3, sticky="w", pady=(8, 0)
    )
    ttk.Label(frame, textvariable=autostart_state).grid(column=0, row=4, columnspan=3, sticky="w")
    entry.focus()
    root.mainloop()


def show_diagnostics(diagnostics) -> None:
    """Live traffic view (tray-send-statistics.md); closing it leaves the agent running."""
    root = tk.Tk()
    root.title("AdVera · Diagnóstico de tráfico")
    text = tk.StringVar()
    ttk.Label(root, textvariable=text, padding=16, justify="left", font=("Consolas", 10)).grid()

    def refresh() -> None:
        snap = diagnostics.snapshot()
        lines = [
            f"Conexión: {snap['connection']}",
            f"Sesión:   {snap['session']}",
            f"Error:    {snap['last_error'] or '—'}",
            "",
        ]
        for track in ("microphone", "system"):
            stats = snap["tracks"].get(track)
            if stats is None:
                lines.append(f"{track:<11} sin actividad")
            else:
                lines.append(
                    f"{track:<11} {stats['frames']:>6} frames  {stats['bytes'] / 1024:>9.1f} KiB"
                    f"  descartados {stats['dropped']}"
                )
        text.set("\n".join(lines))
        root.after(500, refresh)

    refresh()
    root.mainloop()
