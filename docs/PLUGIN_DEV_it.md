# Guida allo sviluppo di plugin VASS

Documento tecnico che descrive il protocollo di comunicazione tra i plugin e il
PluginServer di VASS e le regole per creare nuovi plugin.

Riferimenti nel codice:

- Server: `src/plugin_server.py` (thread daemon `PluginServer`)
- Invio eventi: `src/main.py` (broadcast `state` e `audio`)
- Rendering UI dichiarativa: `src/gui.py` (righe 3367+)
- Plugin di esempio: `plugins/internal/noise_auto_pause/`, `plugins/external/news_publisher/`

---

## 1. Architettura

VASS espone un **server TCP su `localhost:8765`** che gira come thread daemon
all'interno del processo principale (`PluginServer`). I plugin sono **processi
separati** (l'auto-start li lancia con `subprocess.Popen` su `plugin.py`) che si
connettono al server via socket.

Il server ha due ruoli:

- **Esegue comandi** ricevuti dai plugin (TTS, notifiche, AI, stato VASS…).
- **Trasmette eventi** (broadcast) ai plugin che li hanno richiesti
  (`state` a ogni cambio di stato, `audio` a ogni frame audio).

```
┌──────────────┐   broadcast (state/audio)   ┌──────────────────┐
│   VASS app   │ ───────────────────────────▶ │  Plugin (process)│
│  PluginServer│ ◀─────────────────────────── │                  │
│  :8765 (TCP) │      cmd + request_id        │                  │
└──────────────┘       respon. *_response     └──────────────────┘
```

## 2. Trasporto e protocollo

- **Host/porta:** `localhost:8765` (configurabile solo via codice).
- **Formato:** JSON per riga, ogni messaggio termina con `\n` (`json.dumps(...) + "\n"`, `ensure_ascii=False`, UTF-8).
- **Buffering:** il server bufferizza i dati in arrivo e splitta su `\n`; i plugin devono fare lo stesso lato client.
- **Identificazione:** i messaggi di richiesta includono un `request_id` (UUID) che torna identico nella risposta; il client lo usa per abbinare risposte asincrone.
- **Debug:** con `python vass.py --debug` il server logga i messaggi ricevuti (`<= received: ...`, `execute: ...`).

## 3. Handshake

Appena connesso, il plugin deve inviare il messaggio `hello`:

```json
{"type": "hello", "name": "my_plugin", "version": "1.0.0",
 "min_app": "0.8.0", "subscribe": ["state", "audio"]}
```

| Campo | Obbligatorio | Descrizione |
|---|---|---|
| `type` | sì | `"hello"` |
| `name` | sì | Identificativo plugin (deve coincidere con la cartella e il manifest) |
| `version` | sì | Versione del plugin |
| `min_app` | sì | Versione minima di VASS richiesta; se la versione dell'app è inferiore il server risponde `error` e chiude la connessione |
| `subscribe` | no | Lista di tipi di eventi broadcast da ricevere (`"state"`, `"audio"`) |

Esempio Python:

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

## 4. Messaggi plugin → server

Tutti i comandi hanno la forma:

```json
{"type": "cmd", "cmd": "<comando>", ...parametri}
```

### 4.1 Comandi senza risposta (fire-and-forget)

| cmd | Parametri | Effetto |
|---|---|---|
| `set_state` | `state` (es. `"listening"`, `"paused"`) | Imposta lo stato VASS. Se `state="listening"` resetta anche il noise floor del riconoscimento vocale |
| `tts_enqueue` | `text`, `speed` (default `0.9`) | Pronuncia il testo. Il testo viene **tradotto automaticamente** nella lingua dell'app se non è inglese; la coda TTS usa `defer_if_busy=True` |
| `notify` | `text`, `priority` (default `5`), `data` | Mostra una notifica desktop. Il testo viene tradotto come sopra |
| `ui_register` | `schema` (vedi §6) | Registra un'interfaccia dichiarativa associata al plugin |
| `ui_state` | `values` (dict chiave→valore) | Aggiorna lo stato della UI del plugin (letto dalla GUI ogni 1 s) |

### 4.2 Comandi request/response

Devono includere `request_id`; il server risponde sul **tipo** `*_response`
con lo stesso `request_id`.

| cmd | Parametri | Tipo risposta | Campi risposta |
|---|---|---|---|
| `tts_to_file` | `text`, `output_path`, `speed` | `tts_file_response` | `duration_sec`, `output_path` |
| `ai_query` | `prompt`, `temperature` (0.1), `max_tokens` (300), `extra_body` | `ai_response` | `response` (stringa) |
| `chat_text` | `prompt` | `chat_response` | `response` (passa da tutta la pipeline VASS: memoria, profilo, tool) |
| `idle_check` | — | `idle_response` | `input_idle_seconds` |
| `resource_check` | — | `resource_response` | `cpu`, `ram`, `gpu`, `vram` |
| `conversation_history` | `limit` (default 10) | `history_response` | `history` (lista di `{"role": …}`) |
| `app_info` | — | `app_info_response` | `language`, `version`, `debug`, `state` |
| `rss_items` | `limit` (default 10) | `rss_response` | `items` (lista di `{title, source, summary, guid, link, pubDate}`) |
| `ui_list` | — | `ui_list_response` | `uis` (lista di nomi plugin registrati) |

Note importanti:

- `ai_query` e `chat_text` girano in un thread dedicato: la risposta può arrivare
  in un secondo momento (non bloccare l'event loop sul `recv`).
- `ai_query` è serializzata da un semaforo (una chiamata AI alla volta).
- Se il client OpenAI non è disponibile, `ai_query` risponde con una stringa
  JSON `{"error": …}` dentro `response`.
- `tts_to_file` genera il file WAV sul percorso indicato e restituisce la durata
  in secondi.

Pattern client per le richieste sincrone:

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

## 5. Messaggi server → plugin

### 5.1 Broadcast (solo ai plugin sottoscritti)

| type | Campi | Quando |
|---|---|---|
| `state` | `state`, `prev`, `source` | A ogni cambio di stato VASS (`listening`, `paused`, `playing`, …) |
| `audio` | `rms`, `noise_floor`, `auto_paused`, `listening` | A ogni frame audio acquisito |

### 5.2 Messaggi diretti

| type | Campi | Quando |
|---|---|---|
| `error` | `msg` | Rifiuto dell'handshake (versione `min_app` non soddisfatta) o errori del server |
| `cmd` con `cmd="ui_action"` | `action` (`{key, event, values, selected}`) | L'utente interagisce con la UI dichiarativa del plugin dalla GUI |

L'`_on_message` di un plugin deve gestire almeno i tipi `error`, `audio`,
`state` e i comandi `cmd` (`ui_action`), come nel pattern esistente:

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

## 6. UI dichiarativa (`ui_register`)

Il plugin descrive la propria interfaccia con uno schema JSON; la GUI lo
renderizza automaticamente. Lo stato circola in entrambe le direzioni:

- **Plugin → GUI:** `ui_state` con `values`.
- **GUI → Plugin:** `ui_action` quando l'utente preme pulsanti o cambia valori.

Schema:

```json
{
  "id": "my_plugin",
  "title_it": "Titolo italiano",
  "title": "English title",
  "sections": [
    {
      "title_it": "Sezione",
      "title": "Section",
      "rows": [
        {"kind": "toggle", "key": "flag",   "label_it": "Attivo", "label": "Enabled", "value": true, "instant": true},
        {"kind": "slider", "key": "level",  "label_it": "Livello", "label": "Level",  "min": 0, "max": 100, "value": 50, "instant": false},
        {"kind": "text",   "key": "name",   "label_it": "Nome",    "label": "Name",   "value": ""},
        {"kind": "combo",  "key": "mode",   "label_it": "Modo",    "label": "Mode",   "options": ["a", "b", "c"], "value": "a"},
        {"kind": "button", "key": "run",    "label_it": "Esegui",  "label": "Run"},
        {"kind": "list",   "key": "items",  "label_it": "Elementi", "label": "Items",
         "columns": [{"key": "name", "label_it": "Nome", "label": "Name"}],
         "items": [{"id": "1", "name": "uno"}]},
        {"kind": "label",  "key": "status", "text": "pronto"}
      ]
    }
  ]
}
```

Tipi di riga:

| kind | Proprietà specifiche | Evento inviato |
|---|---|---|
| `toggle` | `value` (bool), `instant` (bool) | `toggle` |
| `slider` | `min`, `max`, `value`, `instant` | `slider` |
| `text` | `value` | — (incluso in `values` al click di un pulsante) |
| `combo` | `options[]`, `value` | — (idem) |
| `button` | — | `button` |
| `list` | `columns[]`, `items[]` (con `id`) | `select` con `selected` = id dell'elemento |
| `label` | `text` | — |

Regole di sincronizzazione:

- `toggle`/`slider` con `instant:true` inviano subito la relativa `ui_action`.
- I widget "buffered" (`text`, `combo`, toggle/slider non-instant) vengono
  raccolti in `values` e inviati insieme all'azione del pulsante.
- La GUI fa poll di `get_plugin_uis()` ogni secondo e applica lo stato inviato
  dal plugin (`ui_state`).

## 7. Configurazione e settings GUI

Ogni plugin ha un proprio `settings.ini` (copiato da `settings.example.ini` se
mancante). Il plugin lo legge con un proprio `_load_config()`.

**Regola importante:** le sezioni `[gui.<campo>]` definiscono i campi mostrati
nel dialog di configurazione della GUI. Ogni campo indica in quale sezione
"normale" dell'INI viene scritto il valore (`section`). Le chiavi GUI non vanno
mai messe dentro sezioni normali con chiavi puntate.

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

Tipi di campo supportati (`get_plugin_config` in `plugin_server.py`):

| type | Proprietà |
|---|---|
| `slider` | `min_value`, `max_value`, `step`, `decimals` |
| `dropdown` | `options` (separate da `|`) |
| `text` | — |
| `note` | `note` / `note_<lang>` (solo informativo, non scrive valori) |

Ogni campo accetta `label` e `label_<lang>` per la localizzazione e `section`
per indicare la sezione INI di destinazione.

La GUI scrive i valori con `PluginServer.set_plugin_value(name, section, key, value)`;
il plugin deve ricaricarli (es. rileggendo l'INI al prossimo uso).

## 8. Struttura di un plugin e ciclo di vita

### Layout directory

```
plugins/
├── plugins.json                  # abilitato/disabilitato (gitignored)
├── plugins.json.example
├── internal/<nome>/              # plugin di sistema — NON rimovibili
│   ├── plugin.py
│   ├── plugin_manifest.json
│   ├── settings.ini
│   └── settings.example.ini
└── external/<nome>/              # plugin utente — rimovibili dalla GUI
    └── (stessi file)
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

| Campo | Descrizione |
|---|---|
| `name` | Deve coincidere con la cartella del plugin |
| `version` | Versione del plugin |
| `min_app` | Versione minima di VASS |
| `platform` | `"*"` |
| `description` / `description_<lang>` | Descrizioni localizzate |
| `subscriptions` | Tipi di broadcast da ricevere (`state`, `audio`) |
| `depends_on` | Lista di plugin che devono essere abilitati prima del caricamento |

### `plugins/plugins.json`

```json
{
  "port": 8765,
  "plugins": {
    "my_plugin": {"enabled": true}
  }
}
```

### Ciclo di vita

1. All'avvio, `PluginServer.run()` fa l'auto-start dei plugin con
   `enabled: true`, ordinandoli in base a `depends_on` (le dipendenze partono
   prima; un plugin con dipendenze mancanti resta `blocked`).
2. Ogni plugin parte come `subprocess.Popen([python, plugin.py], cwd=<dir>)`.
3. Vengono fatti al massimo **2 tentativi** di avvio (poi il contatore si azzera).
4. `enable_plugin`/`disable_plugin`/`stop_plugin`/`start_plugin` controllano lo
   stato runtime; `remove_plugin` (solo external) elimina directory e voce config.
5. `get_plugins_status` restituisce per ogni plugin: `enabled`, `running`,
   `status` (`running|blocked|error|stopped|disabled`), `missing_deps`.

## 9. Guida passo-passo: creare un plugin

Crea un plugin minimale che usa lo stato VASS e l'AI.

### Step 1 — Cartella e manifest

Crea `plugins/external/hello_plugin/` con:

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

### Step 2 — settings

`settings.example.ini`:

```ini
[general]
greeting = Ciao da VASS

[gui.greeting]
type = text
label = Greeting message
label_it = Messaggio di saluto
section = general
```

### Step 3 — `plugin.py`

Skeleton completo che segue il pattern dei plugin esistenti:

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

        # Saluta non appena connesso
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

### Step 4 — Abilitazione e test

1. Aggiungi a `plugins/plugins.json`:
   ```json
   "hello_plugin": {"enabled": true}
   ```
2. Avvia VASS (`python vass.py --debug`). Il server auto-avvia il plugin;
   nel log vedrai `Hello from 'hello_plugin'` e `State -> listening` ad ogni
   cambio di stato.
3. Verifica l'audio: il plugin pronuncia il messaggio configurato.

## 10. Debug e risoluzione problemi

| Sintomo | Causa probabile | Soluzione |
|---|---|---|
| `Port 8765 already in use` | Un'altra istanza di VASS sta girando | Chiudi l'altra istanza |
| `App version X < required Y` | `min_app` nel manifest supera la versione di VASS | Abbassa `min_app` o aggiorna VASS |
| Plugin `error` con `socket_missing`/`process_missing` | Processo vivo ma socket non connesso (o viceversa) | Controlla il `log.txt` del plugin; riavvialo |
| Nessuna risposta a `ai_query` | Client OpenAI non disponibile o timeout | Verifica `[ai]` in `settings.ini`; aumenta `timeout` |
| Plugin non parte | Dipendenze disabilitate | Abilita i plugin in `depends_on` |
| Modifiche al codice non applicate | Processo ancora in esecuzione | Riavvia il plugin dalla GUI |
| Testo TTS tradotto inaspettatamente | `tts_enqueue`/`notify` traducono nella lingua app se ≠ EN | Usa `tts_to_file` per bypassare la traduzione |

---

## Appendice — Schema riassuntivo

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
  error (diretto)               {msg}
  cmd:ui_action (direct)        {action: {key, event, values, selected}}
```
