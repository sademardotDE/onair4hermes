"""Dashboard-Backend für onair4hermes, gemountet unter /api/plugins/onair4hermes/.

Läuft im Hermes-Dashboard/Gateway-Prozess (hinter dessen Auth) und ist der
einzige Weg, den die Desktop-Seite benutzt: ``ctx.rest(...)`` im Renderer geht
gegen diese Routen, die wiederum die OnAir Remote-Control-API ansprechen.

Warum der Umweg? Die OnAir-API sendet keine CORS-Header und der Desktop-
Renderer hat ``webSecurity`` an – ein direktes ``fetch`` aus dem Renderer
scheitert. Der Gateway-Proxy läuft serverseitig, kennt den Token aus
``~/.hermes/.env`` (``ONAIR_API_TOKEN``) bzw. den Plugin-Settings und ist
zugleich der Ort, an dem die API-URL zentral konfiguriert wird.

Das Plugin-Paket wird unter einem privaten Namen geladen (wie im
Dashboard-Loader üblich), damit relative Importe im Paket sauber auflösen.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query

_ROOT = Path(__file__).resolve().parents[1]
_NAME = "_onair4hermes_dashboard"
PLUGIN_ID = "onair4hermes"
_SETTINGS_TTL = 10.0
_settings_cache: tuple[float, dict[str, Any]] | None = None

if _NAME not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        _NAME, _ROOT / "__init__.py", submodule_search_locations=[str(_ROOT)]
    )
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_NAME] = _module
    _spec.loader.exec_module(_module)
_module = sys.modules[_NAME]

_onair_client = importlib.import_module(_NAME + ".onair_client")
OnAirError = _onair_client.OnAirError

router = APIRouter()


# --------------------------------------------------------------------------- #
# Konfiguration
# --------------------------------------------------------------------------- #


def _plugin_settings() -> dict[str, Any]:
    """Settings aus ``plugins.entries.onair4hermes.settings`` (kurz gecacht)."""
    global _settings_cache
    now = time.monotonic()
    if _settings_cache is not None and now - _settings_cache[0] < _SETTINGS_TTL:
        return _settings_cache[1]
    settings: dict[str, Any] = {}
    try:
        from hermes_cli.config import load_config_readonly

        config = load_config_readonly() or {}
        entries = ((config.get("plugins") or {}).get("entries") or {})
        entry = entries.get(PLUGIN_ID) or {}
        raw = entry.get("settings")
        if isinstance(raw, dict):
            settings = dict(raw)
    except Exception:  # noqa: BLE001 - Fallback auf Umgebungsvariablen
        settings = {}
    _settings_cache = (now, settings)
    return settings


def _client_kwargs() -> dict[str, Any]:
    settings = _plugin_settings()
    return {
        "config_path": str(settings.get("config") or "") or None,
        "base_url": str(settings.get("base_url") or os.environ.get(_onair_client.BASE_URL_ENV) or "") or None,
        "token": str(settings.get("token") or os.environ.get(_onair_client.TOKEN_ENV) or "") or None,
        "timeout": settings.get("timeout"),
    }


def _client() -> Any:
    return _onair_client.OnAirClient(**_client_kwargs())


def _fail(exc: Exception) -> HTTPException:
    status = 502
    if isinstance(exc, OnAirError) and exc.status and 400 <= exc.status < 600:
        status = exc.status
    return HTTPException(status_code=status, detail={"ok": False, "error": str(exc)})


def _body_dict(body: Any) -> dict[str, Any]:
    return body if isinstance(body, dict) else {}


# --------------------------------------------------------------------------- #
# Lesen
# --------------------------------------------------------------------------- #


@router.get("/config")
def config_info() -> dict[str, Any]:
    settings = _plugin_settings()
    client = _client()
    return {
        "ok": True,
        "base_url": client.base_url,
        "has_token": bool(client.token),
        "config": str(settings.get("config") or ""),
        "timeout": client.timeout,
    }


@router.get("/status")
def status() -> dict[str, Any]:
    try:
        client = _client()
        devices = client.list_devices()
        modes = client.list_modes()
        return {
            "ok": True,
            "plugin": PLUGIN_ID,
            "version": _module.__version__,
            "base_url": client.base_url,
            "config": str(client.config_path or ""),
            "devices": len(devices),
            "modes": len(modes),
            "onair": client.status(),
        }
    except Exception as exc:  # noqa: BLE001 - Status darf nie 500 werfen
        return {"ok": False, "plugin": PLUGIN_ID, "error": str(exc), "onair": {"source": "offline"}}


@router.get("/devices")
def devices() -> dict[str, Any]:
    try:
        client = _client()
        items = client.list_devices()
    except Exception as exc:  # noqa: BLE001
        raise _fail(exc) from None
    return {"ok": True, "count": len(items), "devices": items}


@router.get("/modes")
def modes() -> dict[str, Any]:
    try:
        client = _client()
        items = client.list_modes()
    except Exception as exc:  # noqa: BLE001
        raise _fail(exc) from None
    return {"ok": True, "count": len(items), "modes": items}


@router.get("/telemetry")
def telemetry() -> dict[str, Any]:
    try:
        return {"ok": True, "telemetry": _client().telemetry()}
    except Exception as exc:  # noqa: BLE001
        raise _fail(exc) from None


@router.get("/spectrum")
def spectrum(bins: int = Query(64, ge=16, le=4096)) -> dict[str, Any]:
    try:
        return {"ok": True, "spectrum": _client().spectrum(bins)}
    except Exception as exc:  # noqa: BLE001
        raise _fail(exc) from None


# --------------------------------------------------------------------------- #
# Steuern
# --------------------------------------------------------------------------- #


@router.post("/start")
def start(body: Any = Body(default=None)) -> dict[str, Any]:
    payload = _body_dict(body)
    index = payload.get("device_index", payload.get("device"))
    try:
        _client().start(index)
    except Exception as exc:  # noqa: BLE001
        raise _fail(exc) from None
    return {"ok": True, "started": True, "device_index": index}


@router.post("/stop")
def stop(body: Any = Body(default=None)) -> dict[str, Any]:  # noqa: ARG001 - Body bleibt optional
    try:
        _client().stop()
    except Exception as exc:  # noqa: BLE001
        raise _fail(exc) from None
    return {"ok": True, "stopped": True}


@router.post("/mode")
def set_mode(body: Any = Body(default=None)) -> dict[str, Any]:
    payload = _body_dict(body)
    family = payload.get("family")
    if isinstance(family, str) and family.strip().isdigit():
        family = int(family)
    try:
        _client().set_mode(family, payload.get("sub"))
    except Exception as exc:  # noqa: BLE001
        raise _fail(exc) from None
    return {"ok": True, "mode_set": True, "family": family, "sub": payload.get("sub")}


@router.post("/frequency")
def set_frequency(body: Any = Body(default=None)) -> dict[str, Any]:
    payload = _body_dict(body)
    try:
        _client().set_frequency(hz=payload.get("hz"), mhz=payload.get("mhz"))
    except Exception as exc:  # noqa: BLE001
        raise _fail(exc) from None
    return {"ok": True, "frequency_set": True, "hz": payload.get("hz"), "mhz": payload.get("mhz")}
