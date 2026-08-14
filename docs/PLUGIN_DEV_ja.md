# VASS プラグイン開発ガイド

プラグインと VASS PluginServer 間の通信プロトコル、および新しいプラグインを作成するためのルールを説明した技術文書です。

コードの参照先:

- サーバー: `src/plugin_server.py`(デーモンスレッド `PluginServer`)
- イベント発行: `src/main.py`(`state` と `audio` のブロードキャスト)
- 宣言的 UI のレンダリング: `src/gui.py`(3367 行以降)
- プラグイン例: `plugins/internal/noise_auto_pause/`、`plugins/external/news_publisher/`

---

## 1. アーキテクチャ

VASS は、メインプロセス内でデーモンスレッドとして動作する **TCP サーバー(`localhost:8765`)** を公開しています(`PluginServer`)。プラグインは **独立したプロセス** であり(`plugin.py` を `subprocess.Popen` で自動起動)、ソケット経由でサーバーに接続します。

サーバーには次の 2 つの役割があります。

- プラグインから受信した**コマンドを実行**します(TTS、通知、AI、VASS の状態など)。
- 要求したプラグインに**イベントをブロードキャスト**します(状態が変わるたびに `state`、オーディオフレームごとに `audio`)。

```
┌──────────────┐   broadcast (state/audio)   ┌──────────────────┐
│   VASS app   │ ───────────────────────────▶ │  Plugin (process)│
│  PluginServer│ ◀─────────────────────────── │                  │
│  :8765 (TCP) │      cmd + request_id        │                  │
└──────────────┘       resp. *_response       └──────────────────┘
```

## 2. トランスポートとプロトコル

- **ホスト / ポート:** `localhost:8765`(コード内でのみ設定可能)。
- **形式:** 1 行に 1 つの JSON オブジェクトで、各メッセージは `\n` で終端します(`json.dumps(...) + "\n"`、`ensure_ascii=False`、UTF-8)。
- **バッファリング:** サーバーは受信データをバッファリングし、`\n` で分割します。プラグイン側もクライアント側で同様に行う必要があります。
- **識別:** リクエストメッセージには `request_id`(UUID)が含まれ、レスポンスにエコーされます。クライアントはこれを使って非同期レスポンスを対応付けます。
- **デバッグ:** `python vass.py --debug` で実行すると、サーバーは受信メッセージをログに記録します(`<= received: ...`、`execute: ...`)。

## 3. ハンドシェイク

接続直後に、プラグインは `hello` メッセージを送信する必要があります:

```json
{"type": "hello", "name": "my_plugin", "version": "1.0.0",
 "min_app": "0.8.0", "subscribe": ["state", "audio"]}
```

| フィールド | 必須 | 説明 |
|---|---|---|
| `type` | 必須 | `"hello"` |
| `name` | 必須 | プラグイン識別子(フォルダ名とマニフェストと一致している必要があります) |
| `version` | 必須 | プラグインのバージョン |
| `min_app` | 必須 | 必要な VASS の最小バージョン。アプリのバージョンがそれより低い場合、サーバーは `error` を返して接続を閉じます |
| `subscribe` | 任意 | 受信するブロードキャストイベントタイプのリスト(`"state"`、`"audio"`) |

Python の例:

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

## 4. プラグイン → サーバーのメッセージ

すべてのコマンドは次の形式です:

```json
{"type": "cmd", "cmd": "<command>", ...parameters}
```

### 4.1 レスポンスを伴わないコマンド(fire-and-forget)

| cmd | パラメータ | 効果 |
|---|---|---|
| `set_state` | `state`(例: `"listening"`、`"paused"`) | VASS の状態を設定します。`state="listening"` の場合、音声認識のノイズフロアもリセットされます |
| `tts_enqueue` | `text`、`speed`(デフォルト `0.9`) | テキストを発話します。テキストが英語でない場合、**アプリの言語に自動翻訳**されます。TTS キューは `defer_if_busy=True` を使用します |
| `notify` | `text`、`priority`(デフォルト `5`)、`data` | デスクトップ通知を表示します。テキストは上記と同様に翻訳されます |
| `ui_register` | `schema`(§6 を参照) | プラグインに関連付けられた宣言的 UI を登録します |
| `ui_state` | `values`(キー → 値の dict) | プラグイン UI の状態を更新します(GUI が 1 秒ごとにポーリングします) |

### 4.2 リクエスト / レスポンス型コマンド

必ず `request_id` を含める必要があります。サーバーは同じ `request_id` を使って **タイプ** `*_response` で応答します。

| cmd | パラメータ | レスポンスタイプ | レスポンスのフィールド |
|---|---|---|---|
| `tts_to_file` | `text`、`output_path`、`speed` | `tts_file_response` | `duration_sec`、`output_path` |
| `ai_query` | `prompt`、`temperature`(0.1)、`max_tokens`(300)、`extra_body` | `ai_response` | `response`(文字列) |
| `chat_text` | `prompt` | `chat_response` | `response`(メモリ、プロファイル、ツールなど VASS のパイプライン全体を通ります) |
| `idle_check` | — | `idle_response` | `input_idle_seconds` |
| `resource_check` | — | `resource_response` | `cpu`、`ram`、`gpu`、`vram` |
| `conversation_history` | `limit`(デフォルト 10) | `history_response` | `history`(`{"role": …}` のリスト) |
| `app_info` | — | `app_info_response` | `language`、`version`、`debug`、`state` |
| `rss_items` | `limit`(デフォルト 10) | `rss_response` | `items`(`{title, source, summary, guid, link, pubDate}` のリスト) |
| `ui_list` | — | `ui_list_response` | `uis`(登録済みプラグイン名のリスト) |

重要な注意点:

- `ai_query` と `chat_text` は専用スレッド上で実行されます。レスポンスは遅れて届く可能性があるため、`recv` でイベントループをブロックしないでください。
- `ai_query` はセマフォで直列化されます(同時に実行される AI 呼び出しは 1 つだけ)。
- OpenAI クライアントが利用できない場合、`ai_query` は `response` 内に JSON 文字列 `{"error": …}` を返します。
- `tts_to_file` は指定されたパスに WAV ファイルを生成し、秒単位の再生時間を返します。

同期リクエストのクライアントパターン:

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

## 5. サーバー → プラグインのメッセージ

### 5.1 ブロードキャスト(購読しているプラグインのみ)

| type | フィールド | タイミング |
|---|---|---|
| `state` | `state`、`prev`、`source` | VASS の状態が変わるたび(`listening`、`paused`、`playing` など) |
| `audio` | `rms`、`noise_floor`、`auto_paused`、`listening` | キャプチャされたオーディオフレームごと |

### 5.2 直接送信されるメッセージ

| type | フィールド | タイミング |
|---|---|---|
| `error` | `msg` | ハンドシェイクの拒否(`min_app` バージョンが満たされない)またはサーバーエラー |
| `cmd`(値は `cmd="ui_action"`) | `action`(`{key, event, values, selected}`) | ユーザーが GUI からプラグインの宣言的 UI を操作したとき |

プラグインの `_on_message` は、既存のパターンに従って、少なくとも `error`、`audio`、`state` のタイプと `cmd` コマンド(`ui_action`)を処理する必要があります:

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

## 6. 宣言的 UI(`ui_register`)

プラグインは JSON スキーマでインターフェースを記述し、GUI が自動的にレンダリングします。状態は双方向に流れます:

- **プラグイン → GUI:** `values` を含む `ui_state`。
- **GUI → プラグイン:** ユーザーがボタンを押したり値を変更したりしたときの `ui_action`。

スキーマ:

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

行の種類:

| kind | 固有のプロパティ | 送信されるイベント |
|---|---|---|
| `toggle` | `value`(bool)、`instant`(bool) | `toggle` |
| `slider` | `min`、`max`、`value`、`instant` | `slider` |
| `text` | `value` | —(ボタンがクリックされたときに `values` に含まれます) |
| `combo` | `options[]`、`value` | —(同上) |
| `button` | — | `button` |
| `list` | `columns[]`、`items[]`(`id` 付き) | `selected` = アイテム ID の `select` |
| `label` | `text` | — |

同期のルール:

- `instant:true` の `toggle`/`slider` は、関連する `ui_action` を即座に送信します。
- 「バッファリングされた」ウィジェット(`text`、`combo`、非インスタントのトグル / スライダー)は `values` に集められ、ボタンアクションと一緒に送信されます。
- GUI は 1 秒ごとに `get_plugin_uis()` をポーリングし、プラグインが送信した状態(`ui_state`)を適用します。

## 7. 設定と GUI 設定

各プラグインは独自の `settings.ini` を持ちます(ない場合は `settings.example.ini` からコピーされます)。プラグインは独自の `_load_config()` でこれを読み取ります。

**重要なルール:** `[gui.<field>]` セクションは、GUI 設定ダイアログに表示されるフィールドを定義します。各フィールドは、値が書き込まれる「通常の」INI セクションを指定します(`section`)。GUI キーは通常のセクション内に配置してはいけません。

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

サポートされているフィールドタイプ(`plugin_server.py` の `get_plugin_config`):

| type | プロパティ |
|---|---|
| `slider` | `min_value`、`max_value`、`step`、`decimals` |
| `dropdown` | `options`(パイプ区切り) |
| `text` | — |
| `note` | `note` / `note_<lang>`(情報表示のみ、値は書き込みません) |

各フィールドは、ローカライズ用の `label` と `label_<lang>`、および対象の INI セクションを示す `section` を受け付けます。

GUI は `PluginServer.set_plugin_value(name, section, key, value)` で値を書き込みます。プラグインはそれらを再読み込みする必要があります(例: 次回使用時に INI を読み直す)。

## 8. プラグインの構造とライフサイクル

### ディレクトリ構成

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

| フィールド | 説明 |
|---|---|
| `name` | プラグインのフォルダ名と一致している必要があります |
| `version` | プラグインのバージョン |
| `min_app` | VASS の最小バージョン |
| `platform` | `"*"` |
| `description` / `description_<lang>` | ローカライズされた説明文 |
| `subscriptions` | 受信するブロードキャストタイプ(`state`、`audio`) |
| `depends_on` | ロード前に有効化されている必要があるプラグインのリスト |

### `plugins/plugins.json`

```json
{
  "port": 8765,
  "plugins": {
    "my_plugin": {"enabled": true}
  }
}
```

### ライフサイクル

1. 起動時に、`PluginServer.run()` は `enabled: true` のプラグインを `depends_on` でソートして自動起動します(依存関係が先に起動します。依存関係が不足しているプラグインは `blocked` のままになります)。
2. 各プラグインは `subprocess.Popen([python, plugin.py], cwd=<dir>)` として起動されます。
3. 起動試行は最大 **2 回** 行われます(その後カウンターはリセットされます)。
4. `enable_plugin`/`disable_plugin`/`stop_plugin`/`start_plugin` が実行時状態を制御します。`remove_plugin`(外部プラグインのみ)はディレクトリと設定エントリを削除します。
5. `get_plugins_status` は各プラグインについて `enabled`、`running`、`status`(`running|blocked|error|stopped|disabled`)、`missing_deps` を返します。

## 9. ステップバイステップガイド: プラグインを作成する

VASS の状態と AI を使用する最小限のプラグインを作成します。

### ステップ 1 — フォルダとマニフェスト

次の内容で `plugins/external/hello_plugin/` を作成します:

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

### ステップ 2 — 設定

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

### ステップ 3 — `plugin.py`

既存プラグインのパターンに従った完全なスケルトン:

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

### ステップ 4 — 有効化とテスト

1. `plugins/plugins.json` に追加します:
   ```json
   "hello_plugin": {"enabled": true}
   ```
2. VASS を起動します(`python vass.py --debug`)。サーバーがプラグインを自動起動します。ログには、状態が変わるたびに `Hello from 'hello_plugin'` と `State -> listening` が表示されます。
3. 音声を確認します: プラグインが設定されたメッセージを発話します。

## 10. デバッグとトラブルシューティング

| 症状 | 考えられる原因 | 解決策 |
|---|---|---|
| `Port 8765 already in use` | 別の VASS インスタンスが実行中 | 他のインスタンスを閉じる |
| `App version X < required Y` | マニフェストの `min_app` が VASS のバージョンより高い | `min_app` を下げるか VASS を更新する |
| Plugin `error`(`socket_missing`/`process_missing`) | プロセスは生存しているがソケットが接続されていない(またはその逆) | プラグインの `log.txt` を確認し、再起動する |
| `ai_query` に応答がない | OpenAI クライアントが利用できない、またはタイムアウト | `settings.ini` の `[ai]` を確認する。`timeout` を増やす |
| プラグインが起動しない | 依存関係が無効 | `depends_on` のプラグインを有効にする |
| コードの変更が反映されない | プロセスがまだ実行中 | GUI からプラグインを再起動する |
| TTS テキストが予期せず翻訳される | `tts_enqueue`/`notify` は EN 以外の場合はアプリの言語に翻訳される | 翻訳を回避するには `tts_to_file` を使用する |

---

## 付録 — サマリースキーマ

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
