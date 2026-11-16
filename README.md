# onair4hermes

Hermes-Plugin für OnAir (SDR/Funküberwachung). Stellt OnAir-Modi und -Geräte
als Hermes-Geräte bereit und erlaubt Statusabfrage sowie Steuerung aus dem
Hermes-System heraus.

Aufbau analog zu `iwfcam4hermes`:

* `hermes_plugin.py` — HermesPlugin-Fassade, `create_plugin()`, `register()`
* `plugin.json` — Hermes-Plugin-Manifest
* `onair_client.py` — Anbindung an OnAir (lokaler API / CLI / Plugin-Host)

## Installation

```bash
pip install -e /home/fm/ziot/onair4hermes
```

## Lizenz

GPL v3 oder später (basiert auf OnAir, siehe [OnAir-Lizenz](https://on-air.dev)).
