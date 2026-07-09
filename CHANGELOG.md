# VASS — Registro Modifiche (Compattazione)

Ultima compattazione: 2026-07-09, v0.6.3

---

## v0.6.3 (2026-07-09)

### Fonte Files nella memoria permanente
- **`FileScanner`** (`src/memory_files_scanner.py`): scansione periodica cartelle configurabili, estrazione testo (percorso + prime 2KB), dedup via mtime, classificazione AI tramite coda differita.
- **Dialog "Configura cartelle"** (`FilesFoldersDialog`): aggiungi/rimuovi cartelle, intervallo scansione, dimensione max file, max file per ciclo.
- **Toggle "Files"** nel Fonti dialog con pulsante configurazione.
- **Limite `max_files_per_cycle`** (default 20) e queue guard (≥80 elementi in coda → skip ciclo).
- **Idle automatico**: scanner in pausa quando fonte disattivata, hot-reload config a ogni ciclo.

### Fonti esterne e contesto AI
- **Bottone rinominato**: "Fonti" → "Fonti esterne" (9 lingue).
- **`max_external_entries` configurabile** (QSpinBox 1-20, default 3): quante entry iniettare nel contesto AI per richiesta. Salvato in `memory_sources.json`.

### Fix
- **Eventi disabilitati**: `_calculate_next_alert` ora salta correttamente anche gli "start alerts". `run_startup_schedules` salta schedule con `enabled: false`.
- **`disable_thinking: False`** per chiamate tool MCP multi-turn.
- **Weekday** nel system prompt e tool `current_time`.
- **InfoPanel**: chiusura dopo "Segna tutto come letto", `raise_()` dopo show.
- **URL cleaning**: preserva parentesi legittime, rimuove solo markdown.
- **`get_project_root()`/`get_path()`** in `utils.py`: 39 ripetizioni path sostituite.
- **`log_exc()`**: 32 `except Exception: pass` sostituiti.

### File Chiave
| File | Linee | Contenuto |
|------|-------|-----------|
| `src/memory_files_scanner.py` | 145 | FileScanner: scansione cartelle, estrazione testo, dedup mtime |
| `src/memory_editor.py` | 1075 | Fonti esterne, FilesFoldersDialog, max_external_entries |
| `src/memory_manager.py` | 645 | `_load_files_config()`, `max_external_entries` configurable |
| `src/event_reminder.py` | 628 | Fix enabled check, disable_thinking |
| `VERSION` | 1 | Bump a 0.6.3 |

---

## v0.6.2 (2026-07-08)

### Fix
- **InfoPanel**: chiusura automatica dopo "Segna tutto come letto".
- **Trim memoria**: diagnostica lock skip con retry automatico dopo 30s; log empty content con conteggio entry.
- **Path refactoring**: `get_project_root()` e `get_path()` in `utils.py`; 39 ripetizioni `os.path.dirname(...)` sostituite.
- **`log_exc()`**: 32 `except Exception: pass` sostituiti con `log_exc()` in `main.py`, `memory_manager.py`, `script_engine.py`, `event_reminder.py` — errori ora scritti in `log/crash.log`.
- **Import mancanti**: `get_project_root` aggiunto a `settings_editor.py` e `scripts_editor.py`.
- **`disable_thinking: False`** per chiamate tool MCP multi-turn.
- **Weekday** in system prompt (`%A`) e tool `current_time`.
- **Validazione giorno/data** in `addevent`.
- **`QMenu` import** mancante in settings_editor.
- **URL cleaning** InfoPanel: preserva parentesi legittime, rimuove solo markdown.

### File Chiave
| File | Linee | Contenuto |
|------|-------|-----------|
| `src/utils.py` | 455 | `get_project_root()`, `get_path()`, `log_exc()` |
| `src/gui.py` | 2310 | InfoPanel mark-all-read auto-close |
| `src/memory_manager.py` | 634 | Trim diagnostics: retry, log empty content |
| `VERSION` | 1 | Bump a 0.6.2 |

---

## v0.6.1 (2026-07-05)

### Schedule flags
- **3 nuovi flag per operazioni pianificate**: `wait_for_completion` (subprocess.run bloccante), `run_on_startup` (esecuzione all'avvio), `check_already_running` (salta se già in esecuzione). Visibili e cliccabili solo per file .exe validi.
- **`run_startup_schedules()`**: esegue le schedule marcate all'avvio di VASS.

### Settings editor
- **Hamburger menu selezione modello AI**: bottone ☰ accanto al campo model nell'AI Agent. Fetch da llama.cpp `/v1/models`, popola dropdown.

### Localizzazione
- **Bubble map**: titolo, sottotitolo, tooltip, sidebar e meta testo localizzati in 9 lingue.
- **Schedule descriptions**: tooltip descrittivi per ogni checkbox in 9 lingue.

### Fix
- `QMenu` import mancante in settings_editor.
- `DESCRIPTION_FG` import mancante in events_editor.
- Eventi UI ora accodati per classificazione memoria (`_classify_new_events` in event_reminder).
- Date weekday nel system prompt e tool `current_time` per prevenire allucinazioni AI.
- `QMenu` import mancante in settings_editor.
- InfoPanel `raise_()` dopo show per stare sopra altre finestre.
- MemoryEditor: entry ID invece di indice per delete/rmtag (fix lista filtrata).
- URL cleaning: preserva parentesi legittime, rimuove solo formattazione markdown.
- Orchestratore: `disable_thinking: False` per chiamate tool multi-turn.

### File Chiave
| File | Linee | Contenuto |
|------|-------|-----------|
| `src/memory_editor.py` | 942 | Bubble map localizzata, fix ID delete |
| `src/events_editor.py` | 621 | 3 nuovi flag schedule, layout riorganizzato |
| `src/event_reminder.py` | 596 | `_is_already_running`, `run_startup_schedules` |
| `src/settings_editor.py` | 782 | Hamburger menu selezione modello AI |
| `VERSION` | 1 | Bump a 0.6.1 |

---

## Patch post-v0.6.0 (2026-07-05)

### Cancellazione rumore DSP
- **`NoiseFilter`** (`src/audio_filter.py`): modulo DSP real-time con high-pass 80Hz + spectral subtraction + soft clip. Calibrazione automatica (2s silenzio), aggiornamento continuo (EMA ogni 30s). <0.01% CPU.
- **VAD su raw frame**: rilevazione silenzio su audio non filtrato — evita artefatti IFFT che confondevano `webrtcvad`.
- **Noise floor su raw frame**: calcolato prima del filtro per soglie adattive realistiche.
- **Reset noise tracking**: quando esce da `playing` → pulisce variabili per evitare auto-pausa su eco TTS.

### Mappa memoria
- **Sidebar tag scrollabile** a sinistra: lista ordinata per conteggio decrescente, cliccabile.
- **Fix coordinate canvas**: `getBoundingClientRect()` per hover/click dopo aggiunta sidebar.
- **Fix eliminazione entry**: usa ID invece di indice (bug con lista filtrata per `min_relevance`).
- **InfoPanel**: tab label localizzati anche in `set_links` (auto-open).

### File Chiave
| File | Linee | Contenuto |
|------|-------|-----------|
| `src/audio_filter.py` | 130 | NoiseFilter DSP: high-pass, spectral subtraction, auto-calibration |
| `src/memory_editor.py` | 920 | Sidebar tag list, fix coordinate/delete, InfoPanel fix |
| `src/main.py` | 1993 | Integrazione NoiseFilter, raw frame per VAD/noise floor |

---

## v0.6.0 (2026-07-05)

### Sistema memoria permanente — refactoring e tagging fonti esterne

- **`MemoryManager`** (`src/memory_manager.py`, 634 linee): classe delegata che estrae 11 metodi di gestione memoria da `main.py` (~550 righe). Interfaccia pubblica: `build_content()`, `classify_message()`, `enqueue_external()`, `trim_if_needed()`. Coda differita per classificazione (ogni 60s, solo a AI libera). Supporto `source` field su `memory_tags.json` per tracciare origine dati.
- **Tagging automatico fonti esterne**: email Gmail, Google Calendar, eventi manuali, timer expiry vengono accodati per classificazione AI. Sistema attivabile per fonte dal MemoryEditor (bottone "Fonti", `memory_sources.json`).
- **Auto-iniezione contesto AI** (`_build_external_memory_content`): entry taggate da fonti attive vengono automaticamente incluse nel contesto AI quando pertinenti alla richiesta (max 3 entry, 200 char ciascuna).
- **`search_tags`** (nuovo tool MCP): l'AI può cercare entry taggate per tag, con filtro per fonte attiva. Restituisce top 10 per relevance.
- **Mappa bubble chart** (`src/memory_editor.py`, 858 linee): vista interattiva della memoria permanente con force-directed layout su canvas HTML5. Bolle dimensionate per conteggio, colorate per rilevanza. Click su bolla → pannello laterale con elenco entry (dalla più nuova). Layout deterministico (ordinamento alfabetico).
- **Editor eventi**: conferma eliminazione con dialog. Eventi creati da UI vengono rilevati dal `event_reminder` e accodati per classificazione.

### Compressione memoria

- **Rilevanza minima da `tags_config.json`**: la trim rispetta `min_relevance` configurato dall'utente, non più hardcoded 10.
- **Soglia compressione 500→1000 token**: meno troncamenti nei riassunti.
- **Entry ordinate per relevance decrescente**: informazioni più importanti elaborate per prime.
- **`memory_tags.json` incluso nel calcolo soglia**: tag esterni contano per attivare compressione.
- **Contenuti esterni nel riassunto**: email/eventi/timer entrano nel prompt di summarization.
- **Pulizia entry orfane**: dopo archiviazione, entry in `memory_tags.json` senza file corrispondenti vengono rimosse.
- **Summary rigenerato da zero**: niente più trascinamento di informazioni cancellate dal vecchio summary.

### Date e orari

- **Weekday nel system prompt** (`%A` in `strftime`): l'AI riceve "2026-07-05 (Sunday)" invece di dover calcolare il giorno.
- **`current_time` MCP tool**: restituisce weekday in inglese. Tool sempre disponibile.
- **Validazione giorno/data in `addevent`**: se la descrizione menziona un giorno ma la data non corrisponde, errore esplicito.

### Memory bar e UI

- **Memory bar**: include `memory_tags.json` nel calcolo dimensione.
- **InfoPanel tab**: link e notifiche tradotti correttamente (non più chiavi grezze `gui.links`).
- **Stato AI durante script**: gli script silenziosi non alterano lo stato GUI.
- **`--compress-memory`**: fix per usare `MemoryManager` invece del metodo rimosso.
- **Wizard Google**: sfondo bottoni scuro (ModernStyle), fix link duplicati, `sys.executable` per avvio senza terminale.

### Refactoring `install.py`

- **Allineamento installer grafico**: aggiunte sezioni `google`, `debug`, `compact_mode`, `paused_opacity`, `auto_context_selection`, `compress_context` in `settings.ini`. `loguru` e `transformers` nei verify e pre-install. Launcher `start ""`.

### File Chiave

| File | Linee | Contenuto |
|------|-------|-----------|
| `src/memory_manager.py` | 634 | MemoryManager: coda differita, tagging, build_content, trim, search |
| `src/memory_editor.py` | 858 | Mappa bubble chart, filtro min_relevance, Fonti dialog, icone fonte |
| `src/main.py` | 1979 | -550 righe (delegate a MemoryManager), weekday system prompt, `current_time` tool |
| `src/event_reminder.py` | 577 | `_classify_new_events`: watcher eventi per tagging automatico |
| `mcp_server/src/mcpgoal/tools/memory_tags.py` | 123 | `save_tags` con `source` e `content`, `search_tags` con source filter |
| `mcp_server/src/mcpgoal/tools/datetime_.py` | 14 | `current_time` con weekday `%A` |
| `locales/*.json` (x9) | — | `memory_editor.sources*`, `memory_editor.map`, `events_editor.delete_confirm*` |
| `VERSION` | 1 | Bump a 0.6.0 |

---

## v0.5.25 (2026-07-02)

### Barre trapezoidali con sfondo trasparente

- **`VolumeTopBar`** (`src/gui.py`): barra del volume ridisegnata come trapezio con bordi a 45° (largo sopra, stretto sotto). Sfondo rimosso — trasparente, eredita il colore della finestra.
- **`MemoryBar`** (`src/gui.py`): barra della memoria con la stessa forma ma capovolta (stretto sopra, largo sotto). Sfondo rimosso.
- **Anti-aliasing** attivato su entrambe le barre per bordi lisci.

### Sfondo dinamico per stato applicazione

- **Sfondo colorato** (`src/gui.py`): `_on_set_state` ora imposta il background della finestra principale al colore dello stato corrente con luminosità al 25%. Es. `listening` → verde scuro, `recording` → arancione scuro, etc.
- **Widget trasparenti**: tutti i pulsanti e label ereditano lo sfondo della finestra (`background-color: transparent`).
- **`_refresh_debug_border`** usa il colore corrente invece di `#101010` hardcoded.
- **Compact mode**: sfondo invariato (trasparente).

### Indicatore modalità trascrizione

- **Quadrato grigio** (`#95a5a6`) sul tool indicator quando l'app è in modalità trascrizione. Tooltip: "Modalità trascrizione — tool non disponibili". Quando si torna in chat, l'indicatore scompare.

### Verifica modello AI all'avvio del server

- **`_verify_model_and_autoselect`** (`src/main.py`): dopo che llama-server diventa pronto (autostart), verifica che il modello configurato in `settings.ini` esista tra quelli disponibili. Se non esiste, pulisce `ai_model`, chiama `_auto_select_model()` e notifica l'utente con nome vecchio/nuovo modello.
- Stessa verifica quando il settings.ini viene modificato (watcher).

### Internazionalizzazione e pulizia

- **Installer** (`installer/i18n.py`): 7 chiavi del dialog "Fresh/Update" completate per tutte le 9 lingue (mancavano de/fr/es/pt/ja/ko/zh).
- **`gui.memory_mode.{full,limited,none}`** (`locales/*.json`): aggiunte traduzioni mancanti in 7 lingue.
- **Modalità**: `"trascrizione"` → `"transcription"` in `main.py` e `gui.py` (valore interno, non localizzazione).

### File Chiave

| File | Linee | Contenuto |
|------|-------|-----------|
| `src/gui.py` | 2056 | Barre trapezoidali, sfondo dinamico, widget trasparenti, indicatore trascrizione |
| `src/main.py` | 2122 | `_verify_model_and_autoselect`, fix model auto-select, refactor nomi |
| `installer/i18n.py` | 618 | Traduzioni complete Fresh/Update dialog (9 lingue) |
| `locales/*.json` (x9) | — | `memory_mode`, `transcription_mode` |
| `VERSION` | 1 | Bump a 0.5.25 |

---

## v0.5.24 (2026-07-02)

### InfoPanel: link AI + notifiche in un'unica interfaccia

- **InfoPanel** (`src/gui.py`): `LinkPanel` rinominato ed esteso con due tab — **Links** (URL risposta AI) e **Notifications** (sostituisce `NotificationDialog`).
- **Tab Links**: dominio + URL troncato, cliccabile, tooltip con URL completo. Pulizia URL da punteggiatura markdown (`[text](url)`).
- **Tab Notifications**: pallino letto/non-letto, icona tipo, timestamp, testo a larghezza piena (layout verticale). Clic marca letto, "Mark All Read" azzera tutto.
- **`src/notification_dialog.py`**: rimosso (253 righe) — tutto integrato nell'InfoPanel.
- **Riapertura**: campanella 🔔 apre tab Notifiche (anche con 0 notifiche). Nessun pulsante aggiuntivo.
- **Localizzazione**: `gui.links`, `gui.notifications`, `gui.mark_all_read`, `gui.no_notifications` in 9 lingue.
- **Tooltip**: tooltip su notifiche e link non mostrati su finestre Tool — risolto rimuovendo `Qt.Tool` flag.

### Logging semplificato e MCP dedicato

- **`_ts_print`** in `src/main.py`: scrive direttamente su `_debug_log_file` (file), nessuna redirezione `sys.stdout`. Classe `_TeeOutput` rimossa. Debug funziona identico con/senza console.
- **`src/mcp_server.py`**: log MCP dedicato (`log/mcp.log`, troncato all'avvio). `uvicorn.run(log_config=None)` — non tenta più `dictConfig` che crashava sotto `pythonw.exe`.
- **`src/vass.py`**: guard `sys.stderr`/`sys.stdout` a `os.devnull` se `None` + `logging.basicConfig(force=True)` per prevenire crash `uvicorn`/`loguru` sotto `pythonw`.

### Auto-selezione modello AI

- **`src/main.py`**: se llama-server risponde `"model not found"`, `_handle_ai_fallback` chiama `_auto_select_model()` per selezionare automaticamente un modello valido tra quelli disponibili. Notifica l'utente con nome vecchio/nuovo modello.
- **Unsloth come repo primario** (`installer/gpu_detect.py`): modelli Qwen3 scaricati da `unsloth` (no auth richiesta), fallback `bartowski`.
- **`requirements.txt`**: aggiunte `loguru>=0.7.0` e `transformers>=4.40.0`.

### Bug fix

- **`src/script_engine.py:605`**: rimosso `import sys` locale dentro `_execute_line` che ombreggiava l'import di modulo e causava `UnboundLocalError` su `run()`.
- **`src/main.py`**: rimosso `from i18n import t` locale nell'handler eccezione — stesso bug.
- **`config/commands_*.ini` (de/ko/zh)**: corretti riferimenti script non standard → standard inglese.
- **`.gitignore`**: `scripts/*` + eccezioni per 15 script `.vass` distribuiti.

### Installer improvements

- **Download CUDA completo**: `llama-b` (binari) + `cudart` (CUDA runtime DLL) scaricati entrambi.
- **Progress model**: durante download modello la barra scala nell'intervallo dello step corrente.

### File Chiave

| File | Linee | Contenuto |
|------|-------|-----------|
| `src/gui.py` | 2234 | InfoPanel 2-tab (Links + Notifications), rimozione NotificationDialog |
| `src/main.py` | 2247 | Logging semplificato, model auto-select, fix UnboundLocalError |
| `src/mcp_server.py` | 68 | Log MCP dedicato, `log_config=None` per uvicorn |
| `src/vass.py` | 67 | Guard stderr/stdout + `logging.basicConfig` |
| `src/script_engine.py` | 1843 | Fix `import sys` locale |
| `locales/*.json` (x9) | — | InfoPanel + model_not_found + no_valid_model |
| `VERSION` | 1 | Bump a 0.5.24 |

---

## v0.5.22 (2026-07-01)

### Installer grafico cross-platform

- **`installer/`**: wizard PySide6 7-step auto-contenuto (PyInstaller) con GPU detection, download automatico di llama.cpp + CUDA runtime, download modello AI da unsloth (fallback bartowski), Python embeddable, venv, pip.
- **GPU detection** (`installer/gpu_detect.py`): NVIDIA/AMD/Intel/Apple Silicon via comandi di sistema (nvidia-smi, rocm-smi, wmic, sysctl). Suggerisce automaticamente backend e modello calibrato sulla VRAM.
- **Downloader** (`installer/downloader.py`): llama.cpp da GitHub Releases con selezione asset per piattaforma/backend, HuggingFace via `huggingface-cli`, Python embeddable da python.org.
- **Installazione riprendibile**: ogni step verifica se il lavoro è già stato fatto (file esistente, dipendenze installate, modello scaricato) e skippa.
- **Dialog fresh/update**: se la cartella esiste già, chiede se cancellare tutto (doppia conferma) o aggiornare. Tradotto in 9 lingue.
- **Checklist gitignore**: alla fine del build, stampa tutti i file embedded con verifica contro `.gitignore`.

### Fix pythonw.exe (avvio senza console)

- **`vass.py`**: redirect `sys.stderr`/`sys.stdout` a `os.devnull` se `None` + `logging.basicConfig(force=True)` prima di importare main. Risolve crash di `uvicorn` (usato dal server MCP), `loguru` (usato da Kokoro TTS), e qualsiasi libreria che scrive su stderr sotto `pythonw.exe`.

### Dipendenze mancanti

- **`requirements.txt`**: aggiunte `loguru>=0.7.0` e `transformers>=4.40.0` — richiesti da Kokoro TTS ma non dichiarati.

### Indicatore MCP down

- **`src/gui.py`**: `set_mcp_status()` mostra un quadrato rosso nell'indicatore tool quando il server MCP non è raggiungibile.
- **`src/main.py`**: `_mcp_health_check_loop()` verifica ogni 60s la connettività TCP alla porta MCP.
- **`locales/*.json`**: aggiunta chiave `gui.mcp_down_tooltip` in 9 lingue.

### Script standard corretti

- **`config/commands_de.ini`**: `lies_nachrichten` → `read_news`
- **`config/commands_ko.ini`**: `ilgeo_nyuseu` → `read_news`, `chaja_syoping` → `search_shopping`
- **`config/commands_zh.ini`**: `sou_gouwu` → `search_shopping`
- **`.gitignore`**: `scripts/*` + eccezioni per i 15 script `.vass` standard distribuiti.

### Temi unificati

- **`src/setup_google.py`**: applicato lo stesso dark theme dell'installer (sfondo `#1a1a2e`, pulsanti `#0f3460`, accent `#e94560`).

### File Chiave

| File | Linee | Contenuto |
|------|-------|-----------|
| `installer/installer.py` | 732 | Wizard PySide6 7-page, stato condiviso, retranslate dinamico |
| `installer/install_worker.py` | 548 | Installazione in QThread, step riprendibili, download paralleli |
| `installer/gpu_detect.py` | 231 | Rilevamento GPU + suggerimento modello calibrato |
| `installer/downloader.py` | 169 | Download GitHub/HF/Python con progress, selezione asset |
| `installer/build.py` | 378 | PyInstaller build con embed base64 e checklist gitignore |
| `installer/i18n.py` | 640 | Traduzioni installer in 9 lingue |
| `vass.py` | 58 | Guard stderr/stdout + logging.basicConfig per pythonw |
| `src/main.py` | 2077 | `_mcp_health_check_loop`, MCP status indicator |
| `src/gui.py` | 1769 | `set_mcp_status`, `_on_tool_indicator` MCP down |
| `src/setup_google.py` | 349 | Dark theme installer |
| `requirements.txt` | 48 | `loguru`, `transformers` |
| `VERSION` | 1 | Bump a 0.5.22 |

---

### Risoluzione dispositivi audio stabile per nome

- **`_resolve_audio_device` (nuovo static method in `VassApp`)**: gli ID dispositivo assegnati dal SO non sono stabili tra reboot/plug-unplug. La funzione risolve l'ID salvato confrontandolo con il nome salvato in `settings.ini` (`input_device_name` / `output_device_name`). Se l'ID è stale, cerca il device per nome esatto, poi per nome parziale. Valore `-1` = default di sistema, preservato.
- **`settings_manager.py`**: ora legge e salva `input_device_name` e `output_device_name` da/per `settings.ini`, sia in lettura che nei defaults.
- **`settings_editor.py`**: selezione dispositivi completamente rivista: validazione ID contro nome salvato; se l'ID è stale, risolve per nome (esatto → parziale); se nessuna corrispondenza, fallback a "Automatic" (-1). Quando si seleziona "Automatic", il nome salvato viene rimosso per evitare residui che causavano ID errati al reload.

### Tooltip del tasto principale

- **`gui.py`: `update_button_tooltip()`**: il tooltip del tasto principale mostra ora il dispositivo di input/output attualmente in uso con ID e nome (es. `Input: [2] Microfono (HyperX SoloCast 2)`). Chiamato sia all'avvio che al ricaricamento settings.
- Risolve il problema per cui senza `--debug` (pythonw) il tooltip mostrava dispositivi diversi da quelli reali.

### Avvio llama.cpp robusto

- **`_wait_for_llamacpp_ready()`**: polling di `/v1/models` fino a timeout (60s) prima di procedere.
- **Defer di context/model detection**: se llama.cpp è in autostart, la rilevazione di context length e modello AI viene posticipata a dopo che il server è pronto.
- **Retry context detection in `_handle_ai_fallback`**: se la rilevazione era fallita o saltata, riprova una volta.
- **Rilevazione context length arricchita**: cerca nei metadata del modello, nello `status.args` e infine negli argomenti di lancio di llama.cpp (`-c`). Fallback a 4096.

### Stampa sicura universale (`_ts_print`)

- **`_ts_print` avvolta in try/except**: sotto `pythonw.exe` (senza `--debug`) `sys.stdout` è `None` e qualsiasi `print()` causava eccezioni silenziose che interrompevano blocchi `try/except` critici (es. risoluzione dispositivi). Ora il wrapper cattura l'errore e prosegue.

### Parole protette nei prompt

- **`_MATH_WORDS` → `_PROTECTED_WORDS`** in `src/prompts.py`: rinominato per chiarezza; include marcatori di negazione, operatori matematici, quantificatori e riferimenti temporali essenziali.
- **Aggiunte "fra", "tra", "in"** in tutte le lingue per impedire la rimozione di riferimenti temporali/spaziali critici.
- **Overlap rimosso** tra `_STOPWORDS` e `_PROTECTED_WORDS`: parole protette non possono più essere fermate da entrambi i meccanismi.

### Logging di debug (gated da `debug_enabled`)

- **`state_manager.py`**: `_sm_log()` logga ogni transizione di stato con dettaglio (vecchio→nuovo stato, redirect da listening, flag pausa).
- **`tts_engine.py`**: `_log()` logga coda speak, coda audio, stati playing, start/end riproduzione.
- **`script_runner.py`**: `_sr_log()` logga accodamento/esecuzione script e attese worker.
- **`event_reminder.py`**: `_log()` logga inizio/fine/skip esecuzione schedule.
- **`main.py`**: debug logging per comandi ritardati (`_process_delayed_command`, `_execute_delayed_command`).

### Helper esterno silenzioso

- **`gui.py`: `_launch_helper()`** ora redirige stdin/stdout/stderr a `subprocess.DEVNULL` per evitare che processi helper ereditino console.

### File Chiave

| File | Linee | Contenuto |
|------|-------|-----------|
| `src/main.py` | 2053 | `_resolve_audio_device`, `_wait_for_llamacpp_ready`, `_ts_print` safe, debug delayed, defer context detection |
| `src/gui.py` | 1754 | `update_button_tooltip`, DEVNULL helper |
| `src/settings_editor.py` | 675 | Selezione device per nome, cleanup -1, fallback default |
| `src/settings_manager.py` | 221 | Lettura/salvataggio `input_device_name`/`output_device_name` |
| `src/state_manager.py` | 150 | `_sm_log` debug transizioni stato |
| `src/tts_engine.py` | 511 | `_log` debug coda speak/audio, stato playing |
| `src/event_reminder.py` | 480 | `_log` debug esecuzione schedule |
| `src/script_runner.py` | 256 | `_sr_log` debug accodamento/esecuzione script |
| `src/prompts.py` | 135 | `_PROTECTED_WORDS`, rimozione overlap, "fra"/"tra"/"in" |
| `VERSION` | 1 | Bump a 0.5.21 |

---

### Correzione semantica della pausa

- **Pausa = inibizione solo input vocale**: ripristinato il comportamento pre-StateManager per cui script, timer, alert, comandi ritardati e chat testuale continuano a funzionare anche in pausa manuale o auto-pausa.
- **`StateManager` preserva l'intento di pausa**: i flag `_manual_pause` e `_auto_paused_at` sopravvivono alle transizioni temporanee (`waiting`, `running_script`, `playing`, ...). Quando un'operazione termina e richiede `"listening"`, lo stato ritorna automaticamente a `"paused"` se il flag è ancora attivo.
- **`VassApp.set_state("listening")` delega direttamente a `StateManager`**: rimossa la chiamata a `resume_listening(force=False)` che cancellava l'auto-pausa.
- **`exit_auto_pause()` non interrompe operazioni in corso**: riprende solo se lo stato corrente è effettivamente `"paused"`.
- **`script_runner.py`**: rimosso il blocco su pausa manuale; il worker attende solo `waiting`/`waiting_resources`/`playing`/`recording`.
- **`timer_manager.py`**: rimossi i controlli su pausa manuale; timer e alert attendono solo `recording`/`playing`/`waiting`/`waiting_resources`.
- **`main.py`**:
  - `_process_chat_text()` non ignora più la pausa manuale.
  - Registrazione completata non viene più scartata in pausa manuale.
  - `_listen_once()` ritorna `""` se l'app è in pausa (manuale o auto), così il VASScript `listen()` è inibito come il loop principale.
- **Test aggiornati**: `tests/test_state_manager.py` copre persistenza dei flag attraverso stati temporanei e blocco di `exit_auto_pause` durante operazioni.

### File Chiave

| File | Contenuto |
|------|-----------|
| `src/state_manager.py` | Pause flags persistenti, redirect listening→paused, exit_auto_pause controllato |
| `src/main.py` | Delega semplificata a StateManager, chat/registrazione/listen_once corretti |
| `src/script_runner.py` | Rimosso blocco pausa manuale |
| `src/timer_manager.py` | Rimosso blocco pausa manuale |
| `tests/test_state_manager.py` | Nuovi test sulle transizioni temporanee |
| `VERSION` | Bump a 0.5.20 |

---

## v0.5.19 (2026-06-30)

### State Manager e Pausa

- **Nuovo `src/state_manager.py`**: centralizza tutte le transizioni di stato. La pausa manuale è sacra (nessuna operazione automatica può riprendere l'ascolto), mentre l'auto-pausa può essere interrotta da script/timer/AI.
- **`VassApp.state` come property**: delega a `state_manager`; `set_state("listening")` rispetta la pausa manuale e ritorna a `"paused"` se necessario.
- **Auto-pausa basata sul tempo reale**: sostituito il contatore a frame (inaffidabile perché Whisper blocca il loop) con un timestamp `_noise_high_since`. L'auto-pausa scatta dopo `noise_pause_duration` secondi reali di rumore continuo sopra soglia.
- **Rispetto della pausa manuale in tutti i moduli**: `script_runner`, `timer_manager`, chat input e registrazione non avviano/eseguono nulla mentre l'utente ha messo in pausa.
- **`_listen_once` ripristina lo stato**: se era in pausa, torna in pausa senza riavviare lo stream.
- **Invarianti di stato**: aggiunto `_verify_stream_state` che logga se lo stato atteso e lo stato reale dello stream divergono.

### Wake Word e Microfono

- **Sensibilità default aumentata**: da `0.005` a `0.010` (metà dello slider 1-20) per compensare la soglia effettiva più alta introdotta dal refactor del noise floor.
- **Manual gain override**: `input_volume < 1.0` disabilita l'auto-gain e lo tratta come guadagno fisso; `1.0` abilita la regolazione automatica.
- **Descrizione `input_volume` aggiornata** in tutte le 9 lingue per indicare che 1.0 = automatico.

### Pulizia

- Rimossi file di benchmark obsoleti: `test_whisper.py`, `test_wake_results.txt`.
- Cartella `tests/` aggiunta a `.gitignore`; aggiunta anche `.ruff_cache/`.

### File Chiave

| File | Linee | Contenuto |
|------|-------|-----------|
| `src/main.py` | ~2101 | StateManager integration, time-based auto-pause, manual-pause guards |
| `src/state_manager.py` | ~105 | Centralized state transitions and pause semantics |
| `src/script_runner.py` | ~271 | Skip scripts when manual pause is active |
| `src/timer_manager.py` | ~155 | Wait/abandon timers when manual pause is active |
| `src/voice_recognition.py` | ~268 | input_volume property, auto-gain override, clipping cooldown |
| `src/settings_manager.py` | ~228 | Default sensitivity 0.010 |
| `src/settings_editor.py` | ~722 | Slider default sensitivity 10, input_volume descriptions |
| `tests/test_state_manager.py` | ~175 | Unit tests for StateManager |
| `tests/test_voice_recognition.py` | ~107 | Unit tests for adaptive gain/noise floor |
| `.gitignore` | ~105 | tests/, .ruff_cache/ |

---

## v0.5.18 (2026-06-27)

### Auto-Gain Fix

- **Unificato noise floor**: auto-gain ora usa `_running_noise_floor` (calcolato su ogni frame, α=0.01) invece del noise floor separato di voice_recognition, che era sempre troppo basso per triggerare la riduzione.
- **Rimosso reset input_volume dal watcher**: il watcher non sovrascrive più `input_volume = 1.0` a ogni ricarica settings.
- **Print condizionati a debug_enabled**: i messaggi `[NoiseFloor] Gain adjusted` appaiono solo con debug attivo.

### File Chiave

| File | Linee | Contenuto |
|------|-------|-----------|
| `src/main.py` | ~2029 | Auto-gain unificato, rimosso watcher input_volume, print debug |

## v0.5.17 (2026-06-27)

### Auto-Gain Microfono

- **Noise floor subtraction**: sostituita moltiplicazione `noise_floor * 3.0` con sottrazione `energy - noise_floor` per la soglia wake word. Funziona con microfoni sensibili (HyperX).
- **Auto-calibrazione gain**: se il noise floor > 0.02 dopo 50 frame, `input_volume` viene ridotto automaticamente per portare il rumore a target (~0.03). Aggiornamento continuo ogni 50 frame di silenzio, cap ±20% asimmetrico (riduzione aggressiva, aumento graduale).
- **Reset noise floor**: al cambio di `input_device`, resettato anche il noise floor di `voice_recognition`.
- **Soglia SNR**: `raw_energy > noise_floor * 1.3` per trigger diretto, altrimenti `energy - noise_floor > sensitivity`.

### Compact Mode — Fix Posizione

- **`from_restore=True`**: al riavvio in modalità compatta, la posizione non viene ricalcolata (evita drift cumulativo). `_normal_geometry` ricostruita da coordinate salvate: `normal_x = compact_x + 18 - width/2`.
- **Checkbox `compact_mode`**: aggiunta a `BOOLEAN_KEYS` nel settings editor, con label e descrizione in tutte 9 lingue.

### Rumore — Visualizzazione e Auto-Pausa

- **Noise floor bar**: `VolumeTopBar` disegna una barra arancione 2px a metà altezza, centrata, che rappresenta `input_volume` (gain automatico). Visibile solo con `debug_enabled`.
- **`noise_floor_signal`**: emesso ogni 50 frame (~1s) con `ratio = input_volume` (0.0-1.0).

### Dispositivi Audio

- **Nome dispositivo salvato**: `settings_editor` salva `input_device_name`/`output_device_name` nel settings.ini insieme all'indice. Al caricamento, se `findData(indice)` fallisce (indici PortAudio cambiati), cerca per nome. `HIDDEN_KEYS` nasconde i campi nome dalla UI.
- **Dedup regex**: `[\)\]]?` opzionale per gestire nomi PortAudio troncati (mancanza di `)` finale).
- **`findData` fallback**: iterazione manuale `itemData(i) == current_val` quando `findData` fallisce per tipo QVariant.
- **`list_audio_devices()`**: nuova funzione in `utils.py` che stampa il dispositivo input/output configurato all'avvio e al salvataggio settings.

### Impostazioni

- **`encoding="utf-8"`**: aggiunto a tutte le writes di `settings.ini` (mancava in `save_gui_position`, causava corruzione su Windows).
- **Finestra disabilitata durante loading**: `self.setEnabled(state != "loading")` impedisce interazioni (niente settings editor, niente click) finché VASS non è pronto.

### Bugfix

- **Noise floor tracking in main.py**: l'auto-gain ora traccia il noise floor su tutti i frame (non solo non-speech) con finestra 250 frame e smoothing 0.98.
- **Calibrazione iniziale noise floor**: bloccata detection per primi 50 frame (2 secondi) per calibrare il noise floor prima di processare wake word.
- **Traduzioni `compact_mode`**: aggiunte field_labels e field_descriptions in tutte 9 lingue.
- **Versione**: `0.5.16` → `0.5.17`.

### File Chiave

| File | Linee | Contenuto |
|------|-------|-----------|
| `src/voice_recognition.py` | ~200 | Noise gate, auto-gain, SNR threshold, noise floor calibration |
| `src/gui.py` | ~1871 | VolumeTopBar gain bar, _on_noise_floor, setEnabled(loading), from_restore fix |
| `src/main.py` | ~2010 | Watcher input_device/output_device reload, auto-pause, startup diagnostics |
| `src/settings_editor.py` | ~722 | compact_mode checkbox, dedup fix, device name save/load, HIDDEN_KEYS |
| `src/audio_handler.py` | ~95 | start_stream debug print, try/except |
| `src/utils.py` | ~425 | list_audio_devices() |
| `src/tts_engine.py` | ~517 | update_output_device() |
| `src/script_engine.py` | ~260 | tools_block con append_tool_descriptions |
| `src/prompts.py` | ~134 | append_tool_descriptions() |
| `src/settings_manager.py` | ~228 | encoding utf-8 su default write |
| `src/tool_groups.py` | ~242 | "eventi" aggiunto al fallback |

---

---

## v0.5.16 (2026-06-26)

### Compact Mode — UI

- **`_CompactWidget`**: widget custom QPainter con 3 cerchi concentrici (α=0.2, 0.5, 1.0) e icona centrale (waveform, play, pausa, punti, diamante). Sostituisce il vecchio QPushButton 20×20.
- **`set_compact_mode`**: gestione trasparenza via `WA_TranslucentBackground` toggle, rimosso bordo DWM con `DWMNCRP_DISABLED`, ripristinati angoli arrotondati su Windows 11 con `DWMWCP_ROUND`.
- **Widget background**: tutti i bottoni (`_bell_btn`, `replay_btn`, `_menu_btn`, `_chat_btn`, `_chat_input`, `btn`) cambiati da `background: transparent` a `background-color: #101010` per compatibilità con `WA_TranslucentBackground`.
- **Rimosso `_remove_native_border`**: sostituito da Win32 diretto in `set_compact_mode`.
- **Versione**: `0.5.15` → `0.5.16`.

### File Chiave

| File | Linee | Contenuto |
|------|-------|-----------|
| `src/gui.py` | ~1849 | `_CompactWidget`, `set_compact_mode`, Win32 border fix, widget bg fix |
| `VERSION` | 1 | `0.5.16` |

---

---

## v0.5.15 (2026-06-25)

### App Launcher (Cross-Platform)

- **`app_launcher.py`**: nuovo modulo per enumerazione e lancio app su Windows (.lnk + UWP via `Get-StartApps`), macOS (.app bundles), Linux (.desktop). Fuzzy matching `SequenceMatcher` soglia 0.70, cache TTL 5 minuti.
- **`script_engine.py`**: `run()` cross-platform (PowerShell su Win32, `shell=True` altrove). Aggiunte funzioni VASScript `launch_app(name, args?)` e `list_apps()` con dispatch. `"launch_app"` in `_SIDE_EFFECT_FUNCTIONS`.
- **`scripts_editor.py`**: template `launch_app`, `launch_app con args`, `list_apps`. Template `run` cross-platform (`"echo hello"`).
- **`VASCRIPT_REFERENCE.md`**: documentate `launch_app()` e `list_apps()`.

### Notifiche Email

- **`main.py`**: `_format_email_ago()` parsifica header RFC 2822 con `email.utils.parsedate_to_datetime` e produce stringa relativa localizzata ("2 ore fa"). Iniettata in TTS e notifica.
- **`main.py`**: link Gmail ripristinato nelle notifiche (`{"link": "https://mail.google.com/..."})` per "Leggi online" cliccabile.
- **`gmail_handler.py`**: propagato `entry["sent_date"]` dal header Date Gmail.
- **`locales/*.json`**: 7 nuove chiavi i18n (`just_now`, `ago_minutes`, `ago_hours`, `ago_days`, `ago_weeks`, `ago_months`, `on_date`). `new_email` aggiornato con `{date}`.

### Calendario Eventi

- **`events_editor.py`**: `QCalendarWidget` a sinistra, `day_list` (eventi giorno) + form a destra. Date con eventi evidenziate in grassetto (`#0d7377`). `setFixedHeight(100)` → `setMinimumHeight(80)` per stretch verticale.
- **Bottoni Aggiungi/Aggiorna/Elimina** spostati dentro il frame "Dettagli".

### Tool Groups

- **`tool_groups.py`**: "discussione","discussioni","discorso" aggiunti e tradotti in tutte 9 le lingue in `_ANAPHORA_KEYWORDS`.

### Bugfix Stato App

- **Race waveform click #1 — `_stream_gen`**: `stop()` non incrementava `_stream_gen`, causando `_on_finished` dall'audio thread che accodava `set_state_signal` stale dopo il click. Fix: `self._stream_gen += 1` in `stop()`.
- **Race waveform click #2 — stale queued signal**: click durante `"playing"` processava `set_state("listening")`, ma `_on_tts_done` dall'audio thread aveva già accodato `set_state_signal("waiting")` che sovrascriveva. Fix: `self.gui.schedule(0, lambda: self.set_state("listening"))` dopo stop per ri-assertare dopo la coda eventi.
- **Race waveform click #3 — click su `"waiting"`**: se stale signal arrivava prima del click, stato era `"waiting"` e `pass` ignorava. Fix: controllo `self.gui.player.data is not None` per rilevare waveform ancora attivo.
- **TTS silenzioso dopo stop**: `stop()` setta `_tts_paused = True` ma nessuno lo resettava mai. Fix: `_play_worker` controlla `_audio_queue` quando paused e resetta automaticamente.
- **Script non trovato freeze**: `_execute_script_impl` faceva `return` senza resettare stato `"running_script"`. Fix: reset `"listening"` prima del return.

### Varie

- **Versione**: `0.5.14` → `0.5.15`.

### File Chiave

| File | Linee | Contenuto |
|------|-------|-----------|
| `src/app_launcher.py` | ~280 | Nuovo — enumerazione + lancio app cross-platform |
| `src/script_engine.py` | ~1770 | `run()` cross-platform, `launch_app`/`list_apps` dispatch |
| `src/scripts_editor.py` | ~120 | template launch_app, list_apps, run cross-platform |
| `src/main.py` | ~1967 | `_format_email_ago`, link Gmail, waveform click fix (3 bug) |
| `src/gmail_handler.py` | ~200 | `sent_date` propagation |
| `src/tts_engine.py` | ~514 | `_stream_gen` in stop(), `_play_worker` auto-unpause |
| `src/script_runner.py` | ~267 | script not found state reset fix |
| `src/events_editor.py` | ~420 | calendar widget, day_list stretch |
| `src/tool_groups.py` | ~300 | anaphora keywords tradotti 9 lingue |
| `locales/*.json` | 9 file | 7 chiavi tempo relativo, `new_email` con `{date}` |
| `Allowed_root/VASCRIPT_REFERENCE.md` | ~670 | `launch_app`, `list_apps` docs |

---

## v0.5.14 (2026-06-24)

### VASScript

- **`form()`**: nuova funzione VASScript con dialog modale, 5 tipi campo (`text`, `number`, `checkbox`, `select`, `textarea`). Pattern thread-safe signal+Event come `request_auth()`.
- **Fix `form()` Annulla**: pulsante Cancel chiamava `dlg.reject()` senza settare `_form_event` — script thread bloccato su `_form_event.wait()` per sempre. Risolto: `_form_event.set()` garantito dopo `dlg.exec()`.
- **Fix `form()` OK freeze**: rimossa NameError nel lambda del dizionario — i tipi Qt importati localmente ora non servono più (value extraction inline).
- **`say()` silent skip**: `silent=True` salta completamente TTS senza propagare flag al motore TTS.
- **Documentazione**: guida `form()` aggiunta a `VASCRIPT_REFERENCE.md` con tipi, esempi, formato risultato.

### Bugfix Stato App

- **Race condition TTS event_reminder**: quando un evento reminder faceva partire TTS durante script (es. dentro form modale), `_on_tts_done()` ripristinava lo stato salvato `"running_script"` DOPO che il `finally` dello script aveva già impostato `"listening"`. Risultato: stato bloccato su `"running_script"`, wake word detection disabilitato.
- **Fix `tts_engine.py:_on_tts_done()`**: ripristina `_state_before_tts` solo se lo stato corrente è ancora `"playing"`. Se qualcun altro ha già cambiato stato (es. `finally` dello script), non sovrascrive.
- **Fix `script_runner.py:finally`**: non controlla più `app.tts.tts_playing` — imposta sempre `"listening"`. Il branch `"playing"` era pensato per lo `say_async` dello script ma veniva attivato erroneamente da TTS esterni, causando la race condition.

### Icona

- **Revert a `vass.ico`**: icona tornata a `.ico` nativo Win32. Tre strati: `QIcon` + `SendMessageW` in `showEvent` + `AppUserModelID` via registro.
- **WS_EX_APPWINDOW**: riga commentata dall'utente.

### Varie

- **`crash.log`**: tutti i 4 write unificati a `log/crash.log`. Puliti `debug.log` e `crash.log` vecchi dalla root.
- **Versione**: `0.5.13` → `0.5.14`.

### File Chiave

| File | Linee | Contenuto |
|------|-------|-----------|
| `src/gui.py` | ~1572 | `_on_form_requested`, `_finish_form`, form_signal, fix cancel freeze |
| `src/script_engine.py` | ~1767 | `"form"` in `_SIDE_EFFECT_FUNCTIONS`, handler, silent say |
| `src/script_runner.py` | ~264 | finally sempre "listening", rimosso tts_playing check |
| `src/tts_engine.py` | ~509 | `_on_tts_done` defensive state check |
| `Allowed_root/VASCRIPT_REFERENCE.md` | ~669 | form() reference

### Volume Unificato
- **`[audio] app_volume`**: singolo parametro sostituisce `[tts] volume` + `[audio] output_volume`. Si applica a TTS, beep, alert, Google Home. Migrazione automatica (old keys rimosse da settings.ini). `output_volume` nascosto in settings editor.
- **Live volume durante playback**: audio normalizzato a peak=1.0 al caricamento, `self.app_volume` letto a ogni invocazione `_cb` di PortAudio — la rotellina agisce immediatamente.

### Kokoro Voice Override
- **`kokoro_voice`**: combo box in settings editor con 62 voci in 10 gruppi linguistici (intestazioni disabilitate, separatori). Default calcolato da `LANG`. Override via `_kokoro_voice_override` in `tts_engine.py`.

### VASScript
- **Nomi snake_case**: 24 funzioni rinumerate (`add_event`, `read_state`, `clipboard_get`, ecc.). Vecchi nomi preservati come alias. Tutti i template aggiornati.
- **`filter_json()`**: parsing JSON con filtri condizionali (`colonna>=valore`), formato personalizzato, risoluzione dotted path (`attributes.titles.en_jp`), auto-unwrap JSON:API. Gestione `AttributeError`.
- **`fetch_json()`**: scarica JSON con retry Accept header (JSON → JSON:API → `*/*`).
- **`compress_memory()`**: forza compressione memoria da script.
- **`get_datetime()`**: nuovi vars `$year`, `$month`, `$day`.
- **`notify(text, prio, link)`**: 3° argomento opzionale per link cliccabile.
- **`_sub_vars()`**: dotted `{...}` senza `$` non vengono più risolti come variabili (protegge format string di `filter_json`).
- **fetch_cache**: TTL 300s per `fetch_text` e `fetch_json`.

### Editor Script
- **CodeEditor**: nuovo widget `QPlainTextEdit` con line numbers (`LineNumberArea`) e syntax highlighting (`VassScriptHighlighter`: commenti, stringhe, `$var`, keyword, builtin, numeri, operatori). Posizionamento via `viewport()`.
- **Templates**: tutti rinominati snake_case. Aggiunti `fetch_json`, `filter_json` (3 varianti), `filter_json con filtro`, `filter_json con filtro numerico`.

### Opacità in Pausa
- **`paused_opacity`**: slider 10-100 (scala 0.01) in settings editor. Default 50%. Salva in `[gui] paused_opacity`. Applicato da `_on_set_state`.

### Gmail Encryption
- **`gmail_seen.json`**: crittografato con Fernet (chiave in keyring/machine+user fallback). Migrazione automatica v1→v2. Pruning a 500 entry.

### Notifiche
- **Link cliccabile**: `notify()` supporta `data.link` renderizzato come `<a>` per qualsiasi tipo.
- **`\n` rendering**: sia `\n` reale che `\\n` letterale convertiti in `<br>`.
- **RSS cache**: limite per feed 20→1000, persistente tra sessioni, dedup via GUID.

### Eventi
- **`events_editor.py`**: `_do_save()` ora rilegge il file e fonde per-field con snapshot caricato (`_items_snapshot`). Le modifiche di EventReminder (data/ora/notify) sui campi non toccati dall'utente sopravvivono al salvataggio. Migrazione ID per item senza `id`.

### Selezione Automatica Contesto
- **Checkbox**: `auto_context_selection` in `[ai]`, off di default. Abilita `needs_memory()` in VASScript `ai()`.
- **Heuristic**: anaphora keywords in 9 lingue (dict Python, non locale file). Ordine: anaphora prima di standalone. `fuzzy_match_word()` fallback. Zero falsi negativi.

### Tool Groups
- **Keyword filtering**: `select_tool_groups()` abbina prompt→gruppi MCP. Fuzzy fallback. 900 nuove keyword in 9 lingue.
- **`needs_memory()`**: determina se serve storia conversazione. `STANDALONE_GROUPS` = compute, time, lang.

### Fuzzy Matching
- **`utils.py`**: `fuzzy_ratio()`, `fuzzy_match_word()` estratti. Sostituiti 4 `SequenceMatcher` diretti in `command_executor.py`, `script_engine.py`.

### Thread Safety TTS
- **Gen/Play workers separati**: `_gen_worker` genera audio in background, `_play_worker` riproduce. Thread vivi permanentemente.
- **`stop()`**: incrementa `_gen_seq` (scarta generazioni stale), drena `on_done` da `_audio_queue`, non uccide thread. Imposta `_tts_paused = True`.
- **`pause()`/`unpause()`**: mette in pausa/riprende stream audio.
- **StreamGen**: `_stream_gen` counter + `_cb` closure locale per evitare race `finished_callback`.

### GUI
- **Chat layout**: `self.stacked` nascosto quando chat input è visibile (risolve oscillazione layout).
- **WheelEvent**: semplificato — usa `self.app.app_volume` direttamente, salva in `[audio] app_volume`.
- **Pulsante**: testo elided via `QFontMetrics.elidedText()` in `_on_set_state()` e `eventFilter()`.
- **Bell button**: larghezza ridotta a 35px. Spacers auto-bilanciati.
- **Tooltip**: stile dark applicato a `QToolTip` in `BASE_STYLESHEET`.

### Locales
- **Tutti 9 file**: `read_online`, `kokoro_voice` label+description, `output_volume` sostituito con `app_volume`. 900 keyword tool group. Fix 6 duplicati.
- **`it.json`**: aggiunte `ore`, `piu'`, `attivita`.

### MCP
- **`nextevent()`**: nuovo tool in `mcp_server/src/mcpgoal/server.py` (restituisce solo il primo evento).
- **Tool filtering**: MCP tool gated per gruppo in VASScript `ai()`.

### Dipendenze
- **requirements.txt**: aggiunti `google-auth>=2.0.0`, `google-assistant-sdk>=0.5.0`, `grpcio>=1.60.0`, `GPUtil>=1.4.0`.
- **install.py**: `_verify_imports` include `google-auth`, `google-assistant-sdk`, `grpcio`, `GPUtil`, `feedparser`. Default `kokoro_voice` basato su `LANG`. `[audio] app_volume: "0.50"`.

### Pulizie
- **`memory_manager.py`**: rimosso `trim_memory_json()` morto (bug: inviava solo prompt senza dati).
- **`main.py`**: wrapping `writeinfo()` rimosso da summary. Uso `_trim_memory_if_needed(force=True)` unificato. RSS notification creation spostata in `RssReader` (-22 linee). Stream CPS log condizionato da `debug_enabled`.
- **`rss_reader.py`**: accetta `notification_manager` direttamente, callback `on_new_items` rimosso.

### Versioni
- **`VERSION`**: 0.5.8 → 0.5.13 (commit v0.5.9, v0.5.10, v0.5.11 + fix)

### File Chiave
| File | Linee | Contenuto |
|------|-------|-----------|
| `src/tts_engine.py` | ~507 | gen/play workers, app_volume live, kokoro_voice, pause/unpause |
| `src/main.py` | ~1929 | memory trim unificato, auto_context, chat refactor, RSS rimosso |
| `src/script_engine.py` | ~1590 | filter_json, fetch_json, compress_memory, snake_case aliases |
| `src/code_editor.py` | ~210 | CodeEditor, LineNumberArea, VassScriptHighlighter |
| `src/scripts_editor.py` | ~120 | CodeEditor integrato, templates snake_case |
| `src/gui.py` | ~1461 | chat layout, wheelEvent, elided text, paused_opacity |
| `src/utils.py` | ~400 | fuzzy_ratio, fuzzy_match_word, encrypt/decrypt fields |
| `src/tool_groups.py` | ~300 | needs_memory, select_tool_groups, ANAPHORA_KEYWORDS 9 lingue |
| `src/settings_manager.py` | ~170 | app_volume migrazione, auto_context_selection, paused_opacity |
| `src/settings_editor.py` | ~130 | _KOKORO_VOICES, app_volume nascosto, paused_opacity slider |
| `src/gmail_handler.py` | ~200 | Fernet encryption, v1→v2 migration, 500 pruning |
| `src/events_editor.py` | ~420 | _do_save merge con _items_snapshot |
| `src/rss_reader.py` | ~200 | notification_manager diretto, cache 1000/feed |
| `src/notification_dialog.py` | ~150 | link rendering, \n → <br> |
| `src/command_executor.py` | ~420 | fuzzy_ratio |
| `src/google_home.py` | ~50 | volume param in play_audio_response |
| `src/timer_manager.py` | ~160 | _play_alert instance method |
| `locales/*.json` | 9 file | read_online, app_volume, kokoro_voice, 900 keyword |
| `mcp_server/src/mcpgoal/server.py` | ~550 | nextevent tool |
| `Allowed_root/VASCRIPT_REFERENCE.md` | ~450 | snake_case headers, filter_json section |
| `install.py` | ~1308 | kokoro_voice, app_volume, verify_imports |
| `scripts/rss_read.vass` | ~30 | riscritto con fetch_text + ai_raw |

## v0.5.8 (2026-06-21)

### Dipendenze
- **requirements.txt**: rimossi 5 pacchetti inutilizzati (`loguru`, `scipy`, `transformers`, `structlog`, `tzlocal`).
- **install.py**: `_verify_imports` aggiunta verifica `tiktoken`, rimossa `structlog`.

### File Chiave
| File | Linee | Contenuto |
|------|-------|-----------|
| `requirements.txt` | 42 | -5 pacchetti |
| `install.py` | ~1308 | verify imports fix |

---

## v0.5.7 (2026-06-21)

### Thread Safety
- **`_state_vars_lock`**: `main.py` — nuovo `threading.Lock()` per scritture a `_noise_high_frames`, `_silent_frames`, `_auto_paused_at`, `_running_noise_floor`, `_memory_cache`.

### Security
- **`run()` in `script_engine.py`**: deny-list (non `python`, non `pip`), audit log con `pyautogui`, `pyperclip`. `-EncodedCommand` → `-Command`.
- **`execute_command()` in `command_executor.py`**: stesse mitigazioni.

### Documentazione
- **MCP tool `getidle`**: docstring aggiunta.
- **VASScript**: documentati 5 funzioni mancanti (`ifequals`, `print`, `readfile`, `rss_fetch`, `say_async`).

### Locales
- **`tool_groups`**: aggiunto a 8 file locale non italiani (en, de, fr, es, pt, ja, ko, zh).
- **Traduzioni**: keyword `tool_groups` tradotte in tutte 7 lingue non inglesi.

### File Chiave
| File | Linee | Contenuto |
|------|-------|-----------|
| `src/main.py` | ~2370 | `_state_vars_lock`, 5 lock sites |
| `src/script_engine.py` | ~1600 | deny-list, audit log, -EncodedCommand |
| `src/command_executor.py` | ~420 | same mitigations |
| `locales/*.json` | 9 file | `tool_groups` + traduzioni |

---

## v0.5.6 (2026-06-19)

### Context & AI
- **tiktoken**: conteggio token reale via `cl100k_base` in `main.py:_count_tokens()`, fallback `len//2`. Sostituiti tutti 6 `len//2` in `_handle_ai_fallback`.
- **Compressione summary**: `_compress_summary()` in `main.py:1720-1744` — AI con `temperature=0.1`, `max_tokens=500`. Cache in `_summary_cache`.
- **Context length wait sync**: spin-wait 5s per `_detect_context_length` prima della prima chiamata AI (`main.py:1500-1506`). Rilevazione ri-triggerata quando `context_length` torna a 0.
- **`compress_context` euristico**: `_STOPWORDS` per 9 lingue, `_compress_heuristic(text, lang)` rimuove stopwords. Checkbox in settings `[ai]`. Label `(SPERIMENTALE)` in 9 lingue.
- **MCP_PROMPT direttiva riscritta**: separato `MCP_PROMPT` (web tool, sempre) da `VASSCRIPT_TOOLS_PROMPT` (interact, gated da `allow_ai_scripts`). `main.py:110-122`.

### Comandi Ritardati
- **Sistema delayed**: `command_executor.py` espande comandi in varianti ritardate in-memory (`"{keyword} {prep} {duration}"`). `_delay_originals` mappa delayed→originale. `find_matching_command` restituisce scope `__delayed__`.
- **Esecuzione**: `main.py:_execute_delayed_command` parsa durata (regex→AI fallback), avvia timer con `command_text`. `_process_delayed_command(text)` re-inietta comando originale a scadenza.
- **TimerManager**: `start(duration_str, command_text=None)`, `_run(command_text)` esegue via `_process_delayed_command`.
- **Tie-breaker**: `find_matching_command` preferisce `delayed_command` quando il ratio è identico all'originale (3 posizioni).

### VASScript
- **`ai_raw()`**: `script_engine.py:378-397` — no MCP tools, no memoria, no system prompt, `temperature=0.3`, retry 2×1s. Usato da `timer.vass` e `translate.vass`.
- **Math functions**: `add`, `sub`, `mul`, `div` in `script_engine.py:408-440`.
- **Fix `json` locale**: rimosso `import json` ridondante dentro `_call_function` che shadowava il globale per tutti gli handler dopo `getdatetime` (`script_engine.py:850`).

### Meteo
- **Cascade 3 fonti**: `_do_weather` orchestrator: wttr.in → Open-Meteo → met.no.
- **Risoluzione coordinate**: `_resolve_coordinates(location)` via `cities500.txt` da GeoNames (200K città, 38 MB). `_download_geonames()` lazy-download al primo fallimento wttr.in.
- **Helper**: `_wmo_description(code)`, `_degrees_compass(deg)`.
- **Cache**: `_get_cached_weather()`, `_cache_and_return_weather()`, `_set_weather_vars()` condivisi tra fonti.

### TTS (Kokoro/espeak-ng)
- **Newline splitting**: `tts_engine.py:210-217` — inserisce `\n` ogni 30 parole senza punteggiatura (`.`, `!`, `?`). Previene troncamento silenzioso di espeak-ng su testi lunghi non punteggiati.
- **Timeout dinamico**: `timeout = max(60, len(data)/sr*1.5+5)` per WAV >60s.
- **Stripping caratteri invisibili**: `utils.py:_CONTROL_RE` aggiunto `\u034f` (CGJ). `clean_for_tts` aggiunge filtro `unicodedata.category(c) != 'Cf'`.

### MCP Tool Indicator
- **GUI**: `gui.py:294-299` — `_tool_indicator` QLabel (10×10px, cerchio colorato) a sinistra del pulsante principale. `tool_indicator_signal` thread-safe.
- **Colori**: blue (browse/webfetch), purple (websearch), yellow (file), red (interact/script), gray (altri).
- **Hook**: `utils.py:execute_mcp_tool_calls(gui=None)`, chiamato da `main.py:1631` e `script_engine.py:365` con `gui=self.gui`.

### Gestione Stato
- **Wake word guard**: `main.py:827` — `if wake and self.state == "listening"` previene comandi vocali durante AI/playback/recording.
- **TTS pause**: aggiunto `"playing"` a lista pause in `tts_engine.py:64` e `ScriptQueue._worker:181`.
- **Blacklist**: `set_state("listening")` prima di `return` (`main.py:1424`).
- **AI error**: `set_state("listening")` prima di spawnare TTS thread (`main.py:1611-1612`).
- **Crash recovery**: `set_state("listening")` prima di `continue` (`main.py:890`).
- **ScriptQueue queue check**: lock held per `len(_queue)` (`main.py:1492`).
- **Cancel buttons**: `cancel_current()` e `cancel_all()` chiamano `set_state("listening")`.
- **`_listen_once` finally**: `set_state("listening")` (`main.py:1165`).
- **Script finish con TTS attivo**: ripristina `"playing"` invece di `"listening"` se `tts.tts_playing` (`main.py:1493-1496`).
- **TTS fallback**: `_set_state(self._state_before_tts)` invece di `"listening"` hardcoded (`tts_engine.py:220`).

### GUI & Tema
- **BASE_STYLESHEET centralizzato**: `theme.py:13-83` — 70 linee CSS. Tutte 8 finestre secondarie importano da `theme.py`. ~250 linee duplicate rimosse.
- **Auto-fade/auto-pause**: `gui.py:609-612` — `_on_set_state` skippa cambio opacità quando fullscreen+idle.
- **Tool indicator**: vedi sezione MCP sopra.

### Varie
- **`execute_command` cross-platform**: `command_executor.py:335-350` — Win32 usa PowerShell+`CREATE_NO_WINDOW`, altrimenti `shell=True`+`DEVNULL`.
- **Debug log flush**: `main.py:730-733` — `_TeeOutput` chiama `flush()` su ogni `write()`.
- **Schedule pause**: `event_reminder.py:514-517` — skippa esecuzione durante `"playing"`/`"recording"`, riprova al prossimo ciclo.
- **Llama restart button**: `settings_editor.py:592-603` — `_update_llama_start_btn()` mostra Riavvia/Avvia. `_start_llama_server` riscritto: kill, riavvia con args non salvati.
- **Settings label wrap**: `settings_editor.py:230-233` — `(SPERIMENTALE)` su nuova linea, `setWordWrap(True)`.
- **`DESCRIPTION_FG` import fix**: `commands_editor.py:12` ri-aggiunto.

### Documentazione
- **README authorization notice**: aggiunto a tutti i 10 README (root + 9 lingue). Spiega verifica SHA-256 e auto-revoca su modifica.
- **Math VASScript**: template e docs aggiornati per `add/sub/mul/div`.
- **`ai_raw`**: template e docs aggiornati.

### Interni
- **Settings dict FLAT**: tutte le chiavi al top level. `_SECTION_DEFAULTS` auto-genera sezioni `[audio]`, `[google]`, `[debug]`, `[ai]`.
- **MCP server in-process**: `McpServerThread` come daemon thread, porta 9988. Config path `__file__`-assoluti. 23-24 tool.
- **Backup**: 9 backup da `vass_20260617_195415.zip` a `vass_20260619_232056.zip`.
- **Versione**: `0.4.17` → `0.5.6`.
- **Dipendenze**: `tiktoken>=0.5.0` aggiunto a `requirements.txt`.

---

## Branch

- **`rework`** creato per BASE_STYLESHEET, mergiato in `main`, eliminato.

## File Chiave

| File | Linee | Contenuto |
|------|-------|-----------|
| `src/main.py` | ~2370 | STOPWORDS, compress_heuristic, count_tokens, compress_summary, delayed, MCP_PROMPT, state guards |
| `src/script_engine.py` | ~1590 | ai_raw, weather cascade, geonames, math functions |
| `src/command_executor.py` | ~420 | delayed variants, execute_command cross-platform |
| `src/timer_manager.py` | ~160 | start/run with command_text |
| `src/tts_engine.py` | ~260 | newline splitting, dynamic timeout, state fixes |
| `src/gui.py` | ~700 | tool indicator, auto-fade fix |
| `src/theme.py` | ~90 | BASE_STYLESHEET |
| `src/event_reminder.py` | ~530 | schedule pause during playback |
| `src/settings_editor.py` | ~650 | compress_context, llama restart, label wrap |
| `src/utils.py` | ~380 | MCP tool indicator hook, CONTROL_RE, clean_for_tts |

## Riferimenti

- **Qwen3-8B-Q4_K_M**: function calling inconsistente (~1/10), richiede MCP_PROMPT direttivo.
- **Python 3.13**: Kokoro 0.7.16 richiede `--ignore-requires-python`.
- **cities500.txt**: 38 MB, gitignorato, lazy-download da `download.geonames.org`.
