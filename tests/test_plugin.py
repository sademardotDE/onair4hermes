"""Tests für das onair4hermes Hermes-Plugin.

Laufen ohne laufenden OnAir-Server: die API-Tests benutzen einen lokalen
Mock-HTTP-Server, die Offline-Tests einen geschlossenen Port.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
import threading
import urllib.parse
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

# Paket im Quellverzeichnis finden: das Repo-Wurzelverzeichnis *ist* das Paket.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from onair4hermes import OnAirClient, OnAirError, __version__, create_plugin, register  # noqa: E402
from onair4hermes import _TOOL_SCHEMAS  # noqa: E402
from onair4hermes.hermes_plugin import (  # noqa: E402
    _cli_setup,
    plugin_from_ctx,
    register_cli,
)

_INVALID = object()
CLOSED_URL = "http://127.0.0.1:9"


# --------------------------------------------------------------------------- #
# Mock-OnAir-Server
# --------------------------------------------------------------------------- #


class _MockHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _fmt: str, *args: Any) -> None:  # noqa: D401 - leise
        return

    # -- helpers ---------------------------------------------------------
    def _send(self, status: int, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> Any:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _INVALID

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        self._dispatch("POST")

    def _dispatch(self, method: str) -> None:
        server: Any = self.server
        split = urllib.parse.urlsplit(self.path)
        body = self._read_body() if method == "POST" else None
        server.requests.append(
            {
                "method": method,
                "path": split.path,
                "query": urllib.parse.parse_qs(split.query),
                "body": body,
                "auth": self.headers.get("Authorization", ""),
                "content_type": self.headers.get("Content-Type", ""),
            }
        )

        if server.token and self.headers.get("Authorization") != f"Bearer {server.token}":
            return self._send(401, {"error": "unauthorized"})
        if method == "POST" and body is _INVALID:
            return self._send(400, {"error": "invalid json"})
        if method == "POST" and "application/json" not in (self.headers.get("Content-Type") or ""):
            return self._send(400, {"error": "content type required"})

        route = (method, split.path)
        if route == ("GET", "/api/v1"):
            return self._send(200, {"name": "OnAir remote API", "version": 1})
        if route == ("GET", "/api/v1/status"):
            return self._send(200, dict(server.status_payload))
        if route == ("GET", "/api/v1/devices"):
            return self._send(200, list(server.devices))
        if route == ("GET", "/api/v1/modes"):
            return self._send(200, list(server.modes))
        if route == ("GET", "/api/v1/telemetry"):
            return self._send(200, dict(server.telemetry_payload))
        if route == ("GET", "/api/v1/spectrum"):
            bins = int((urllib.parse.parse_qs(split.query).get("bins") or ["64"])[0])
            payload = dict(server.spectrum_payload)
            payload["bins"] = bins
            payload["dbfs"] = [-80.0] * bins
            return self._send(200, payload)

        if route == ("POST", "/api/v1/start"):
            server.status_payload["running"] = True
            return self._send(200, {"ok": True})
        if route == ("POST", "/api/v1/stop"):
            server.status_payload["running"] = False
            return self._send(200, {"ok": True})
        if route == ("POST", "/api/v1/mode"):
            data = body or {}
            server.status_payload["family"] = data.get("family")
            server.status_payload["mode"] = str(data.get("family"))
            return self._send(200, {"ok": True})
        if route == ("POST", "/api/v1/frequency"):
            data = body or {}
            if "hz" in data:
                server.status_payload["frequencyHz"] = data["hz"]
            elif "mhz" in data:
                server.status_payload["frequencyHz"] = int(float(data["mhz"]) * 1_000_000)
            return self._send(200, {"ok": True})

        return self._send(404, {"error": f"unknown endpoint {split.path}"})


class MockOnAir:
    """Kontextmanager: lokaler Mock der OnAir Remote-Control-API."""

    def __init__(self, token: str = "") -> None:
        self.token = token
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def __enter__(self) -> "MockOnAir":
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _MockHandler)
        self.httpd.token = self.token  # type: ignore[attr-defined]
        self.httpd.requests = []  # type: ignore[attr-defined]
        self.httpd.status_payload = {  # type: ignore[attr-defined]
            "running": True,
            "wanted": True,
            "deviceIndex": 0,
            "device": "Mock Radio",
            "family": 7,
            "mode": "FM broadcast",
            "frequencyHz": 100_000_000,
        }
        self.httpd.devices = [  # type: ignore[attr-defined]
            {
                "index": 0,
                "name": "Mock Radio",
                "kind": "synthetic",
                "board": "",
                "serial": "",
                "gainMinDb": 0,
                "gainMaxDb": 0,
                "selected": True,
            }
        ]
        self.httpd.modes = [  # type: ignore[attr-defined]
            {"id": "fm", "family": 7, "name": "FM broadcast", "sub": None}
        ]
        self.httpd.telemetry_payload = {  # type: ignore[attr-defined]
            "running": True,
            "locked": True,
            "snrDb": 42.5,
            "quality": {"percent": 100, "label": "excellent"},
            "details": {"psName": "MOCK FM", "radioText": "test"},
        }
        self.httpd.spectrum_payload = {  # type: ignore[attr-defined]
            "centerHz": 100_000_000,
            "sampleRateHz": 4_000_000,
            "dbfs": [-80.0] * 64,
        }
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        assert self.httpd is not None
        self.httpd.shutdown()
        self.httpd.server_close()
        if self.thread is not None:
            self.thread.join(timeout=2)

    @property
    def base_url(self) -> str:
        assert self.httpd is not None
        host, port = self.httpd.server_address[:2]
        return f"http://{host}:{port}"

    @property
    def requests(self) -> list[dict[str, Any]]:
        assert self.httpd is not None
        return self.httpd.requests  # type: ignore[attr-defined]

    @property
    def status_payload(self) -> dict[str, Any]:
        assert self.httpd is not None
        return self.httpd.status_payload  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# Recording-Plugin-Kontext
# --------------------------------------------------------------------------- #


class RecordingCtx:
    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = dict(settings or {})
        self.tools: dict[str, dict[str, Any]] = {}
        self.commands: dict[str, dict[str, Any]] = {}

    def get_config(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    def register_tool(self, name: str, **kwargs: Any) -> None:
        self.tools[name] = kwargs

    def register_cli_command(self, **kwargs: Any) -> None:
        self.commands[kwargs["name"]] = kwargs


# --------------------------------------------------------------------------- #
# Client-Tests
# --------------------------------------------------------------------------- #


def test_version_consistent() -> None:
    manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "onair4hermes"
    assert manifest["version"] == __version__
    assert "onair" in manifest["extensions"]["com.nousresearch.hermes"]["commands"]
    print("PASS test_version_consistent")


def test_manifest_declares_registered_tools() -> None:
    text = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
    for tool in _TOOL_SCHEMAS:
        assert f"- {tool}" in text, f"{tool} fehlt in plugin.yaml"
    assert "- onair" in text
    print("PASS test_manifest_declares_registered_tools")


def test_client_offline() -> None:
    client = OnAirClient(Path("/tmp/onair-does-not-exist.json"), base_url=CLOSED_URL, timeout=0.5)
    status = client.status()
    assert status["source"] == "offline"
    assert status["running"] is False
    assert "error" in status
    assert client.list_devices() == []
    assert client.list_modes() == []
    print("PASS test_client_offline")


def test_client_reads_live_mock() -> None:
    with MockOnAir() as mock:
        client = OnAirClient(None, base_url=mock.base_url)
        status = client.status()
        assert status["source"] == "onair-api"
        assert status["device"] == "Mock Radio"
        assert status["frequencyHz"] == 100_000_000

        devices = client.list_devices()
        assert len(devices) == 1
        assert devices[0]["id"] == "onair-device-0"
        assert devices[0]["source"] == "onair-api"
        assert client.get_device("onair-device-0") is not None
        assert client.get_device("nope") is None

        modes = client.list_modes()
        assert modes == [
            {"id": "fm", "name": "FM broadcast", "family": 7, "sub": None, "source": "onair-api"}
        ]

        telemetry = client.telemetry()
        assert telemetry["locked"] is True

        spectrum = client.spectrum(32)
        assert len(spectrum["dbfs"]) == 32
        assert mock.requests[-1]["query"]["bins"] == ["32"]
    print("PASS test_client_reads_live_mock")


def test_client_token() -> None:
    with MockOnAir(token="geheim") as mock:
        without = OnAirClient(None, base_url=mock.base_url, timeout=1.0)
        try:
            without.status()
        except OnAirError as exc:  # status() fängt das ab, direkter Request nicht
            raise AssertionError("status() darf nicht werfen") from exc
        assert without.status()["source"] == "offline"
        assert without.status()["error"].startswith("OnAir API GET /api/v1/status: HTTP 401")

        with_token = OnAirClient(None, base_url=mock.base_url, token="geheim")
        assert with_token.status()["source"] == "onair-api"
        assert mock.requests[-1]["auth"] == "Bearer geheim"
    print("PASS test_client_token")


def test_client_controls() -> None:
    with MockOnAir() as mock:
        client = OnAirClient(None, base_url=mock.base_url)
        assert client.start(2) is True
        assert mock.requests[-1]["body"] == {"device": 2}

        assert client.stop() is True
        assert mock.requests[-1]["body"] == {}

        assert client.set_mode(7, "ft8") is True
        assert mock.requests[-1]["body"] == {"family": 7, "sub": "ft8"}

        # Modus-Name wird über /modes auf die Familien-ID abgebildet
        assert client.set_mode("fm") is True
        assert mock.requests[-1]["body"] == {"family": 7}

        assert client.set_frequency(mhz=100.0) is True
        assert mock.requests[-1]["body"] == {"mhz": 100.0}

        assert client.set_frequency(hz=100_000_000) is True
        assert mock.requests[-1]["body"] == {"hz": 100_000_000}

        for bad in (
            lambda: client.set_frequency(),
            lambda: client.set_frequency(hz=1, mhz=2),
            lambda: client.set_frequency(hz=-1),
            lambda: client.spectrum(1),
        ):
            try:
                bad()
            except ValueError:
                pass
            else:
                raise AssertionError("ValueError erwartet")
    print("PASS test_client_controls")


def test_config_device_fallback() -> None:
    payload = {"devices": [{"id": "rig1", "name": "Rig", "host": "127.0.0.1", "port": 8765}]}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump(payload, handle)
        path = Path(handle.name)
    try:
        client = OnAirClient(path, base_url=CLOSED_URL, timeout=0.5)
        devices = client.list_devices()
        assert [d["id"] for d in devices] == ["rig1"]
        assert devices[0]["source"] == "config"
    finally:
        path.unlink(missing_ok=True)
    print("PASS test_config_device_fallback")


# --------------------------------------------------------------------------- #
# Tool-Registrierung / Dispatch
# --------------------------------------------------------------------------- #


def test_register_tools_and_cli() -> None:
    with MockOnAir() as mock:
        ctx = RecordingCtx({"base_url": mock.base_url})
        register(ctx)
        assert set(ctx.tools) == set(_TOOL_SCHEMAS)
        assert "onair" in ctx.commands
        assert ctx.commands["onair"]["help"]
    print("PASS test_register_tools_and_cli")


def test_tool_handlers_dispatch() -> None:
    with MockOnAir() as mock:
        ctx = RecordingCtx({"base_url": mock.base_url})
        register(ctx)

        def call(name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
            # Genau wie der Hermes-Dispatcher: handler(args, **kwargs)
            result = ctx.tools[name]["handler"](args or {}, task_id="test")
            assert isinstance(result, str), f"{name} muss JSON-String liefern, nicht {type(result)}"
            return json.loads(result)

        assert call("onair_status")["ok"] is True
        assert call("onair_status")["onair"]["device"] == "Mock Radio"
        assert call("onair_list_devices")["count"] == 1
        assert call("onair_list_modes")["count"] == 1
        assert call("onair_telemetry")["telemetry"]["locked"] is True
        assert call("onair_spectrum", {"bins": 32})["spectrum"]["bins"] == 32
        assert call("onair_start", {"device_index": 0})["started"] is True
        assert call("onair_stop")["stopped"] is True
        assert call("onair_set_mode", {"family": "7", "sub": "ft8"})["family"] == 7
        assert call("onair_set_frequency", {"mhz": 100})["frequency_set"] is True
        assert call("onair_set_frequency", {})["ok"] is False
    print("PASS test_tool_handlers_dispatch")


def test_tool_handlers_offline() -> None:
    ctx = RecordingCtx({"base_url": CLOSED_URL, "timeout": 0.5})
    register(ctx)
    result = json.loads(ctx.tools["onair_telemetry"]["handler"]({}, task_id="test"))
    assert result["ok"] is False
    assert "nicht erreichbar" in result["error"]
    print("PASS test_tool_handlers_offline")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _build_cli(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    top = parser.add_subparsers(dest="command")
    onair_parser = top.add_parser("onair")
    _cli_setup(onair_parser)
    return parser.parse_args(argv)


def test_cli_status() -> None:
    with MockOnAir() as mock:
        ctx = RecordingCtx({"base_url": mock.base_url})
        register_cli(ctx)
        args = _build_cli(["onair", "status"])
        out = io.StringIO()
        with redirect_stdout(out):
            code = ctx.commands["onair"]["handler_fn"](args)
        assert code == 0
        payload = json.loads(out.getvalue())
        assert payload["ok"] is True
        assert payload["onair"]["device"] == "Mock Radio"
    print("PASS test_cli_status")


def test_cli_frequency() -> None:
    with MockOnAir() as mock:
        ctx = RecordingCtx({"base_url": mock.base_url})
        register_cli(ctx)
        args = _build_cli(["onair", "freq", "--mhz", "100"])
        out = io.StringIO()
        with redirect_stdout(out):
            code = ctx.commands["onair"]["handler_fn"](args)
        assert code == 0
        assert mock.requests[-1]["body"] == {"mhz": 100.0}
        assert mock.requests[-1]["path"] == "/api/v1/frequency"
    print("PASS test_cli_frequency")


def test_cli_device_unknown() -> None:
    with MockOnAir() as mock:
        ctx = RecordingCtx({"base_url": mock.base_url})
        register_cli(ctx)
        args = _build_cli(["onair", "device", "fehlt"])
        out = io.StringIO()
        with redirect_stdout(out):
            code = ctx.commands["onair"]["handler_fn"](args)
        assert code == 1
        assert json.loads(out.getvalue())["ok"] is False
    print("PASS test_cli_device_unknown")


# --------------------------------------------------------------------------- #
# Settings / Desktop-Surface
# --------------------------------------------------------------------------- #


def test_plugin_from_ctx_precedence() -> None:
    ctx = RecordingCtx(
        {
            "config": "/tmp/custom.json",
            "base_url": "http://127.0.0.1:9999",
            "token": "abc",
            "timeout": 1.5,
        }
    )
    plugin = plugin_from_ctx(ctx)
    assert plugin.config_path == Path("/tmp/custom.json")
    assert plugin.base_url == "http://127.0.0.1:9999"
    assert plugin.client.token == "abc"
    assert plugin.client.timeout == 1.5

    override = plugin_from_ctx(ctx, base_url="http://127.0.0.1:8765")
    assert override.base_url == "http://127.0.0.1:8765"
    print("PASS test_plugin_from_ctx_precedence")


def test_desktop_hooks_imported_from_react() -> None:
    """Regression: React-Hooks kommen aus 'react', nicht aus 'react/jsx-runtime'.

    Der alte Stand importierte useState/useEffect/useRef aus
    react/jsx-runtime; das Modul exportiert sie nicht, der Desktop-Loader
    scheiterte mit "does not provide an export named 'useEffect'".
    """
    source = (ROOT / "desktop" / "plugin.js").read_text(encoding="utf-8")
    runtime_imports = [
        line for line in source.splitlines()
        if "react/jsx-runtime" in line and line.lstrip().startswith("import")
    ]
    assert runtime_imports, "jsx/jsxs-Import fehlt"
    for line in runtime_imports:
        for hook in ("useState", "useEffect", "useRef", "useMemo", "useCallback"):
            assert hook not in line, f"{hook} darf nicht aus react/jsx-runtime kommen: {line}"
    assert any(
        line.lstrip().startswith("import") and "from 'react'" in line and "useState" in line
        for line in source.splitlines()
    ), "useState muss aus 'react' importiert werden"
    print("PASS test_desktop_hooks_imported_from_react")


def test_desktop_plugin_uses_backend_proxy() -> None:
    source = (ROOT / "desktop" / "plugin.js").read_text(encoding="utf-8")
    assert "ctx.rest" in source
    assert "await fetch(" not in source  # kein direkter API-Zugriff aus dem Renderer
    assert "127.0.0.1:8765" not in source
    assert "usePluginI18n" in source
    print("PASS test_desktop_plugin_uses_backend_proxy")


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    failures = 0
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - Testrunner
            failures += 1
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
    print()
    if failures:
        print(f"{failures} von {len(tests)} Tests fehlgeschlagen.")
        return 1
    print(f"Alle {len(tests)} Tests bestanden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
