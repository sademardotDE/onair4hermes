"""onair4hermes — Hermes-Plugin für OnAir (SDR / Funküberwachung).

Hermes lädt dieses Paket als Verzeichnis-Plugin (``plugin.json`` + ``__init__.py``)
und ruft :func:`register` mit einem Plugin-Kontext auf. Die Registrierung ist
bewusst schlank: sie registriert nur Tools, Schemas und die ``hermes onair``-CLI.
Teure Importe (Netzwerk, Subprozesse) passieren erst in den Handlern.

Die öffentlichen Klassen/Funktionen bleiben als lazy Re-Exports erhalten, damit
bestehende Importe (``from onair4hermes import HermesPlugin``) weiter
funktionieren, ohne beim Plugin-Laden alle Module zu importieren.
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


def register(ctx: Any) -> None:
    """Hermes-Plugin-Einstiegspunkt: Tools + CLI registrieren.

    Wird vom Hermes-Loader nach dem Import aufgerufen (auch im isolierten
    Capability-Probe von ``hermes plugins validate``). Darf daher weder Netzwerk
    noch OnAir-Hardware voraussetzen.
    """
    from .hermes_plugin import register_cli

    register_cli(ctx)
