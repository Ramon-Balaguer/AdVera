"""Current-user Windows autostart (windows-agent-tray-autostart.md).

The registry value holds only the agent's startup command; no audio, tokens or meeting data.
Outside Windows every operation is a no-op.
"""

import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "AdVeraCaptureAgent"


def startup_command() -> str:
    # pythonw avoids a console window at login when available.
    executable = sys.executable
    if executable.lower().endswith("python.exe"):
        candidate = executable[: -len("python.exe")] + "pythonw.exe"
        executable = candidate
    return f'"{executable}" -m agent --tray'


def _winreg():
    if sys.platform != "win32":
        return None
    import winreg

    return winreg


def is_enabled() -> bool:
    winreg = _winreg()
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
            return True
    except OSError:
        return False


def enable() -> None:
    winreg = _winreg()
    if winreg is None:
        return
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, startup_command())


def disable() -> None:
    """Remove only the agent's own entry."""
    winreg = _winreg()
    if winreg is None:
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except FileNotFoundError:
        pass
