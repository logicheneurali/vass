# VASS — Voice assistant software

## What is VASS

VASS is a voice assistant for Windows, macOS, and Linux. It responds to voice commands, runs scripts, manages events and reminders, and interacts with a local or remote AI via an OpenAI-compatible API.

**Default wake word:** "Erika"

**Key features:**
- Voice recognition via Whisper (faster-whisper) with adaptive noise floor
- Natural speech synthesis via Kokoro TTS with 4-step fallback chain
- Local or remote AI (llama.cpp, OpenAI, any compatible server)
- VASScript scripting for desktop automation with 30+ built-in functions
- Event and schedule management with editor GUI
- Multilingual countdown timer (voice-activated, 5 simultaneous)
- MCP server with 23 tools for AI orchestration
- Permanent memory with automatic classification and summarization
- Conversation history viewer with per-message actions
- 9 language support
- Context overflow protection (truncate or AI summarization)
- Audio device selection (input/output)
- Multi-turn tool calling for complex AI tasks
- 3-source weather system with 200K city geolocation database
- Time-shifted voice commands ("shutdown in 5 minutes")
- Real-time MCP tool activity indicator in GUI
- Heuristic context compression with multilingual stopword support
- Token-accurate context counting
- Script execution sandbox with deny-list and audit logging


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

# Create settings.ini (copy from example settings.ini)
```

---

## Configuration

The `settings.ini` file contains all settings. Here are the most important ones:

| Section | Parameter | Description |
|---------|-----------|-------------|
| `[locale]` | `language` | Language (it/en/de/fr/es/pt/ja/ko/zh) |
| `[ai]` | `url` | OpenAI-compatible AI server URL |
| `[ai]` | `model` | AI model name |
| `[ai]` | `system_message` | Assistant personality |
| `[ai]` | `memory_tokens` | Maximum memory size |
| `[wakeword]` | `wakeword` | Wake word (default: erika) |
| `[wakeword]` | `sensitivity` | Detection sensitivity (0-1) |
| `[tts]` | `volume` | TTS volume (0-1) |

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

The wake word is **configurable** by the user in the `settings.ini` file and can be any word or short phrase. The default is "**Erika**".

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
- **Full** — The AI receives the memory summary
- **Limited** — The AI receives only recent history
- **None** — No historical context

### Voice commands

Commands are configured in `commands.ini` (standard INI format), also editable via the GUI editor (`python commands_editor.py`). Each line is a **phrase = action** pair: the phrase is the pattern to recognize (can include `{variables}`), the action is what to execute.

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

1. **Fuzzy recognition**: exact match is not required. VASS compares the spoken phrase against all patterns using a similarity algorithm (`difflib`). The pattern with the highest score above the threshold (default `0.75`, configurable in `settings.ini`) is activated.

2. **Variables `{name}`**: capture the spoken words at that position. Example: saying *"search cats on the internet"* captures `term = "cats on the internet"`.

3. **Escaped variables `{escaped_name}`**: same as regular variables, but the captured text is URL-encoded (spaces become `%20`). Useful for web searches.

4. **AI fallback**: if no command exceeds the similarity threshold, the phrase is sent to the AI for a natural language response.

#### Comma alternatives (Cartesian product)

You can specify multiple alternatives for each word position using commas. **Spaces** separate word positions, **commas** separate alternatives within a position. VASS generates all possible combinations (Cartesian product).

```ini
# Single position: alternatives for the preposition
click the,on text {text}
```
Generates 3 patterns: `click the text {text}`, `click on text {text}`, `click text {text}`.

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
| URL | `https://...` | Opened in the default browser |
| Command | `shutdown /s` | Executed directly as a system command |

#### Section names

Section names like `[general]` and `[system]` are just organizational categories — they don't affect matching. The **key** (the phrase to recognize) is what matters.

### Creating VASScript scripts

Open the script editor from the GUI menu or run:
```bash
python scripts_editor.py
```

All scripts go in the `scripts/` folder with a `.vass` extension.

**Authorization**: before executing a new or modified script, VASS shows a popup asking for permission. Scripts are verified via SHA-256 hash: if a script file is modified after being authorized, permissions are automatically revoked and the popup will appear again on the next execution. This ensures no script can run on your machine without your explicit consent.

See the [VASCRIPT_REFERENCE.md](../Allowed_root/VASCRIPT_REFERENCE.md) file for the complete language reference.

### Events and reminders

Events are managed via the `events.json` file. A voice reminder is issued 1 hour in advance (configurable).

Schedules (automated procedures) are in `schedule.json` and trigger command execution with TTS notification.

---

## GUI Interface

- **Main button** — Click to change state (listening/paused). Mouse wheel for volume. Drag to move the window.
- **Volume bar** (green, at top) — Shows the current TTS volume
- **Multi-state bar** — Shows memory usage, volume, or script progress depending on context
- **Auto-fade** — The window becomes semi-transparent when idle and in fullscreen

### Shortcuts

| Key | Action |
|-------|--------|
| `Ctrl+S` | Save (in editors) |
| Button click | Change state |
| Wheel on button | Adjust volume |
| Right-click | Context menu |
| "Read" button in scripts | Reads the script with TTS |

---

## Troubleshooting

> **Important:** This application depends heavily on the AI model used. Ineffective models or models not suited for MCP tool usage may compromise functionality.

### VASS won't start
- Check Python 3.13+: `python --version`
- Verify `.venv` exists and contains dependencies
- Check `debug.log` for errors

### Microphone not working
- Verify the microphone is connected and not in use by other apps
- Check system permissions for the microphone
- On Windows: Settings → Privacy → Microphone

### AI not responding
- Verify the AI server is running at `http://127.0.0.1:8080/v1`
- Check `[ai] url` in `settings.ini`
- If using llama.cpp, verify the model exists in the `models/` folder

### OCR not recognizing on-screen text
- Increase font size or text contrast on screen
- EasyOCR works best with large fonts and high contrast
- OCR language automatically adapts to the configured locale

---

## Important files

| File | Description |
|------|-------------|
| `settings.ini` | Main configuration |
| `commands.ini` | Custom voice commands |
| `scripts/*.vass` | Your VASScript scripts |
| `events.json` | Your events and reminders |
| `schedule.json` | Automated procedures |
| `memory.json` | Conversation history |
| `debug.log` | Debug log |
| `vass.log` | Application log |
