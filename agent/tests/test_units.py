import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import pytest

from advera_agent import autostart, config
from advera_agent.capture import rms, to_pcm16
from advera_agent.diagnostics import Diagnostics


def test_normalize_url():
    assert config.normalize_url(" http://host:8000/ ") == "http://host:8000"
    for bad in ("ftp://host", "host:8000", "http://", "http://h/?q=1"):
        with pytest.raises(config.ConfigError):
            config.normalize_url(bad)
    with pytest.raises(config.ConfigError) as error:
        config.normalize_url("http://user:secret@host")
    assert error.value.code == "CREDENTIALS_IN_URL"


def test_websocket_base_follows_scheme():
    assert config.AgentConfig("https://advera.local/").websocket_base() == "wss://advera.local"
    assert config.AgentConfig("http://localhost:8000").websocket_base() == "ws://localhost:8000"


def serve(payloads: dict[str, tuple[int, dict]]):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            status, body = payloads.get(self.path, (404, {}))
            self.send_response(status)
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def test_health_contract_is_validated():
    server, url = serve({"/api/health": (200, {"service": "advera-api", "status": "ok"})})
    try:
        assert config.check_health(url) == "ok"
    finally:
        server.shutdown()


def test_health_falls_back_to_legacy_path_and_rejects_other_services():
    server, url = serve({"/health": (200, {"service": "advera-api", "status": "ok"})})
    try:
        assert config.check_health(url) == "ok"
    finally:
        server.shutdown()
    server, url = serve({"/api/health": (200, {"status": "ok"})})
    try:
        with pytest.raises(config.ConfigError) as error:
            config.check_health(url)
        assert error.value.code == "INCOMPATIBLE"
    finally:
        server.shutdown()


def test_unreachable_backend():
    with pytest.raises(config.ConfigError) as error:
        config.check_health("http://127.0.0.1:9", timeout=0.5)
    assert error.value.code == "UNREACHABLE"


def test_config_round_trip_and_corrupt_file(tmp_path):
    path = tmp_path / "agent.json"
    saved = config.AgentConfig("http://host:8000", token=None)
    config.save(saved, path)
    assert config.load(path) == saved
    path.write_text("{corrupt")
    fresh = config.load(path)
    assert not fresh.configured and fresh.agent_id


def test_pcm_conversion_downmixes_and_clips():
    stereo = np.array([[1.0, 0.0], [2.0, 2.0], [-1.0, -1.0]], dtype=np.float32)
    samples = np.frombuffer(to_pcm16(stereo), dtype="<i2")
    assert samples.tolist() == [16383, 32767, -32767]
    assert rms(b"") == 0.0
    assert rms(to_pcm16(np.ones(100, dtype=np.float32))) == pytest.approx(1.0, abs=1e-3)


def test_autostart_is_a_no_op_off_windows(monkeypatch):
    monkeypatch.setattr(autostart, "_winreg", lambda: None)
    autostart.enable()
    autostart.disable()
    assert autostart.is_enabled() is False
    assert autostart.startup_command().endswith("-m advera_agent --tray")


def test_diagnostics_counts_per_track_and_resets_per_session():
    diagnostics = Diagnostics()
    diagnostics.reset_session("s1", ["microphone", "system"])
    diagnostics.sent("microphone", 100)
    diagnostics.sent("microphone", 100)
    diagnostics.dropped("system")
    snap = diagnostics.snapshot()
    assert snap["tracks"]["microphone"]["frames"] == 2
    assert snap["tracks"]["microphone"]["bytes"] == 200
    assert snap["tracks"]["system"]["dropped"] == 1
    diagnostics.reset_session("s2", ["microphone"])
    assert diagnostics.snapshot()["tracks"] == {
        "microphone": {"frames": 0, "bytes": 0, "dropped": 0, "last_activity": None}
    }
