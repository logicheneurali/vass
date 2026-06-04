---
name: documentazione-vass
description: Generates VASS user and advanced documentation in all configured languages. Analyzes the codebase and creates README_{lang}.md and README_ADV_{lang}.md files.
---

# Documentazione VASS

Creates two types of documentation for each of the 9 supported languages (`it`, `en`, `de`, `fr`, `es`, `pt`, `ja`, `ko`, `zh`):

- `README_{lang}.md` — Simple user guide: installation, configuration, daily usage
- `README_ADV_{lang}.md` — Advanced: architecture, internal components, dependencies, how it works

## Rules

1. **Analyze first** — read the codebase to understand all features before writing
2. **All 9 languages** — generate both files for every language
3. **Keep existing README.md** — do NOT modify the root README.md
4. **Translate content** — not just the headings; translate the actual descriptions

## Analysis Checklist

Read these files to extract all relevant information:

### For README (user-facing):
- `install.py` — installation steps and requirements
- `settings.ini` — all configurable parameters with descriptions
- `commands.ini` — how voice commands work, examples
- `vass.py` — application features, states, modes
- `gui.py` — GUI elements and interactions
- `scripts_editor.py` — how to create scripts
- `history_viewer.py` — conversation history
- `Allowed_root/VASCRIPT_REFERENCE.md` — scripting language reference

### For README_ADV (advanced):
- All files in `README` scope plus:
- `vass.py` — full architecture: initialization, audio pipeline, AI fallback, MCP integration
- `script_engine.py` — VASScript interpreter internals
- `event_reminder.py` — event/schedule monitoring
- `tts_engine.py` — Kokoro TTS integration
- `voice_recognition.py` — Whisper STT pipeline
- `idle_tracker.py` — cross-platform idle detection
- `resource_monitor.py` — resource gating
- `mcp_server/` — MCP server architecture, all tools, ACL
- `command_executor.py` — voice command matching algorithm
- `window_manager.py` — cross-platform window control
- `log_utils.py` — log rotation
- `requirements.txt` — full dependency list with explanations
- `locales/` — i18n system

## README_{lang}.md Template

```markdown
# VASS — Assistente Vocale Intelligente

## Cos'è VASS
[Brief description of the voice assistant]

## Requisiti
- Python 3.13+
- Connessione internet
- GPU NVIDIA consigliata (per AI locale)
- Microfono

## Installazione
[Steps from install.py, simple language]

## Configurazione
[Key settings from settings.ini, only the most important ones]

## Utilizzo quotidiano
- **Wake word flow**: VASS beeps AFTER detecting the wake word to signal readiness. The user speaks the command AFTER the beep. NEVER document it as "say wakeword followed by command, then beep" — the sequence is: wakeword → beep → command.
- **commands.ini format**: Standard INI `key = value`. The KEY is the voice phrase, the VALUE is the action. Example: `cerca {termine} = script:ricerca`. NEVER document it with `pattern =` / `action =` sub-keys — that is WRONG. The section name is the category (e.g. `[general]`, `[system]`).
- **Install command**: Always include `cd vass` before `python install.py`. The user must be in the project directory first. Document as: "Download or clone the project, then enter the folder and run the script" followed by `cd vass` + `python install.py`.
- Modalità (full/limited/none memory)
- Come creare script VASScript
- Come aggiungere eventi/schedule
- Tasti e scorciatoie GUI

## Comandi vocali supportati
[Examples of commands.ini patterns]

## Risoluzione problemi
- VASS non si avvia
- Il microfono non funziona
- L'AI non risponde
```

## README_ADV_{lang}.md Template

```markdown
# VASS — Documentazione Avanzata

## Architettura generale
[Component diagram description]
- vass.py — orchestratore principale
- gui.py — interfaccia Qt
- script_engine.py — interprete VASScript
- tts_engine.py — sintesi vocale Kokoro
- voice_recognition.py — riconoscimento vocale Whisper
- event_reminder.py — eventi e schedulazioni
- mcp_server/ — server MCP con 15 tool

## Pipeline audio
[Wake word → transcription → command/ai → TTS flow]

## VASScript — linguaggio di scripting
[Full language description from VASCRIPT_REFERENCE.md, condensed]

## Server MCP e tool
[List of all 15 MCP tools with descriptions]

## Sistema di memoria
[File-based memory: memory.json, info files, summarization, archive]

## Eventi e schedulazioni
[events.json vs schedule.json, formato, reminder]

## Dipendenze
[requirements.txt with brief explanation of each]

## Internals
- Threading model
- File watching
- IPC via exec_queue.json
- Credential storage (Windows Credential Manager)
- i18n system

## Configurazione avanzata
[All settings.ini sections with detailed explanations]
```

## Output

Place files in `docs/` subdirectory:

```
docs/
  README_it.md       README_ADV_it.md
  README_en.md       README_ADV_en.md
  README_de.md       README_ADV_de.md
  README_fr.md       README_ADV_fr.md
  README_es.md       README_ADV_es.md
  README_pt.md       README_ADV_pt.md
  README_ja.md       README_ADV_ja.md
  README_ko.md       README_ADV_ko.md
  README_zh.md       README_ADV_zh.md
```

## Final step — GitHub README

After generating all files, **always** copy `docs/README_en.md` to the project root as `README.md`:

```bash
Copy-Item -Path "docs\README_en.md" -Destination "README.md" -Force   # Windows
cp docs/README_en.md README.md                                           # macOS/Linux
```

This makes it the default README displayed on GitHub.
