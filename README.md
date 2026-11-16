# onair4hermes

Hermes-Plugin für **[OnAir](https://on-air.dev)** (SDR / Funküberwachung). Es
bindet den OnAir-Receiver über die lokale Remote-Control-HTTP-API als
Hermes-Geräte ein: Status, Geräte, Modi, Telemetrie, Spektrum, Start/Stop,
Modus- und Frequenzwechsel – als Tools, als `hermes onair`-CLI, als
Dashboard-Backend und als Desktop-Seite mit Status-Chip und Live-Spektrum.

Aufbau analog zu [`iwfcam4hermes`](../iwfcam4hermes):

| Datei | Zweck |
|---|---|
| `plugin.yaml` | Hermes-Manifest (v2) mit Tools, CLI und Konfigurationsschema |
| `plugin.json` | portables Manifest (agent-plugins.org) |
| `__init__.py` | `register(ctx)`: Tools + CLI registrieren (schlank, ohne Netzwerk) |
| `hermes_plugin.py` | Fassade, Settings-Auflösung und `hermes onair`-CLI |
| `onair_client.py` | HTTP-Client für die OnAir-API (nur Standardbibliothek) |
| `dashboard/plugin_api.py` | Proxy-Backend unter `/api/plugins/onair4hermes/` |
| `desktop/plugin.js` | Hermes-Desktop-Pane + Status-Chip (nutzt `ctx.rest`) |
| `onair_devices.json` | statischer Geräte-Fallback, wenn die API nicht läuft |

## Voraussetzungen

* OnAir läuft und die **Remote-Control-API** ist aktiv:
  *Ansicht → Datenfeeds → Remote-Control-API*, Standard-Port `8765`.
* Optional Token: Wenn in OnAir „Programs on this computer need the token too“
  aktiv ist, den Token unter *Ansicht → Datenfeeds → Remote-Control-API →
  „Token kopieren“* holen und im Plugin hinterlegen (siehe unten).

## Installation

```bash
# Verzeichnis-Plugin in den Hermes-Plugin-Root kopieren
cp -r /home/fm/ziot/onair4hermes ~/.hermes/plugins/onair4hermes
hermes plugins enable onair4hermes
hermes plugins doctor onair4hermes   # optional: Runtime-Checks
```

Für die Desktop-Seite zusätzlich die Desktop-Hälfte kopieren (das
Dashboard-Backend liefert die Daten, deshalb kein direkter API-Zugriff aus dem
Renderer):

```bash
mkdir -p ~/.hermes/desktop-plugins/onair4hermes
cp desktop/plugin.js ~/.hermes/desktop-plugins/onair4hermes/plugin.js
```

Danach in Hermes die Desktop-Plugins neu laden (⌘K/Ctrl+K → „Reload desktop
plugins“). Das Dashboard-Backend wird beim ersten Request automatisch
nachgeladen (Hot-Mount), ein Neustart des Gateways ist nur nötig, wenn das
Plugin erst nach dem Start aktiviert wurde.

> Das Dashboard ist ein maschinenweiter Server und liest die
> `plugins.enabled`-Liste des **Default-Profils** (`~/.hermes/config.yaml`).
> Damit `/api/plugins/onair4hermes/` auch dort antwortet, das Plugin zusätzlich
> in diesem Profil aktivieren (bei profilgebundenen Installationen genügt der
> Eintrag in der jeweiligen Profil-Config nicht).

## Konfiguration

Einstellungen liegen unter
`plugins.entries.onair4hermes.settings` in `~/.hermes/config.yaml` bzw. in der
Hermes-Oberfläche:

| Schlüssel | Typ | Standard | Bedeutung |
|---|---|---|---|
| `config` | str | leer | Pfad zur JSON-Gerätekonfiguration (Fallback) |
| `base_url` | str | `http://127.0.0.1:8765` | Basis-URL der OnAir-API |
| `token` | secret | leer | OnAir-API-Token, landet in `~/.hermes/.env` als `ONAIR_API_TOKEN` |
| `timeout` | float | `5.0` | Timeout je Anfrage (0,5–60 s) |

Der Token wird zur Laufzeit in dieser Reihenfolge aufgelöst: Plugin-Setting →
Umgebungsvariable `ONAIR_API_TOKEN` → leer. Die Basis-URL analog über
`ONAIR_BASE_URL`.

### Statischer Geräte-Fallback

Wenn die OnAir-API nicht erreichbar ist, listet das Plugin die Geräte aus
`onair_devices.json` (oder dem unter `config` gesetzten Pfad):

```json
{
  "devices": [
    {"id": "rig1", "name": "IC-7300", "host": "127.0.0.1", "port": 8765}
  ]
}
```

## Tools

| Tool | Zweck |
|---|---|
| `onair_list_devices` | Radios/Quellen auflisten |
| `onair_list_modes` | verfügbare Decoder-Modi auflisten |
| `onair_status` | Receiver-Status (Gerät, Modus, Frequenz, Laufzeit) |
| `onair_telemetry` | Telemetrie des aktiven Modus (SNR, Lock, Qualität, RDS …) |
| `onair_spectrum` | Spektrum als dBFS-Bins (`bins` 16–4096) |
| `onair_start` | Receiver starten (optional `device_index`) |
| `onair_stop` | Receiver stoppen |
| `onair_set_mode` | Modus wechseln (`family`, optional `sub`) |
| `onair_set_frequency` | Frequenz setzen (`hz` **oder** `mhz`) |

Alle Tools liefern JSON-Strings mit `ok`, bei Fehlern zusätzlich `error` und –
falls die API geantwortet hat – `status` (HTTP-Code).

## CLI

```bash
hermes onair status
hermes onair devices
hermes onair modes
hermes onair device onair-device-0
hermes onair telemetry
hermes onair spectrum --bins 128
hermes onair start --device 0
hermes onair stop
hermes onair mode 7 --sub ft8
hermes onair freq --mhz 100
hermes onair freq --hz 100000000
```

`--config PFAD` und `--base-url URL` überschreiben die Plugin-Settings pro
Aufruf.

## Dashboard und Desktop

* `dashboard/plugin_api.py` wird unter `/api/plugins/onair4hermes/` gemountet
  und proxyt `status`, `devices`, `modes`, `telemetry`, `spectrum`, `start`,
  `stop`, `mode`, `frequency`, `config`.
* `desktop/plugin.js` registriert ein Pane (`panes`, rechts, 360 px) und einen
  Status-Chip (`statusBar.right`). Beide pollen über `ctx.rest`; der Renderer
  spricht nie direkt mit OnAir (die API sendet keine CORS-Header).

## Tests

```bash
# Plugin-Tests (Mock-OnAir, ohne laufendes OnAir)
python3 -m pytest -p no:syrupy -q tests/test_plugin.py

# oder ohne pytest
python3 tests/test_plugin.py

# Dashboard-Backend (braucht FastAPI + httpx, z. B. im Dashboard-Venv)
/home/fm/ziot/.venv-dashboard-test/bin/python tests/test_dashboard_api.py
```

## Fehlersuche

* **`HTTP 401` / `403`** – Token fehlt oder ist falsch. Token in OnAir kopieren
  und als Plugin-Setting `token` eintragen (oder `ONAIR_API_TOKEN` in
  `~/.hermes/.env`). Der Fehlertext nennt den Pfad.
* **`OnAir API nicht erreichbar`** – läuft OnAir, ist die Remote-Control-API
  aktiviert, stimmt `base_url`? `hermes onair status` zeigt die verwendete URL.
* **Desktop-Pane bleibt offline** – ist das Plugin in Hermes aktiviert
  (`hermes plugins list`), und wurde das Desktop-Plugin neu geladen? Das
  Backend antwortet unter `/api/plugins/onair4hermes/config`.
* **CORS** – direkte `fetch`-Aufrufe aus dem Electron-Renderer zur OnAir-API
  schlagen fehl; deshalb der Proxy. Nicht auf Direktzugriff zurückbauen.

## Lizenz

GPL-3.0-or-later (basiert auf OnAir, siehe [OnAir-Lizenz](https://on-air.dev)).
