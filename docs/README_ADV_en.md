# VASS — Advanced Documentation

## General Architecture

VASS is a modular application composed of several independent components that communicate via file queues, Qt signals, and direct calls.

```
┌─────────────────────────────────────────────────┐
│                    vass.py                       │
│              Main Orchestrator                   │
│  - Component initialization                      │
│  - Listen/write loop                            │
│  - AI fallback management                       │
│  - Script execution                             │
│  - File queue watchdog                          │
└──────┬──────┬──────┬──────┬──────┬──────────────┘
       │      │      │      │      │
       ▼      ▼      ▼      ▼      ▼
  ┌────────┐┌─────┐┌─────┐┌────┐┌──────────┐
  │  gui.py││TTS  ││STT  ││Evt ││mcp_server│
  │  PySide││Eng. ││Whisp││Rem ││  15 tool │
  └────────┘└─────┘└─────┘└────┘└──────────┘
```

### Core Components

| Component | File | Responsibility |
|-----------|------|---------------|
| Orchestrator | `vass.py` (1313 lines) | Initialization, main loop, AI, scripts, memory |
| GUI | `gui.py` (832 lines) | PySide6 window, bars, fade, sub-windows |
| TTS | `tts_engine.py` (138 lines) | Kokoro TTS, audio playback, volume |
| STT | `voice_recognition.py` (133 lines) | faster-whisper, wake word detection |
| Interpreter | `script_engine.py` (761 lines) | VASScript parser, evaluator, 26 functions |
| Events | `event_reminder.py` (280 lines) | Event/schedule monitor, TTS alerts |
| Commands | `command_executor.py` (184 lines) | Fuzzy pattern matching, variable extraction |
| MCP Server | `mcp_server/` | FastMCP server, 15 tools, IP-based ACL |
| OCR | `script_engine.py:_preprocess_screen` | EasyOCR with preprocessing |
| Idle | `idle_tracker.py` (67 lines) | Cross-platform idle detection |
| Resources | `resource_monitor.py` (52 lines) | CPU/RAM/GPU/VRAM gate before AI requests |
| Log | `log_utils.py` (13 lines) | Log file rotation |

---

## Audio Pipeline

```
Microphone ──► sounddevice (callback) ──► audio queue ──► Whisper (transcription)
                                                             │
                    ┌────────────────────────────────────────┤
                    ▼                                        ▼
         "Erika" detection?                        Full transcription
                    │                                        │
                    ▼                                        ▼
               Beep (ready for command)                    Match commands.ini?
                    │                                  │            │
                    ▼                                  ▼            ▼
             Wait for command                       Command      No match
                    │                               found
                    ▼                                  │            │
             Transcription                              ▼            ▼
                    │                          Execute action   AI fallback
                    ▼
            Kokoro TTS ──► Speakers
```

### Audio Component Detail

- **Input**: `sounddevice.InputStream` with callback at 16000 Hz mono
- **VAD**: webrtcvad to filter silence
- **Wake word**: Whisper tiny model, searches for "erika" in transcription
- **Transcription**: Whisper medium model (configurable) after wake word confirmation
- **TTS**: Kokoro `KPipeline(lang_code='i')`, voice `if_sara`, generates WAV via UUID filename
- **Playback**: `sounddevice.play()` with `_tts_done` event for synchronization

---

## VASScript — Scripting Language

VASScript is a minimalist scripting language for desktop automation. Line-by-line execution, no arithmetic operators, everything is a string.

### Available Functions (26 total)

#### AI and TTS
- `ai(prompt)` — Queries the AI, returns text
- `say(text, speed?)` — Speech synthesis (speed: 0.5-1.5)
- `listen(prompt?)` — Records voice, returns transcription

#### System
- `run(command)` — Executes PowerShell, returns output
- `wait(seconds)` — Pauses execution
- `exit()` — Terminates the script
- `getdatetime()` — Current date/time "YYYY-MM-DD HH:MM"

#### Screen (OCR)
- `screen_search(query)` — Searches text on screen, sets `$_sx`, `$_sy`, `$_sw`, `$_sh`
- `screen_click(x?, y?)` — Click at coordinates
- `screen_highlight(x, y, w?, h?, dur?)` — Highlight area

#### Windows and Keyboard
- `setActiveWindow(name)` — Activates window by process/title
- `sendText(text)` — Types text with human-like delay

#### Events
- `addevent(date, time, duration, description, recur?)` — Adds event
- `listevents(until_date)` — Lists events (JSON)
- `removeevent(name)` — Removes event (fuzzy match)
- `prettyevents(json)` — Formats events into readable text

#### Memory and Clipboard
- `readinfo(id)` — Reads info file
- `writeinfo(text)` — Writes info file, returns ID
- `clipboardget()` — Reads clipboard
- `clipboardset(text)` — Writes clipboard

#### Conditions
- `ifcontains(var, substring, if_true, if_false?)` — Contains substring
- `ifempty(var, if_empty, if_notempty?)` — Checks if empty

#### Utility
- `trim(text)` — Removes spaces
- `len(text)` — String length
- `contains(text, substring)` — Contains? ("True"/"False")
- `equals(a, b)` — Equal? ("True"/"False")

### Variables

```vascript
$name = "Fabio"            # Assignment
$age = "54"                # Everything is a string
$result = ai("Hello")      # Function result
say("Hello {$name}!")      # Interpolation in strings
say("You are {$age} old")  # Also with variables
```

**Note:** VASScript does NOT support concatenation with `+`. Use `{$var}` in strings.

### screen_search Global Variables

`screen_search()` sets these global variables for the first match:
- `$_sx`, `$_sy` — center coordinates
- `$_sw`, `$_sh` — width and height

---

## MCP Server — 15 Tools

The MCP server exposes 15 tools accessible to the AI at `http://localhost:9988`.

### File System
- `read_file(path)` — Reads file within Allowed_root
- `write_file(path, content)` — Writes file within Allowed_root

### Web
- `browse(url)` — Downloads page (static, httpx+BeautifulSoup)
- `websearch(query)` — Searches DuckDuckGo via Playwright
- `webfetch(url)` — Loads JS-rendered page via Playwright

### Calculation and Time
- `calculate(expression)` — Evaluates mathematical expressions (AST, safe)
- `current_time()` — Current date/time
- `disk_space()` — Available disk space

### Execution
- `execute(command)` — Executes commands (whitelist)
- `script(script_name)` — Runs VASScript file
- `interact(code)` — Executes inline VASScript

### Memory and Clipboard
- `readinfo(id)` — Reads info file
- `writeinfo(text)` — Writes info file
- `clipboardget()` — Reads clipboard
- `clipboardset(text)` — Writes clipboard

### Authentication

IP-based ACL via `mcp_server/config/tools.yaml`. Each tool has whitelist/blacklist. Default deny.

### Script → VASS Communication

The `script` and `interact` tools use file-based IPC:
1. Write request to `scripts/exec_queue.json`
2. VASS reads the queue (1s polling)
3. Executes the script
4. Writes result to `scripts/exec_result.json`
5. The MCP client reads the result

---

## Memory System

### Structure

```
Allowed_root/
  memory.json          # Index: {"history": [id1, id2], "summary_id": "id3"}
  memory/
    1780394454383.json  # Single entry: {"info": "JSON string"}
    1780427888604.json
    archive/
      2026-06/          # Monthly archive
```

### Flow

1. Each AI exchange (user+assistant) is saved as a JSON file in `memory/`
2. `memory.json` tracks the last 20 IDs
3. After 5 saves, unreferenced files go to `archive/{YYYY-MM}/`
4. Archives older than 6 months are deleted
5. When memory exceeds `memory_tokens * 4` bytes, AI compression is triggered:
   - Old messages are summarized by the AI
   - The summary is saved as a `summary_id` entry
   - Original files are archived

---

## Events and Schedules

### events.json
```json
{
  "events": [{
    "date": "2026-06-15",
    "time": "14:30",
    "duration": 60,
    "description": "Team meeting",
    "recur": "7d",
    "notify": "2026-06-15 13:30:00"
  }]
}
```
- `recur`: "1d"=daily, "7d"=weekly, "1m"=monthly, "2h"=every 2 hours
- `notify`: timestamp of when the notification was sent

### schedule.json
```json
{
  "schedules": [{
    "date": "2026-06-05",
    "time": "08:00",
    "duration": 5,
    "description": "Backup",
    "recur": "1d",
    "command": "powershell",
    "arguments": "-File backup.ps1"
  }]
}
```
- Like events but trigger command execution
- TTS notification at start and end
- Command validation against safe pattern (`.exe`, `.bat`, `.ps1`, `.py`, `.cmd`, `.vbs`)

---

## Dependencies

### Core (13)
| Package | Usage |
|-----------|-----|
| `sounddevice` | Audio input/output |
| `numpy` | Arrays for audio and images |
| `faster-whisper` | STT voice recognition |
| `webrtcvad` | Voice Activity Detection |
| `kokoro` | TTS speech synthesis |
| `torch` | Deep learning (Kokoro, Whisper, EasyOCR) |
| `soundfile` | WAV file writing |
| `openai` | OpenAI-compatible API client |
| `mcp[cli]` | FastMCP MCP server |
| `pynput` | Mouse/keyboard control |
| `PySide6` | Qt6 GUI |
| `keyring` | Windows Credential Manager |
| `httpx` | HTTP client for AI and web |

### Web and OCR (6)
| Package | Usage |
|-----------|-----|
| `beautifulsoup4` | Static page HTML parsing |
| `lxml` | Fast XML/HTML engine |
| `playwright` | Headless browser for JS pages |
| `mss` | Fast screenshots |
| `easyocr` | On-screen text recognition |
| `pillow` | Image processing |

### Utility (5)
| Package | Usage |
|-----------|-----|
| `pyyaml` | MCP server configuration |
| `structlog` | MCP structured logging |
| `uvicorn` | MCP HTTP server |
| `psutil` | Resource monitoring |
| `misaki` | Kokoro tokenization |
| `dateparser` | Natural language date parsing |

---

## Internals

### Threading Model

- **Main thread**: Qt GUI (event loop)
- **Audio thread**: sounddevice callback
- **VASS thread**: listen/transcription loop
- **Watchdog threads**: `_watch_commands_file`, `_watch_settings_file`, `_watch_script_queue`
- **Ephemeral**: TTS playback, AI fallback, script execution

### Lock Mechanisms

- `_trim_lock` — Protects memory operations
- `_script_engine_lock` — Protects the active engine
- `_tts_done` (Event) — Synchronizes TTS completion
- `state_lock` — Protects application state

### File-based IPC

**exec_queue.json / exec_result.json**:
- MCP server writes script execution requests
- VASS polls (1s), executes, writes result
- Timeout: 60s for file scripts, 120s for inline

### File Watchdogs

VASS monitors changes to:
- `settings.ini` — auto-reload
- `commands.ini` — auto-reload
- `events.json` / `schedule.json` — next alert recalculation

### Credential Storage

- Windows: Windows Credential Manager via `keyring`
- macOS: Keychain
- Linux: D-Bus Secret Service or file
- Used for: AI API key, VASScript script permissions (per function)

### i18n System

- `locales/*.json`: 9 languages, 215+ keys each
- `i18n.py` file: `t(key, lang)` lookup
- Reference: `it.json`
- All files automatically aligned

### Log Rotation

- `debug.log`: max 500 KB → `.1`, `.2`
- `mcp_server/LOG/`: max 1 MB → `.1`, `.2`
- Helper: `log_utils.py`

---

## Advanced Configuration

### [ai]
| Parameter | Default | Description |
|-----------|---------|-------------|
| `url` | `http://127.0.0.1:8080/v1` | API endpoint |
| `model` | `Qwen3-8B-Q4_K_M` | Model name |
| `api_key` | (empty) | API key (empty for local) |
| `system_message` | (long text) | System prompt |
| `mcp_server_url` | `http://localhost:9988` | MCP server URL |
| `memory_tokens` | `4000` | Memory limit in tokens×4 bytes |
| `blacklist` | `Amara.org,QTTS` | Comma-separated blocked words |

### [tts]
| Parameter | Default | Description |
|-----------|---------|-------------|
| `tts_engine` | `kokoro` | TTS engine |
| `volume` | `0.50` | Volume 0-1 |

### [wakeword]
| Parameter | Default | Description |
|-----------|---------|-------------|
| `wakeword` | `erika` | Wake word |
| `sensitivity` | `0.01` | Sensitivity 0-1 |

### [resources]
| Parameter | Default | Description |
|-----------|---------|-------------|
| `cpu_max` | `75` | CPU threshold % |
| `ram_max` | `99` | RAM threshold % |
| `gpu_max` | `75` | GPU threshold % |
| `vram_max` | `99` | VRAM threshold % |
| `resource_timeout` | `30` | Wait timeout seconds |

### [llamacpp]
| Parameter | Description |
|-----------|-------------|
| `llama_server_path` | llama.cpp executable path |
| `llama_server_arguments` | Command line arguments |

### [events]
| Parameter | Default | Description |
|-----------|---------|-------------|
| `reminder_advance` | `3600` | Reminder advance in seconds (1 hour) |

### [gui]
| Parameter | Default | Description |
|-----------|---------|-------------|
| `x`, `y` | auto | Window position |
| `width`, `height` | `200`, `32` | Window dimensions |
| `font_family` | `Segoe UI` | GUI font |
| `font_size` | `10` | Font size |
