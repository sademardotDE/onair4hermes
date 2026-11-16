"""Tests für das onair4hermes Hermes-Plugin.

Laufen ohne laufenden OnAir-Server (API-Calls fallen auf Offline-Fallbacks zurück).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Paket im Quellverzeichnis finden
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from onair4hermes import HermesPlugin, create_plugin, OnAirClient  # noqa: E402


def test_import() -> None:
    """Alle öffentlichen Exporte sind importierbar."""
    assert HermesPlugin is not None
    assert create_plugin is not None
    assert OnAirClient is not None
    print("PASS test_import")


def test_create_plugin() -> None:
    """create_plugin() liefert eine HermesPlugin-Instanz."""
    plugin = create_plugin()
    assert isinstance(plugin, HermesPlugin)
    assert plugin.name == "onair4hermes"
    assert plugin.version == "0.1.0"
    print("PASS test_create_plugin")


def test_get_devices_offline() -> None:
    """get_devices() gibt eine Liste zurück (möglicherweise leer ohne API)."""
    plugin = create_plugin()
    devices = plugin.get_devices()
    assert isinstance(devices, list)
    print(f"PASS test_get_devices_offline ({len(devices)} Geräte)")


def test_get_device_unknown() -> None:
    """get_device() gibt None für unbekannte IDs zurück."""
    plugin = create_plugin()
    assert plugin.get_device("nicht-vorhanden") is None
    print("PASS test_get_device_unknown")


def test_list_modes_offline() -> None:
    """list_modes() gibt eine Liste zurück (möglicherweise leer ohne API)."""
    plugin = create_plugin()
    modes = plugin.list_modes()
    assert isinstance(modes, list)
    print(f"PASS test_list_modes_offline ({len(modes)} Modi)")


def test_status() -> None:
    """status() liefert ein Dict mit den erwarteten Schlüsseln."""
    plugin = create_plugin()
    st = plugin.status()
    assert st["plugin"] == "onair4hermes"
    assert st["version"] == "0.1.0"
    assert "devices" in st
    assert "modes" in st
    assert "config" in st
    assert "onair" in st
    print("PASS test_status")


def test_plugin_json() -> None:
    """plugin.json ist valides JSON mit den erwarteten Feldern."""
    pj = Path(__file__).resolve().parent.parent / "onair4hermes" / "plugin.json"
    data = json.loads(pj.read_text(encoding="utf-8"))
    assert data["id"] == "onair4hermes"
    assert data["name"] == "onair4hermes"
    assert data["version"] == "0.1.0"
    assert data["entry"] == "hermes_plugin.py"
    assert data["factory"] == "create_plugin"
    assert data["register"] == "register"
    print("PASS test_plugin_json")


def test_onair_client_direct() -> None:
    """OnAirClient kann direkt instanziiert werden."""
    client = OnAirClient(Path("/tmp/nonexistent.json"))
    assert client.list_devices() == []
    assert client.list_modes() == []
    assert client.get_device("x") is None
    print("PASS test_onair_client_direct")


if __name__ == "__main__":
    test_import()
    test_create_plugin()
    test_get_devices_offline()
    test_get_device_unknown()
    test_list_modes_offline()
    test_status()
    test_plugin_json()
    test_onair_client_direct()
    print("\nAlle Tests bestanden.")
