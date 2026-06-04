# VASS — 詳細ドキュメント

## 全体アーキテクチャ

VASSは、ファイルキュー、Qtシグナル、および直接呼び出しを介して通信する複数の独立コンポーネントで構成されるモジュラーアプリケーションです。

```
┌─────────────────────────────────────────────────┐
│                    vass.py                       │
│              メインオーケストレータ                │
│  - コンポーネント初期化                          │
│  - リスン/ライトループ                           │
│  - AIフォールバック管理                          │
│  - スクリプト実行                                │
│  - ファイルキューウォッチドッグ                   │
└──────┬──────┬──────┬──────┬──────┬──────────────┘
       │      │      │      │      │
       ▼      ▼      ▼      ▼      ▼
  ┌────────┐┌─────┐┌─────┐┌────┐┌──────────┐
  │  gui.py││TTS  ││STT  ││イベ││mcp_server│
  │  PySide││エン ││Whisp││リマ││  15ツール│
  └────────┘└─────┘└─────┘└────┘└──────────┘
```

### 主要コンポーネント

| コンポーネント | ファイル | 責任 |
|-----------|------|---------------|
| オーケストレータ | `vass.py` (1313行) | 初期化、メインループ、AI、スクリプト、メモリ |
| GUI | `gui.py` (832行) | PySide6ウィンドウ、バー、フェード、サブウィンドウ |
| TTS | `tts_engine.py` (138行) | Kokoro TTS、音声再生、音量 |
| STT | `voice_recognition.py` (133行) | faster-whisper、ウェイクワード検出 |
| インタープリタ | `script_engine.py` (761行) | VASScriptパーサー、評価器、26関数 |
| イベント | `event_reminder.py` (280行) | イベント/スケジュール監視、TTSアラート |
| コマンド | `command_executor.py` (184行) | ファジーパターンマッチング、変数抽出 |
| MCPサーバー | `mcp_server/` | FastMCPサーバー、15ツール、IPベースACL |
| OCR | `script_engine.py:_preprocess_screen` | 前処理付きEasyOCR |
| アイドル | `idle_tracker.py` (67行) | クロスプラットフォームアイドル検出 |
| リソース | `resource_monitor.py` (52行) | AIリクエスト前のCPU/RAM/GPU/VRAMゲート |
| ログ | `log_utils.py` (13行) | ログファイルローテーション |

---

## 音声パイプライン

```
マイク ──► sounddevice (コールバック) ──► 音声キュー ──► Whisper (文字起こし)
                                                             │
                    ┌────────────────────────────────────────┤
                    ▼                                        ▼
         "Erika"検出？                          完全な文字起こし
                    │                                        │
                    ▼                                        ▼
              確認音                            commands.ini と一致？
                    │                                  │            │
                    ▼                                  ▼            ▼
             コマンド待機                          コマンド     一致なし
                    │                              発見
                    ▼                                  │            │
             文字起こし                                 ▼            ▼
                    │                          アクション実行   AIフォールバック
                    ▼
            Kokoro TTS ──► スピーカー
```

### 音声コンポーネント詳細

- **入力**: `sounddevice.InputStream` (16000 Hz モノラル、コールバック付き)
- **VAD**: 無音フィルタリング用 webrtcvad
- **ウェイクワード**: Whisper tiny モデル、文字起こし内で "erika" を検索
- **文字起こし**: ウェイクワード確認後の Whisper medium モデル (設定可能)
- **TTS**: Kokoro `KPipeline(lang_code='i')`、音声 `if_sara`、UUIDファイル名でWAV生成
- **再生**: `sounddevice.play()` (同期用 `_tts_done` イベント付き)

---

## VASScript — スクリプト言語

VASScriptはデスクトップ自動化のためのミニマリストなスクリプト言語です。行単位の実行、算術演算子なし、すべては文字列です。

### 利用可能な関数 (全26)

#### AI と TTS
- `ai(prompt)` — AIに問い合わせ、テキストを返す
- `say(text, speed?)` — 音声合成 (速度: 0.5-1.5)
- `listen(prompt?)` — 音声を録音し、文字起こしを返す

#### システム
- `run(command)` — PowerShellを実行し、出力を返す
- `wait(seconds)` — 実行を一時停止
- `exit()` — スクリプトを終了
- `getdatetime()` — 現在の日付/時刻 "YYYY-MM-DD HH:MM"

#### 画面 (OCR)
- `screen_search(query)` — 画面上のテキストを検索、`$_sx`、`$_sy`、`$_sw`、`$_sh` を設定
- `screen_click(x?, y?)` — 座標をクリック
- `screen_highlight(x, y, w?, h?, dur?)` — 領域をハイライト

#### ウィンドウとキーボード
- `setActiveWindow(name)` — プロセス/タイトルでウィンドウをアクティブ化
- `sendText(text)` — 人間らしい遅延でテキストを入力

#### イベント
- `addevent(date, time, duration, description, recur?)` — イベントを追加
- `listevents(until_date)` — イベントを一覧表示 (JSON)
- `removeevent(name)` — イベントを削除 (ファジーマッチ)
- `prettyevents(json)` — イベントを読みやすいテキストに整形

#### メモリとクリップボード
- `readinfo(id)` — 情報ファイルを読み取り
- `writeinfo(text)` — 情報ファイルを書き込み、IDを返す
- `clipboardget()` — クリップボードを読み取り
- `clipboardset(text)` — クリップボードに書き込み

#### 条件
- `ifcontains(var, substring, if_true, if_false?)` — 部分文字列を含むか
- `ifempty(var, if_empty, if_notempty?)` — 空かどうかをチェック

#### ユーティリティ
- `trim(text)` — スペースを削除
- `len(text)` — 文字列の長さ
- `contains(text, substring)` — 含むか？ ("True"/"False")
- `equals(a, b)` — 等しいか？ ("True"/"False")

### 変数

```vascript
$name = "Fabio"            # 代入
$age = "54"                # すべては文字列
$result = ai("こんにちは")  # 関数の結果
say("こんにちは {$name}!")   # 文字列内の補間
say("あなたは {$age} 歳です") # 変数でも同様
```

**注意:** VASScriptは `+` による連結をサポートしていません。文字列内で `{$var}` を使用してください。

### screen_search グローバル変数

`screen_search()` は最初の一致に対して以下のグローバル変数を設定します:
- `$_sx`, `$_sy` — 中心座標
- `$_sw`, `$_sh` — 幅と高さ

---

## MCPサーバー — 15ツール

MCPサーバーは、`http://localhost:9988` でAIがアクセス可能な15のツールを公開します。

### ファイルシステム
- `read_file(path)` — Allowed_root 内のファイルを読み取り
- `write_file(path, content)` — Allowed_root 内のファイルに書き込み

### Web
- `browse(url)` — ページをダウンロード (静的、httpx+BeautifulSoup)
- `websearch(query)` — Playwright経由でDuckDuckGoを検索
- `webfetch(url)` — Playwright経由でJSレンダリングページを読み込み

### 計算と時間
- `calculate(expression)` — 数式を評価 (AST、安全)
- `current_time()` — 現在の日付/時刻
- `disk_space()` — 利用可能なディスク容量

### 実行
- `execute(command)` — コマンドを実行 (ホワイトリスト)
- `script(script_name)` — VASScriptファイルを実行
- `interact(code)` — インラインVASScriptを実行

### メモリとクリップボード
- `readinfo(id)` — 情報ファイルを読み取り
- `writeinfo(text)` — 情報ファイルを書き込み
- `clipboardget()` — クリップボードを読み取り
- `clipboardset(text)` — クリップボードに書き込み

### 認証

`mcp_server/config/tools.yaml` によるIPベースのACL。各ツールにホワイトリスト/ブラックリストがあります。デフォルトは拒否。

### スクリプト → VASS 通信

`script` および `interact` ツールはファイルベースのIPCを使用します:
1. リクエストを `scripts/exec_queue.json` に書き込み
2. VASSがキューを読み取り (1秒ポーリング)
3. スクリプトを実行
4. 結果を `scripts/exec_result.json` に書き込み
5. MCPクライアントが結果を読み取り

---

## メモリシステム

### 構造

```
Allowed_root/
  memory.json          # インデックス: {"history": [id1, id2], "summary_id": "id3"}
  memory/
    1780394454383.json  # 単一エントリ: {"info": "JSON文字列"}
    1780427888604.json
    archive/
      2026-06/          # 月次アーカイブ
```

### フロー

1. 各AI交換 (ユーザー+アシスタント) は `memory/` にJSONファイルとして保存されます
2. `memory.json` は最新20件のIDを追跡します
3. 5回の保存後、参照されていないファイルは `archive/{YYYY-MM}/` に移動します
4. 6ヶ月以上経過したアーカイブは削除されます
5. メモリが `memory_tokens * 4` バイトを超えると、AI圧縮がトリガーされます:
   - 古いメッセージがAIによって要約されます
   - 要約は `summary_id` エントリとして保存されます
   - 元のファイルはアーカイブされます

---

## イベントとスケジュール

### events.json
```json
{
  "events": [{
    "date": "2026-06-15",
    "time": "14:30",
    "duration": 60,
    "description": "チームミーティング",
    "recur": "7d",
    "notify": "2026-06-15 13:30:00"
  }]
}
```
- `recur`: "1d"=毎日, "7d"=毎週, "1m"=毎月, "2h"=2時間ごと
- `notify`: 通知が送信されたタイムスタンプ

### schedule.json
```json
{
  "schedules": [{
    "date": "2026-06-05",
    "time": "08:00",
    "duration": 5,
    "description": "バックアップ",
    "recur": "1d",
    "command": "powershell",
    "arguments": "-File backup.ps1"
  }]
}
```
- イベントと同様ですが、コマンド実行をトリガーします
- 開始時と終了時にTTS通知
- 安全なパターンに対するコマンド検証 (`.exe`, `.bat`, `.ps1`, `.py`, `.cmd`, `.vbs`)

---

## 依存関係

### コア (13)
| パッケージ | 用途 |
|-----------|-----|
| `sounddevice` | 音声入出力 |
| `numpy` | 音声と画像用配列 |
| `faster-whisper` | STT音声認識 |
| `webrtcvad` | 音声アクティビティ検出 |
| `kokoro` | TTS音声合成 |
| `torch` | ディープラーニング (Kokoro, Whisper, EasyOCR) |
| `soundfile` | WAVファイル書き込み |
| `openai` | OpenAI互換APIクライアント |
| `mcp[cli]` | FastMCP MCPサーバー |
| `pynput` | マウス/キーボード制御 |
| `PySide6` | Qt6 GUI |
| `keyring` | Windows資格情報マネージャー |
| `httpx` | AIとWeb用HTTPクライアント |

### Web と OCR (6)
| パッケージ | 用途 |
|-----------|-----|
| `beautifulsoup4` | 静的ページHTML解析 |
| `lxml` | 高速XML/HTMLエンジン |
| `playwright` | JSページ用ヘッドレスブラウザ |
| `mss` | 高速スクリーンショット |
| `easyocr` | 画面テキスト認識 |
| `pillow` | 画像処理 |

### ユーティリティ (5)
| パッケージ | 用途 |
|-----------|-----|
| `pyyaml` | MCPサーバー設定 |
| `structlog` | MCP構造化ログ |
| `uvicorn` | MCP HTTPサーバー |
| `psutil` | リソース監視 |
| `misaki` | Kokoroトークン化 |
| `dateparser` | 自然言語日付解析 |

---

## 内部構造

### スレッディングモデル

- **メインスレッド**: Qt GUI (イベントループ)
- **音声スレッド**: sounddevice コールバック
- **VASSスレッド**: リスン/文字起こしループ
- **ウォッチドッグスレッド**: `_watch_commands_file`, `_watch_settings_file`, `_watch_script_queue`
- **一時的**: TTS再生、AIフォールバック、スクリプト実行

### ロック機構

- `_trim_lock` — メモリ操作を保護
- `_script_engine_lock` — アクティブエンジンを保護
- `_tts_done` (イベント) — TTS完了を同期
- `state_lock` — アプリケーション状態を保護

### ファイルベースIPC

**exec_queue.json / exec_result.json**:
- MCPサーバーがスクリプト実行リクエストを書き込み
- VASSがポーリング (1秒)、実行、結果を書き込み
- タイムアウト: ファイルスクリプトは60秒、インラインは120秒

### ファイルウォッチドッグ

VASSは以下の変更を監視します:
- `settings.ini` — 自動再読み込み
- `commands.ini` — 自動再読み込み
- `events.json` / `schedule.json` — 次回アラートの再計算

### 資格情報ストレージ

- Windows: `keyring` 経由の Windows資格情報マネージャー
- macOS: キーチェーン
- Linux: D-Bus Secret Service またはファイル
- 用途: AI APIキー、VASScriptスクリプト権限 (関数ごと)

### i18nシステム

- `locales/*.json`: 9言語、各215+キー
- ファイル `i18n.py`: `t(key, lang)` ルックアップ
- リファレンス: `it.json`
- すべてのファイルは自動的に整列

### ログローテーション

- `debug.log`: 最大500 KB → `.1`, `.2`
- `mcp_server/LOG/`: 最大1 MB → `.1`, `.2`
- ヘルパー: `log_utils.py`

---

## 詳細設定

### [ai]
| パラメータ | デフォルト | 説明 |
|-----------|---------|-------------|
| `url` | `http://127.0.0.1:8080/v1` | APIエンドポイント |
| `model` | `Qwen3-8B-Q4_K_M` | モデル名 |
| `api_key` | (空) | APIキー (ローカルでは空) |
| `system_message` | (長文) | システムプロンプト |
| `mcp_server_url` | `http://localhost:9988` | MCPサーバーURL |
| `memory_tokens` | `4000` | メモリ制限 (トークン×4バイト) |
| `blacklist` | `Amara.org,QTTS` | カンマ区切りのブロックワード |

### [tts]
| パラメータ | デフォルト | 説明 |
|-----------|---------|-------------|
| `tts_engine` | `kokoro` | TTSエンジン |
| `volume` | `0.50` | 音量 0-1 |

### [wakeword]
| パラメータ | デフォルト | 説明 |
|-----------|---------|-------------|
| `wakeword` | `erika` | ウェイクワード |
| `sensitivity` | `0.01` | 感度 0-1 |

### [resources]
| パラメータ | デフォルト | 説明 |
|-----------|---------|-------------|
| `cpu_max` | `75` | CPUしきい値 % |
| `ram_max` | `99` | RAMしきい値 % |
| `gpu_max` | `75` | GPUしきい値 % |
| `vram_max` | `99` | VRAMしきい値 % |
| `resource_timeout` | `30` | 待機タイムアウト秒 |

### [llamacpp]
| パラメータ | 説明 |
|-----------|-------------|
| `llama_server_path` | llama.cpp実行可能ファイルのパス |
| `llama_server_arguments` | コマンドライン引数 |

### [events]
| パラメータ | デフォルト | 説明 |
|-----------|---------|-------------|
| `reminder_advance` | `3600` | リマインダー事前通知秒数 (1時間) |

### [gui]
| パラメータ | デフォルト | 説明 |
|-----------|---------|-------------|
| `x`, `y` | auto | ウィンドウ位置 |
| `width`, `height` | `200`, `32` | ウィンドウサイズ |
| `font_family` | `Segoe UI` | GUIフォント |
| `font_size` | `10` | フォントサイズ |
