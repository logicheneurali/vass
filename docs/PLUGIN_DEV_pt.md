# Guia de Desenvolvimento de Plugins do VASS

Documento técnico que descreve o protocolo de comunicação entre plugins e o
PluginServer do VASS, e as regras para criar novos plugins.

Referências de código:

- Servidor: `src/plugin_server.py` (thread daemon `PluginServer`)
- Emissão de eventos: `src/main.py` (broadcast de `state` e `audio`)
- Renderização de UI declarativa: `src/gui.py` (linha 3367+)
- Exemplos de plugins: `plugins/internal/noise_auto_pause/`, `plugins/external/news_publisher/`

---

## 1. Arquitetura

O VASS expõe um **servidor TCP em `localhost:8765`** que roda como uma thread
daemon dentro do processo principal (`PluginServer`). Os plugins são
**processos separados** (a inicialização automática os inicia com
`subprocess.Popen` em `plugin.py`) que se conectam ao servidor por um socket.

O servidor tem dois papéis:

- **Executa comandos** recebidos dos plugins (TTS, notificações, IA, estado do VASS…).
- **Faz broadcast de eventos** para os plugins que os solicitaram
  (`state` a cada mudança de estado, `audio` a cada quadro de áudio).

```
┌──────────────┐   broadcast (state/audio)   ┌──────────────────┐
│   VASS app   │ ───────────────────────────▶ │  Plugin (process)│
│  PluginServer│ ◀─────────────────────────── │                  │
│  :8765 (TCP) │      cmd + request_id        │                  │
└──────────────┘       resp. *_response       └──────────────────┘
```

## 2. Transporte e protocolo

- **Host/porta:** `localhost:8765` (configurável apenas no código).
- **Formato:** um objeto JSON por linha, cada mensagem terminada por `\n`
  (`json.dumps(...) + "\n"`, `ensure_ascii=False`, UTF-8).
- **Bufferização:** o servidor armazena os dados recebidos em buffer e divide
  por `\n`; os plugins devem fazer o mesmo no lado do cliente.
- **Identificação:** as mensagens de solicitação incluem um `request_id` (UUID)
  que é ecoado na resposta; o cliente o usa para correlacionar as respostas
  assíncronas.
- **Depuração:** com `python vass.py --debug` o servidor registra as mensagens
  recebidas (`<= received: ...`, `execute: ...`).

## 3. Handshake

Imediatamente após se conectar, o plugin deve enviar a mensagem `hello`:

```json
{"type": "hello", "name": "my_plugin", "version": "1.0.0",
 "min_app": "0.8.0", "subscribe": ["state", "audio"]}
```

| Campo | Obrigatório | Descrição |
|---|---|---|
| `type` | sim | `"hello"` |
| `name` | sim | Identificador do plugin (deve corresponder à pasta e ao manifest) |
| `version` | sim | Versão do plugin |
| `min_app` | sim | Versão mínima do VASS necessária; se a versão do aplicativo for inferior, o servidor responde `error` e fecha a conexão |
| `subscribe` | não | Lista de tipos de eventos de broadcast a receber (`"state"`, `"audio"`) |

Exemplo em Python:

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

## 4. Mensagens do plugin → servidor

Todos os comandos têm a forma:

```json
{"type": "cmd", "cmd": "<command>", ...parameters}
```

### 4.1 Comandos sem resposta (fire-and-forget)

| cmd | Parâmetros | Efeito |
|---|---|---|
| `set_state` | `state` (ex.: `"listening"`, `"paused"`) | Define o estado do VASS. Se `state="listening"`, também redefine o piso de ruído do reconhecimento de fala |
| `tts_enqueue` | `text`, `speed` (padrão `0.9`) | Fala o texto. O texto é **traduzido automaticamente** para o idioma do aplicativo se não estiver em inglês; a fila TTS usa `defer_if_busy=True` |
| `notify` | `text`, `priority` (padrão `5`), `data` | Mostra uma notificação de desktop. O texto é traduzido como acima |
| `ui_register` | `schema` (ver §6) | Registra uma UI declarativa associada ao plugin |
| `ui_state` | `values` (dict chave→valor) | Atualiza o estado da UI do plugin (consultado pela GUI a cada 1 s) |

### 4.2 Comandos de solicitação/resposta

Eles devem incluir `request_id`; o servidor responde com o tipo `*_response`
usando o mesmo `request_id`.

| cmd | Parâmetros | Tipo de resposta | Campos da resposta |
|---|---|---|---|
| `tts_to_file` | `text`, `output_path`, `speed` | `tts_file_response` | `duration_sec`, `output_path` |
| `ai_query` | `prompt`, `temperature` (0.1), `max_tokens` (300), `extra_body` | `ai_response` | `response` (string) |
| `chat_text` | `prompt` | `chat_response` | `response` (passa por todo o pipeline do VASS: memória, perfil, ferramentas) |
| `idle_check` | — | `idle_response` | `input_idle_seconds` |
| `resource_check` | — | `resource_response` | `cpu`, `ram`, `gpu`, `vram` |
| `conversation_history` | `limit` (padrão 10) | `history_response` | `history` (lista de `{"role": …}`) |
| `app_info` | — | `app_info_response` | `language`, `version`, `debug`, `state` |
| `rss_items` | `limit` (padrão 10) | `rss_response` | `items` (lista de `{title, source, summary, guid, link, pubDate}`) |
| `ui_list` | — | `ui_list_response` | `uis` (lista de nomes de plugins registrados) |

Observações importantes:

- `ai_query` e `chat_text` rodam em uma thread dedicada: a resposta pode chegar
  mais tarde (não bloqueie o event loop no `recv`).
- `ai_query` é serializado por um semáforo (uma chamada de IA por vez).
- Se o cliente OpenAI não estiver disponível, `ai_query` responde com uma
  string JSON `{"error": …}` dentro de `response`.
- `tts_to_file` gera o arquivo WAV no caminho informado e retorna a duração
  em segundos.

Padrão de cliente para solicitações síncronas:

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

## 5. Mensagens do servidor → plugin

### 5.1 Broadcasts (somente para plugins inscritos)

| type | Campos | Quando |
|---|---|---|
| `state` | `state`, `prev`, `source` | A cada mudança de estado do VASS (`listening`, `paused`, `playing`, …) |
| `audio` | `rms`, `noise_floor`, `auto_paused`, `listening` | A cada quadro de áudio capturado |

### 5.2 Mensagens diretas

| type | Campos | Quando |
|---|---|---|
| `error` | `msg` | Rejeição do handshake (versão `min_app` não atendida) ou erros do servidor |
| `cmd` com `cmd="ui_action"` | `action` (`{key, event, values, selected}`) | O usuário interage com a UI declarativa do plugin pela GUI |

O `_on_message` do plugin deve tratar pelo menos os tipos `error`, `audio`,
`state` e os comandos `cmd` (`ui_action`), seguindo o padrão existente:

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

## 6. UI declarativa (`ui_register`)

O plugin descreve sua interface com um schema JSON; a GUI o renderiza
automaticamente. O estado flui nas duas direções:

- **Plugin → GUI:** `ui_state` com `values`.
- **GUI → Plugin:** `ui_action` quando o usuário pressiona botões ou altera valores.

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

Tipos de linha:

| kind | Propriedades específicas | Evento enviado |
|---|---|---|
| `toggle` | `value` (bool), `instant` (bool) | `toggle` |
| `slider` | `min`, `max`, `value`, `instant` | `slider` |
| `text` | `value` | — (incluído em `values` quando um botão é clicado) |
| `combo` | `options[]`, `value` | — (idem) |
| `button` | — | `button` |
| `list` | `columns[]`, `items[]` (com `id`) | `select` com `selected` = id do item |
| `label` | `text` | — |

Regras de sincronização:

- `toggle`/`slider` com `instant:true` enviam o `ui_action` correspondente
  imediatamente.
- Widgets "com buffer" (`text`, `combo`, toggles/sliders não instantâneos) são
  coletados em `values` e enviados junto com a ação do botão.
- A GUI consulta `get_plugin_uis()` a cada segundo e aplica o estado enviado
  pelo plugin (`ui_state`).

## 7. Configuração e definições da GUI

Cada plugin tem seu próprio `settings.ini` (copiado de `settings.example.ini`
se não existir). O plugin o lê com seu próprio `_load_config()`.

**Regra importante:** as seções `[gui.<field>]` definem os campos mostrados no
diálogo de configuração da GUI. Cada campo indica em qual seção INI "normal" o
valor é gravado (`section`). As chaves da GUI nunca devem ser colocadas dentro
de seções normais.

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

Tipos de campo suportados (`get_plugin_config` em `plugin_server.py`):

| type | Propriedades |
|---|---|
| `slider` | `min_value`, `max_value`, `step`, `decimals` |
| `dropdown` | `options` (separados por barra vertical) |
| `text` | — |
| `note` | `note` / `note_<lang>` (apenas informativo, não grava valores) |

Cada campo aceita `label` e `label_<lang>` para localização e `section` para
indicar a seção INI de destino.

A GUI grava os valores com `PluginServer.set_plugin_value(name, section, key, value)`;
o plugin deve recarregá-los (ex.: relendo o INI no próximo uso).

## 8. Estrutura e ciclo de vida do plugin

### Layout do diretório

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

| Campo | Descrição |
|---|---|
| `name` | Deve corresponder à pasta do plugin |
| `version` | Versão do plugin |
| `min_app` | Versão mínima do VASS |
| `platform` | `"*"` |
| `description` / `description_<lang>` | Descrições localizadas |
| `subscriptions` | Tipos de broadcast a receber (`state`, `audio`) |
| `depends_on` | Lista de plugins que devem estar habilitados antes do carregamento |

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

1. Na inicialização, `PluginServer.run()` inicia automaticamente os plugins
   com `enabled: true`, ordenando-os por `depends_on` (as dependências iniciam
   primeiro; um plugin com dependências ausentes permanece `blocked`).
2. Cada plugin inicia como `subprocess.Popen([python, plugin.py], cwd=<dir>)`.
3. São feitas no máximo **2 tentativas de inicialização** (depois o contador
   reinicia).
4. `enable_plugin`/`disable_plugin`/`stop_plugin`/`start_plugin` controlam o
   estado em tempo de execução; `remove_plugin` (somente externos) exclui o
   diretório e a entrada de configuração.
5. `get_plugins_status` retorna para cada plugin: `enabled`, `running`,
   `status` (`running|blocked|error|stopped|disabled`), `missing_deps`.

## 9. Guia passo a passo: criar um plugin

Crie um plugin mínimo que use o estado do VASS e a IA.

### Etapa 1 — Pasta e manifest

Crie `plugins/external/hello_plugin/` com:

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

### Etapa 2 — Definições

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

### Etapa 3 — `plugin.py`

Esqueleto completo seguindo o padrão dos plugins existentes:

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

### Etapa 4 — Habilitar e testar

1. Adicione a `plugins/plugins.json`:
   ```json
   "hello_plugin": {"enabled": true}
   ```
2. Inicie o VASS (`python vass.py --debug`). O servidor inicia o plugin
   automaticamente; no log você verá `Hello from 'hello_plugin'` e `State -> listening`
   a cada mudança de estado.
3. Verifique o áudio: o plugin fala a mensagem configurada.

## 10. Depuração e resolução de problemas

| Sintoma | Causa provável | Solução |
|---|---|---|
| `Port 8765 already in use` | Outra instância do VASS está em execução | Feche a outra instância |
| `App version X < required Y` | `min_app` no manifest excede a versão do VASS | Diminua `min_app` ou atualize o VASS |
| Plugin `error` com `socket_missing`/`process_missing` | Processo ativo, mas socket não conectado (ou vice-versa) | Verifique o `log.txt` do plugin; reinicie-o |
| Nenhuma resposta de `ai_query` | Cliente OpenAI indisponível ou timeout | Verifique `[ai]` em `settings.ini`; aumente o `timeout` |
| O plugin não inicia | Dependências desabilitadas | Habilite os plugins em `depends_on` |
| Alterações no código não são aplicadas | O processo ainda está em execução | Reinicie o plugin pela GUI |
| Texto TTS traduzido inesperadamente | `tts_enqueue`/`notify` traduzem para o idioma do aplicativo se ≠ EN | Use `tts_to_file` para contornar a tradução |

---

## Apêndice — Esquema resumido

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
