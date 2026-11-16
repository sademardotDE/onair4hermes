"""onair4hermes — Hermes-Plugin für OnAir (SDR / Funküberwachung).

Hermes lädt dieses Paket als Verzeichnis-Plugin (``plugin.yaml`` + ``__init__.py``)
und ruft :func:`register` mit einem Plugin-Kontext auf. Die Registrierung ist
bewusst schlank: sie registriert nur Tools, Schemas und die ``hermes onair``-CLI.
Teure Importe (Netzwerk) passieren erst in den Handlern.

Die Handler geben JSON-Strings zurück (Hermes-Tool-Vertrag) und akzeptieren die
Argumente als Dict, wie der Tool-Dispatcher sie übergibt.
"""

from __future__ import annotations

import json
from typing import Any, Callable

__version__ = "0.2.0"

# name -> (Modul, Attribut); wird beim ersten Zugriff importiert.
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "HermesPlugin": (".hermes_plugin", "HermesPlugin"),
    "create_plugin": (".hermes_plugin", "create_plugin"),
    "plugin_from_ctx": (".hermes_plugin", "plugin_from_ctx"),
    "OnAirClient": (".onair_client", "OnAirClient"),
    "OnAirError": (".onair_client", "OnAirError"),
}

__all__ = ["register", "__version__", *sorted(_LAZY_EXPORTS)]


def __getattr__(name: str) -> Any:
    """Lazy-Import der Paket-Exports."""
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = target
    from importlib import import_module

    module = import_module(module_name, __name__)
    value = module if attribute is None else getattr(module, attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


# --- Tool-Schemas (JSON-Schema für die Hermes-Tool-Registrierung) -----------

_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "onair_list_devices": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
        "description": "Liste aller OnAir-Geräte (Radios/Quellen).",
    },
    "onair_list_modes": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
        "description": "Liste aller verfügbaren OnAir-Decoder-Modi.",
    },
    "onair_status": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
        "description": "Aktueller OnAir-Receiver-Status inklusive Gerät, Modus und Frequenz.",
    },
    "onair_telemetry": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
        "description": "Telemetrie des aktiven OnAir-Modus (SNR, Lock, Qualität, Details).",
    },
    "onair_spectrum": {
        "type": "object",
        "properties": {
            "bins": {
                "type": "integer",
                "minimum": 16,
                "maximum": 4096,
                "default": 512,
                "description": "Anzahl der Spektrum-Bins",
            }
        },
        "additionalProperties": False,
        "description": "Aktuelles OnAir-Spektrum (dBFS pro Bin).",
    },
    "onair_start": {
        "type": "object",
        "properties": {
            "device_index": {
                "type": "integer",
                "minimum": 0,
                "description": "Index des zu startenden Radios (optional).",
            }
        },
        "additionalProperties": False,
        "description": "OnAir-Receiver starten.",
    },
    "onair_stop": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
        "description": "OnAir-Receiver stoppen.",
    },
    "onair_set_mode": {
        "type": "object",
        "properties": {
            "family": {
                "anyOf": [{"type": "integer"}, {"type": "string"}],
                "description": "Modus-Familie (ID oder Name, z. B. 7 oder 'fm').",
            },
            "sub": {
                "type": "string",
                "description": "Optionaler Sub-Modus (z. B. 'ft8').",
            },
        },
        "required": ["family"],
        "additionalProperties": False,
        "description": "OnAir-Decoder-Modus wechseln (OnAir verlangt einen gestoppten Receiver).",
    },
    "onair_set_frequency": {
        "type": "object",
        "properties": {
            "hz": {
                "type": "integer",
                "description": "Frequenz in Hertz (z. B. 100000000).",
            },
            "mhz": {
                "type": "number",
                "description": "Frequenz in Megahertz (z. B. 100.0).",
            },
        },
        "anyOf": [{"required": ["hz"]}, {"required": ["mhz"]}],
        "additionalProperties": False,
        "description": "Empfangsfrequenz setzen – genau eine der beiden Angaben.",
    },
}

_TOOL_EMOJIS = {
    "onair_list_devices": "📻",
    "onair_list_modes": "📡",
    "onair_status": "📊",
    "onair_telemetry": "📈",
    "onair_spectrum": "📶",
    "onair_start": "▶️",
    "onair_stop": "⏹️",
    "onair_set_mode": "🔀",
    "onair_set_frequency": "🎚️",
}


def _dump(payload: Any) -> str:
    """Tool-Ergebnis als JSON-String (Hermes verlangt String oder Multimodal-Envelope)."""
    return json.dumps(payload, ensure_ascii=False, default=str)


def _make_handlers(plugin: Any) -> dict[str, Callable[..., str]]:
    """Erstellt Handler-Funktionen für alle Tools aus der Plugin-Instanz."""
    from .onair_client import OnAirError

    def wrap(func: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable[..., str]:
        def handler(args: Any = None, **kwargs: Any) -> str:
            call_args = dict(args or {}) if isinstance(args, dict) else {}
            try:
                payload = func(call_args)
            except OnAirError as exc:
                return _dump({"ok": False, "error": str(exc), "status": exc.status})
            except (TypeError, ValueError, KeyError) as exc:
                return _dump({"ok": False, "error": str(exc)})
            return _dump(payload)

        return handler

    def list_devices(_args: dict[str, Any]) -> dict[str, Any]:
        devices = plugin.get_devices()
        return {"ok": True, "count": len(devices), "devices": devices}

    def list_modes(_args: dict[str, Any]) -> dict[str, Any]:
        modes = plugin.list_modes()
        return {"ok": True, "count": len(modes), "modes": modes}

    def status(_args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, **plugin.status()}

    def telemetry(_args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "telemetry": plugin.telemetry()}

    def spectrum(args: dict[str, Any]) -> dict[str, Any]:
        bins = args.get("bins", 512)
        return {"ok": True, "spectrum": plugin.spectrum(int(bins))}

    def start(args: dict[str, Any]) -> dict[str, Any]:
        index = args.get("device_index")
        plugin.start(index)
        return {"ok": True, "started": True, "device_index": index}

    def stop(_args: dict[str, Any]) -> dict[str, Any]:
        plugin.stop()
        return {"ok": True, "stopped": True}

    def set_mode(args: dict[str, Any]) -> dict[str, Any]:
        family = args["family"]
        if isinstance(family, str) and family.strip().isdigit():
            family = int(family)
        sub = args.get("sub")
        plugin.set_mode(family, sub)
        return {"ok": True, "mode_set": True, "family": family, "sub": sub}

    def set_frequency(args: dict[str, Any]) -> dict[str, Any]:
        hz = args.get("hz")
        mhz = args.get("mhz")
        plugin.set_frequency(hz=hz, mhz=mhz)
        return {"ok": True, "frequency_set": True, "hz": hz, "mhz": mhz}

    functions: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
        "onair_list_devices": list_devices,
        "onair_list_modes": list_modes,
        "onair_status": status,
        "onair_telemetry": telemetry,
        "onair_spectrum": spectrum,
        "onair_start": start,
        "onair_stop": stop,
        "onair_set_mode": set_mode,
        "onair_set_frequency": set_frequency,
    }
    return {name: wrap(func) for name, func in functions.items()}


def register(ctx: Any) -> None:
    """Hermes-Plugin-Einstiegspunkt: Tools + CLI registrieren.

    Wird vom Hermes-Loader nach dem Import aufgerufen (auch im isolierten
    Capability-Probe von ``hermes plugins validate``). Darf daher weder Netzwerk
    noch OnAir-Hardware voraussetzen.
    """
    from .hermes_plugin import plugin_from_ctx, register_cli

    plugin = plugin_from_ctx(ctx)
    handlers = _make_handlers(plugin)

    for name, schema in _TOOL_SCHEMAS.items():
        ctx.register_tool(
            name=name,
            toolset="onair",
            schema=schema,
            handler=handlers[name],
            emoji=_TOOL_EMOJIS.get(name, "📻"),
        )
    register_cli(ctx)
