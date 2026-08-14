# VASS 插件开发指南

描述插件与 VASS PluginServer 之间通信协议以及创建新插件规则的技术文档。

代码参考：

- 服务端：`src/plugin_server.py`（守护线程 `PluginServer`）
- 事件发送：`src/main.py`（`state` 与 `audio` 的广播）
- 声明式 UI 渲染：`src/gui.py`（第 3367 行起）
- 示例插件：`plugins/internal/noise_auto_pause/`、`plugins/external/news_publisher/`

---

## 1. 架构

VASS 在 `localhost:8765` 上暴露一个 **TCP 服务端**，它以守护线程的形式运行在主进程内部（`PluginServer`）。插件是**独立的进程**（自动启动时由 `plugin.py` 通过 `subprocess.Popen` 启动），并通过 socket 连接到服务端。

服务端有两个职责：

- **执行**来自插件的命令（TTS、通知、AI、VASS 状态等）。
- **向**请求过广播的插件**广播事件**（每次状态变化时广播 `state`，每个音频帧广播 `audio`）。

```
┌──────────────┐   broadcast (state/audio)   ┌──────────────────┐
│   VASS app   │ ───────────────────────────▶ │  Plugin (process)│
│  PluginServer│ ◀─────────────────────────── │                  │
│  :8765 (TCP) │      cmd + request_id        │                  │
└──────────────┘       resp. *_response       └──────────────────┘
```

## 2. 传输层与协议

- **主机/端口：** `localhost:8765`（仅在代码中可配置）。
- **格式：** 每行一个 JSON 对象，每条消息以 `\n` 结尾（`json.dumps(...) + "\n"`、`ensure_ascii=False`、UTF-8）。
- **缓冲：** 服务端缓冲收到的数据，并按 `\n` 拆分；插件在客户端也须执行同样的操作。
- **标识：** 请求消息包含一个 `request_id`（UUID），响应会原样回显该字段；客户端用它来匹配异步响应。
- **调试：** 使用 `python vass.py --debug` 运行时，服务端会记录收到的消息（`<= received: ...`、`execute: ...`）。

## 3. 握手

连接后，插件必须立即发送 `hello` 消息：

```json
{"type": "hello", "name": "my_plugin", "version": "1.0.0",
 "min_app": "0.8.0", "subscribe": ["state", "audio"]}
```

| 字段 | 是否必需 | 说明 |
|---|---|---|
| `type` | 是 | `"hello"` |
| `name` | 是 | 插件标识符（必须与文件夹名和清单一致） |
| `version` | 是 | 插件版本 |
| `min_app` | 是 | 所需的 VASS 最低版本；若应用版本更低，服务端会回复 `error` 并关闭连接 |
| `subscribe` | 否 | 需要接收的广播事件类型列表（`"state"`、`"audio"`） |

Python 示例：

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

## 4. 插件 → 服务端消息

所有命令都具有如下形式：

```json
{"type": "cmd", "cmd": "<command>", ...parameters}
```

### 4.1 无响应命令（fire-and-forget）

| cmd | 参数 | 效果 |
|---|---|---|
| `set_state` | `state`（如 `"listening"`、`"paused"`） | 设置 VASS 状态。若 `state="listening"`，同时会重置语音识别的噪声底限 |
| `tts_enqueue` | `text`、`speed`（默认 `0.9`） | 朗读文本。若文本不是英文，将**自动翻译**为应用语言；TTS 队列使用 `defer_if_busy=True` |
| `notify` | `text`、`priority`（默认 `5`）、`data` | 显示桌面通知。文本会像上面一样被翻译 |
| `ui_register` | `schema`（见 §6） | 注册与该插件关联的声明式 UI |
| `ui_state` | `values`（dict，键→值） | 更新插件 UI 状态（GUI 每 1 秒轮询一次） |

### 4.2 请求/响应命令

它们必须包含 `request_id`；服务端使用相同的 `request_id` 以 **`*_response`** 类型回复。

| cmd | 参数 | 响应类型 | 响应字段 |
|---|---|---|---|
| `tts_to_file` | `text`、`output_path`、`speed` | `tts_file_response` | `duration_sec`、`output_path` |
| `ai_query` | `prompt`、`temperature`（0.1）、`max_tokens`（300）、`extra_body` | `ai_response` | `response`（字符串） |
| `chat_text` | `prompt` | `chat_response` | `response`（会走完整的 VASS 流水线：记忆、个人资料、工具） |
| `idle_check` | — | `idle_response` | `input_idle_seconds` |
| `resource_check` | — | `resource_response` | `cpu`、`ram`、`gpu`、`vram` |
| `conversation_history` | `limit`（默认 10） | `history_response` | `history`（`{"role": …}` 的列表） |
| `app_info` | — | `app_info_response` | `language`、`version`、`debug`、`state` |
| `rss_items` | `limit`（默认 10） | `rss_response` | `items`（`{title, source, summary, guid, link, pubDate}` 的列表） |
| `ui_list` | — | `ui_list_response` | `uis`（已注册插件名列表） |

重要说明：

- `ai_query` 和 `chat_text` 在专用线程上运行：响应可能会延迟到达（不要在 `recv` 上阻塞事件循环）。
- `ai_query` 通过信号量串行化（同一时刻只能有一个 AI 调用）。
- 若 OpenAI 客户端不可用，`ai_query` 会在 `response` 内返回一个 JSON 字符串 `{"error": …}`。
- `tts_to_file` 会在指定路径生成 WAV 文件，并返回时长（秒）。

同步请求的客户端模式：

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

## 5. 服务端 → 插件消息

### 5.1 广播（仅发送给已订阅的插件）

| type | 字段 | 时机 |
|---|---|---|
| `state` | `state`、`prev`、`source` | 每次 VASS 状态变化时（`listening`、`paused`、`playing` 等） |
| `audio` | `rms`、`noise_floor`、`auto_paused`、`listening` | 每个捕获的音频帧 |

### 5.2 直接消息

| type | 字段 | 时机 |
|---|---|---|
| `error` | `msg` | 握手被拒绝（`min_app` 版本不满足）或服务端出错 |
| `cmd` 且 `cmd="ui_action"` | `action`（`{key, event, values, selected}`） | 用户从 GUI 操作插件的声明式 UI |

插件的 `_on_message` 至少必须处理 `error`、`audio`、`state` 类型以及 `cmd` 命令（`ui_action`），遵循现有模式：

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

## 6. 声明式 UI（`ui_register`）

插件用 JSON schema 描述自己的界面；GUI 自动渲染它。状态双向流动：

- **插件 → GUI：** 通过 `ui_state` 携带 `values`。
- **GUI → 插件：** 当用户按下按钮或修改数值时发送 `ui_action`。

Schema：

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

行类型：

| kind | 专属属性 | 发送的事件 |
|---|---|---|
| `toggle` | `value`（布尔）、`instant`（布尔） | `toggle` |
| `slider` | `min`、`max`、`value`、`instant` | `slider` |
| `text` | `value` | —（点击按钮时包含在 `values` 中） |
| `combo` | `options[]`、`value` | —（同上） |
| `button` | — | `button` |
| `list` | `columns[]`、`items[]`（含 `id`） | `select`，`selected` = 条目 id |
| `label` | `text` | — |

同步规则：

- `toggle`/`slider` 若 `instant:true`，会立即发送对应的 `ui_action`。
- "缓冲型"控件（`text`、`combo`、非即时的 toggle/slider）会收集到 `values` 中，与按钮动作一起发送。
- GUI 每秒调用一次 `get_plugin_uis()`，并应用插件通过 `ui_state` 发送的状态。

## 7. 配置与 GUI 设置

每个插件都有自己的 `settings.ini`（若缺失，则从 `settings.example.ini` 复制）。插件用自身的 `_load_config()` 读取它。

**重要规则：** `[gui.<field>]` 小节定义的是 GUI 配置对话框中显示的字段。每个字段指明其值写入哪一个"普通" INI 小节（`section`）。GUI 键绝不能放进普通小节里。

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

支持的字段类型（`plugin_server.py` 中的 `get_plugin_config`）：

| type | 属性 |
|---|---|
| `slider` | `min_value`、`max_value`、`step`、`decimals` |
| `dropdown` | `options`（以竖线分隔） |
| `text` | — |
| `note` | `note` / `note_<lang>`（仅作说明，不写入值） |

每个字段接受 `label` 和 `label_<lang>` 用于本地化，以及 `section` 用于指明目标 INI 小节。

GUI 通过 `PluginServer.set_plugin_value(name, section, key, value)` 写入值；插件必须重新加载这些值（例如在下一次使用时重新读取 INI）。

## 8. 插件结构与生命周期

### 目录结构

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

| 字段 | 说明 |
|---|---|
| `name` | 必须与插件文件夹名一致 |
| `version` | 插件版本 |
| `min_app` | VASS 最低版本 |
| `platform` | `"*"` |
| `description` / `description_<lang>` | 本地化描述 |
| `subscriptions` | 要接收的广播类型（`state`、`audio`） |
| `depends_on` | 加载前必须启用的插件列表 |

### `plugins/plugins.json`

```json
{
  "port": 8765,
  "plugins": {
    "my_plugin": {"enabled": true}
  }
}
```

### 生命周期

1. 启动时，`PluginServer.run()` 自动启动 `enabled: true` 的插件，并按 `depends_on` 排序（依赖项先启动；依赖缺失的插件保持 `blocked` 状态）。
2. 每个插件以 `subprocess.Popen([python, plugin.py], cwd=<dir>)` 启动。
3. 最多尝试启动 **2 次**（随后计数器重置）。
4. `enable_plugin`/`disable_plugin`/`stop_plugin`/`start_plugin` 控制运行时状态；`remove_plugin`（仅限外部插件）会删除目录和配置项。
5. `get_plugins_status` 为每个插件返回：`enabled`、`running`、`status`（`running|blocked|error|stopped|disabled`）、`missing_deps`。

## 9. 分步指南：创建插件

创建一个使用 VASS 状态和 AI 的最小插件。

### 第 1 步 — 文件夹与清单

创建 `plugins/external/hello_plugin/`，包含：

`plugin_manifest.json`：

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

### 第 2 步 — 设置

`settings.example.ini`：

```ini
[general]
greeting = Hello from VASS

[gui.greeting]
type = text
label = Greeting message
label_it = Messaggio di saluto
section = general
```

### 第 3 步 — `plugin.py`

遵循现有插件模式的完整骨架：

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

### 第 4 步 — 启用并测试

1. 添加到 `plugins/plugins.json`：
   ```json
   "hello_plugin": {"enabled": true}
   ```
2. 启动 VASS（`python vass.py --debug`）。服务端会自动启动插件；在日志中你会看到 `Hello from 'hello_plugin'`，并且每次状态变化都会看到 `State -> listening`。
3. 验证音频：插件会朗读配置好的消息。

## 10. 调试与故障排查

| 症状 | 可能的原因 | 解决方案 |
|---|---|---|
| `Port 8765 already in use` | 有另一个 VASS 实例在运行 | 关闭另一个实例 |
| `App version X < required Y` | 清单中的 `min_app` 高于 VASS 版本 | 调低 `min_app` 或升级 VASS |
| 插件返回 `error`，报 `socket_missing`/`process_missing` | 进程存活但 socket 未连接（或反之） | 检查插件的 `log.txt`；重启它 |
| `ai_query` 无响应 | OpenAI 客户端不可用或超时 | 检查 `settings.ini` 中的 `[ai]`；调大 `timeout` |
| 插件未启动 | 依赖被禁用 | 启用 `depends_on` 中的插件 |
| 代码修改未生效 | 进程仍在运行 | 从 GUI 重启插件 |
| TTS 文本被意外翻译 | 当文本非英文时 `tts_enqueue`/`notify` 会翻译成应用语言 | 使用 `tts_to_file` 绕过翻译 |

---

## 附录 — 汇总 schema

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
