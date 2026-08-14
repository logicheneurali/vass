# VASS — Voice assistant software

## What is VASS

VASS is a voice assistant for Windows, macOS, and Linux. It responds to voice commands, runs scripts, manages events and reminders, reads and answers emails, and interacts with a local or remote AI via an OpenAI-compatible API. It also hosts an MCP server that gives the AI direct access to files, browser, calendar, email, news, and system tools.

**Default wake word:** "Erika" (configurable)

**Current version:** 0.8.7

**Key features:**
- Voice recognition via Whisper (faster-whisper) with Silero VAD and adaptive noise floor
- Natural speech synthesis via Kokoro TTS with a multi-step fallback chain
- Local or remote AI (llama.cpp, OpenAI, any compatible server) with optional llama.cpp auto-start
- VASScript scripting for desktop automation with 70+ built-in functions
- Event and schedule management with editor GUI (reminders, automated procedures)
- Multilingual countdown timer (voice-activated, 5 simultaneous)
- MCP server with 50+ tools for AI orchestration (browser, mail, news, calendar, places, files, system)
- Permanent memory with automatic classification, summarization, and user profile injection
- Integrated email client: Gmail, IMAP, POP3 with queue, contacts, and AI-sent emails
- Plugin system: internal and external plugins over a local TCP socket
- Notification center with per-event-type routing
- Conversation history viewer with per-message actions
- 9 language support
- Context overflow protection (truncate or AI summarization)
- Audio device selection (input/output)
- Multi-turn tool calling for complex AI tasks
- 3-source weather system with 200K city geolocation database
- Time-shifted voice commands ("shutdown in 5 minutes")
- Real-time MCP tool activity indicator in GUI
- Heuristic context compression with multilingual stopword support
- Token-accurate context counting (tiktoken)
- Script execution sandbox with SHA-256 authorization and audit logging
- Security gate for sensitive online tools (consent, rate limit, audit log)
- Optional OS autostart

---

## Requirements

- **Python 3.13** or higher
- **AI Server** (llama.cpp or OpenAI-compatible) already installed and configured on the system. VASS can auto-start llama.cpp if configured, but **does NOT install llama.cpp or download AI models**: you must obtain them separately.
- **Internet connection** (for TTS/STT model downloads and remote AI)
- **NVIDIA GPU recommended** for local AI (CPU possible but slow)
- **Working microphone**
- Windows 10+, macOS 12+, or modern Linux

---

## Installation

### Graphical installation (recommended)

Download the installer from the [Releases page](https://github.com/logicheneurali/vass/releases) and run it. The wizard will install Python, VASS, llama.cpp, and an AI model automatically — no manual setup required.

### Guided installation

Download or clone the project, then enter the folder and run the script:

```bash
cd vass
python install.py
```

> **Note:** the guided installation sets up VASS but does **NOT install the AI server or models**.
> You must have an OpenAI-compatible server already running (llama.cpp, Ollama, LM Studio, Groq, OpenAI, etc.)
> or configure llama.cpp in VASS settings (which can auto-start it).

**Note:** the guided installation procedure is still experimental and may not work on all systems. If you encounter issues, use the manual installation procedure below.

The wizard will guide you through:
1. Language selection
2. Prerequisite check (Python 3.13+, pip)
3. Destination folder
4. Parameter configuration (AI URL, model, wake word)
5. File copy
6. Python virtual environment creation (.venv)
7. Pip dependency installation
8. settings.ini file creation
9. Launcher creation

### Manual installation

```bash
# Clone or copy files to the desired folder
cd VASS

# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate
# or (macOS/Linux)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Chromium for Playwright (web searches)
playwright install chromium

# Create config/settings.ini (copy from config/settings.example.ini)
```

---

## Configuration

All settings live in `config/settings.ini` (the template is `config/settings.example.ini`). Here are the most important ones:

| Section | Parameter | Description |
|---------|-----------|-------------|
| `[locale]` | `language` | Language (it/en/de/fr/es/pt/ja/ko/zh) |
| `[wakeword]` | `wakeword` | Wake word (default: erika) |
| `[wakeword]` | `sensitivity` | Wake-word detection sensitivity |
| `[commands]` | `similarity` | Voice-command fuzzy-match threshold (default 0.6) |
| `[commands]` | `word_learning_enabled` | Learn new spoken words over time (true/false) |
| `[ai]` | `url` | OpenAI-compatible AI server URL |
| `[ai]` | `model` | AI model name |
| `[ai]` | `system_message` | Assistant personality |
| `[ai]` | `api_key` | API key (stored in the system keyring if set) |
| `[ai]` | `mcp_server_url` | URL of the bundled MCP server (default `http://localhost:9988`) |
| `[ai]` | `memory_tokens` | Maximum memory size |
| `[ai]` | `context_length` | Max context tokens (0 = auto) |
| `[ai]` | `overflow_strategy` | Context overflow handling: `truncate` or `summarize` |
| `[ai]` | `allow_ai_scripts` | Allow the AI to run VASScript scripts (true/false) |
| `[llamacpp]` | `llama_server_path` | llama.cpp server location |
| `[llamacpp]` | `llama_autostart` | Auto-start llama.cpp with VASS (true/false) |
| `[resources]` | `cpu_max`, `ram_max`, `gpu_max`, `vram_max` | Resource limits that gate AI operations |
| `[events]` | `reminder_advance` | Seconds before an event the reminder is issued (default 3600) |
| `[audio]` | `input_device`, `output_device` | Audio device selection (-1 = system default) |
| `[audio]` | `input_volume`, `output_volume` | Input/output volume levels (0-1) |
| `[audio]` | `app_volume` | Master TTS volume (replaces the legacy `[tts] volume`) |
| `[google]` | — | Google Calendar / Gmail / Google Home integration |
| `[startup]` | `app_autostart` | Start VASS automatically at login (true/false) |
| `[debug]` | `debug_enabled` | Write a verbose log to `log/debug.log` (true/false) |

Settings are automatically reloaded if modified while VASS is running.

---

## Daily usage

### Starting

Double-click `vass.bat` (Windows) or `vass.sh`/`vass.command` (macOS/Linux).

Or from terminal:
```bash
cd VASS
.venv\Scripts\python vass.py    # Windows
.venv/bin/python vass.py         # macOS/Linux
```

> **Note:** on first launch, speech recognition (Whisper) and speech synthesis (Kokoro) models are downloaded automatically from HuggingFace. The first startup may take several minutes (~2-4 GB download). This only happens once.

### Wake word

The wake word is **configurable** by the user in the `config/settings.ini` file and can be any word or short phrase. The default is "**Erika**".

When VASS detects the wake word, it emits a beep to signal it's ready to receive the command. Speak after the beep.

Examples:
- *"Erika"* (wait for beep), then *"what is the weather?"*
- *"Erika"* (wait for beep), then *"read the latest news"*
- *"Erika"* (wait for beep), then *"what is artificial intelligence?"*
- *"Erika"* (wait for beep), then *"translate to italian good morning everyone"*
- *"Erika"* (wait for beep), then *"recipe pasta carbonara"*

### Modes: Chat and Transcription

VASS can operate in two modes, selectable from the popup menu (≡ button to the right of the main button):

- **Chat** `[C]` — The application recognizes voice commands and performs actions (scripts, system commands) or interacts with the AI. The response is read via TTS.
- **Transcription** `[T]` — Instead of interpreting commands, VASS faithfully transcribes what the user says after the wake word (always after the beep). The text is then pasted into the active application, making VASS a text dictation system.

The current mode is shown on the main button: `[C]` for Chat, `[T]` for Transcription. The last used mode is restored on restart.

### Memory mode

From the GUI menu or by clicking the main button:
- **Full** — The AI receives the memory summary and your user profile
- **Limited** — The AI receives only recent history
- **None** — No historical context

### Voice commands

Commands are configured in `config/commands.ini` (standard INI format, `phrase = action`), also editable via the GUI editor (`python src/commands_editor.py`). Language-specific files `config/commands_{lang}.ini` are loaded on top of the base file. Each line is a **phrase = action** pair: the phrase is the pattern to recognize (can include `{variables}`), the action is what to execute.

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

#### How matching works

1. **Fuzzy recognition**: exact match is not required. VASS compares the spoken phrase against all patterns using a similarity algorithm (`difflib`). The pattern with the highest score above the threshold (default `0.6`, configurable in `config/settings.ini` under `[commands] similarity`) is activated.

2. **Variables `{name}`**: capture the spoken words at that position. Example: saying *"search cats on the internet"* captures `term = "cats on the internet"`.

3. **Escaped variables `{escaped_name}`**: same as regular variables, but the captured text is URL-encoded (spaces become `%20`). Useful for web searches.

4. **Time-shifted commands**: a `{duration}` suffix (e.g. *"shutdown in 5 minutes"*) schedules the command to run after the given time via the timer system.

5. **Word learning**: if enabled, VASS records how you pronounce words to improve recognition over time.

6. **AI fallback**: if no command exceeds the similarity threshold, the phrase is sent to the AI for a natural language response.

#### Comma alternatives (Cartesian product)

You can specify multiple alternatives for each word position using commas. **Spaces** separate word positions, **commas** separate alternatives within a position. VASS generates all possible combinations (Cartesian product).

```ini
# Single position: alternatives for the preposition
click the,on text {text}
```
Generates 2 patterns: `click the text {text}`, `click on text {text}`.

```ini
# Two positions: each position has its own alternatives
aa,xx bb,cc {var}
```
Generates 4 patterns: `aa bb {var}`, `aa cc {var}`, `xx bb {var}`, `xx cc {var}` (2x2 = 4).

```ini
# Mixed: fixed word + alternatives
turn on,off {device}
```
Generates 2 patterns: `turn on {device}`, `turn off {device}` (no space between `on` and `off` -> same position).

The spoken phrase is compared against all generated patterns. The best fuzzy match wins.

#### Action types

| Prefix | Example | Behavior |
|--------|---------|----------|
| `script:` | `script:search` | Runs `scripts/search.vass`. Captured variables become `$param1`, `$param2`, etc. |
| `vasscript:` | `vasscript:events` | Same as `script:` (alternative prefix) |
| Command | `shutdown /s` | Executed directly as a system command |

#### Section names

Section names like `[general]` and `[system]` are just organizational categories — they don't affect matching. The **key** (the phrase to recognize) is what matters.

### Creating VASScript scripts

Open the script editor from the GUI menu or run:
```bash
python src/scripts_editor.py
```

All scripts go in the `scripts/` folder with a `.vass` extension.

**Authorization**: before executing a new or modified script, VASS shows a popup asking for permission. Scripts are verified via SHA-256 hash (stored in the system keyring): if a script file is modified after being authorized, permissions are automatically revoked and the popup will appear again on the next execution. Permission can be granted per-function or for the whole script. This ensures no script can run on your machine without your explicit consent.

See the [VASCRIPT_REFERENCE.md](../Allowed_root/VASCRIPT_REFERENCE.md) file for the complete language reference.

### Events and reminders

Events are managed via the `Allowed_root/events.json` file. A voice reminder is issued 1 hour in advance (configurable via `[events] reminder_advance`).

Schedules (automated procedures) are in `Allowed_root/schedules.json` and trigger command execution with TTS notification. Additional flags: `silent`, `run_on_startup`, `check_already_running`, `wait_for_completion`.

### Plugin system

VASS exposes a local TCP server (`localhost:8765`) that plugins use to communicate with the app: TTS, notifications, AI queries, RSS items, chat, declarative UIs, and more. **Internal plugins** (bundled with VASS) cannot be removed; **external plugins** can be enabled, disabled, and removed from the GUI (Plugins menu).

Bundled internal plugins: noise auto-pause, proactive agent, user profile, RSS reader, world events, Telegram bot. External plugins available on disk: image generator, news publisher, timeline viewer.

See the [PLUGIN_DEV_en.md](PLUGIN_DEV_en.md) guide for the full protocol and how to create your own plugins (also available in `PLUGIN_DEV_{it,de,fr,es,pt,ja,ko,zh}.md`).

### Email

Configure one or more accounts in Settings → Mail (Gmail via OAuth, or IMAP/POP3 with plain SSL/TLS). Incoming messages are detected and notified; the AI can search, read, reply, forward, and send emails — but sent emails are always placed in a **queue** that you must approve and send from the outbox. Contacts are stored encrypted.

---

## GUI Interface

- **Main button** — Click to change state (listening/paused). Mouse wheel for volume. Drag to move the window.
- **Volume bar** (green, at top) — Shows the current TTS volume
- **Multi-state bar** — Shows memory usage, volume, or script/activity progress depending on context
- **Notification center** (bell) — Per-type tabs with message actions and mark-all-read
- **Tool indicator** — Real-time icon showing the MCP tool the AI is using
- **Mic button** — Direct voice input in chat mode
- **Plugin menu** — Manage plugins, plugin settings, and plugin UIs
- **Settings dialog** — Full configuration from the GUI (Settings menu)
- **Auto-fade** — The window becomes semi-transparent when idle and in fullscreen
- **Splash screen** — Loading progress at startup
- **Theme** — Shared theme across the app and all editors

### Shortcuts

| Key | Action |
|-------|--------|
| `Ctrl+S` | Save (in editors) |
| Button click | Change state |
| Wheel on button | Adjust volume |
| Right-click | Context menu |
| Middle-click on button | Exit |

---

## Troubleshooting

> **Important:** This application depends heavily on the AI model used. Ineffective models or models not suited for MCP tool usage may compromise functionality.

### VASS won't start
- Check Python 3.13+: `python --version`
- Verify `.venv` exists and contains dependencies
- Check `log/debug.log` (enable `[debug] debug_enabled = true`) and `log/crash.log`

### Microphone not working
- Verify the microphone is connected and not in use by other apps
- Check system permissions for the microphone
- On Windows: Settings → Privacy → Microphone

### AI not responding
- Verify the AI server is running at `http://127.0.0.1:8080/v1`
- Check `[ai] url` in `config/settings.ini`
- If using llama.cpp, verify the model exists and `[llamacpp] llama_server_path` is correct
- Check `log/llamacpp.log` for llama.cpp errors

### OCR not recognizing on-screen text
- Increase font size or text contrast on screen
- EasyOCR works best with large fonts and high contrast
- OCR language automatically adapts to the configured locale

### The AI can't use a tool
- Some online tools require your consent (Security gate) — check the InfoPanel for pending requests
- Verify the MCP server is reachable at `http://localhost:9988` (see `[ai] mcp_server_url`)
- Check `log/mcp_server.log` for MCP errors

---

## Important files

| File | Description |
|------|-------------|
| `config/settings.ini` | Main configuration |
| `config/commands.ini` | Base voice commands (plus `commands_{lang}.ini`) |
| `config/notifications.ini` | Per-event-type notification routing |
| `scripts/*.vass` | Your VASScript scripts |
| `Allowed_root/events.json` | Your events and reminders |
| `Allowed_root/schedules.json` | Automated procedures |
| `Allowed_root/memory.json` | Conversation history and memory |
| `Allowed_root/private_profile.json` | User profile injected into AI context |
| `plugins/` | Internal and external plugins |
| `log/debug.log` | Verbose debug log (when enabled) |
| `log/crash.log` | Crash log |
| `log/faulthandler.log` | Fault handler output |
| `log/llamacpp.log` | llama.cpp server log |
