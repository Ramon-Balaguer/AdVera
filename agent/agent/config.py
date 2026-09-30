"""Agent configuration and backend health validation (agent-configuration-wizard.md).

The local configuration stores only the backend URL, a stable agent id, an optional token
and the last health status. It never stores audio, transcripts or meeting ids.
"""

import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

HEALTH_TIMEOUT_SECONDS = 5


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or os.path.join(Path.home(), ".config")
    return Path(base) / "AdVera"


def config_path() -> Path:
    return config_dir() / "agent.json"


@dataclass
class AgentConfig:
    backend_url: str = ""
    agent_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    token: str | None = None
    last_health: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.backend_url)

    def websocket_base(self) -> str:
        parsed = urllib.parse.urlsplit(self.backend_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        return urllib.parse.urlunsplit((scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


class ConfigError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def normalize_url(raw: str) -> str:
    """Validate and normalize a backend base URL. Credentials in the URL are rejected."""
    value = (raw or "").strip()
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ConfigError("INVALID_URL")
    if parsed.username or parsed.password:
        raise ConfigError("CREDENTIALS_IN_URL")
    if parsed.query or parsed.fragment:
        raise ConfigError("INVALID_URL")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def check_health(backend_url: str, timeout: float = HEALTH_TIMEOUT_SECONDS) -> str:
    """Validate the AdVera health contract at /api/health, falling back to /health.

    Returns "ok" or raises ConfigError with UNREACHABLE, HTTP_ERROR or INCOMPATIBLE.
    """
    base = normalize_url(backend_url)
    # Report the most informative failure: a wrong service beats an HTTP error beats no answer.
    priority = {"UNREACHABLE": 0, "HTTP_ERROR": 1, "INCOMPATIBLE": 2}
    worst = "UNREACHABLE"
    for path in ("/api/health", "/health"):
        try:
            with urllib.request.urlopen(base + path, timeout=timeout) as response:
                payload = json.loads(response.read() or b"{}")
        except urllib.error.HTTPError:
            outcome = "HTTP_ERROR"
        except (urllib.error.URLError, TimeoutError, OSError):
            outcome = "UNREACHABLE"
        except ValueError:
            outcome = "INCOMPATIBLE"
        else:
            if payload.get("service") == "advera-api" and payload.get("status") == "ok":
                return "ok"
            outcome = "INCOMPATIBLE"
        worst = max(worst, outcome, key=priority.__getitem__)
    raise ConfigError(worst)


def load(path: Path | None = None) -> AgentConfig:
    """Load the configuration; a corrupt file is ignored and can be replaced by the wizard."""
    path = path or config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return AgentConfig(
            **{key: data[key] for key in AgentConfig.__dataclass_fields__ if key in data}
        )
    except (OSError, ValueError, TypeError):
        return AgentConfig()


def save(config: AgentConfig, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".agent-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(asdict(config), handle, indent=2)
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
