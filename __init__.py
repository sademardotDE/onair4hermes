"""onair4hermes — Hermes-Plugin für OnAir (SDR / Funküberwachung).

Hermes lädt dieses Paket als Verzeichnis-Plugin (``plugin.yaml`` + ``__init__.py``)
und ruft :func:`register` mit einem Plugin-Kontext auf. Die Registrierung ist
bewusst schlank: sie registriert nur Tools, Schemas und die ``hermes onair``-CLI.
Teure Importe (Netzwerk, Subprozesse) passieren erst in den Handlern.
"""

from __future__ import annotations

from typing import Any

__version__ = "0.1.0"

# name -> (Modul, Attribut); wird beim ersten Zugriff importiert.
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "HermesPlugin": (".hermes_plugin", "HermesPlugin"),
    "create_plugin": (".hermes_plugin", "create_plugin"),
    "OnAirClient": (".onair_client", "OnAirClient"),
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


# --- Tool-Schemas (JSON-Schema für Hermes-Tool-Registrierung) ---------------

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
        "description": "Aktueller OnAir-Receiver-Status.",
    },
    "onair_telemetry": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
        "description": "Telemetrie des aktiven OnAir-Modus.",
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
            }
        },
        "required": ["family"],
        "additionalProperties": False,
        "description": "OnAir-Decoder-Modus wechseln (nur bei gestopptem Receiver).",
    },
    "onair_set_frequency": {
        "type": "object",
        "properties": {
            "hz": {
                "type": "integer",
                "description": "Frequenz in Hertz.",
            },
            "mhz": {
                "type": "number",
                "description": "Frequenz in Megahertz.",
            }
        },
        "additionalProperties": False,
        "description": "Empfangsfrequenz setzen (Hz oder MHz).",
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


def _make_handlers(plugin: Any) -> dict[str, Any]:
    """Erstellt Handler-Funktionen für alle Tools aus der Plugin-Instanz."""
    return {
        "onair_list_devices": lambda **kw: plugin.get_devices(),
        "onair_list_modes": lambda **kw: plugin.list_modes(),
        "onair_status": lambda **kw: plugin.status(),
        "onair_telemetry": lambda **kw: plugin.telemetry(),
        "onair_spectrum": lambda **kw: plugin.spectrum(kw.get("bins", 512)),
        "onair_start": lambda **kw: {"started": plugin.start(kw.get("device_index"))},
        "onair_stop": lambda **kw: {"stopped": plugin.stop()},
        "onair_set_mode": lambda **kw: {
            "mode_set": plugin.set_mode(kw["family"], kw.get("sub"))
        },
        "onair_set_frequency": lambda **kw: {
            "freq_set": plugin.set_frequency(kw.get("hz"), kw.get("mhz"))
        },
    }


def register(ctx: Any) -> None:
    """Hermes-Plugin-Einstiegspunkt: Tools + CLI registrieren.

    Wird vom Hermes-Loader nach dem Import aufgerufen (auch im isolierten
    Capability-Probe von ``hermes plugins validate``). Darf daher weder Netzwerk
    noch OnAir-Hardware voraussetzen.
    """
    from .hermes_plugin import register_cli, create_plugin

    plugin = create_plugin()
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
