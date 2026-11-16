# Aufgabenstand — onair4hermes

Stand: **16.11.2026**, Version **0.2.0** (9 Tools, CLI, Dashboard-Backend,
Desktop-Pane). Doku: [README.md](README.md).

## Erledigt

### Plugin-Kern
- [x] `plugin.yaml` (Manifest v2) mit 9 Tools, `provides_commands: [onair]` und
      Konfigurationsschema (`config`, `base_url`, `token`, `timeout`)
- [x] `plugin.json` (portables agent-plugins-Manifest) ergänzt
- [x] `__init__.py`: Tool-Handler nach Hermes-Vertrag (JSON-String,
      `handler(args, **kwargs)`) – vorher waren die Lambdas mit `**kw` für den
      Dispatcher nicht aufrufbar
- [x] `hermes_plugin.py`: Fassade, `plugin_from_ctx(ctx)` liest die
      Plugin-Settings (vorher wurden `config`/`base_url` ignoriert)
- [x] Echte CLI-Registrierung über `ctx.register_cli_command` (vorher
      `ctx.register_cli`, das es nicht gibt → CLI war tot)
- [x] `onair_client.py`: Token (Bearer), Timeouts, klare HTTP-Fehler
      (inkl. 401-Hinweis), Wertevalidierung, Fallback auf statische Geräte
- [x] `setup.py`: korrektes Package-Mapping (`packages`, `package_dir`),
      `package_data`, Console-Script

### Oberflächen
- [x] Dashboard-Backend `dashboard/plugin_api.py` unter
      `/api/plugins/onair4hermes/` (Proxy, kein CORS-Problem im Renderer)
- [x] `dashboard/manifest.json` (hidden tab, `api`)
- [x] `desktop/plugin.js`: Pane + Status-Chip, Umzug von
      `desktop-plugin.js` nach `desktop/`, `ctx.rest` statt direktem `fetch`,
      StatusChip-Crash (`t` undefiniert) behoben, Offline-/Fehlerzustände,
      Modus-/Frequenz-Eingabe, Live-Spektrum
- [x] Desktop-Loader-Fehler behoben: `useState`/`useEffect`/`useRef` kamen aus
      `react/jsx-runtime` (exportiert keine Hooks) → jetzt aus `react`
      (Fund im Desktop-Log: „does not provide an export named 'useEffect'“);
      Regressionstest ergänzt
- [x] Modus-Namen (`"fm"`, `"FM broadcast"`) werden über `/modes` auf die
      Familien-ID abgebildet (`set_mode`)

### Tests & Doku
- [x] 16 Plugin-Tests mit Mock-OnAir-Server (Client, Token, Tools, CLI,
      Settings-Präzedenz, Manifest-Konsistenz)
- [x] 3 Dashboard-API-Tests (FastAPI TestClient, inkl. 401-Mapping)
- [x] README (Installation, Settings, CLI, Tools, Fehlersuche)
- [x] `hermes plugins validate`: alle Checks grün, inkl.
      „desktop surface | stays inside the plugin SDK surface“
- [x] `hermes plugins doctor onair4hermes`: 9 Tools, Import/Registrierung OK
- [x] `hermes onair status` gegen das laufende OnAir: echte Werte

### Verifiziert
- [x] Live gegen OnAir auf `127.0.0.1:8765`: Status (`Test signal`, FM,
      100 MHz), 1 Gerät, 172 Modi, Telemetrie (locked, SNR ≈ 52 dB,
      Qualität 100 %), Spektrum (64 Bins, max ≈ −36 dBFS)
- [x] `python3 tests/test_plugin.py` → 16/16
- [x] `pytest -p no:syrupy tests/test_plugin.py` → 16 passed
- [x] Dashboard-Venv: `tests/test_dashboard_api.py` → 3/3
- [x] `node --check` für `desktop/plugin.js` (ESM)
- [x] Dashboard-Backend live am laufenden Server (`127.0.0.1:9119`):
      `/api/plugins/onair4hermes/{config,status,devices,spectrum}` → 200
      mit echten OnAir-Daten (Hot-Mount nach Aktivierung)

## Offen / bewusst nicht umgesetzt

- [ ] Desktop-Pane in der laufenden Hermes-Desktop-App sichtbar prüfen:
      Plugin neu laden (⌘K/Ctrl+K → „Reload desktop plugins“) und Pane/Chip
      ansehen. Code, Importe, Syntax und SDK-Lint sind geprüft; die App lief
      während der Umstellung nicht durchgehend (GPU-Crash im Desktop-Log).
- [ ] WebSocket `/api/v1/ws` (Live-Events/Telemetrie statt Polling)
- [ ] Weitere OnAir-Endpunkte: `memories`, `events`, `audio`, `recording`,
      `rotator`, `tx` (bewusst nicht im Manifest, weil nicht Teil des
      Geräte-/Empfangs-Scopes)
- [ ] Multi-Receiver-Umschaltung im UI (API kann `device_index` beim Start,
      das Pane zeigt den aktiven Receiver)

## Umgebung (Referenz)

- OnAir-API: `http://127.0.0.1:8765`, Token in OnAir unter
  *Ansicht → Datenfeeds → Remote-Control-API*
- Plugin-Settings: `plugins.entries.onair4hermes.settings` in
  `~/.hermes/config.yaml`; Token als `ONAIR_API_TOKEN` in `~/.hermes/.env`
- Installiert: `~/.hermes/plugins/onair4hermes` (Default-Profil, für das
  Dashboard) sowie `~/.hermes/profiles/reverser/plugins/onair4hermes` und
  `~/.hermes/profiles/scout/plugins/onair4hermes`; Desktop-Hälfte unter
  `~/.hermes/desktop-plugins/onair4hermes/plugin.js`
- Dashboard-Venv für API-Tests: `/home/fm/ziot/.venv-dashboard-test`
- Hermes-Validator: `hermes plugins validate /home/fm/ziot/onair4hermes`
