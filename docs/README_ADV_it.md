# VASS — Documentazione Avanzata

## Architettura generale

VASS è un'applicazione modulare composta da diversi componenti indipendenti che comunicano tramite code di file, segnali Qt, e chiamate dirette.

```
┌─────────────────────────────────────────────────┐
│                    vass.py                       │
│              Orchestratore principale            │
│  - Inizializzazione componenti                   │
│  - Loop ascolto/scrittura                       │
│  - Gestione AI fallback                         │
│  - Esecuzione script                            │
│  - Watchdog code di file                        │
└──────┬──────┬──────┬──────┬──────┬──────────────┘
       │      │      │      │      │
       ▼      ▼      ▼      ▼      ▼
  ┌────────┐┌─────┐┌─────┐┌────┐┌──────────┐
  │  gui.py││TTS  ││STT  ││Evt ││mcp_server│
  │  PySide││Eng. ││Whisp││Rem ││  15 tool │
  └────────┘└─────┘└─────┘└────┘└──────────┘
```

### Componenti principali

| Componente | File | Responsabilità |
|-----------|------|---------------|
| Orchestratore | `vass.py` (1313 righe) | Inizializzazione, loop principale, AI, script, memoria |
| GUI | `gui.py` (832 righe) | Finestra PySide6, barre, fade, finestre secondarie |
| TTS | `tts_engine.py` (138 righe) | Kokoro TTS, playback audio, volume |
| STT | `voice_recognition.py` (133 righe) | faster-whisper, rilevamento wake word |
| Interprete | `script_engine.py` (761 righe) | VASScript parser, evaluator, 26 funzioni |
| Eventi | `event_reminder.py` (280 righe) | Monitor eventi/schedule, TTS avvisi |
| Comandi | `command_executor.py` (184 righe) | Pattern matching fuzzy, estrazione variabili |
| MCP Server | `mcp_server/` | Server FastMCP, 15 tool, ACL IP-based |
| OCR | `script_engine.py:_preprocess_screen` | EasyOCR con preprocessing |
| Idle | `idle_tracker.py` (67 righe) | Rilevamento inattività cross-platform |
| Risorse | `resource_monitor.py` (52 righe) | Gate CPU/RAM/GPU/VRAM prima di richieste AI |
| Log | `log_utils.py` (13 righe) | Rotazione file di log |

---

## Pipeline audio

```
Microfono ──► sounddevice (callback) ──► coda audio ──► Whisper (trascrizione)
                                                            │
                    ┌───────────────────────────────────────┤
                    ▼                                       ▼
        Rilevamento "Erika"?                        Trascrizione completa
                    │                                       │
                    ▼                                       ▼
               Bip (pronto al comando)                          Match commands.ini?
                    │                                  │            │
                    ▼                                  ▼            ▼
           Attesa comando                         Comando      Nessuna
                    │                             trovato      corrisp.
                    ▼                                  │            │
           Trascrizione                                 ▼            ▼
                    │                          Esegui azione   AI fallback
                    ▼
           Kokoro TTS ──► Altoparlanti
```

### Dettaglio componente audio

- **Input**: `sounddevice.InputStream` con callback a 16000 Hz mono
- **VAD**: webrtcvad per filtrare il silenzio
- **Wake word**: Whisper tiny model, cerca "erika" nella trascrizione
- **Trascrizione**: Whisper medium model (configurabile) dopo conferma wake word
- **TTS**: Kokoro `KPipeline(lang_code='i')`, voice `if_sara`, genera WAV via UUID filename
- **Playback**: `sounddevice.play()` con evento `_tts_done` per sincronizzazione

---

## VASScript — Linguaggio di scripting

VASScript è un linguaggio di scripting minimalista per l'automazione desktop. Esecuzione linea per linea, nessun operatore aritmetico, tutto è una stringa.

### Funzioni disponibili (26 totali)

#### AI e TTS
- `ai(prompt)` — Interroga l'AI, restituisce testo
- `say(testo, velocità?)` — Sintesi vocale (velocità: 0.5-1.5)
- `listen(prompt?)` — Registra voce, restituisce trascrizione

#### Sistema
- `run(comando)` — Esegue PowerShell, restituisce output
- `wait(secondi)` — Pausa esecuzione
- `exit()` — Termina lo script
- `getdatetime()` — Data/ora corrente "YYYY-MM-DD HH:MM"

#### Schermo (OCR)
- `screen_search(query)` — Cerca testo sullo schermo, imposta `$_sx`, `$_sy`, `$_sw`, `$_sh`
- `screen_click(x?, y?)` — Clic alle coordinate
- `screen_highlight(x, y, w?, h?, dur?)` — Evidenzia area

#### Finestre e tastiera
- `setActiveWindow(nome)` — Attiva finestra per processo/titolo
- `sendText(testo)` — Digita testo con ritardo umano

#### Eventi
- `addevent(data, ora, durata, descrizione, recur?)` — Aggiunge evento
- `listevents(fino_a_data)` — Elenca eventi (JSON)
- `removeevent(nome)` — Rimuove evento (fuzzy match)
- `prettyevents(json)` — Formatta eventi in testo leggibile

#### Memoria e clipboard
- `readinfo(id)` — Legge file informativo
- `writeinfo(testo)` — Scrive file informativo, restituisce ID
- `clipboardget()` — Legge clipboard
- `clipboardset(testo)` — Scrive clipboard

#### Condizioni
- `ifcontains(var, substring, se_vero, se_falso?)` — Contiene sottostringa
- `ifempty(var, se_vuoto, se_pieno?)` — Controlla se vuoto

#### Utility
- `trim(testo)` — Rimuove spazi
- `len(testo)` — Lunghezza stringa
- `contains(testo, substring)` — Contiene? ("True"/"False")
- `equals(a, b)` — Uguali? ("True"/"False")

### Variabili

```vascript
$nome = "Fabio"           # Assegnazione
$eta = "54"               # Tutto è stringa
$risultato = ai("Ciao")   # Risultato funzione
say("Ciao {$nome}!")      # Interpolazione in stringhe
say("Hai {$eta} anni")    # Anche con variabili
```

**Nota:** VASScript NON supporta concatenazione con `+`. Usa `{$var}` nelle stringhe.

### Variabili globali di screen_search

`screen_search()` imposta queste variabili globali per il primo match:
- `$_sx`, `$_sy` — coordinate centro
- `$_sw`, `$_sh` — larghezza e altezza

---

## Server MCP — 15 tool

Il server MCP espone 15 tool accessibili all'AI su `http://localhost:9988`.

### File system
- `read_file(path)` — Legge file in Allowed_root
- `write_file(path, content)` — Scrive file in Allowed_root

### Web
- `browse(url)` — Scarica pagina (statica, httpx+BeautifulSoup)
- `websearch(query)` — Cerca su DuckDuckGo via Playwright
- `webfetch(url)` — Carica pagina JS-rendered via Playwright

### Calcolo e tempo
- `calculate(expression)` — Valuta espressioni matematiche (AST, sicuro)
- `current_time()` — Data/ora corrente
- `disk_space()` — Spazio disco disponibile

### Esecuzione
- `execute(command)` — Esegue comandi (whitelist)
- `script(script_name)` — Esegue file VASScript
- `interact(code)` — Esegue VASScript inline

### Memoria e clipboard
- `readinfo(id)` — Legge info file
- `writeinfo(text)` — Scrive info file
- `clipboardget()` — Legge clipboard
- `clipboardset(text)` — Scrive clipboard

### Autenticazione

IP-based ACL via `mcp_server/config/tools.yaml`. Ogni tool ha whitelist/blacklist. Default deny.

### Comunicazione script → VASS

I tool `script` e `interact` usano IPC basata su file:
1. Scrivono richiesta in `scripts/exec_queue.json`
2. VASS legge la coda (polling 1s)
3. Esegue lo script
4. Scrive risultato in `scripts/exec_result.json`
5. Il client MCP legge il risultato

---

## Sistema di memoria

### Struttura

```
Allowed_root/
  memory.json          # Indice: {"history": [id1, id2], "summary_id": "id3"}
  memory/
    1780394454383.json  # Singola entry: {"info": "JSON string"}
    1780427888604.json
    archive/
      2026-06/          # Archivio mensile
```

### Flusso

1. Ogni scambio AI (user+assistant) viene salvato come file JSON in `memory/`
2. `memory.json` tiene traccia degli ultimi 20 ID
3. Dopo 5 salvataggi, i file non referenziati vanno in `archive/{YYYY-MM}/`
4. Gli archivi più vecchi di 6 mesi vengono cancellati
5. Quando la memoria supera `memory_tokens * 4` byte, viene attivata la compressione AI:
   - I vecchi messaggi vengono riassunti dall'AI
   - Il riassunto viene salvato come entry `summary_id`
   - I file originali vengono archiviati

---

## Eventi e schedulazioni

### events.json
```json
{
  "events": [{
    "date": "2026-06-15",
    "time": "14:30",
    "duration": 60,
    "description": "Riunione team",
    "recur": "7d",
    "notify": "2026-06-15 13:30:00"
  }]
}
```
- `recur`: "1d"=giornaliero, "7d"=settimanale, "1m"=mensile, "2h"=ogni 2 ore
- `notify`: timestamp di quando è stato inviato l'avviso

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
- Come gli eventi ma attivano l'esecuzione di comandi
- Comunicazione TTS all'inizio e alla fine
- Validazione comandi contro pattern sicuro (`.exe`, `.bat`, `.ps1`, `.py`, `.cmd`, `.vbs`)

---

## Dipendenze

### Core (13)
| Pacchetto | Uso |
|-----------|-----|
| `sounddevice` | Input/output audio |
| `numpy` | Array per audio e immagini |
| `faster-whisper` | Riconoscimento vocale STT |
| `webrtcvad` | Voice Activity Detection |
| `kokoro` | Sintesi vocale TTS |
| `torch` | Deep learning (Kokoro, Whisper, EasyOCR) |
| `soundfile` | Scrittura file WAV |
| `openai` | Client API OpenAI-compatibile |
| `mcp[cli]` | Server MCP FastMCP |
| `pynput` | Controllo mouse/tastiera |
| `PySide6` | GUI Qt6 |
| `keyring` | Windows Credential Manager |
| `httpx` | HTTP client per AI e web |

### Web e OCR (6)
| Pacchetto | Uso |
|-----------|-----|
| `beautifulsoup4` | Parsing HTML pagine statiche |
| `lxml` | Motore XML/HTML veloce |
| `playwright` | Browser headless per pagine JS |
| `mss` | Screenshot veloci |
| `easyocr` | Riconoscimento testo su schermo |
| `pillow` | Elaborazione immagini |

### Utility (5)
| Pacchetto | Uso |
|-----------|-----|
| `pyyaml` | Configurazione MCP server |
| `structlog` | Logging strutturato MCP |
| `uvicorn` | Server HTTP MCP |
| `psutil` | Monitoraggio risorse |
| `misaki` | Tokenizzazione Kokoro |
| `dateparser` | Parsing date in linguaggio naturale |

---

## Internals

### Modello di threading

- **Main thread**: GUI Qt (event loop)
- **Audio thread**: sounddevice callback
- **VASS thread**: loop di ascolto/trascrizione
- **Watchdog threads**: `_watch_commands_file`, `_watch_settings_file`, `_watch_script_queue`
- **Effimeri**: TTS playback, AI fallback, esecuzione script

### Meccanismi di lock

- `_trim_lock` — Protegge operazioni di memoria
- `_script_engine_lock` — Protegge l'engine attivo
- `_tts_done` (Event) — Sincronizza fine TTS
- `state_lock` — Protegge stato applicazione

### IPC via file

**exec_queue.json / exec_result.json**:
- MCP server scrive richieste di esecuzione script
- VASS polla (1s), esegue, scrive risultato
- Timeout: 60s per script da file, 120s per inline

### Watchdog file

VASS monitora modifiche a:
- `settings.ini` — ricarica automatica
- `commands.ini` — ricarica automatica
- `events.json` / `schedule.json` — ricalcolo prossimo alert

### Credential storage

- Windows: Windows Credential Manager via `keyring`
- macOS: Keychain
- Linux: D-Bus Secret Service o file
- Usato per: API key AI, permessi script VASScript (per funzione)

### Sistema i18n

- `locales/*.json`: 9 lingue, 215+ chiavi ciascuna
- File `i18n.py`: lookup `t(key, lang)`
- Riferimento: `it.json`
- Tutti i file allineati automaticamente

### Log rotation

- `debug.log`: max 500 KB → `.1`, `.2`
- `mcp_server/LOG/`: max 1 MB → `.1`, `.2`
- Helper: `log_utils.py`

---

## Configurazione avanzata

### [ai]
| Parametro | Default | Descrizione |
|-----------|---------|-------------|
| `url` | `http://127.0.0.1:8080/v1` | Endpoint API |
| `model` | `Qwen3-8B-Q4_K_M` | Nome modello |
| `api_key` | (vuoto) | Chiave API (vuoto per locale) |
| `system_message` | (testo lungo) | Prompt di sistema |
| `mcp_server_url` | `http://localhost:9988` | URL server MCP |
| `memory_tokens` | `4000` | Limite memoria in token×4 byte |
| `blacklist` | `Amara.org,QTTS` | Parole bloccate separata da virgola |

### [tts]
| Parametro | Default | Descrizione |
|-----------|---------|-------------|
| `tts_engine` | `kokoro` | Motore TTS |
| `volume` | `0.50` | Volume 0-1 |

### [wakeword]
| Parametro | Default | Descrizione |
|-----------|---------|-------------|
| `wakeword` | `erika` | Parola attivazione |
| `sensitivity` | `0.01` | Sensibilità 0-1 |

### [resources]
| Parametro | Default | Descrizione |
|-----------|---------|-------------|
| `cpu_max` | `75` | Soglia CPU % |
| `ram_max` | `99` | Soglia RAM % |
| `gpu_max` | `75` | Soglia GPU % |
| `vram_max` | `99` | Soglia VRAM % |
| `resource_timeout` | `30` | Timeout attesa secondi |

### [llamacpp]
| Parametro | Descrizione |
|-----------|-------------|
| `llama_server_path` | Percorso eseguibile llama.cpp |
| `llama_server_arguments` | Argomenti linea di comando |

### [events]
| Parametro | Default | Descrizione |
|-----------|---------|-------------|
| `reminder_advance` | `3600` | Anticipo reminder in secondi (1 ora) |

### [gui]
| Parametro | Default | Descrizione |
|-----------|---------|-------------|
| `x`, `y` | auto | Posizione finestra |
| `width`, `height` | `200`, `32` | Dimensioni finestra |
| `font_family` | `Segoe UI` | Font GUI |
| `font_size` | `10` | Dimensione font |
