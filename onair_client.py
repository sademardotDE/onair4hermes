"""Client-Anbindung an OnAir für das Hermes-Plugin onair4hermes.

Kapselt den Zugriff auf OnAir (lokaler API / CLI / Plugin-Host) und stellt
Geräte/Modi als einheitliche Dicts bereit. Keine externen Pflicht-Abhängigkeiten.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


class OnAirClient:
    """Einfacher Client für OnAir-Geräte/Modi."""

    def __init__(self, config_path: Path):
        self.config_path = Path(config_path)
        self._devices: list[dict[str, Any]] | None = None

    def _load_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {}
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def list_devices(self) -> list[dict[str, Any]]:
        """Liste aller bekannten OnAir-Geräte/Modi."""
        if self._devices is not None:
            return self._devices
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
            }
            for i, d in enumerate(devices)
        ]
        return self._devices

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        for dev in self.list_devices():
            if dev["id"] == device_id:
                return dev
        return None

    def reload(self) -> None:
        self._devices = None
