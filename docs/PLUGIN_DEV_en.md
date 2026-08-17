# VASS Plugin Development Guide

Technical document describing the communication protocol between plugins and
the VASS PluginServer, and the rules for creating new plugins.

Code references:

- Server: `src/plugin_server.py` (daemon thread `PluginServer`)
- Event emission: `src/main.py` (broadcast of `state` and `audio`)
- Declarative UI rendering: `src/gui.py` (line 3367+)
- Example plugins: `plugins/internal/noise_auto_pause/`, `plugins/external/news_publisher/`

---

## 1. Architecture

VASS exposes a **TCP server on `localhost:8765`** that runs as a daemon thread
inside the main process (`PluginServer`). Plugins are **separate processes**
(auto-start launches them with `subprocess.Popen` on `plugin.py`) that connect
to the server over a socket.

The server has two roles:

- **Executes commands** received from plugins (TTS, notifications, AI, VASS state…).
- **Broadcasts events** to the plugins that requested them
  (`state` on every state change, `audio` on every audio frame).

```
┌──────────────┐   broadcast (state/audio)   ┌──────────────────┐
│   VASS app   │ ───────────────────────────▶ │  Plugin (process)│
│  PluginServer│ ◀─────────────────────────── │                  │
│  :8765 (TCP) │      cmd + request_id        │                  │
└──────────────┘       resp. *_response       └──────────────────┘
```

## 2. Transport and protocol

- **Host/port:** `localhost:8765` (configurable only in code).
- **Format:** one JSON object per line, each message terminated by `\n`
  (`json.dumps(...) + "\n"`, `ensure_ascii=False`, UTF-8).
- **Buffering:** the server buffers incoming data and splits on `\n`; plugins
  must do the same on the client side.
- **Identification:** request messages include a `request_id` (UUID) that is
  echoed in the response; the client uses it to match asynchronous responses.
- **Debugging:** with `python vass.py --debug` the server logs received
  messages (`<= received: ...`, `execute: ...`).

## 3. Handshake

Immediately after connecting, the plugin must send the `hello` message:

```json
{"type": "hello", "name": "my_plugin", "version": "1.0.0",
 "min_app": "0.8.0", "subscribe": ["state", "audio"]}
```

| Field | Required | Description |
|---|---|---|
| `type` | yes | `"hello"` |
| `name` | yes | Plugin identifier (must match the folder and the manifest) |
| `version` | yes | Plugin version |
| `min_app` | yes | Minimum VASS version required; if the app version is lower the server replies `error` and closes the connection |
| `subscribe` | no | List of broadcast event types to receive (`"state"`, `"audio"`) |

Python example:

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

## 4. Plugin → server messages

All commands have the form:

```json
{"type": "cmd", "cmd": "<command>", ...parameters}
```

### 4.1 Commands without response (fire-and-forget)

| cmd | Parameters | Effect |
|---|---|---|
| `set_state` | `state` (e.g. `"listening"`, `"paused"`) | Sets the VASS state. If `state="listening"` it also resets the speech recognition noise floor |
| `tts_enqueue` | `text`, `speed` (default `0.9`) | Speaks the text. The text is **automatically translated** to the app language if it is not English; the TTS queue uses `defer_if_busy=True` |
| `notify` | `text`, `priority` (default `5`), `data` | Shows a desktop notification. The text is translated as above |
| `ui_register` | `schema` (see §6) | Registers a declarative UI associated with the plugin |
| `ui_state` | `values` (dict key→value) | Updates the plugin UI state (polled by the GUI every 1 s) |
| `confirm_exec` | `title`, `command`, `audit_label` | Shows a GUI consent dialog; executes the command **only after explicit user approval** (audited). Response: `cmd_response` |

### 4.2 Request/response commands

They must include `request_id`; the server replies with the **type** `*_response`
using the same `request_id`.

| cmd | Parameters | Response type | Response fields |
|---|---|---|---|
| `tts_to_file` | `text`, `output_path`, `speed` | `tts_file_response` | `duration_sec`, `output_path` |
| `ai_query` | `prompt`, `temperature` (0.1), `max_tokens` (300), `extra_body` | `ai_response` | `response` (string) |
| `chat_text` | `prompt` | `chat_response` | `response` (goes through the whole VASS pipeline: memory, profile, tools) |
| `idle_check` | — | `idle_response` | `input_idle_seconds` |
| `resource_check` | — | `resource_response` | `cpu`, `ram`, `gpu`, `vram` |
| `conversation_history` | `limit` (default 10) | `history_response` | `history` (list of `{"role": …}`) |
| `app_info` | — | `app_info_response` | `language`, `version`, `debug`, `state` |
| `rss_items` | `limit` (default 10) | `rss_response` | `items` (list of `{title, source, summary, guid, link, pubDate}`) |
| `ui_list` | — | `ui_list_response` | `uis` (list of registered plugin names) |

Important notes:

- `ai_query` and `chat_text` run on a dedicated thread: the response may arrive
  later (do not block the event loop on `recv`).
- `ai_query` is serialized by a semaphore (one AI call at a time).
- If the OpenAI client is not available, `ai_query` replies with a JSON string
  `{"error": …}` inside `response`.
- `tts_to_file` generates the WAV file at the given path and returns the
  duration in seconds.

Client pattern for synchronous requests:

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

## 5. Server → plugin messages

### 5.1 Broadcasts (only to subscribed plugins)

| type | Fields | When |
|---|---|---|
| `state` | `state`, `prev`, `source` | On every VASS state change (`listening`, `paused`, `playing`, …) |
| `audio` | `rms`, `noise_floor`, `auto_paused`, `listening` | On every captured audio frame |

### 5.2 Direct messages

| type | Fields | When |
|---|---|---|
| `error` | `msg` | Handshake rejection (`min_app` version not satisfied) or server errors |
| `cmd` with `cmd="ui_action"` | `action` (`{key, event, values, selected}`) | The user interacts with the plugin's declarative UI from the GUI |

The plugin's `_on_message` must handle at least the types `error`, `audio`,
`state` and the `cmd` commands (`ui_action`), following the existing pattern:

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

## 6. Declarative UI (`ui_register`)

The plugin describes its interface with a JSON schema; the GUI renders it
automatically. State flows in both directions:

- **Plugin → GUI:** `ui_state` with `values`.
- **GUI → Plugin:** `ui_action` when the user presses buttons or changes values.

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

Row kinds:

| kind | Specific properties | Event sent |
|---|---|---|
| `toggle` | `value` (bool), `instant` (bool) | `toggle` |
| `slider` | `min`, `max`, `value`, `instant` | `slider` |
| `text` | `value` | — (included in `values` when a button is clicked) |
| `combo` | `options[]`, `value` | — (same) |
| `button` | — | `button` |
| `list` | `columns[]`, `items[]` (with `id`) | `select` with `selected` = item id |
| `label` | `text` | — |

Synchronization rules:

- `toggle`/`slider` with `instant:true` send the related `ui_action` immediately.
- "Buffered" widgets (`text`, `combo`, non-instant toggles/sliders) are
  collected in `values` and sent together with the button action.
- The GUI polls `get_plugin_uis()` every second and applies the state sent by
  the plugin (`ui_state`).

## 7. Configuration and GUI settings

Each plugin has its own `settings.ini` (copied from `settings.example.ini` if
missing). The plugin reads it with its own `_load_config()`.

**Important rule:** the `[gui.<field>]` sections define the fields shown in the
GUI configuration dialog. Each field indicates in which "normal" INI section the
value is written (`section`). GUI keys must never be placed inside normal
sections.

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

Supported field types (`get_plugin_config` in `plugin_server.py`):

| type | Properties |
|---|---|
| `slider` | `min_value`, `max_value`, `step`, `decimals` |
| `dropdown` | `options` (pipe-separated) |
| `text` | — |
| `note` | `note` / `note_<lang>` (informational only, does not write values) |

Each field accepts `label` and `label_<lang>` for localization and `section`
to indicate the target INI section.

The GUI writes values with `PluginServer.set_plugin_value(name, section, key, value)`;
the plugin must reload them (e.g. by re-reading the INI on next use).

## 8. Plugin structure and lifecycle

### Directory layout

```
plugins/
├── plugins.json                  # enabled/disabled (gitignored)
├── plugins.json.example
├── internal/<name>/              # system plugins — NOT removable
│   ├── plugin.py
│   ├── plugin_manifest.json
│   ├── settings.ini
│   └── settings.example.ini
└── external/<name>/              # user plugins — removable from the GUI
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

| Field | Description |
|---|---|
| `name` | Must match the plugin folder |
| `version` | Plugin version |
| `min_app` | Minimum VASS version |
| `platform` | `"*"` |
| `description` / `description_<lang>` | Localized descriptions |
| `subscriptions` | Broadcast types to receive (`state`, `audio`) |
| `depends_on` | List of plugins that must be enabled before loading |

### `plugins/plugins.json`

```json
{
  "port": 8765,
  "plugins": {
    "my_plugin": {"enabled": true}
  }
}
```

### Lifecycle

1. On startup, `PluginServer.run()` auto-starts the plugins with
   `enabled: true`, sorting them by `depends_on` (dependencies start first;
   a plugin with missing dependencies stays `blocked`).
2. Each plugin starts as `subprocess.Popen([python, plugin.py], cwd=<dir>)`.
3. At most **2 start attempts** are made (then the counter resets).
4. `enable_plugin`/`disable_plugin`/`stop_plugin`/`start_plugin` control the
   runtime state; `remove_plugin` (external only) deletes the directory and the
   config entry.
5. `get_plugins_status` returns for each plugin: `enabled`, `running`,
   `status` (`running|blocked|error|stopped|disabled`), `missing_deps`.

## 9. Step-by-step guide: create a plugin

Create a minimal plugin that uses the VASS state and the AI.

### Step 1 — Folder and manifest

Create `plugins/external/hello_plugin/` with:

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

### Step 2 — Settings

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

### Step 3 — `plugin.py`

Complete skeleton following the pattern of the existing plugins:

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

### Step 4 — Enable and test

1. Add to `plugins/plugins.json`:
   ```json
   "hello_plugin": {"enabled": true}
   ```
2. Start VASS (`python vass.py --debug`). The server auto-starts the plugin;
   in the log you will see `Hello from 'hello_plugin'` and `State -> listening`
   on every state change.
3. Verify the audio: the plugin speaks the configured message.

## 10. Debugging and troubleshooting

| Symptom | Likely cause | Solution |
|---|---|---|
| `Port 8765 already in use` | Another VASS instance is running | Close the other instance |
| `App version X < required Y` | `min_app` in the manifest exceeds the VASS version | Lower `min_app` or update VASS |
| Plugin `error` with `socket_missing`/`process_missing` | Process alive but socket not connected (or vice versa) | Check the plugin's `log.txt`; restart it |
| No response to `ai_query` | OpenAI client unavailable or timeout | Check `[ai]` in `settings.ini`; increase `timeout` |
| Plugin does not start | Disabled dependencies | Enable the plugins in `depends_on` |
| Code changes not applied | Process still running | Restart the plugin from the GUI |
| TTS text translated unexpectedly | `tts_enqueue`/`notify` translate to the app language if ≠ EN | Use `tts_to_file` to bypass the translation |

---

## Appendix — Summary schema

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
