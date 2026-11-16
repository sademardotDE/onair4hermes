"""Client-Anbindung an OnAir für das Hermes-Plugin onair4hermes.

Nutzt die OnAir Remote-Control HTTP API (Port 8765, localhost), um OnAir
aus Hermes heraus zu steuern und Status abzufragen. Keine externen
Pflicht-Abhängigkeiten (nur Python-Standardbibliothek).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class OnAirClient:
    """Client für die OnAir Remote-Control HTTP API."""

    def __init__(self, config_path: Path, base_url: str = "http://127.0.0.1:8765"):
        self.config_path = Path(config_path)
        self.base_url = base_url.rstrip("/")
        self._devices: list[dict[str, Any]] | None = None
        self._modes: list[dict[str, Any]] | None = None

    # --- Konfiguration ------------------------------------------------------

    def _load_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {}
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    # --- HTTP-Hilfsfunktion -------------------------------------------------

    def _get(self, path: str, timeout: float = 5.0) -> Any:
        """GET-Request an die OnAir API. Gibt None zurück bei Fehler."""
        url = f"{self.base_url}{path}"
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                data = resp.read()
                if not data:
                    return None
                return json.loads(data)
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return None

    def _post(self, path: str, payload: dict[str, Any] | None = None,
              timeout: float = 5.0) -> bool:
        """POST-Request an die OnAir API. Gibt True bei Erfolg zurück."""
        url = f"{self.base_url}{path}"
        body = b""
        headers: dict[str, str] = {}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as _resp:
                return True
        except (urllib.error.URLError, OSError):
            return False

    # --- Geräte / Modi ------------------------------------------------------

    def list_devices(self) -> list[dict[str, Any]]:
        """Liste aller OnAir-Geräte (Radios/Quellen)."""
        if self._devices is not None:
            return self._devices

        # Versuch über die OnAir API
        api_devices = self._get("/api/v1/devices")
        if isinstance(api_devices, list):
            self._devices = [
                {
                    "id": f"onair-device-{d.get('index', i)}",
                    "name": d.get("name", f"OnAir Device {i}"),
                    "type": "radio",
                    "kind": d.get("kind", ""),
                    "board": d.get("board", ""),
                    "serial": d.get("serial", ""),
                    "selected": d.get("selected", False),
                    "source": "onair-api",
                }
                for i, d in enumerate(api_devices)
            ]
            return self._devices

        # Fallback: statische Konfigurationsdatei
        config = self._load_config()
        devices = config.get("devices", [])
        self._devices = [
            {
                "id": d.get("id", f"onair-{i}"),
                "name": d.get("name", f"OnAir {i}"),
                "type": d.get("type", "onair"),
                "host": d.get("host", "localhost"),
                "port": d.get("port", 0),
                "mode": d.get("mode", ""),
                "frequency_hz": d.get("frequency_hz", 0),
                "configured": True,
                "source": "config",
            }
            for i, d in enumerate(devices)
        ]
        return self._devices

    def list_modes(self) -> list[dict[str, Any]]:
        """Liste aller verfügbaren OnAir-Modi."""
        if self._modes is not None:
            return self._modes

        api_modes = self._get("/api/v1/modes")
        if isinstance(api_modes, list):
            self._modes = [
                {
                    "id": m.get("id", f"mode-{i}"),
                    "name": m.get("name", m.get("family", f"Mode {i}")),
                    "family": m.get("family", ""),
                    "sub": m.get("sub", ""),
                    "source": "onair-api",
                }
                for i, m in enumerate(api_modes)
            ]
            return self._modes

        self._modes = []
        return self._modes

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        for dev in self.list_devices():
            if dev["id"] == device_id:
                return dev
        return None

    # --- Status / Steuerung -------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Aktueller OnAir-Status (Receiver, Modus, Frequenz, …)."""
        api_status = self._get("/api/v1/status")
        if isinstance(api_status, dict):
            return {"source": "onair-api", **api_status}
        return {"source": "offline", "running": False, "error": "OnAir API nicht erreichbar"}

    def telemetry(self) -> dict[str, Any]:
        """Telemetrie des aktiven Modus."""
        return self._get("/api/v1/telemetry") or {"source": "offline"}

    def spectrum(self, bins: int = 512) -> dict[str, Any]:
        """Aktuelles Spektrum."""
        return self._get(f"/api/v1/spectrum?bins={bins}") or {"source": "offline"}

    def start(self, device_index: int | None = None) -> bool:
        """OnAir-Receiver starten."""
        payload: dict[str, Any] = {}
        if device_index is not None:
            payload["device"] = device_index
        return self._post("/api/v1/start", payload or None)

    def stop(self) -> bool:
        """OnAir-Receiver stoppen."""
        return self._post("/api/v1/stop")

    def set_mode(self, family: int | str, sub: str | None = None) -> bool:
        """OnAir-Modus wechseln (nur bei gestopptem Receiver)."""
        payload: dict[str, Any] = {"family": family}
        if sub is not None:
            payload["sub"] = sub
        return self._post("/api/v1/mode", payload)

    def set_frequency(self, hz: int | None = None, mhz: float | None = None) -> bool:
        """Frequenz setzen (Hz oder MHz)."""
        if hz is not None:
            return self._post("/api/v1/frequency", {"hz": hz})
        if mhz is not None:
            return self._post("/api/v1/frequency", {"mhz": mhz})
        return False

    def reload(self) -> None:
        self._devices = None
        self._modes = None
