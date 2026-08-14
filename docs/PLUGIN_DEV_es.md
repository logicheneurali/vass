# Guía de desarrollo de plugins de VASS

Documento técnico que describe el protocolo de comunicación entre los plugins y
el PluginServer de VASS, y las reglas para crear nuevos plugins.

Referencias de código:

- Servidor: `src/plugin_server.py` (thread demonio `PluginServer`)
- Emisión de eventos: `src/main.py` (difusión de `state` y `audio`)
- Renderizado de la interfaz declarativa: `src/gui.py` (línea 3367+)
- Plugins de ejemplo: `plugins/internal/noise_auto_pause/`, `plugins/external/news_publisher/`

---

## 1. Arquitectura

VASS expone un **servidor TCP en `localhost:8765`** que se ejecuta como thread
demonio dentro del proceso principal (`PluginServer`). Los plugins son
**procesos separados** (el arranque automático los lanza con
`subprocess.Popen` sobre `plugin.py`) que se conectan al servidor a través de un
socket.

El servidor tiene dos roles:

- **Ejecuta comandos** recibidos de los plugins (TTS, notificaciones, IA, estado de VASS…).
- **Difunde eventos** a los plugins que los hayan solicitado
  (`state` en cada cambio de estado, `audio` en cada fotograma de audio).

```
┌──────────────┐   broadcast (state/audio)   ┌──────────────────┐
│   VASS app   │ ───────────────────────────▶ │  Plugin (process)│
│  PluginServer│ ◀─────────────────────────── │                  │
│  :8765 (TCP) │      cmd + request_id        │                  │
└──────────────┘       resp. *_response       └──────────────────┘
```

## 2. Transporte y protocolo

- **Host/puerto:** `localhost:8765` (configurable solo en el código).
- **Formato:** un objeto JSON por línea, cada mensaje termina con `\n`
  (`json.dumps(...) + "\n"`, `ensure_ascii=False`, UTF-8).
- **Buffering:** el servidor acumula los datos entrantes y los divide por `\n`;
  los plugins deben hacer lo mismo en el lado del cliente.
- **Identificación:** los mensajes de petición incluyen un `request_id` (UUID)
  que se repite en la respuesta; el cliente lo usa para asociar las respuestas
  asíncronas.
- **Depuración:** con `python vass.py --debug` el servidor registra los mensajes
  recibidos (`<= received: ...`, `execute: ...`).

## 3. Handshake

Inmediatamente después de conectarse, el plugin debe enviar el mensaje `hello`:

```json
{"type": "hello", "name": "my_plugin", "version": "1.0.0",
 "min_app": "0.8.0", "subscribe": ["state", "audio"]}
```

| Campo | Obligatorio | Descripción |
|---|---|---|
| `type` | sí | `"hello"` |
| `name` | sí | Identificador del plugin (debe coincidir con la carpeta y el manifest) |
| `version` | sí | Versión del plugin |
| `min_app` | sí | Versión mínima de VASS requerida; si la versión de la app es inferior, el servidor responde `error` y cierra la conexión |
| `subscribe` | no | Lista de tipos de eventos de difusión que se desea recibir (`"state"`, `"audio"`) |

Ejemplo en Python:

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

## 4. Mensajes del plugin al servidor

Todos los comandos tienen la forma:

```json
{"type": "cmd", "cmd": "<command>", ...parameters}
```

### 4.1 Comandos sin respuesta (fire-and-forget)

| cmd | Parámetros | Efecto |
|---|---|---|
| `set_state` | `state` (p. ej. `"listening"`, `"paused"`) | Establece el estado de VASS. Si `state="listening"` también reinicia el umbral de ruido del reconocimiento de voz |
| `tts_enqueue` | `text`, `speed` (por defecto `0.9`) | Pronuncia el texto. El texto se **traduce automáticamente** al idioma de la aplicación si no es inglés; la cola de TTS usa `defer_if_busy=True` |
| `notify` | `text`, `priority` (por defecto `5`), `data` | Muestra una notificación de escritorio. El texto se traduce como arriba |
| `ui_register` | `schema` (ver §6) | Registra una interfaz declarativa asociada al plugin |
| `ui_state` | `values` (dict clave→valor) | Actualiza el estado de la interfaz del plugin (consultado por la GUI cada 1 s) |

### 4.2 Comandos de petición/respuesta

Deben incluir `request_id`; el servidor responde con el **tipo** `*_response`
usando el mismo `request_id`.

| cmd | Parámetros | Tipo de respuesta | Campos de la respuesta |
|---|---|---|---|
| `tts_to_file` | `text`, `output_path`, `speed` | `tts_file_response` | `duration_sec`, `output_path` |
| `ai_query` | `prompt`, `temperature` (0.1), `max_tokens` (300), `extra_body` | `ai_response` | `response` (cadena) |
| `chat_text` | `prompt` | `chat_response` | `response` (recorre todo el pipeline de VASS: memoria, perfil, herramientas) |
| `idle_check` | — | `idle_response` | `input_idle_seconds` |
| `resource_check` | — | `resource_response` | `cpu`, `ram`, `gpu`, `vram` |
| `conversation_history` | `limit` (por defecto 10) | `history_response` | `history` (lista de `{"role": …}`) |
| `app_info` | — | `app_info_response` | `language`, `version`, `debug`, `state` |
| `rss_items` | `limit` (por defecto 10) | `rss_response` | `items` (lista de `{title, source, summary, guid, link, pubDate}`) |
| `ui_list` | — | `ui_list_response` | `uis` (lista de nombres de plugins registrados) |

Notas importantes:

- `ai_query` y `chat_text` se ejecutan en un thread dedicado: la respuesta puede
  llegar más tarde (no bloquees el bucle de eventos en `recv`).
- `ai_query` está serializado por un semáforo (una llamada de IA a la vez).
- Si el cliente OpenAI no está disponible, `ai_query` responde con una cadena
  JSON `{"error": …}` dentro de `response`.
- `tts_to_file` genera el archivo WAV en la ruta indicada y devuelve la duración
  en segundos.

Patrón de cliente para peticiones síncronas:

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

## 5. Mensajes del servidor al plugin

### 5.1 Difusiones (solo a los plugins suscritos)

| type | Campos | Cuándo |
|---|---|---|
| `state` | `state`, `prev`, `source` | En cada cambio de estado de VASS (`listening`, `paused`, `playing`, …) |
| `audio` | `rms`, `noise_floor`, `auto_paused`, `listening` | En cada fotograma de audio capturado |

### 5.2 Mensajes directos

| type | Campos | Cuándo |
|---|---|---|
| `error` | `msg` | Rechazo del handshake (versión de `min_app` no satisfecha) o errores del servidor |
| `cmd` con `cmd="ui_action"` | `action` (`{key, event, values, selected}`) | El usuario interactúa con la interfaz declarativa del plugin desde la GUI |

El `_on_message` del plugin debe gestionar al menos los tipos `error`, `audio`,
`state` y los comandos `cmd` (`ui_action`), siguiendo el patrón existente:

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

## 6. Interfaz declarativa (`ui_register`)

El plugin describe su interfaz con un esquema JSON; la GUI la renderiza
automáticamente. El estado fluye en ambas direcciones:

- **Plugin → GUI:** `ui_state` con `values`.
- **GUI → Plugin:** `ui_action` cuando el usuario pulsa botones o cambia valores.

Esquema:

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

Tipos de fila:

| kind | Propiedades específicas | Evento enviado |
|---|---|---|
| `toggle` | `value` (bool), `instant` (bool) | `toggle` |
| `slider` | `min`, `max`, `value`, `instant` | `slider` |
| `text` | `value` | — (incluido en `values` al pulsar un botón) |
| `combo` | `options[]`, `value` | — (igual) |
| `button` | — | `button` |
| `list` | `columns[]`, `items[]` (con `id`) | `select` con `selected` = id del elemento |
| `label` | `text` | — |

Reglas de sincronización:

- Los `toggle`/`slider` con `instant:true` envían el `ui_action` correspondiente
  inmediatamente.
- Los widgets "con búfer" (`text`, `combo`, toggles/sliders no instantáneos) se
  recogen en `values` y se envían junto con la acción del botón.
- La GUI consulta `get_plugin_uis()` cada segundo y aplica el estado enviado por
  el plugin (`ui_state`).

## 7. Configuración y ajustes de la GUI

Cada plugin tiene su propio `settings.ini` (copiado de `settings.example.ini` si
falta). El plugin lo lee con su propio `_load_config()`.

**Regla importante:** las secciones `[gui.<field>]` definen los campos que se
muestran en el diálogo de configuración de la GUI. Cada campo indica en qué
sección "normal" del INI se escribe el valor (`section`). Las claves de la GUI
nunca deben colocarse dentro de secciones normales.

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

Tipos de campo admitidos (`get_plugin_config` en `plugin_server.py`):

| type | Propiedades |
|---|---|
| `slider` | `min_value`, `max_value`, `step`, `decimals` |
| `dropdown` | `options` (separados por tubo) |
| `text` | — |
| `note` | `note` / `note_<lang>` (solo informativo, no escribe valores) |

Cada campo acepta `label` y `label_<lang>` para la localización y `section`
para indicar la sección INI de destino.

La GUI escribe los valores con `PluginServer.set_plugin_value(name, section, key, value)`;
el plugin debe recargarlos (p. ej. releyendo el INI en el siguiente uso).

## 8. Estructura y ciclo de vida de los plugins

### Estructura de directorios

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

| Campo | Descripción |
|---|---|
| `name` | Debe coincidir con la carpeta del plugin |
| `version` | Versión del plugin |
| `min_app` | Versión mínima de VASS |
| `platform` | `"*"` |
| `description` / `description_<lang>` | Descripciones localizadas |
| `subscriptions` | Tipos de difusión a recibir (`state`, `audio`) |
| `depends_on` | Lista de plugins que deben estar habilitados antes de cargar |

### `plugins/plugins.json`

```json
{
  "port": 8765,
  "plugins": {
    "my_plugin": {"enabled": true}
  }
}
```

### Ciclo de vida

1. Al arrancar, `PluginServer.run()` inicia automáticamente los plugins con
   `enabled: true`, ordenándolos según `depends_on` (las dependencias arrancan
   primero; un plugin con dependencias faltantes permanece `blocked`).
2. Cada plugin arranca como `subprocess.Popen([python, plugin.py], cwd=<dir>)`.
3. Como máximo se realizan **2 intentos de arranque** (luego el contador se
   reinicia).
4. `enable_plugin`/`disable_plugin`/`stop_plugin`/`start_plugin` controlan el
   estado en tiempo de ejecución; `remove_plugin` (solo externo) elimina el
   directorio y la entrada de configuración.
5. `get_plugins_status` devuelve para cada plugin: `enabled`, `running`,
   `status` (`running|blocked|error|stopped|disabled`), `missing_deps`.

## 9. Guía paso a paso: crear un plugin

Crea un plugin mínimo que use el estado de VASS y la IA.

### Paso 1 — Carpeta y manifest

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

### Paso 2 — Ajustes

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

### Paso 3 — `plugin.py`

Esqueleto completo siguiendo el patrón de los plugins existentes:

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

### Paso 4 — Habilitar y probar

1. Añade a `plugins/plugins.json`:
   ```json
   "hello_plugin": {"enabled": true}
   ```
2. Arranca VASS (`python vass.py --debug`). El servidor inicia el plugin
   automáticamente; en el log verás `Hello from 'hello_plugin'` y
   `State -> listening` en cada cambio de estado.
3. Verifica el audio: el plugin pronuncia el mensaje configurado.

## 10. Depuración y solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `Port 8765 already in use` | Hay otra instancia de VASS en ejecución | Cierra la otra instancia |
| `App version X < required Y` | `min_app` del manifest supera la versión de VASS | Reduce `min_app` o actualiza VASS |
| Plugin `error` con `socket_missing`/`process_missing` | Proceso activo pero socket sin conectar (o viceversa) | Revisa el `log.txt` del plugin; reinícialo |
| Sin respuesta a `ai_query` | Cliente OpenAI no disponible o timeout | Revisa `[ai]` en `settings.ini`; aumenta el `timeout` |
| El plugin no arranca | Dependencias deshabilitadas | Habilita los plugins en `depends_on` |
| Los cambios de código no se aplican | El proceso sigue en ejecución | Reinicia el plugin desde la GUI |
| Texto TTS traducido de forma inesperada | `tts_enqueue`/`notify` traducen al idioma de la app si ≠ EN | Usa `tts_to_file` para evitar la traducción |

---

## Apéndice — Esquema resumen

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
