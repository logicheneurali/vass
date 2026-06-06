# VASS — Intelligent Voice Assistant

## What is VASS

VASS is a voice assistant for Windows, macOS, and Linux. It responds to voice commands, runs scripts, manages events and reminders, and interacts with a local or remote AI via an OpenAI-compatible API.

**Default wake word:** "Erika"

**Key features:**
- Voice recognition via Whisper (faster-whisper)
- Natural speech synthesis via Kokoro TTS
- Local or remote AI (llama.cpp, OpenAI, any compatible server)
- VASScript scripting for desktop automation
- Event and reminder management
- MCP server with 15 tools for AI orchestration
- Conversation history
- 9 language support (Italian, English, German, French, Spanish, Portuguese, Japanese, Korean, Chinese)

---

## Requirements

- **Python 3.13** or higher
- **Internet connection** (for model downloads and remote AI)
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

### Wake word

The wake word is **configurable** by the user in the `settings.ini` file and can be any word or short phrase. The default is "**Erika**".

When VASS detects the wake word, it emits a beep to signal it's ready to receive the command. Speak after the beep.

Examples:
- *"Erika"* (wait for beep), then *"what time is it?"*
- *"Erika"* (wait for beep), then *"search for the latest news"*
- *"Erika"* (wait for beep), then *"remind me about the meeting tomorrow at 2 PM"*

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

Commands are configured in `commands.ini` using standard INI format. The key is the phrase to recognize, the value is the action:

```ini
[general]
search {term} = script:search
open {program} = start {program}
top news = script:news
what time is it = script:datetime

[system]
shutdown system = shutdown /s /t 60
lock screen = rundll32.exe user32.dll,LockWorkStation
```

- `{term}`, `{program}` — variables captured from speech
- `script:scriptname` — runs `scripts/scriptname.vass`
- Alternative prefix: `vasscript:`

If the pattern has variables, their values are passed to the script as `$param1`, `$param2`, etc.

### Creating VASScript scripts

Open the script editor from the GUI menu or run:
```bash
python scripts_editor.py
```

All scripts go in the `scripts/` folder with a `.vass` extension.

See the `VASCRIPT_REFERENCE.md` file for the complete language reference.

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
