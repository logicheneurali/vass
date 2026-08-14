# VASS 플러그인 개발 가이드

플러그인과 VASS PluginServer 간의 통신 프로토콜과 새 플러그인 생성 규칙을
설명하는 기술 문서입니다.

코드 참조:

- 서버: `src/plugin_server.py` (데몬 스레드 `PluginServer`)
- 이벤트 발생: `src/main.py` (`state` 및 `audio` 브로드캐스트)
- 선언형 UI 렌더링: `src/gui.py` (3367행 이후)
- 예제 플러그인: `plugins/internal/noise_auto_pause/`, `plugins/external/news_publisher/`

---

## 1. 아키텍처

VASS는 메인 프로세스 내부에서 데몬 스레드로 실행되는 **TCP 서버를 `localhost:8765`에**
노출합니다(`PluginServer`). 플러그인은 **별도의 프로세스**로(자동 시작 시
`subprocess.Popen`으로 `plugin.py`를 실행) 소켓을 통해 서버에 연결됩니다.

서버는 두 가지 역할을 합니다:

- 플러그인으로부터 받은 **명령을 실행**(TTS, 알림, AI, VASS 상태 등).
- 이를 요청한 플러그인들에게 **이벤트를 브로드캐스트**합니다
  (상태가 바뀔 때마다 `state`, 오디오 프레임마다 `audio`).

```
┌──────────────┐   broadcast (state/audio)   ┌──────────────────┐
│   VASS app   │ ───────────────────────────▶ │  Plugin (process)│
│  PluginServer│ ◀─────────────────────────── │                  │
│  :8765 (TCP) │      cmd + request_id        │                  │
└──────────────┘       resp. *_response       └──────────────────┘
```

## 2. 전송 계층과 프로토콜

- **호스트/포트:** `localhost:8765` (코드에서만 변경 가능).
- **형식:** 한 줄에 JSON 객체 하나, 각 메시지는 `\n`으로 끝납니다
  (`json.dumps(...) + "\n"`, `ensure_ascii=False`, UTF-8).
- **버퍼링:** 서버는 수신 데이터를 버퍼링한 후 `\n` 기준으로 분할합니다. 플러그인도
  클라이언트 쪽에서 동일하게 처리해야 합니다.
- **식별:** 요청 메시지에는 `request_id`(UUID)가 포함되며, 응답에 그대로
  반영됩니다. 클라이언트는 이를 사용해 비동기 응답을 매칭합니다.
- **디버깅:** `python vass.py --debug`로 실행하면 서버가 수신된 메시지를
  로그로 기록합니다 (`<= received: ...`, `execute: ...`).

## 3. 핸드셰이크(Handshake)

연결 직후 플러그인은 반드시 `hello` 메시지를 보내야 합니다:

```json
{"type": "hello", "name": "my_plugin", "version": "1.0.0",
 "min_app": "0.8.0", "subscribe": ["state", "audio"]}
```

| 필드 | 필수 여부 | 설명 |
|---|---|---|
| `type` | 예 | `"hello"` |
| `name` | 예 | 플러그인 식별자 (폴더 이름 및 매니페스트와 일치해야 함) |
| `version` | 예 | 플러그인 버전 |
| `min_app` | 예 | 요구되는 최소 VASS 버전. 앱 버전이 이보다 낮으면 서버는 `error`로 응답하고 연결을 종료합니다 |
| `subscribe` | 아니요 | 수신할 브로드캐스트 이벤트 유형 목록 (`"state"`, `"audio"`) |

Python 예제:

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

## 4. 플러그인 → 서버 메시지

모든 명령은 다음 형태입니다:

```json
{"type": "cmd", "cmd": "<command>", ...parameters}
```

### 4.1 응답이 없는 명령 (fire-and-forget)

| cmd | 파라미터 | 효과 |
|---|---|---|
| `set_state` | `state` (예: `"listening"`, `"paused"`) | VASS 상태를 설정합니다. `state="listening"`이면 음성 인식 노이즈 플로어도 리셋합니다 |
| `tts_enqueue` | `text`, `speed` (기본값 `0.9`) | 텍스트를 음성으로 출력합니다. 텍스트가 영어가 아니면 **앱 언어로 자동 번역**되며, TTS 큐는 `defer_if_busy=True`를 사용합니다 |
| `notify` | `text`, `priority` (기본값 `5`), `data` | 데스크톱 알림을 표시합니다. 텍스트는 위와 같이 번역됩니다 |
| `ui_register` | `schema` (§6 참조) | 플러그인에 연결된 선언형 UI를 등록합니다 |
| `ui_state` | `values` (딕셔너리 key→value) | 플러그인 UI 상태를 업데이트합니다 (GUI가 1초마다 폴링) |

### 4.2 요청/응답 명령

`request_id`가 포함되어야 하며, 서버는 동일한 `request_id`를 사용해 **타입**
`*_response`로 응답합니다.

| cmd | 파라미터 | 응답 타입 | 응답 필드 |
|---|---|---|---|
| `tts_to_file` | `text`, `output_path`, `speed` | `tts_file_response` | `duration_sec`, `output_path` |
| `ai_query` | `prompt`, `temperature` (0.1), `max_tokens` (300), `extra_body` | `ai_response` | `response` (문자열) |
| `chat_text` | `prompt` | `chat_response` | `response` (전체 VASS 파이프라인 통과: 메모리, 프로필, 도구) |
| `idle_check` | — | `idle_response` | `input_idle_seconds` |
| `resource_check` | — | `resource_response` | `cpu`, `ram`, `gpu`, `vram` |
| `conversation_history` | `limit` (기본값 10) | `history_response` | `history` (`{"role": …}` 목록) |
| `app_info` | — | `app_info_response` | `language`, `version`, `debug`, `state` |
| `rss_items` | `limit` (기본값 10) | `rss_response` | `items` (`{title, source, summary, guid, link, pubDate}` 목록) |
| `ui_list` | — | `ui_list_response` | `uis` (등록된 플러그인 이름 목록) |

중요 사항:

- `ai_query`와 `chat_text`는 전용 스레드에서 실행됩니다. 응답이 나중에 도착할 수
  있으므로 `recv`에서 이벤트 루프를 블로킹하지 마세요.
- `ai_query`는 세마포어로 직렬화됩니다 (한 번에 하나의 AI 호출).
- OpenAI 클라이언트를 사용할 수 없으면 `ai_query`는 `response` 안에 JSON 문자열
  `{"error": …}`로 응답합니다.
- `tts_to_file`은 지정된 경로에 WAV 파일을 생성하고 지속 시간을 초 단위로
  반환합니다.

동기 요청을 위한 클라이언트 패턴:

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

## 5. 서버 → 플러그인 메시지

### 5.1 브로드캐스트 (구독한 플러그인에게만 전송)

| type | 필드 | 시점 |
|---|---|---|
| `state` | `state`, `prev`, `source` | VASS 상태가 바뀔 때마다 (`listening`, `paused`, `playing`, …) |
| `audio` | `rms`, `noise_floor`, `auto_paused`, `listening` | 캡처된 오디오 프레임마다 |

### 5.2 직접 메시지

| type | 필드 | 시점 |
|---|---|---|
| `error` | `msg` | 핸드셰이크 거부(`min_app` 버전 미충족) 또는 서버 오류 시 |
| `cmd` (`cmd="ui_action"`) | `action` (`{key, event, values, selected}`) | 사용자가 GUI에서 플러그인의 선언형 UI와 상호작용할 때 |

플러그인의 `_on_message`는 최소한 `error`, `audio`, `state` 타입과 `cmd` 명령
(`ui_action`)을 기존 패턴에 따라 처리해야 합니다:

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

## 6. 선언형 UI (`ui_register`)

플러그인은 JSON 스키마로 자체 인터페이스를 기술하며, GUI가 이를 자동으로
렌더링합니다. 상태는 양방향으로 흐릅니다:

- **플러그인 → GUI:** `values`를 포함한 `ui_state`.
- **GUI → 플러그인:** 사용자가 버튼을 누르거나 값을 변경하면 `ui_action`.

스키마:

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

행 종류:

| kind | 고유 속성 | 전송되는 이벤트 |
|---|---|---|
| `toggle` | `value` (bool), `instant` (bool) | `toggle` |
| `slider` | `min`, `max`, `value`, `instant` | `slider` |
| `text` | `value` | — (버튼 클릭 시 `values`에 포함됨) |
| `combo` | `options[]`, `value` | — (동일) |
| `button` | — | `button` |
| `list` | `columns[]`, `items[]` (`id` 포함) | `selected` = 항목 id인 `select` |
| `label` | `text` | — |

동기화 규칙:

- `instant:true`인 `toggle`/`slider`는 관련 `ui_action`을 즉시 전송합니다.
- "버퍼링" 위젯(`text`, `combo`, 비즉시형 toggle/slider)은 `values`에
  모아져 버튼 액션과 함께 전송됩니다.
- GUI는 1초마다 `get_plugin_uis()`를 폴링하여 플러그인이 보낸 상태(`ui_state`)를
  적용합니다.

## 7. 설정 및 GUI 설정

각 플러그인은 자체 `settings.ini`를 갖습니다(없으면 `settings.example.ini`에서
복사). 플러그인은 자체 `_load_config()`로 이를 읽습니다.

**중요한 규칙:** `[gui.<field>]` 섹션은 GUI 설정 대화상자에 표시될 필드를
정의합니다. 각 필드는 값이 기록될 "일반" INI 섹션(`section`)을 지정합니다. GUI
키는 절대 일반 섹션 안에 넣으면 안 됩니다.

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

지원되는 필드 타입 (`plugin_server.py`의 `get_plugin_config`):

| type | 속성 |
|---|---|
| `slider` | `min_value`, `max_value`, `step`, `decimals` |
| `dropdown` | `options` (파이프 `|`로 구분) |
| `text` | — |
| `note` | `note` / `note_<lang>` (정보 표시 전용, 값을 쓰지 않음) |

각 필드는 현지화를 위한 `label`과 `label_<lang>`, 그리고 대상 INI 섹션을
지정하는 `section`을 허용합니다.

GUI는 `PluginServer.set_plugin_value(name, section, key, value)`로 값을
기록합니다. 플러그인은 이를 다시 로드해야 합니다(예: 다음 사용 시 INI를 다시 읽기).

## 8. 플러그인 구조와 수명 주기

### 디렉터리 구조

```
plugins/
├── plugins.json                  # enabled/disabled (gitignored)
├── plugins.json.example
├── internal/<name>/              # 시스템 플러그인 — 제거 불가
│   ├── plugin.py
│   ├── plugin_manifest.json
│   ├── settings.ini
│   └── settings.example.ini
└── external/<name>/              # 사용자 플러그인 — GUI에서 제거 가능
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

| 필드 | 설명 |
|---|---|
| `name` | 플러그인 폴더 이름과 일치해야 함 |
| `version` | 플러그인 버전 |
| `min_app` | 최소 VASS 버전 |
| `platform` | `"*"` |
| `description` / `description_<lang>` | 현지화된 설명 |
| `subscriptions` | 수신할 브로드캐스트 타입 (`state`, `audio`) |
| `depends_on` | 로딩 전에 반드시 활성화되어 있어야 하는 플러그인 목록 |

### `plugins/plugins.json`

```json
{
  "port": 8765,
  "plugins": {
    "my_plugin": {"enabled": true}
  }
}
```

### 수명 주기

1. 시작 시 `PluginServer.run()`은 `enabled: true`인 플러그인을 `depends_on`을
   기준으로 정렬하여 자동 시작합니다(의존 플러그인이 먼저 시작되고, 의존성이
   누락된 플러그인은 `blocked` 상태로 유지됩니다).
2. 각 플러그인은 `subprocess.Popen([python, plugin.py], cwd=<dir>)`로 시작됩니다.
3. 시작 시도는 최대 **2회**입니다(이후 카운터는 리셋됨).
4. `enable_plugin`/`disable_plugin`/`stop_plugin`/`start_plugin`이 런타임
   상태를 제어하며, `remove_plugin`(외부 플러그인 전용)은 디렉터리와 설정 항목을
   삭제합니다.
5. `get_plugins_status`는 각 플러그인에 대해 `enabled`, `running`,
   `status` (`running|blocked|error|stopped|disabled`), `missing_deps`를
   반환합니다.

## 9. 단계별 가이드: 플러그인 만들기

VASS 상태와 AI를 사용하는 최소 플러그인을 만들어 봅니다.

### 1단계 — 폴더와 매니페스트

`plugins/external/hello_plugin/`을 생성하고 다음 파일을 넣습니다:

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

### 2단계 — 설정

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

### 3단계 — `plugin.py`

기존 플러그인의 패턴을 따르는 전체 스켈레톤:

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

### 4단계 — 활성화 및 테스트

1. `plugins/plugins.json`에 추가:
   ```json
   "hello_plugin": {"enabled": true}
   ```
2. VASS 시작 (`python vass.py --debug`). 서버가 플러그인을 자동 시작하고,
   로그에서 `Hello from 'hello_plugin'`와 상태가 바뀔 때마다
   `State -> listening`을 볼 수 있습니다.
3. 오디오 확인: 플러그인이 설정된 메시지를 음성으로 출력합니다.

## 10. 디버깅 및 문제 해결

| 증상 | 예상 원인 | 해결책 |
|---|---|---|
| `Port 8765 already in use` | 다른 VASS 인스턴스가 실행 중 | 다른 인스턴스 종료 |
| `App version X < required Y` | 매니페스트의 `min_app`이 VASS 버전보다 높음 | `min_app`을 낮추거나 VASS 업데이트 |
| `socket_missing`/`process_missing`과 함께 플러그인 `error` | 프로세스는 살아있지만 소켓이 연결되지 않음(또는 그 반대) | 플러그인의 `log.txt` 확인 후 재시작 |
| `ai_query`에 응답 없음 | OpenAI 클라이언트를 사용할 수 없거나 타임아웃 | `settings.ini`의 `[ai]` 확인 후 `timeout` 증가 |
| 플러그인이 시작되지 않음 | 의존 플러그인이 비활성화됨 | `depends_on`의 플러그인 활성화 |
| 코드 변경이 반영되지 않음 | 프로세스가 여전히 실행 중 | GUI에서 플러그인 재시작 |
| TTS 텍스트가 예기치 않게 번역됨 | `tts_enqueue`/`notify`가 앱 언어가 ≠ EN이면 해당 언어로 번역 | `tts_to_file`을 사용해 번역 우회 |

---

## 부록 — 요약 스키마

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
