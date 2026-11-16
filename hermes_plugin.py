#!/usr/bin/env python3
"""Hermes-Plugin-Einstiegspunkt für onair4hermes.

Zwei Nutzungswege:

* **Als Verzeichnis-Plugin** lädt Hermes ``onair4hermes/__init__.py`` und ruft
  dort ``register(ctx)`` auf. ``hermes_plugin.py`` ist dann die
  objektorientierte Fassade (z. B. für Skripte, die Dashboard-API und die
  ``hermes onair``-CLI).
* **Direkt** per ``python3 -m onair4hermes.hermes_plugin [--config PFAD]``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

from . import __version__
from .onair_client import (
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    OnAirClient,
    OnAirError,
)

__all__ = [
    "HermesPlugin",
    "create_plugin",
    "plugin_from_ctx",
    "register",
    "register_cli",
    "OnAirClient",
    "OnAirError",
]

_PLUGIN_ROOT = Path(__file__).resolve().parent

PLUGIN_NAME = "onair4hermes"


def _default_config_path() -> Path:
    """Standard-Konfigurationspfad für OnAir-Geräte."""
    return _PLUGIN_ROOT / "onair_devices.json"


def _ctx_setting(ctx: Any, key: str, default: Any) -> Any:
    """``ctx.get_config(key, default)`` ohne Ausnahme, falls der Kontext es nicht kann."""
    getter = getattr(ctx, "get_config", None)
    if not callable(getter):
        return default
    try:
        value = getter(key, default)
    except Exception:  # noqa: BLE001 - ein defekter Kontext darf das Laden nicht kippen
        return default
    return default if value is None else value


def plugin_from_ctx(
    ctx: Any,
    *,
    config_path: str | Path | None = None,
    base_url: str | None = None,
    token: str | None = None,
    timeout: float | None = None,
) -> "HermesPlugin":
    """Plugin-Instanz aus den Hermes-Plugin-Einstellungen bauen.

    Explizite Argumente (z. B. von der CLI) haben Vorrang vor den Settings aus
    ``plugins.entries.onair4hermes.settings``.
    """
    resolved_config = config_path
    if not resolved_config:
        resolved_config = str(_ctx_setting(ctx, "config", "") or "").strip() or None
    resolved_base = base_url
    if not resolved_base:
        resolved_base = str(_ctx_setting(ctx, "base_url", "") or "").strip() or None
    resolved_token = token
    if not resolved_token:
        resolved_token = str(_ctx_setting(ctx, "token", "") or "").strip() or None
    resolved_timeout = timeout
    if resolved_timeout is None:
        resolved_timeout = _ctx_setting(ctx, "timeout", DEFAULT_TIMEOUT)
    return create_plugin(
        resolved_config,
        base_url=resolved_base,
        token=resolved_token,
        timeout=resolved_timeout,
    )


class HermesPlugin:
    """Hermes-kompatible Plugin-Fassade für OnAir."""

    name = PLUGIN_NAME
    version = __version__
    description = "OnAir (SDR / Funküberwachung) als Hermes-Geräte einbinden"

    def __init__(
        self,
        config_path: str | Path | None = None,
        *,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.config_path = (
            Path(config_path).expanduser() if config_path else _default_config_path()
        )
        self.client = OnAirClient(
            self.config_path, base_url=base_url, token=token, timeout=timeout
        )

    @property
    def base_url(self) -> str:
        return self.client.base_url

    # --- OnAir-Geräte / Modi -------------------------------------------------

    def get_devices(self) -> list[dict[str, Any]]:
        """Liste aller bekannten OnAir-Geräte als Hermes-Geräte-Dicts."""
        return self.client.list_devices()

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        return self.client.get_device(device_id)

    def list_modes(self) -> list[dict[str, Any]]:
        """Liste aller verfügbaren OnAir-Modi."""
        return self.client.list_modes()

    # --- Status --------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Kompakter Plugin-Status inklusive OnAir-Receiver-Status."""
        onair_status = self.client.status()
        return {
            "plugin": self.name,
            "version": self.version,
            "base_url": self.client.base_url,
            "config": str(self.config_path),
            "devices": len(self.get_devices()),
            "modes": len(self.list_modes()),
            "onair": onair_status,
        }

    def telemetry(self) -> dict[str, Any]:
        return self.client.telemetry()

    def spectrum(self, bins: int = 512) -> dict[str, Any]:
        return self.client.spectrum(bins)

    # --- Steuerung -----------------------------------------------------------

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


def create_plugin(
    config_path: str | Path | None = None,
    *,
    base_url: str | None = None,
    token: str | None = None,
    timeout: float | None = None,
) -> HermesPlugin:
    """Fassade erzeugen; ohne Argument wird die Standard-Konfiguration benutzt."""
    return HermesPlugin(config_path, base_url=base_url, token=token, timeout=timeout)


# --------------------------------------------------------------------------- #
# ``hermes onair``-CLI
# --------------------------------------------------------------------------- #


def _cli_setup(subparser: Any) -> None:
    """Argparse-Setup für ``hermes onair <befehl>``."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--config", default="", metavar="PFAD",
        help="JSON-Gerätekonfiguration (überschreibt das Plugin-Setting)",
    )
    common.add_argument(
        "--base-url", default="", metavar="URL",
        help=f"OnAir-API-URL (Standard: {DEFAULT_BASE_URL})",
    )

    subs = subparser.add_subparsers(dest="onair_command", metavar="BEFEHL")
    subs.required = True

    subs.add_parser("status", parents=[common], help="Plugin- und Receiver-Status")
    subs.add_parser("devices", parents=[common], help="OnAir-Geräte auflisten")
    subs.add_parser("modes", parents=[common], help="OnAir-Decoder-Modi auflisten")
    subs.add_parser("telemetry", parents=[common], help="Telemetrie des aktiven Modus")

    p = subs.add_parser("device", parents=[common], help="Ein Gerät anzeigen")
    p.add_argument("device_id", help="Geräte-ID (z. B. onair-device-0)")

    p = subs.add_parser("spectrum", parents=[common], help="Spektrum abrufen")
    p.add_argument("--bins", type=int, default=64, help="Anzahl Bins (16-4096)")

    p = subs.add_parser("start", parents=[common], help="Receiver starten")
    p.add_argument("--device", type=int, default=None, metavar="INDEX", help="Geräteindex")

    subs.add_parser("stop", parents=[common], help="Receiver stoppen")

    p = subs.add_parser("mode", parents=[common], help="Decoder-Modus wechseln")
    p.add_argument("family", help="Modus-Familie (ID oder Name, z. B. 7 oder fm)")
    p.add_argument("--sub", default=None, help="Optionaler Sub-Modus")

    p = subs.add_parser("freq", parents=[common], help="Frequenz setzen")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--hz", type=int, help="Frequenz in Hertz")
    group.add_argument("--mhz", type=float, help="Frequenz in Megahertz")


def _cli_handler(ctx: Any) -> Callable[[Any], int]:
    def handle(args: Any) -> int:
        plugin = plugin_from_ctx(
            ctx,
            config_path=getattr(args, "config", "") or None,
            base_url=getattr(args, "base_url", "") or None,
        )
        try:
            result = _run_cli_command(plugin, args)
        except (OnAirError, ValueError) as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok", True) else 1

    return handle


def _run_cli_command(plugin: HermesPlugin, args: Any) -> dict[str, Any]:
    command = getattr(args, "onair_command", "")

    if command == "status":
        return {"ok": True, **plugin.status()}
    if command == "devices":
        devices = plugin.get_devices()
        return {"ok": True, "count": len(devices), "devices": devices}
    if command == "modes":
        modes = plugin.list_modes()
        return {"ok": True, "count": len(modes), "modes": modes}
    if command == "device":
        device = plugin.get_device(str(args.device_id))
        if device is None:
            return {"ok": False, "error": f"Gerät nicht gefunden: {args.device_id}"}
        return {"ok": True, "device": device}
    if command == "telemetry":
        return {"ok": True, "telemetry": plugin.telemetry()}
    if command == "spectrum":
        return {"ok": True, "spectrum": plugin.spectrum(int(args.bins))}
    if command == "start":
        plugin.start(args.device)
        return {"ok": True, "started": True, "device_index": args.device}
    if command == "stop":
        plugin.stop()
        return {"ok": True, "stopped": True}
    if command == "mode":
        family: int | str = args.family
        try:
            family = int(family)
        except (TypeError, ValueError):
            pass
        plugin.set_mode(family, args.sub)
        return {"ok": True, "mode_set": True, "family": family, "sub": args.sub}
    if command == "freq":
        plugin.set_frequency(hz=args.hz, mhz=args.mhz)
        return {
            "ok": True,
            "frequency_set": True,
            "hz": args.hz,
            "mhz": args.mhz,
        }
    raise ValueError(f"Unbekannter Befehl: {command}")


def register_cli(ctx: Any) -> None:
    """Registriert ``hermes onair`` beim Hermes-Kontext (echte Plugin-API)."""
    register_command = getattr(ctx, "register_cli_command", None)
    if not callable(register_command):
        return
    register_command(
        name="onair",
        help="OnAir (SDR) steuern und Status abfragen",
        setup_fn=_cli_setup,
        handler_fn=_cli_handler(ctx),
        description=(
            "OnAir-Receiver über die lokale Remote-Control-API steuern: Status, "
            "Geräte, Modi, Telemetrie, Spektrum, Start/Stop, Modus- und "
            "Frequenzwechsel."
        ),
    )


def register(ctx: Any) -> None:
    """Entry-Point-Fallback: identisch zum Paket-Register (``onair4hermes``)."""
    from . import register as _register

    _register(ctx)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="onair4hermes",
        description="OnAir-Status und -Geräte als JSON ausgeben.",
    )
    parser.add_argument("--config", default="", metavar="PFAD", help="JSON-Gerätekonfiguration")
    parser.add_argument("--base-url", default="", metavar="URL", help="OnAir-API-URL")
    parsed = parser.parse_args(args)
    plugin = create_plugin(
        parsed.config or None,
        base_url=parsed.base_url or None,
    )
    print(json.dumps(plugin.status(), indent=2, ensure_ascii=False, default=str))
    print(json.dumps(plugin.get_devices(), indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
