# VASS — 音声アシスタントソフトウェア

## VASSとは

VASSは、Windows、macOS、Linux向けの音声アシスタントです。音声コマンドに応答し、スクリプトを実行し、イベントやリマインダーを管理し、メールの読み上げと返信を行い、OpenAI互換API経由でローカルまたはリモートのAIとやり取りします。また、AIがファイル、ブラウザ、カレンダー、メール、ニュース、システムツールへ直接アクセスできるようにするMCPサーバーも内蔵しています。

**デフォルトのウェイクワード:** 「Erika」(変更可能)

**現在のバージョン:** 0.8.7

**主な機能:**
- Silero VADと適応型ノイズフロアを備えたWhisper (faster-whisper)による音声認識
- 多段フォールバックチェーンを備えたKokoro TTSによる自然な音声合成
- ローカルまたはリモートのAI (llama.cpp、OpenAI、互換サーバー)と、任意のllama.cpp自動起動
- 70以上の組み込み関数を備えたデスクトップ自動化用のVASScriptスクリプト
- エディタGUI付きのイベント・スケジュール管理(リマインダー、自動処理)
- 多言語対応のカウントダウンタイマー(音声起動、同時5つ)
- AIオーケストレーション用の50以上のツールを備えたMCPサーバー(ブラウザ、メール、ニュース、カレンダー、場所、ファイル、システム)
- 自動分類・要約・ユーザープロファイル注入を備えた永続メモリ
- 統合メールクライアント: Gmail、IMAP、POP3(キュー、連絡先、AI送信メール対応)
- プラグインシステム: ローカルTCPソケット経由の内部・外部プラグイン
- イベントタイプ別ルーティング対応の通知センター
- メッセージ単位の操作に対応した会話履歴ビューア
- 9言語対応
- コンテキストオーバーフロー保護(truncateまたはAI要約)
- オーディオデバイス選択(入力/出力)
- 複雑なAIタスク向けのマルチターンツール呼び出し
- 20万都市の位置データベースを備えた3ソースの天気システム
- タイムシフト音声コマンド(「5分後にシャットダウン」)
- GUIのMCPツールアクティビティリアルタイムインジケーター
- 多言語ストップワード対応のヒューリスティックなコンテキスト圧縮
- トークン正確なコンテキストカウント(tiktoken)
- SHA-256認証と監査ログを備えたスクリプト実行サンドボックス
- 機密性の高いオンラインツール向けセキュリティゲート(同意、レート制限、監査ログ)
- 任意のOS自動起動

---

## システム要件

- **Python 3.13**以上
- **AIサーバー**(llama.cppまたはOpenAI互換)がシステムにインストール済み・設定済みであること。VASSは設定されていればllama.cppを自動起動できますが、llama.cppの**インストールやAIモデルのダウンロードは行いません**: 別途入手する必要があります。
- **インターネット接続**(TTS/STTモデルのダウンロードとリモートAI用)
- ローカルAIには**NVIDIA GPU推奨**(CPUでも可能ですが遅い)
- **動作するマイク**
- Windows 10+、macOS 12+、または最新のLinux

---

## インストール

### グラフィカルインストール(推奨)

[リリースページ](https://github.com/logicheneurali/vass/releases)からインストーラーをダウンロードして実行します。ウィザードがPython、VASS、llama.cpp、AIモデルを自動的にインストールします — 手動設定は不要です。

### ガイド付きインストール

プロジェクトをダウンロードまたはクローンし、フォルダーに入ってスクリプトを実行します:

```bash
cd vass
python install.py
```

> **注:** ガイド付きインストールはVASSをセットアップしますが、AIサーバーやモデルは**インストールしません**。
> OpenAI互換サーバーがすでに起動している必要があります(llama.cpp、Ollama、LM Studio、Groq、OpenAIなど)
> またはVASSの設定でllama.cppを構成します(自動起動可能)。

**注:** ガイド付きインストール手順はまだ実験的なもので、すべてのシステムで動作しない場合があります。問題が発生した場合は、以下の手動インストール手順を使用してください。

ウィザードは次の手順をガイドします:
1. 言語の選択
2. 前提条件のチェック(Python 3.13+、pip)
3. インストール先フォルダー
4. パラメータ設定(AIのURL、モデル、ウェイクワード)
5. ファイルのコピー
6. Python仮想環境の作成(.venv)
7. Pip依存関係のインストール
8. settings.iniファイルの作成
9. ランチャーの作成

### 手動インストール

```bash
# 目的のフォルダーにクローンまたはコピーする
cd VASS

# 仮想環境を作成する
python -m venv .venv

# アクティベート(Windows)
.venv\Scripts\activate
# または (macOS/Linux)
source .venv/bin/activate

# 依存関係をインストールする
pip install -r requirements.txt

# Playwright用のChromiumをインストールする(ウェブ検索)
playwright install chromium

# config/settings.iniを作成する(config/settings.example.iniからコピー)
```

---

## 設定

すべての設定は `config/settings.ini` にあります(テンプレートは `config/settings.example.ini`)。最も重要なものは以下のとおりです:

| セクション | パラメータ | 説明 |
|---------|-----------|-------------|
| `[locale]` | `language` | 言語(it/en/de/fr/es/pt/ja/ko/zh) |
| `[wakeword]` | `wakeword` | ウェイクワード(デフォルト: erika) |
| `[wakeword]` | `sensitivity` | ウェイクワード検出の感度 |
| `[commands]` | `similarity` | 音声コマンドのあいまい一致のしきい値(デフォルト 0.6) |
| `[commands]` | `word_learning_enabled` | 時間の経過とともに新しい話し言葉を学習する(true/false) |
| `[ai]` | `url` | OpenAI互換AIサーバーのURL |
| `[ai]` | `model` | AIモデル名 |
| `[ai]` | `system_message` | アシスタントのパーソナリティ |
| `[ai]` | `api_key` | APIキー(設定されている場合はシステムキーリングに保存) |
| `[ai]` | `mcp_server_url` | バンドルされているMCPサーバーのURL(デフォルト `http://localhost:9988`) |
| `[ai]` | `memory_tokens` | メモリの最大サイズ |
| `[ai]` | `context_length` | 最大コンテキストトークン(0 = 自動) |
| `[ai]` | `overflow_strategy` | コンテキストオーバーフローの処理: `truncate` または `summarize` |
| `[ai]` | `allow_ai_scripts` | AIによるVASScriptスクリプトの実行を許可する(true/false) |
| `[llamacpp]` | `llama_server_path` | llama.cppサーバーの場所 |
| `[llamacpp]` | `llama_autostart` | VASS起動時にllama.cppを自動起動する(true/false) |
| `[resources]` | `cpu_max`, `ram_max`, `gpu_max`, `vram_max` | AI操作を制限するリソース上限 |
| `[events]` | `reminder_advance` | イベントの何秒前にリマインダーを発行するか(デフォルト 3600) |
| `[audio]` | `input_device`, `output_device` | オーディオデバイスの選択(-1 = システムデフォルト) |
| `[audio]` | `input_volume`, `output_volume` | 入力/出力の音量レベル(0-1) |
| `[audio]` | `app_volume` | TTSのマスター音量(旧 `[tts] volume` を置き換え) |
| `[google]` | — | Google Calendar / Gmail / Google Home統合 |
| `[startup]` | `app_autostart` | ログイン時にVASSを自動起動する(true/false) |
| `[debug]` | `debug_enabled` | 詳細ログを `log/debug.log` に書き込む(true/false) |

VASSの実行中に設定を変更すると、自動的に再読み込みされます。

---

## 日常的な使い方

### 起動

`vass.bat`(Windows)または `vass.sh`/`vass.command`(macOS/Linux)をダブルクリックします。

またはターミナルから:
```bash
cd VASS
.venv\Scripts\python vass.py    # Windows
.venv/bin/python vass.py         # macOS/Linux
```

> **注:** 初回起動時には、音声認識(Whisper)と音声合成(Kokoro)のモデルがHuggingFaceから自動的にダウンロードされます。初回起動には数分かかる場合があります(約2〜4GBのダウンロード)。これは一度だけ行われます。

### ウェイクワード

ウェイクワードは `config/settings.ini` ファイル内でユーザーが**変更可能**で、任意の単語や短いフレーズを指定できます。デフォルトは「**Erika**」です。

VASSがウェイクワードを検出すると、コマンドを受け付ける準備ができたことを知らせるビープ音を発します。ビープ音の後に話してください。

例:
- *「Erika」*(ビープ音を待つ)、次に *「what is the weather?」*
- *「Erika」*(ビープ音を待つ)、次に *「read the latest news」*
- *「Erika」*(ビープ音を待つ)、次に *「what is artificial intelligence?」*
- *「Erika」*(ビープ音を待つ)、次に *「translate to italian good morning everyone」*
- *「Erika」*(ビープ音を待つ)、次に *「recipe pasta carbonara」*

### モード: チャットと文字起こし

VASSは2つのモードで動作し、ポップアップメニュー(メインボタンの右にある≡ボタン)から選択できます:

- **チャット** `[C]` — アプリが音声コマンドを認識してアクションを実行(スクリプト、システムコマンド)したり、AIとやり取りします。応答はTTSで読み上げられます。
- **文字起こし** `[T]` — コマンドを解釈する代わりに、VASSはウェイクワードの後にユーザーが話した内容を忠実に文字起こしします(常にビープ音の後)。テキストはアクティブなアプリケーションに貼り付けられ、VASSはテキストディクテーションシステムになります。

現在のモードはメインボタンに表示されます: チャットは `[C]`、文字起こしは `[T]`。最後に使用したモードは再起動時に復元されます。

### メモリモード

GUIメニューまたはメインボタンのクリックから:
- **完全** — AIはメモリの要約とユーザープロファイルを受け取ります
- **限定** — AIは最近の履歴のみを受け取ります
- **なし** — 履歴コンテキストはありません

### 音声コマンド

コマンドは `config/commands.ini`(標準のINI形式、`phrase = action`)で設定され、GUIエディタ(`python src/commands_editor.py`)からも編集できます。言語固有のファイル `config/commands_{lang}.ini` は基本ファイルの上に読み込まれます。各行は **phrase = action** のペアです: phraseは認識するパターン(`{variables}` を含められます)、actionは実行する内容です。

```ini
[general]
search {term} = script:search
open {program} = start {program}
search online {escaped_terms} = start firefox "https://duckduckgo.com?q={escaped_terms}"
what time is it = script:datetime

[system]
shutdown system = shutdown /s /t 60
lock screen = rundll32.exe user32.dll,LockWorkStation
```

#### マッチングの仕組み

1. **あいまい認識**: 完全一致は必須ではありません。VASSは類似度アルゴリズム(`difflib`)を使用して、話されたフレーズをすべてのパターンと比較します。しきい値(デフォルト `0.6`、`config/settings.ini` の `[commands] similarity` で変更可能)を超える最も高いスコアを持つパターンがアクティブになります。

2. **変数 `{name}`**: その位置の話された単語をキャプチャします。例: *「search cats on the internet」* と言うと `term = "cats on the internet"` がキャプチャされます。

3. **エスケープ変数 `{escaped_name}`**: 通常の変数と同じですが、キャプチャされたテキストはURLエンコードされます(スペースは `%20` になります)。ウェブ検索に便利です。

4. **タイムシフトコマンド**: `{duration}` サフィックス(例: *「shutdown in 5 minutes」*)は、タイマーシステムを介して指定時間後にコマンドを実行するようにスケジュールします。

5. **単語学習**: 有効にすると、VASSは時間の経過とともに認識を向上させるため、単語の発音方法を記録します。

6. **AIフォールバック**: 類似度のしきい値を超えるコマンドがない場合、フレーズは自然言語応答のためにAIに送信されます。

#### カンマによる代替(直積)

カンマを使用して、各単語位置に複数の代替を指定できます。**スペース**は単語位置を区切り、**カンマ**は位置内の代替を区切ります。VASSはすべての可能な組み合わせ(直積)を生成します。

```ini
# 単一位置: 前置詞の代替
click the,on text {text}
```
2つのパターンが生成されます: `click the text {text}`、`click on text {text}`。

```ini
# 2つの位置: 各位置に独自の代替がある
aa,xx bb,cc {var}
```
4つのパターンが生成されます: `aa bb {var}`、`aa cc {var}`、`xx bb {var}`、`xx cc {var}` (2x2 = 4)。

```ini
# 混合: 固定語 + 代替
turn on,off {device}
```
2つのパターンが生成されます: `turn on {device}`、`turn off {device}`(`on` と `off` の間にスペースがない -> 同じ位置)。

話されたフレーズは生成されたすべてのパターンと比較されます。最良のあいまい一致が勝ちます。

#### アクションタイプ

| プレフィックス | 例 | 動作 |
|--------|---------|----------|
| `script:` | `script:search` | `scripts/search.vass` を実行します。キャプチャされた変数は `$param1`、`$param2` などになります。 |
| `vasscript:` | `vasscript:events` | `script:` と同じ(代替プレフィックス) |
| コマンド | `shutdown /s` | システムコマンドとして直接実行されます |

#### セクション名

`[general]` や `[system]` のようなセクション名は単なる整理用のカテゴリであり、マッチングには影響しません。重要なのは**キー**(認識するフレーズ)です。

### VASScriptスクリプトの作成

GUIメニューからスクリプトエディタを開くか、以下を実行します:
```bash
python src/scripts_editor.py
```

すべてのスクリプトは `.vass` 拡張子で `scripts/` フォルダーに置きます。

**承認**: 新しいスクリプトまたは変更されたスクリプトを実行する前に、VASSは許可を求めるポップアップを表示します。スクリプトはSHA-256ハッシュで検証されます(システムキーリングに保存)。スクリプトファイルが承認後に変更された場合、権限は自動的に取り消され、次回の実行時に再びポップアップが表示されます。権限は関数単位またはスクリプト全体に対して付与できます。これにより、明示的な同意なしにスクリプトがお使いのマシンで実行されることはありません。

完全な言語リファレンスについては、[VASCRIPT_REFERENCE.md](../Allowed_root/VASCRIPT_REFERENCE.md) ファイルを参照してください。

### イベントとリマインダー

イベントは `Allowed_root/events.json` ファイルで管理されます。音声リマインダーは1時間前(`[events] reminder_advance` で変更可能)に発行されます。

スケジュール(自動処理)は `Allowed_root/schedules.json` にあり、TTS通知付きでコマンド実行をトリガーします。追加フラグ: `silent`、`run_on_startup`、`check_already_running`、`wait_for_completion`。

### プラグインシステム

VASSはローカルTCPサーバー(`localhost:8765`)を公開しており、プラグインはこれを使用してアプリと通信します: TTS、通知、AIクエリ、RSS項目、チャット、宣言型UIなど。**内部プラグイン**(VASSにバンドル済み)は削除できません。**外部プラグイン**はGUI(プラグインメニュー)から有効化・無効化・削除できます。

バンドルされている内部プラグイン: ノイズ自動一時停止、プロアクティブエージェント、ユーザープロファイル、RSSリーダー、世界のイベント、Telegramボット。ディスク上の外部プラグイン: 画像生成、ニュース公開、タイムライン表示。

完全なプロトコルと独自プラグインの作成方法については、[PLUGIN_DEV_ja.md](PLUGIN_DEV_ja.md) ガイドを参照してください(`PLUGIN_DEV_{en,it,de,fr,es,pt,ko,zh}.md` でも利用可能)。

### メール

設定 → メールで1つ以上のアカウントを構成します(GmailはOAuth、IMAP/POP3は標準のSSL/TLS)。受信メッセージは検出されて通知されます。AIはメールの検索、読み取り、返信、転送、送信ができます — ただし、送信メールは常に**キュー**に入れられ、送信トレイから承認して送信する必要があります。連絡先は暗号化されて保存されます。

---

## GUIインターフェース

- **メインボタン** — クリックで状態を変更(リスニング/一時停止)。マウスホイールで音量調整。ドラッグでウィンドウを移動。
- **音量バー**(上部、緑) — 現在のTTS音量を表示
- **マルチステートバー** — 状況に応じてメモリ使用量、音量、またはスクリプト/アクティビティの進行状況を表示
- **通知センター**(ベル) — タイプ別タブ付きで、メッセージ操作とすべて既読機能付き
- **ツールインジケーター** — AIが使用しているMCPツールを表示するリアルタイムアイコン
- **マイクボタン** — チャットモードでの直接音声入力
- **プラグインメニュー** — プラグイン、プラグイン設定、プラグインUIを管理
- **設定ダイアログ** — GUIからの完全な設定(設定メニュー)
- **自動フェード** — アイドル時や全画面表示時にウィンドウが半透明になる
- **スプラッシュスクリーン** — 起動時の読み込み進行状況
- **テーマ** — アプリとすべてのエディタで共有されるテーマ

### ショートカット

| キー | 操作 |
|-------|--------|
| `Ctrl+S` | 保存(エディタ内) |
| ボタンクリック | 状態の変更 |
| ボタン上のホイール | 音量調整 |
| 右クリック | コンテキストメニュー |
| ボタンのミドルクリック | 終了 |

---

## トラブルシューティング

> **重要:** このアプリケーションは使用するAIモデルに大きく依存します。効果のないモデルやMCPツールの使用に適さないモデルは、機能を損なう可能性があります。

### VASSが起動しない
- Python 3.13+を確認: `python --version`
- `.venv` が存在し、依存関係が含まれていることを確認
- `log/debug.log`(`[debug] debug_enabled = true` を有効化)と `log/crash.log` を確認

### マイクが機能しない
- マイクが接続され、他のアプリで使用されていないことを確認
- マイクのシステム権限を確認
- Windows: 設定 → プライバシー → マイク

### AIが応答しない
- AIサーバーが `http://127.0.0.1:8080/v1` で実行されていることを確認
- `config/settings.ini` の `[ai] url` を確認
- llama.cppを使用している場合、モデルが存在し、`[llamacpp] llama_server_path` が正しいことを確認
- llama.cppのエラーについて `log/llamacpp.log` を確認

### OCRが画面上のテキストを認識しない
- 画面上のフォントサイズまたはテキストのコントラストを上げる
- EasyOCRは大きなフォントと高いコントラストで最適に動作します
- OCR言語は設定されたロケールに自動的に適応します

### AIがツールを使用できない
- 一部のオンラインツールは同意が必要です(セキュリティゲート) — 保留中のリクエストについてInfoPanelを確認
- MCPサーバーが `http://localhost:9988` で到達可能か確認(`[ai] mcp_server_url` を参照)
- MCPエラーについて `log/mcp_server.log` を確認

---

## 重要なファイル

| ファイル | 説明 |
|------|-------------|
| `config/settings.ini` | メイン設定 |
| `config/commands.ini` | 基本の音声コマンド(プラス `commands_{lang}.ini`) |
| `config/notifications.ini` | イベントタイプ別の通知ルーティング |
| `scripts/*.vass` | お使いのVASScriptスクリプト |
| `Allowed_root/events.json` | お使いのイベントとリマインダー |
| `Allowed_root/schedules.json` | 自動処理 |
| `Allowed_root/memory.json` | 会話履歴とメモリ |
| `Allowed_root/private_profile.json` | AIコンテキストに注入されるユーザープロファイル |
| `plugins/` | 内部および外部プラグイン |
| `log/debug.log` | 詳細なデバッグログ(有効時) |
| `log/crash.log` | クラッシュログ |
| `log/faulthandler.log` | フォールトハンドラの出力 |
| `log/llamacpp.log` | llama.cppサーバーログ |
