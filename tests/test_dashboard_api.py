"""Tests für das Dashboard-Backend (dashboard/plugin_api.py).

Braucht FastAPI + httpx (im Dashboard-/Gateway-Environment vorhanden). Ohne
diese Pakete werden die Tests übersprungen, damit die normalen Plugin-Tests
überall laufen.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_plugin import MockOnAir  # noqa: E402

try:  # pragma: no cover - Umgebungsabhängig
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    HAVE_FASTAPI = True
except Exception:  # noqa: BLE001
    HAVE_FASTAPI = False


def _load_api_module():
    spec = importlib.util.spec_from_file_location(
        "_onair_dashboard_test",
        ROOT / "dashboard" / "plugin_api.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _client(module):
    app = FastAPI()
    app.include_router(module.router, prefix="/api/plugins/onair4hermes")
    return TestClient(app)


def _with_env(**values: str):
    class _Env:
        def __enter__(self):
            self.old = {key: os.environ.get(key) for key in values}
            os.environ.update(values)
            return self

        def __exit__(self, *exc):
            for key, value in self.old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    return _Env()


def test_dashboard_read() -> None:
    if not HAVE_FASTAPI:
        print("SKIP test_dashboard_read (fastapi/httpx fehlen)")
        return
    with MockOnAir() as mock, _with_env(ONAIR_BASE_URL=mock.base_url):
        module = _load_api_module()
        api = _client(module)

        status = api.get("/api/plugins/onair4hermes/status").json()
        assert status["ok"] is True
        assert status["onair"]["device"] == "Mock Radio"

        devices = api.get("/api/plugins/onair4hermes/devices").json()
        assert devices["count"] == 1

        modes = api.get("/api/plugins/onair4hermes/modes").json()
        assert modes["count"] == 1

        telemetry = api.get("/api/plugins/onair4hermes/telemetry").json()
        assert telemetry["telemetry"]["locked"] is True

        spectrum = api.get("/api/plugins/onair4hermes/spectrum?bins=48").json()
        assert len(spectrum["spectrum"]["dbfs"]) == 48

        config = api.get("/api/plugins/onair4hermes/config").json()
        assert config["base_url"] == mock.base_url
    print("PASS test_dashboard_read")


def test_dashboard_controls() -> None:
    if not HAVE_FASTAPI:
        print("SKIP test_dashboard_controls (fastapi/httpx fehlen)")
        return
    with MockOnAir() as mock, _with_env(ONAIR_BASE_URL=mock.base_url):
        module = _load_api_module()
        api = _client(module)

        assert api.post("/api/plugins/onair4hermes/start", json={"device_index": 0}).json()["started"] is True
        assert mock.requests[-1]["body"] == {"device": 0}

        assert api.post("/api/plugins/onair4hermes/stop", json={}).json()["stopped"] is True
        assert api.post("/api/plugins/onair4hermes/mode", json={"family": "7"}).json()["mode_set"] is True
        assert mock.requests[-1]["body"] == {"family": 7}
        assert api.post("/api/plugins/onair4hermes/frequency", json={"mhz": 100}).json()["frequency_set"] is True
        assert mock.requests[-1]["body"] == {"mhz": 100}
    print("PASS test_dashboard_controls")


def test_dashboard_token_missing_maps_to_401() -> None:
    if not HAVE_FASTAPI:
        print("SKIP test_dashboard_token_missing_maps_to_401 (fastapi/httpx fehlen)")
        return
    with MockOnAir(token="secret") as mock, _with_env(ONAIR_BASE_URL=mock.base_url):
        os.environ.pop("ONAIR_API_TOKEN", None)
        module = _load_api_module()
        api = _client(module)
        response = api.post("/api/plugins/onair4hermes/stop", json={})
        assert response.status_code == 401
        assert response.json()["detail"]["ok"] is False
    print("PASS test_dashboard_token_missing_maps_to_401")


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    failures = 0
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
    print()
    if failures:
        print(f"{failures} von {len(tests)} Dashboard-Tests fehlgeschlagen.")
        return 1
    print(f"Alle {len(tests)} Dashboard-Tests bestanden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
