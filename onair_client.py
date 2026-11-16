"""Client-Anbindung an OnAir für das Hermes-Plugin onair4hermes.

Nutzt die OnAir Remote-Control HTTP API (standardmäßig ``127.0.0.1:8765``), um
OnAir aus Hermes heraus zu steuern und Status abzufragen. Keine externen
Pflicht-Abhängigkeiten (nur Python-Standardbibliothek).

Die API verlangt je nach OnAir-Einstellung einen Bearer-Token
("Programs on this computer need the token too"). Der Token wird in dieser
Reihenfolge aufgelöst:

1. Argument ``token`` (Plugin-Setting, siehe ``plugin.yaml``),
2. Umgebungsvariable ``ONAIR_API_TOKEN`` (z. B. aus ``~/.hermes/.env``).

Basis-URL: Argument ``base_url``, sonst ``ONAIR_BASE_URL``, sonst
``http://127.0.0.1:8765``.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_TIMEOUT = 5.0
BASE_URL_ENV = "ONAIR_BASE_URL"
TOKEN_ENV = "ONAIR_API_TOKEN"

API_ROOT = "/api/v1"
SPECTRUM_MIN_BINS = 16
SPECTRUM_MAX_BINS = 4096

__all__ = [
    "BASE_URL_ENV",
    "DEFAULT_BASE_URL",
    "DEFAULT_TIMEOUT",
    "OnAirClient",
    "OnAirError",
    "SPECTRUM_MAX_BINS",
    "SPECTRUM_MIN_BINS",
    "TOKEN_ENV",
]


class OnAirError(RuntimeError):
    """Fehler beim Zugriff auf die OnAir Remote-Control API.

    ``status`` ist der HTTP-Status, sofern die API geantwortet hat (z. B. 401
    bei fehlendem/falschem Token), sonst ``None`` (Verbindungsfehler).
    """

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def _clamp_timeout(value: Any) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT
    return max(0.5, min(timeout, 60.0))


class OnAirClient:
    """Client für die OnAir Remote-Control HTTP API."""

    def __init__(
        self,
        config_path: str | Path | None = None,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.config_path = Path(config_path).expanduser() if config_path else None
        resolved_base = (base_url or "").strip() or os.environ.get(BASE_URL_ENV, "").strip()
        self.base_url = (resolved_base or DEFAULT_BASE_URL).rstrip("/")
        self._token = (token or "").strip() or None
        self.timeout = _clamp_timeout(timeout)
        self._devices: list[dict[str, Any]] | None = None
        self._modes: list[dict[str, Any]] | None = None

    # --- Konfiguration ------------------------------------------------------

    @property
    def token(self) -> str:
        """Aktiver API-Token (Argument vor ``ONAIR_API_TOKEN``)."""
        return self._token or os.environ.get(TOKEN_ENV, "").strip()

    def _load_config(self) -> dict[str, Any]:
        """Statische Gerätekonfiguration lesen (leeres Dict bei Fehlern)."""
        if self.config_path is None or not self.config_path.exists():
            return {}
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    # --- HTTP-Hilfsfunktionen ----------------------------------------------

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        """Eine API-Anfrage ausführen und die JSON-Antwort zurückgeben.

        Raises:
            OnAirError: bei Verbindungsfehlern, HTTP-Fehlern und ungültigem JSON.
        """
        url = f"{self.base_url}{path}"
        body: bytes | None = None
        headers = {"Accept": "application/json"}

        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise OnAirError(self._http_error_message(method, path, exc), status=exc.code) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise OnAirError(
                f"OnAir API nicht erreichbar unter {self.base_url} ({reason}). "
                "Läuft OnAir und ist die Remote-Control-API aktiviert?"
            ) from None

        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OnAirError(
                f"OnAir API {method} {path}: ungültige JSON-Antwort ({exc})"
            ) from None

    def _http_error_message(self, method: str, path: str, exc: urllib.error.HTTPError) -> str:
        detail = ""
        try:
            payload = json.loads(exc.read().decode("utf-8", "replace"))
            if isinstance(payload, dict):
                detail = str(payload.get("error") or payload.get("detail") or "")
        except Exception:  # noqa: BLE001 - Fehlertext ist nur Kosmetik
            detail = ""
        suffix = f": {detail}" if detail else ""
        hint = ""
        if exc.code in (401, 403):
            hint = (
                " (Token prüfen: OnAir > Datenfeeds > Remote-Control-API > "
                "Token kopieren, dann in den Plugin-Einstellungen als Token "
                "eintragen oder in ~/.hermes/.env als ONAIR_API_TOKEN ablegen)"
            )
        return f"OnAir API {method} {path}: HTTP {exc.code}{suffix}{hint}"

    def _get(self, path: str) -> Any:
        return self._request("GET", path)

    def _post(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        result = self._request("POST", path, payload if payload is not None else {})
        return result if isinstance(result, dict) else {}

    # --- Geräte / Modi ------------------------------------------------------

    def list_devices(self) -> list[dict[str, Any]]:
        """Liste aller OnAir-Geräte (Radios/Quellen).

        Fällt bei nicht erreichbarer API auf die statische Konfigurationsdatei
        zurück; ohne beides kommt eine leere Liste.
        """
        if self._devices is not None:
            return self._devices

        try:
            api_devices = self._get(f"{API_ROOT}/devices")
        except OnAirError:
            api_devices = None

        if isinstance(api_devices, list) and api_devices:
            self._devices = [self._device_from_api(item, index) for index, item in enumerate(api_devices)]
        else:
            self._devices = self._devices_from_config()
        return self._devices

    @staticmethod
    def _device_from_api(item: Any, index: int) -> dict[str, Any]:
        data = item if isinstance(item, dict) else {}
        return {
            "id": f"onair-device-{data.get('index', index)}",
            "index": data.get("index", index),
            "name": data.get("name") or f"OnAir Device {index}",
            "type": "radio",
            "kind": data.get("kind", ""),
            "board": data.get("board", ""),
            "serial": data.get("serial", ""),
            "selected": bool(data.get("selected", False)),
            "gain_min_db": data.get("gainMinDb"),
            "gain_max_db": data.get("gainMaxDb"),
            "min_freq_hz": data.get("minFreqHz"),
            "max_freq_hz": data.get("maxFreqHz"),
            "source": "onair-api",
        }

    def _devices_from_config(self) -> list[dict[str, Any]]:
        config = self._load_config()
        configured = config.get("devices")
        if not isinstance(configured, list):
            return []
        devices: list[dict[str, Any]] = []
        for index, item in enumerate(configured):
            if not isinstance(item, dict):
                continue
            devices.append(
                {
                    "id": str(item.get("id") or f"onair-{index}"),
                    "name": str(item.get("name") or f"OnAir {index}"),
                    "type": str(item.get("type") or "onair"),
                    "host": str(item.get("host") or "localhost"),
                    "port": item.get("port", 0),
                    "mode": str(item.get("mode") or ""),
                    "frequency_hz": item.get("frequency_hz", 0),
                    "configured": True,
                    "source": "config",
                }
            )
        return devices

    def list_modes(self) -> list[dict[str, Any]]:
        """Liste aller von OnAir angebotenen Decoder-Modi."""
        if self._modes is not None:
            return self._modes

        try:
            api_modes = self._get(f"{API_ROOT}/modes")
        except OnAirError:
            api_modes = None

        if isinstance(api_modes, list):
            self._modes = [
                {
                    "id": str(item.get("id") or item.get("family") or f"mode-{index}"),
                    "name": str(item.get("name") or item.get("family") or f"Mode {index}"),
                    "family": item.get("family", ""),
                    "sub": item.get("sub", ""),
                    "source": "onair-api",
                }
                for index, item in enumerate(api_modes)
                if isinstance(item, dict)
            ]
        else:
            self._modes = []
        return self._modes

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        for device in self.list_devices():
            if device["id"] == device_id:
                return device
        return None

    # --- Status -------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Aktueller OnAir-Status; bei Offline ein sauberes Offline-Dict."""
        try:
            api_status = self._get(f"{API_ROOT}/status")
        except OnAirError as exc:
            return {"source": "offline", "running": False, "error": str(exc)}
        if not isinstance(api_status, dict):
            return {
                "source": "offline",
                "running": False,
                "error": "OnAir API lieferte einen unerwarteten Status",
            }
        return {"source": "onair-api", **api_status}

    def telemetry(self) -> dict[str, Any]:
        """Telemetrie des aktiven Modus."""
        result = self._get(f"{API_ROOT}/telemetry")
        if not isinstance(result, dict):
            raise OnAirError("OnAir API lieferte eine unerwartete Telemetrie-Antwort")
        return result

    def spectrum(self, bins: int = 512) -> dict[str, Any]:
        """Aktuelles Spektrum (dBFS pro Bin)."""
        count = self._normalize_bins(bins)
        result = self._get(f"{API_ROOT}/spectrum?bins={count}")
        if not isinstance(result, dict):
            raise OnAirError("OnAir API lieferte eine unerwartete Spektrum-Antwort")
        return result

    @staticmethod
    def _normalize_bins(bins: Any) -> int:
        try:
            count = int(bins)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"bins muss eine Ganzzahl sein, nicht {bins!r}") from exc
        if not SPECTRUM_MIN_BINS <= count <= SPECTRUM_MAX_BINS:
            raise ValueError(
                f"bins muss zwischen {SPECTRUM_MIN_BINS} und {SPECTRUM_MAX_BINS} liegen"
            )
        return count

    # --- Steuerung ----------------------------------------------------------

    def start(self, device_index: int | None = None) -> bool:
        """OnAir-Receiver starten (optional mit Geräteindex)."""
        payload: dict[str, Any] = {}
        if device_index is not None:
            try:
                index = int(device_index)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"device_index muss eine Ganzzahl sein, nicht {device_index!r}") from exc
            if index < 0:
                raise ValueError("device_index darf nicht negativ sein")
            payload["device"] = index
        self._post(f"{API_ROOT}/start", payload)
        return True

    def stop(self) -> bool:
        """OnAir-Receiver stoppen."""
        self._post(f"{API_ROOT}/stop")
        return True

    def set_mode(self, family: int | str, sub: str | None = None) -> bool:
        """OnAir-Modus wechseln (OnAir verlangt einen gestoppten Receiver).

        ``family`` darf eine numerische Familien-ID oder ein Modus-Name aus
        :meth:`list_modes` sein (z. B. ``7``, ``"fm"`` oder ``"FM broadcast"``).
        Namen werden über die Modus-Liste auf die Familien-ID abgebildet.
        """
        if family is None or (isinstance(family, str) and not family.strip()):
            raise ValueError("family fehlt")

        resolved: int | str = family
        if isinstance(family, str) and not family.strip().lstrip("-").isdigit():
            wanted = family.strip().lower()
            for mode in self.list_modes():
                candidates = {
                    str(mode.get("id", "")).lower(),
                    str(mode.get("family", "")).lower(),
                    str(mode.get("name", "")).lower(),
                }
                if wanted in candidates:
                    resolved = mode.get("family") or family
                    if sub is None and mode.get("sub"):
                        sub = str(mode["sub"])
                    break

        payload: dict[str, Any] = {"family": resolved}
        if sub is not None and str(sub).strip():
            payload["sub"] = str(sub).strip()
        self._post(f"{API_ROOT}/mode", payload)
        return True

    def set_frequency(self, hz: int | None = None, mhz: float | None = None) -> bool:
        """Frequenz setzen – genau eine der beiden Angaben."""
        if hz is None and mhz is None:
            raise ValueError("hz oder mhz erforderlich")
        if hz is not None and mhz is not None:
            raise ValueError("hz und mhz dürfen nicht gleichzeitig gesetzt werden")

        payload: dict[str, Any]
        if hz is not None:
            try:
                value = int(hz)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"hz muss eine Ganzzahl sein, nicht {hz!r}") from exc
            if value <= 0:
                raise ValueError("hz muss größer als 0 sein")
            payload = {"hz": value}
        else:
            try:
                mhz_value = float(mhz)  # type: ignore[arg-type]
            except (TypeError, ValueError) as exc:
                raise ValueError(f"mhz muss eine Zahl sein, nicht {mhz!r}") from exc
            if mhz_value <= 0:
                raise ValueError("mhz muss größer als 0 sein")
            payload = {"mhz": mhz_value}

        self._post(f"{API_ROOT}/frequency", payload)
        return True

    def reload(self) -> None:
        """Caches für Geräte/Modi verwerfen."""
        self._devices = None
        self._modes = None
