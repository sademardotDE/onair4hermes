#!/usr/bin/env python3
"""Hermes-Plugin-Einstiegspunkt für onair4hermes.

Zwei Nutzungswege:

* **Als Verzeichnis-Plugin** lädt Hermes ``onair4hermes/__init__.py`` und ruft
  dort ``register(ctx)`` auf. ``hermes_plugin.py`` ist dann die
  objektorientierte Fassade (z. B. für Skripte und die Dashboard-API).
* **Direkt** per ``python3 -m onair4hermes.hermes_plugin``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .onair_client import OnAirClient

__all__ = [
    "HermesPlugin",
    "create_plugin",
    "register",
    "OnAirClient",
]

_PLUGIN_ROOT = Path(__file__).resolve().parent


def _default_config_path() -> Path:
    """Standard-Konfigurationspfad für OnAir-Geräte."""
    return _PLUGIN_ROOT / "onair_devices.json"


class HermesPlugin:
    """Hermes-kompatible Plugin-Fassade für OnAir."""

    name = "onair4hermes"
    version = "0.1.0"
    description = "OnAir (SDR / Funküberwachung) als Hermes-Geräte einbinden"

    def __init__(self, config_path: str | Path | None = None):
        self.config_path = Path(config_path).expanduser() if config_path else _default_config_path()
        self.client = OnAirClient(self.config_path)

    # --- OnAir-Geräte / Modi -------------------------------------------------

    def get_devices(self) -> list[dict[str, Any]]:
        """Liste aller bekannten OnAir-Geräte/Modi als Hermes-Geräte-Dicts."""
        return self.client.list_devices()

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        return self.client.get_device(device_id)

    def list_modes(self) -> list[dict[str, Any]]:
        """Liste aller verfügbaren OnAir-Modi."""
        return self.client.list_modes()

    # --- Status ------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        onair_status = self.client.status()
        return {
            "plugin": self.name,
            "version": self.version,
            "devices": len(self.get_devices()),
            "modes": len(self.list_modes()),
            "config": str(self.config_path),
            "onair": onair_status,
        }

    def telemetry(self) -> dict[str, Any]:
        return self.client.telemetry()

    def spectrum(self, bins: int = 512) -> dict[str, Any]:
        return self.client.spectrum(bins)

    # --- Steuerung ----------------------------------------------------------

    def start(self, device_index: int | None = None) -> bool:
        return self.client.start(device_index)

    def stop(self) -> bool:
        return self.client.stop()

    def set_mode(self, family: int | str, sub: str | None = None) -> bool:
        return self.client.set_mode(family, sub)

    def set_frequency(self, hz: int | None = None, mhz: float | None = None) -> bool:
        return self.client.set_frequency(hz, mhz)

    def reload(self) -> None:
        self.client.reload()


def create_plugin(config_path: str | Path | None = None) -> HermesPlugin:
    """Fassade erzeugen; ohne Argument wird die Standard-Konfiguration benutzt."""
    return HermesPlugin(config_path)


def register_cli(ctx: Any) -> None:
    """Registriert die ``hermes onair``-CLI beim Hermes-Kontext."""
    if hasattr(ctx, "register_cli"):
        ctx.register_cli("onair", _onair_cli)


def _onair_cli(args: list[str]) -> int:
    """Einfache CLI für OnAir-Geräte."""
    plugin = create_plugin()
    if not args or args[0] in ("-h", "--help"):
        print("Usage: hermes onair [status|devices|modes|device <id>|start|stop|mode <family> [sub]|freq <hz|mhz>]")
        return 0
    cmd = args[0]
    try:
        if cmd == "status":
            print(json.dumps(plugin.status(), indent=2, ensure_ascii=False))
        elif cmd == "devices":
            print(json.dumps(plugin.get_devices(), indent=2, ensure_ascii=False))
        elif cmd == "modes":
            print(json.dumps(plugin.list_modes(), indent=2, ensure_ascii=False))
        elif cmd == "device" and len(args) > 1:
            dev = plugin.get_device(args[1])
            if dev is None:
                print(f"Gerät nicht gefunden: {args[1]}", file=sys.stderr)
                return 1
            print(json.dumps(dev, indent=2, ensure_ascii=False))
        elif cmd == "start":
            di = int(args[1]) if len(args) > 1 else None
            print(json.dumps({"started": plugin.start(di)}, indent=2, ensure_ascii=False))
        elif cmd == "stop":
            print(json.dumps({"stopped": plugin.stop()}, indent=2, ensure_ascii=False))
        elif cmd == "mode" and len(args) > 1:
            family = args[1]
            sub = args[2] if len(args) > 2 else None
            try:
                family = int(family)
            except ValueError:
                pass
            print(json.dumps({"mode_set": plugin.set_mode(family, sub)}, indent=2, ensure_ascii=False))
        elif cmd == "freq" and len(args) > 1:
            val = args[1]
            if val.endswith(("M", "m")):
                print(json.dumps({"freq_set": plugin.set_frequency(mhz=float(val[:-1]))}, indent=2, ensure_ascii=False))
            else:
                print(json.dumps({"freq_set": plugin.set_frequency(hz=int(val))}, indent=2, ensure_ascii=False))
        else:
            print(f"Unbekannter Befehl: {cmd}", file=sys.stderr)
            return 2
    except (ValueError, KeyError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    return 0


def register(ctx: Any) -> None:
    """Entry-Point-Fallback: identisch zum Paket-Register (``onair4hermes``)."""
    from . import register as _register

    _register(ctx)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    plugin = create_plugin(args[0] if args and not args[0].startswith("-") else None)
    if args and args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    print(json.dumps(plugin.status(), indent=2, ensure_ascii=False))
    print(json.dumps(plugin.get_devices(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
