# VASS-Plugin-Entwicklungsleitfaden

Technisches Dokument, das das Kommunikationsprotokoll zwischen Plugins und dem
VASS-PluginServer sowie die Regeln für die Erstellung neuer Plugins beschreibt.

Code-Verweise:

- Server: `src/plugin_server.py` (Daemon-Thread `PluginServer`)
- Ereignisausgabe: `src/main.py` (Broadcast von `state` und `audio`)
- Deklarative UI-Darstellung: `src/gui.py` (Zeile 3367+)
- Beispiel-Plugins: `plugins/internal/noise_auto_pause/`, `plugins/external/news_publisher/`

---

## 1. Architektur

VASS stellt einen **TCP-Server auf `localhost:8765`** bereit, der als
Daemon-Thread innerhalb des Hauptprozesses läuft (`PluginServer`). Plugins sind
**eigenständige Prozesse** (der Autostart startet sie mit `subprocess.Popen` auf
`plugin.py`), die sich über einen Socket mit dem Server verbinden.

Der Server hat zwei Aufgaben:

- **Führt Befehle aus**, die von Plugins empfangen werden (TTS, Benachrichtigungen, KI, VASS-Zustand …).
- **Sendet Ereignisse per Broadcast** an die Plugins, die sie angefordert haben
  (`state` bei jeder Zustandsänderung, `audio` bei jedem Audio-Frame).

```
┌──────────────┐   broadcast (state/audio)   ┌──────────────────┐
│   VASS app   │ ───────────────────────────▶ │  Plugin (process)│
│  PluginServer│ ◀─────────────────────────── │                  │
│  :8765 (TCP) │      cmd + request_id        │                  │
└──────────────┘       resp. *_response       └──────────────────┘
```

## 2. Transport und Protokoll

- **Host/Port:** `localhost:8765` (nur im Code konfigurierbar).
- **Format:** ein JSON-Objekt pro Zeile, jede Nachricht wird durch `\n`
  beendet (`json.dumps(...) + "\n"`, `ensure_ascii=False`, UTF-8).
- **Puffern:** Der Server puffert eingehende Daten und trennt sie anhand von
  `\n`; Plugins müssen dasselbe auf der Client-Seite tun.
- **Identifikation:** Anforderungsnachrichten enthalten eine `request_id`
  (UUID), die in der Antwort wiederholt wird; der Client verwendet sie, um
  asynchrone Antworten zuzuordnen.
- **Debugging:** Mit `python vass.py --debug` protokolliert der Server
  empfangene Nachrichten (`<= received: ...`, `execute: ...`).

## 3. Handshake

Unmittelbar nach dem Verbindungsaufbau muss das Plugin die `hello`-Nachricht
senden:

```json
{"type": "hello", "name": "my_plugin", "version": "1.0.0",
 "min_app": "0.8.0", "subscribe": ["state", "audio"]}
```

| Feld | Erforderlich | Beschreibung |
|---|---|---|
| `type` | ja | `"hello"` |
| `name` | ja | Plugin-Identifikator (muss mit dem Ordner und dem Manifest übereinstimmen) |
| `version` | ja | Plugin-Version |
| `min_app` | ja | Mindestens erforderliche VASS-Version; ist die App-Version niedriger, antwortet der Server mit `error` und schließt die Verbindung |
| `subscribe` | nein | Liste der zu empfangenden Broadcast-Ereignistypen (`"state"`, `"audio"`) |

Python-Beispiel:

```python
hello = json.dumps({
    "type": "hello",
    "name": manifest["name"],
    "version": manifest["version"],
    "min_app": manifest["min_app"],
    "subscribe": manifest["subscriptions"],
}) + "\n"
self._sock.sendall(hello.encode("utf-8"))
```

## 4. Nachrichten vom Plugin → Server

Alle Befehle haben die Form:

```json
{"type": "cmd", "cmd": "<command>", ...parameters}
```

### 4.1 Befehle ohne Antwort (fire-and-forget)

| cmd | Parameter | Wirkung |
|---|---|---|
| `set_state` | `state` (z. B. `"listening"`, `"paused"`) | Setzt den VASS-Zustand. Bei `state="listening"` wird zusätzlich der Störgeräuschpegel (Noise Floor) der Spracherkennung zurückgesetzt |
| `tts_enqueue` | `text`, `speed` (Standard `0.9`) | Spricht den Text. Der Text wird **automatisch** in die App-Sprache übersetzt, wenn er nicht Englisch ist; die TTS-Warteschlange verwendet `defer_if_busy=True` |
| `notify` | `text`, `priority` (Standard `5`), `data` | Zeigt eine Desktop-Benachrichtigung an. Der Text wird wie oben übersetzt |
| `ui_register` | `schema` (siehe §6) | Registriert eine dem Plugin zugeordnete deklarative UI |
| `ui_state` | `values` (dict key→value) | Aktualisiert den Plugin-UI-Zustand (wird von der GUI jede 1 s per Polling abgefragt) |

### 4.2 Request/Response-Befehle

Sie müssen `request_id` enthalten; der Server antwortet mit dem **Typ**
`*_response` unter Verwendung derselben `request_id`.

| cmd | Parameter | Antworttyp | Antwortfelder |
|---|---|---|---|
| `tts_to_file` | `text`, `output_path`, `speed` | `tts_file_response` | `duration_sec`, `output_path` |
| `ai_query` | `prompt`, `temperature` (0.1), `max_tokens` (300), `extra_body` | `ai_response` | `response` (Zeichenkette) |
| `chat_text` | `prompt` | `chat_response` | `response` (durchläuft die gesamte VASS-Pipeline: Speicher, Profil, Tools) |
| `idle_check` | — | `idle_response` | `input_idle_seconds` |
| `resource_check` | — | `resource_response` | `cpu`, `ram`, `gpu`, `vram` |
| `conversation_history` | `limit` (Standard 10) | `history_response` | `history` (Liste von `{"role": …}`) |
| `app_info` | — | `app_info_response` | `language`, `version`, `debug`, `state` |
| `rss_items` | `limit` (Standard 10) | `rss_response` | `items` (Liste von `{title, source, summary, guid, link, pubDate}`) |
| `ui_list` | — | `ui_list_response` | `uis` (Liste der registrierten Plugin-Namen) |

Wichtige Hinweise:

- `ai_query` und `chat_text` laufen in einem eigenen Thread: Die Antwort kann
  später eintreffen (den Event-Loop nicht an `recv` blockieren).
- `ai_query` wird durch einen Semaphor serialisiert (jeweils ein KI-Aufruf).
- Ist der OpenAI-Client nicht verfügbar, antwortet `ai_query` mit einer
  JSON-Zeichenkette `{"error": …}` innerhalb von `response`.
- `tts_to_file` erzeugt die WAV-Datei am angegebenen Pfad und gibt die Dauer
  in Sekunden zurück.

Client-Muster für synchrone Anfragen:

```python
def _send_and_wait(self, cmd, params, expected_type, timeout=120):
    rid = str(uuid.uuid4())
    params = params or {}
    params["request_id"] = rid
    self._send_cmd(cmd, params)
    deadline = time.time() + timeout
    while time.time() < deadline:
        with self._lock:
            resp = self._pending_responses.pop(rid, None)
        if resp and resp.get("type") == expected_type:
            return resp
        time.sleep(0.1)
    return None
```

## 5. Nachrichten vom Server → Plugin

### 5.1 Broadcasts (nur an abonnierte Plugins)

| Typ | Felder | Wann |
|---|---|---|
| `state` | `state`, `prev`, `source` | Bei jeder VASS-Zustandsänderung (`listening`, `paused`, `playing`, …) |
| `audio` | `rms`, `noise_floor`, `auto_paused`, `listening` | Bei jedem erfassten Audio-Frame |

### 5.2 Direkte Nachrichten

| Typ | Felder | Wann |
|---|---|---|
| `error` | `msg` | Ablehnung des Handshakes (`min_app`-Version nicht erfüllt) oder Serverfehler |
| `cmd` mit `cmd="ui_action"` | `action` (`{key, event, values, selected}`) | Der Benutzer interagiert über die GUI mit der deklarativen UI des Plugins |

Das `_on_message` des Plugins muss mindestens die Typen `error`, `audio`,
`state` und die `cmd`-Befehle (`ui_action`) behandeln, dem vorhandenen Muster
folgend:

```python
def _on_message(self, msg):
    msg_type = msg.get("type", "")
    if msg_type == "error":
        print(f"[Plugin] Server error: {msg.get('msg', 'unknown')}")
    elif msg_type == "cmd" and msg.get("cmd") == "ui_action":
        self._handle_ui_action(msg.get("action") or {})
    elif msg_type in ("ai_response", "tts_file_response", "rss_response",
                      "chat_response", "app_info_response", ...):
        rid = msg.get("request_id", "")
        if rid:
            with self._lock:
                self._pending_responses[rid] = msg
```

## 6. Deklarative UI (`ui_register`)

Das Plugin beschreibt seine Oberfläche mit einem JSON-Schema; die GUI rendert
sie automatisch. Der Zustand fließt in beide Richtungen:

- **Plugin → GUI:** `ui_state` mit `values`.
- **GUI → Plugin:** `ui_action`, wenn der Benutzer Schaltflächen drückt oder Werte ändert.

Schema:

```json
{
  "id": "my_plugin",
  "title_it": "Italian title",
  "title": "English title",
  "sections": [
    {
      "title_it": "Section title (IT)",
      "title": "Section title",
      "rows": [
        {"kind": "toggle", "key": "flag",   "label_it": "Attivo", "label": "Enabled", "value": true, "instant": true},
        {"kind": "slider", "key": "level",  "label_it": "Livello", "label": "Level",  "min": 0, "max": 100, "value": 50, "instant": false},
        {"kind": "text",   "key": "name",   "label_it": "Nome",    "label": "Name",   "value": ""},
        {"kind": "combo",  "key": "mode",   "label_it": "Modo",    "label": "Mode",   "options": ["a", "b", "c"], "value": "a"},
        {"kind": "button", "key": "run",    "label_it": "Esegui",  "label": "Run"},
        {"kind": "list",   "key": "items",  "label_it": "Elementi", "label": "Items",
         "columns": [{"key": "name", "label_it": "Nome", "label": "Name"}],
         "items": [{"id": "1", "name": "uno"}]},
        {"kind": "label",  "key": "status", "text": "ready"}
      ]
    }
  ]
}
```

Zeilenarten:

| kind | Spezifische Eigenschaften | Gesendetes Ereignis |
|---|---|---|
| `toggle` | `value` (bool), `instant` (bool) | `toggle` |
| `slider` | `min`, `max`, `value`, `instant` | `slider` |
| `text` | `value` | — (in `values` enthalten, wenn eine Schaltfläche geklickt wird) |
| `combo` | `options[]`, `value` | — (dasselbe) |
| `button` | — | `button` |
| `list` | `columns[]`, `items[]` (mit `id`) | `select` mit `selected` = Element-ID |
| `label` | `text` | — |

Synchronisierungsregeln:

- `toggle`/`slider` mit `instant:true` senden die zugehörige `ui_action` sofort.
- „Gepufferte" Widgets (`text`, `combo`, nicht-instantane Toggles/Slider) werden
  in `values` gesammelt und zusammen mit der Schaltflächenaktion gesendet.
- Die GUI fragt `get_plugin_uis()` jede Sekunde per Polling ab und wendet den
  vom Plugin gesendeten Zustand (`ui_state`) an.

## 7. Konfiguration und GUI-Einstellungen

Jedes Plugin besitzt eine eigene `settings.ini` (wird aus
`settings.example.ini` kopiert, wenn sie fehlt). Das Plugin liest sie mit seiner
eigenen `_load_config()`.

**Wichtige Regel:** Die Abschnitte `[gui.<field>]` definieren die Felder, die im
GUI-Konfigurationsdialog angezeigt werden. Jedes Feld gibt an, in welchem
„normalen" INI-Abschnitt der Wert geschrieben wird (`section`). GUI-Keys dürfen
niemals innerhalb normaler Abschnitte platziert werden.

```ini
[schedule]
interval_hours = 6

[gui.interval_hours]
type = dropdown
options = 1|2|4|6|8|12|24
label = Interval (hours)
label_it = Intervallo (ore)
section = schedule
```

Unterstützte Feldtypen (`get_plugin_config` in `plugin_server.py`):

| type | Eigenschaften |
|---|---|
| `slider` | `min_value`, `max_value`, `step`, `decimals` |
| `dropdown` | `options` (durch Pipe getrennt) |
| `text` | — |
| `note` | `note` / `note_<lang>` (nur informativ, schreibt keine Werte) |

Jedes Feld akzeptiert `label` und `label_<lang>` zur Lokalisierung sowie
`section`, um den Ziel-INI-Abschnitt anzugeben.

Die GUI schreibt Werte mit
`PluginServer.set_plugin_value(name, section, key, value)`;
das Plugin muss sie neu laden (z. B. durch erneutes Lesen der INI bei der
nächsten Verwendung).

## 8. Plugin-Struktur und Lebenszyklus

### Verzeichnisstruktur

```
plugins/
├── plugins.json                  # enabled/disabled (gitignored)
├── plugins.json.example
├── internal/<name>/              # System-Plugins — NICHT entfernbar
│   ├── plugin.py
│   ├── plugin_manifest.json
│   ├── settings.ini
│   └── settings.example.ini
└── external/<name>/              # Benutzer-Plugins — aus der GUI entfernbar
    └── (same files)
```

### `plugin_manifest.json`

```json
{
  "name": "my_plugin",
  "version": "1.0.0",
  "min_app": "0.8.0",
  "platform": "*",
  "description": "English description",
  "description_it": "Descrizione in italiano",
  "subscriptions": ["state", "audio"],
  "depends_on": ["rss_reader"]
}
```

| Feld | Beschreibung |
|---|---|
| `name` | Muss mit dem Plugin-Ordner übereinstimmen |
| `version` | Plugin-Version |
| `min_app` | Mindestens erforderliche VASS-Version |
| `platform` | `"*"` |
| `description` / `description_<lang>` | Lokalisierte Beschreibungen |
| `subscriptions` | Zu empfangende Broadcast-Typen (`state`, `audio`) |
| `depends_on` | Liste der Plugins, die vor dem Laden aktiviert sein müssen |

### `plugins/plugins.json`

```json
{
  "port": 8765,
  "plugins": {
    "my_plugin": {"enabled": true}
  }
}
```

### Lebenszyklus

1. Beim Start startet `PluginServer.run()` die Plugins mit
   `enabled: true` automatisch und sortiert sie nach `depends_on`
   (Abhängigkeiten starten zuerst; ein Plugin mit fehlenden Abhängigkeiten
   bleibt `blocked`).
2. Jedes Plugin startet als `subprocess.Popen([python, plugin.py], cwd=<dir>)`.
3. Es werden höchstens **2 Startversuche** unternommen (danach wird der Zähler zurückgesetzt).
4. `enable_plugin`/`disable_plugin`/`stop_plugin`/`start_plugin` steuern den
   Laufzeitzustand; `remove_plugin` (nur extern) löscht das Verzeichnis und den
   Konfigurationseintrag.
5. `get_plugins_status` liefert für jedes Plugin: `enabled`, `running`,
   `status` (`running|blocked|error|stopped|disabled`), `missing_deps`.

## 9. Schritt-für-Schritt-Anleitung: ein Plugin erstellen

Erstelle ein minimales Plugin, das den VASS-Zustand und die KI verwendet.

### Schritt 1 — Ordner und Manifest

Erstelle `plugins/external/hello_plugin/` mit:

`plugin_manifest.json`:

```json
{
  "name": "hello_plugin",
  "version": "1.0.0",
  "min_app": "0.8.0",
  "platform": "*",
  "description": "Example plugin",
  "description_it": "Plugin di esempio",
  "subscriptions": ["state"],
  "depends_on": []
}
```

### Schritt 2 — Einstellungen

`settings.example.ini`:

```ini
[general]
greeting = Hello from VASS

[gui.greeting]
type = text
label = Greeting message
label_it = Messaggio di saluto
section = general
```

### Schritt 3 — `plugin.py`

Vollständiges Grundgerüst nach dem Muster der vorhandenen Plugins:

```python
"""Example VASS plugin — standalone process connected via TCP socket."""
import json
import os
import socket
import threading
import time
import uuid
import configparser


class HelloPlugin:
    def __init__(self):
        self._host = "localhost"
        self._port = 8765
        self._sock = None
        self._buf = b""
        self._lock = threading.Lock()
        self._pending_responses = {}
        self._config = self._load_config()

    def _load_config(self):
        cfg = configparser.ConfigParser()
        ini = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.ini")
        if not os.path.exists(ini):
            ex = ini.replace("settings.ini", "settings.example.ini")
            if os.path.exists(ex):
                import shutil
                shutil.copy(ex, ini)
        if os.path.exists(ini):
            cfg.read(ini, encoding="utf-8")
        return {"greeting": cfg.get("general", "greeting", fallback="Ciao da VASS")}

    def _load_manifest(self):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "plugin_manifest.json"), encoding="utf-8") as f:
            return json.load(f)

    def run(self):
        manifest = self._load_manifest()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self._sock.connect((self._host, self._port))
        except ConnectionRefusedError:
            print("[HelloPlugin] VASS not running. Exiting.")
            return

        hello = json.dumps({
            "type": "hello", "name": manifest["name"],
            "version": manifest["version"], "min_app": manifest["min_app"],
            "subscribe": manifest["subscriptions"],
        }) + "\n"
        self._sock.sendall(hello.encode("utf-8"))

        # Greet as soon as connected
        threading.Thread(target=self._greet, daemon=True).start()

        while True:
            try:
                data = self._sock.recv(4096)
            except (ConnectionResetError, OSError):
                break
            if not data:
                break
            self._buf += data
            while b"\n" in self._buf:
                line, self._buf = self._buf.split(b"\n", 1)
                try:
                    msg = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                self._on_message(msg)

    def _on_message(self, msg):
        msg_type = msg.get("type", "")
        if msg_type == "error":
            print(f"[HelloPlugin] Server error: {msg.get('msg')}")
        elif msg_type == "state":
            print(f"[HelloPlugin] State -> {msg.get('state')}")
        elif msg_type == "cmd" and msg.get("cmd") == "ui_action":
            self._handle_ui_action(msg.get("action") or {})
        else:
            rid = msg.get("request_id", "")
            if rid:
                with self._lock:
                    self._pending_responses[rid] = msg

    def _greet(self):
        time.sleep(2)
        self._send_cmd("tts_enqueue", {"text": self._config["greeting"]})

    def _send_cmd(self, cmd, params=None):
        msg = json.dumps({"type": "cmd", "cmd": cmd, **(params or {})}) + "\n"
        try:
            self._sock.sendall(msg.encode("utf-8"))
        except Exception as e:
            print(f"[HelloPlugin] Send failed: {e}")

    def _send_and_wait(self, cmd, params, expected_type, timeout=120):
        rid = str(uuid.uuid4())
        params = params or {}
        params["request_id"] = rid
        self._send_cmd(cmd, params)
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                resp = self._pending_responses.pop(rid, None)
            if resp and resp.get("type") == expected_type:
                return resp
            time.sleep(0.1)
        return None

    def _handle_ui_action(self, action):
        key = action.get("key", "")
        if key == "speak" and action.get("event") == "button":
            self._greet()


if __name__ == "__main__":
    HelloPlugin().run()
```

### Schritt 4 — Aktivieren und testen

1. Füge in `plugins/plugins.json` hinzu:
   ```json
   "hello_plugin": {"enabled": true}
   ```
2. Starte VASS (`python vass.py --debug`). Der Server startet das Plugin
   automatisch; im Log siehst du bei jeder Zustandsänderung `Hello from 'hello_plugin'` und `State -> listening`.
3. Verifiziere das Audio: Das Plugin spricht die konfigurierte Nachricht.

## 10. Debugging und Fehlerbehebung

| Symptom | Wahrscheinliche Ursache | Lösung |
|---|---|---|
| `Port 8765 already in use` | Eine andere VASS-Instanz läuft | Die andere Instanz schließen |
| `App version X < required Y` | `min_app` im Manifest übersteigt die VASS-Version | `min_app` senken oder VASS aktualisieren |
| Plugin `error` mit `socket_missing`/`process_missing` | Prozess lebt, aber Socket nicht verbunden (oder umgekehrt) | `log.txt` des Plugins prüfen; es neu starten |
| Keine Antwort auf `ai_query` | OpenAI-Client nicht verfügbar oder Timeout | `[ai]` in `settings.ini` prüfen; `timeout` erhöhen |
| Plugin startet nicht | Deaktivierte Abhängigkeiten | Die Plugins in `depends_on` aktivieren |
| Codeänderungen werden nicht übernommen | Prozess läuft noch | Das Plugin aus der GUI neu starten |
| TTS-Text wird unerwartet übersetzt | `tts_enqueue`/`notify` übersetzen in die App-Sprache, wenn ≠ EN | `tts_to_file` verwenden, um die Übersetzung zu umgehen |

---

## Anhang — Schemazusammenfassung

```
PLUGIN ──▶ SERVER (cmd)

  hello                       {name, version, min_app, subscribe}
  set_state                   {state}
  tts_enqueue                 {text, speed}
  notify                      {text, priority, data}
  ui_register                 {schema}
  ui_state                    {values}
  tts_to_file            ─▶   tts_file_response   {request_id, duration_sec, output_path}
  ai_query               ─▶   ai_response         {request_id, response}
  chat_text              ─▶   chat_response       {request_id, response}
  idle_check             ─▶   idle_response       {request_id, input_idle_seconds}
  resource_check         ─▶   resource_response   {request_id, cpu, ram, gpu, vram}
  conversation_history   ─▶   history_response    {request_id, history}
  app_info               ─▶   app_info_response   {request_id, language, version, debug, state}
  rss_items              ─▶   rss_response        {request_id, items}
  ui_list                ─▶   ui_list_response    {request_id, uis}

SERVER ──▶ PLUGIN

  state (broadcast, subscribe)  {state, prev, source}
  audio (broadcast, subscribe)  {rms, noise_floor, auto_paused, listening}
  error (direct)                {msg}
  cmd:ui_action (direct)        {action: {key, event, values, selected}}
```
