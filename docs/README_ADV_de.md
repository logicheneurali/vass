# VASS — Erweiterte Dokumentation

## Allgemeine Architektur

VASS ist eine modulare Anwendung, die aus mehreren unabhängigen Komponenten besteht, die über Dateiwarteschlangen, Qt-Signale und direkte Aufrufe kommunizieren.

```
┌─────────────────────────────────────────────────┐
│                    vass.py                       │
│              Haupt-Orchestrator                  │
│  - Komponenteninitialisierung                    │
│  - Hör-/Schreibschleife                         │
│  - KI-Fallback-Verwaltung                       │
│  - Skriptausführung                             │
│  - Dateiwarteschlangen-Watchdog                 │
└──────┬──────┬──────┬──────┬──────┬──────────────┘
       │      │      │      │      │
       ▼      ▼      ▼      ▼      ▼
  ┌────────┐┌─────┐┌─────┐┌────┐┌──────────┐
  │  gui.py││TTS  ││STT  ││Ere ││mcp_server│
  │  PySide││Eng. ││Whisp││Erin││  15 Tool │
  └────────┘└─────┘└─────┘└────┘└──────────┘
```

### Kernkomponenten

| Komponente | Datei | Verantwortung |
|-----------|------|---------------|
| Orchestrator | `vass.py` (1313 Zeilen) | Initialisierung, Hauptschleife, KI, Skripte, Speicher |
| GUI | `gui.py` (832 Zeilen) | PySide6-Fenster, Balken, Fade, Unterfenster |
| TTS | `tts_engine.py` (138 Zeilen) | Kokoro TTS, Audiowiedergabe, Lautstärke |
| STT | `voice_recognition.py` (133 Zeilen) | faster-whisper, Wake-Wort-Erkennung |
| Interpreter | `script_engine.py` (761 Zeilen) | VASScript-Parser, Evaluator, 26 Funktionen |
| Ereignisse | `event_reminder.py` (280 Zeilen) | Ereignis-/Zeitplanüberwachung, TTS-Benachrichtigungen |
| Befehle | `command_executor.py` (184 Zeilen) | Fuzzy-Pattern-Matching, Variablenextraktion |
| MCP-Server | `mcp_server/` | FastMCP-Server, 15 Tools, IP-basierte ACL |
| OCR | `script_engine.py:_preprocess_screen` | EasyOCR mit Vorverarbeitung |
| Inaktivität | `idle_tracker.py` (67 Zeilen) | Plattformübergreifende Inaktivitätserkennung |
| Ressourcen | `resource_monitor.py` (52 Zeilen) | CPU/RAM/GPU/VRAM-Prüfung vor KI-Anfragen |
| Protokoll | `log_utils.py` (13 Zeilen) | Protokolldatei-Rotation |

---

## Audio-Pipeline

```
Mikrofon ──► sounddevice (Callback) ──► Audio-Warteschlange ──► Whisper (Transkription)
                                                                   │
                    ┌──────────────────────────────────────────────┤
                    ▼                                              ▼
         "Erika"-Erkennung?                              Vollständige Transkription
                    │                                              │
                    ▼                                              ▼
               Ton (bereit für Befehl)                            Match commands.ini?
                    │                                  │            │
                    ▼                                  ▼            ▼
             Warte auf Befehl                       Befehl     Kein Treffer
                    │                              gefunden
                    ▼                                  │            │
             Transkription                              ▼            ▼
                    │                          Aktion ausführen  KI-Fallback
                    ▼
            Kokoro TTS ──► Lautsprecher
```

### Audio-Komponentendetail

- **Eingabe**: `sounddevice.InputStream` mit Callback bei 16000 Hz Mono
- **VAD**: webrtcvad zum Filtern von Stille
- **Wake-Wort**: Whisper tiny-Modell, sucht nach "erika" in der Transkription
- **Transkription**: Whisper medium-Modell (konfigurierbar) nach Wake-Wort-Bestätigung
- **TTS**: Kokoro `KPipeline(lang_code='i')`, Stimme `if_sara`, erzeugt WAV über UUID-Dateiname
- **Wiedergabe**: `sounddevice.play()` mit `_tts_done`-Ereignis zur Synchronisation

---

## VASScript — Skriptsprache

VASScript ist eine minimalistische Skriptsprache für die Desktop-Automatisierung. Zeilenweise Ausführung, keine arithmetischen Operatoren, alles ist ein String.

### Verfügbare Funktionen (26 insgesamt)

#### KI und TTS
- `ai(prompt)` — Fragt die KI ab, gibt Text zurück
- `say(text, geschwindigkeit?)` — Sprachsynthese (Geschwindigkeit: 0.5-1.5)
- `listen(prompt?)` — Nimmt Sprache auf, gibt Transkription zurück

#### System
- `run(befehl)` — Führt PowerShell aus, gibt Ausgabe zurück
- `wait(sekunden)` — Pausiert die Ausführung
- `exit()` — Beendet das Skript
- `getdatetime()` — Aktuelles Datum/Uhrzeit "YYYY-MM-DD HH:MM"

#### Bildschirm (OCR)
- `screen_search(suchbegriff)` — Sucht Text auf dem Bildschirm, setzt `$_sx`, `$_sy`, `$_sw`, `$_sh`
- `screen_click(x?, y?)` — Klickt an Koordinaten
- `screen_highlight(x, y, b?, h?, dauer?)` — Hebt Bereich hervor

#### Fenster und Tastatur
- `setActiveWindow(name)` — Aktiviert Fenster nach Prozess/Titel
- `sendText(text)` — Tippt Text mit menschenähnlicher Verzögerung

#### Ereignisse
- `addevent(datum, uhrzeit, dauer, beschreibung, recur?)` — Fügt Ereignis hinzu
- `listevents(bis_datum)` — Listet Ereignisse auf (JSON)
- `removeevent(name)` — Entfernt Ereignis (Fuzzy-Match)
- `prettyevents(json)` — Formatiert Ereignisse in lesbaren Text

#### Speicher und Zwischenablage
- `readinfo(id)` — Liest Info-Datei
- `writeinfo(text)` — Schreibt Info-Datei, gibt ID zurück
- `clipboardget()` — Liest Zwischenablage
- `clipboardset(text)` — Schreibt Zwischenablage

#### Bedingungen
- `ifcontains(var, teilstring, wenn_wahr, wenn_falsch?)` — Enthält Teilstring
- `ifempty(var, wenn_leer, wenn_voll?)` — Prüft ob leer

#### Hilfsfunktionen
- `trim(text)` — Entfernt Leerzeichen
- `len(text)` — Stringlänge
- `contains(text, teilstring)` — Enthält? ("True"/"False")
- `equals(a, b)` — Gleich? ("True"/"False")

### Variablen

```vascript
$name = "Fabio"            # Zuweisung
$alter = "54"              # Alles ist String
$ergebnis = ai("Hallo")    # Funktionsergebnis
say("Hallo {$name}!")      # Interpolation in Strings
say("Du bist {$alter}")    # Auch mit Variablen
```

**Hinweis:** VASScript unterstützt KEINE Verkettung mit `+`. Verwenden Sie `{$var}` in Strings.

### screen_search Globale Variablen

`screen_search()` setzt diese globalen Variablen für den ersten Treffer:
- `$_sx`, `$_sy` — Mittelpunktkoordinaten
- `$_sw`, `$_sh` — Breite und Höhe

---

## MCP-Server — 15 Tools

Der MCP-Server stellt 15 Tools bereit, die für die KI unter `http://localhost:9988` zugänglich sind.

### Dateisystem
- `read_file(pfad)` — Liest Datei innerhalb von Allowed_root
- `write_file(pfad, inhalt)` — Schreibt Datei innerhalb von Allowed_root

### Web
- `browse(url)` — Lädt Seite herunter (statisch, httpx+BeautifulSoup)
- `websearch(suchbegriff)` — Sucht auf DuckDuckGo via Playwright
- `webfetch(url)` — Lädt JS-gerenderte Seite via Playwright

### Berechnung und Zeit
- `calculate(ausdruck)` — Wertet mathematische Ausdrücke aus (AST, sicher)
- `current_time()` — Aktuelles Datum/Uhrzeit
- `disk_space()` — Verfügbarer Speicherplatz

### Ausführung
- `execute(befehl)` — Führt Befehle aus (Whitelist)
- `script(skriptname)` — Führt VASScript-Datei aus
- `interact(code)` — Führt Inline-VASScript aus

### Speicher und Zwischenablage
- `readinfo(id)` — Liest Info-Datei
- `writeinfo(text)` — Schreibt Info-Datei
- `clipboardget()` — Liest Zwischenablage
- `clipboardset(text)` — Schreibt Zwischenablage

### Authentifizierung

IP-basierte ACL über `mcp_server/config/tools.yaml`. Jedes Tool hat Whitelist/Blacklist. Standardmäßig verweigert.

### Skript → VASS Kommunikation

Die Tools `script` und `interact` verwenden dateibasierte IPC:
1. Anfrage in `scripts/exec_queue.json` schreiben
2. VASS liest die Warteschlange (1s Polling)
3. Führt das Skript aus
4. Schreibt Ergebnis in `scripts/exec_result.json`
5. Der MCP-Client liest das Ergebnis

---

## Speichersystem

### Struktur

```
Allowed_root/
  memory.json          # Index: {"history": [id1, id2], "summary_id": "id3"}
  memory/
    1780394454383.json  # Einzeleintrag: {"info": "JSON-String"}
    1780427888604.json
    archive/
      2026-06/          # Monatliches Archiv
```

### Ablauf

1. Jeder KI-Austausch (Benutzer+Assistent) wird als JSON-Datei in `memory/` gespeichert
2. `memory.json` verfolgt die letzten 20 IDs
3. Nach 5 Speicherungen gehen nicht referenzierte Dateien nach `archive/{YYYY-MM}/`
4. Archive älter als 6 Monate werden gelöscht
5. Wenn der Speicher `memory_tokens * 4` Byte überschreitet, wird die KI-Komprimierung ausgelöst:
   - Alte Nachrichten werden von der KI zusammengefasst
   - Die Zusammenfassung wird als `summary_id`-Eintrag gespeichert
   - Originaldateien werden archiviert

---

## Ereignisse und Zeitpläne

### events.json
```json
{
  "events": [{
    "date": "2026-06-15",
    "time": "14:30",
    "duration": 60,
    "description": "Team-Meeting",
    "recur": "7d",
    "notify": "2026-06-15 13:30:00"
  }]
}
```
- `recur`: "1d"=täglich, "7d"=wöchentlich, "1m"=monatlich, "2h"=alle 2 Stunden
- `notify`: Zeitstempel, wann die Benachrichtigung gesendet wurde

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
- Wie Ereignisse, lösen aber Befehlsausführung aus
- TTS-Benachrichtigung zu Beginn und am Ende
- Befehlsvalidierung gegen sicheres Muster (`.exe`, `.bat`, `.ps1`, `.py`, `.cmd`, `.vbs`)

---

## Abhängigkeiten

### Kern (13)
| Paket | Verwendung |
|-----------|-----|
| `sounddevice` | Audio-Ein-/Ausgabe |
| `numpy` | Arrays für Audio und Bilder |
| `faster-whisper` | STT-Spracherkennung |
| `webrtcvad` | Sprachaktivitätserkennung |
| `kokoro` | TTS-Sprachsynthese |
| `torch` | Deep Learning (Kokoro, Whisper, EasyOCR) |
| `soundfile` | WAV-Dateischreibung |
| `openai` | OpenAI-kompatibler API-Client |
| `mcp[cli]` | FastMCP MCP-Server |
| `pynput` | Maus-/Tastatursteuerung |
| `PySide6` | Qt6 GUI |
| `keyring` | Windows-Anmeldeinformationsverwaltung |
| `httpx` | HTTP-Client für KI und Web |

### Web und OCR (6)
| Paket | Verwendung |
|-----------|-----|
| `beautifulsoup4` | HTML-Parsing statischer Seiten |
| `lxml` | Schnelle XML/HTML-Engine |
| `playwright` | Headless-Browser für JS-Seiten |
| `mss` | Schnelle Screenshots |
| `easyocr` | Bildschirmtext-Erkennung |
| `pillow` | Bildverarbeitung |

### Hilfsprogramme (5)
| Paket | Verwendung |
|-----------|-----|
| `pyyaml` | MCP-Server-Konfiguration |
| `structlog` | Strukturiertes MCP-Logging |
| `uvicorn` | MCP-HTTP-Server |
| `psutil` | Ressourcenüberwachung |
| `misaki` | Kokoro-Tokenisierung |
| `dateparser` | Datumsanalyse in natürlicher Sprache |

---

## Interna

### Threading-Modell

- **Haupt-Thread**: Qt GUI (Ereignisschleife)
- **Audio-Thread**: sounddevice-Callback
- **VASS-Thread**: Hör-/Transkriptionsschleife
- **Watchdog-Threads**: `_watch_commands_file`, `_watch_settings_file`, `_watch_script_queue`
- **Flüchtig**: TTS-Wiedergabe, KI-Fallback, Skriptausführung

### Sperrmechanismen

- `_trim_lock` — Schützt Speicheroperationen
- `_script_engine_lock` — Schützt die aktive Engine
- `_tts_done` (Event) — Synchronisiert TTS-Abschluss
- `state_lock` — Schützt Anwendungszustand

### Dateibasierte IPC

**exec_queue.json / exec_result.json**:
- MCP-Server schreibt Skriptausführungsanfragen
- VASS pollt (1s), führt aus, schreibt Ergebnis
- Timeout: 60s für Dateiskripte, 120s für Inline

### Datei-Watchdogs

VASS überwacht Änderungen an:
- `settings.ini` — automatisches Neuladen
- `commands.ini` — automatisches Neuladen
- `events.json` / `schedule.json` — Neuberechnung des nächsten Alarms

### Anmeldeinformationsspeicher

- Windows: Windows-Anmeldeinformationsverwaltung via `keyring`
- macOS: Schlüsselbund
- Linux: D-Bus Secret Service oder Datei
- Verwendet für: KI-API-Schlüssel, VASScript-Skriptberechtigungen (pro Funktion)

### i18n-System

- `locales/*.json`: 9 Sprachen, jeweils 215+ Schlüssel
- Datei `i18n.py`: `t(key, lang)`-Lookup
- Referenz: `it.json`
- Alle Dateien automatisch ausgerichtet

### Protokollrotation

- `debug.log`: max 500 KB → `.1`, `.2`
- `mcp_server/LOG/`: max 1 MB → `.1`, `.2`
- Hilfsprogramm: `log_utils.py`

---

## Erweiterte Konfiguration

### [ai]
| Parameter | Standard | Beschreibung |
|-----------|---------|-------------|
| `url` | `http://127.0.0.1:8080/v1` | API-Endpunkt |
| `model` | `Qwen3-8B-Q4_K_M` | Modellname |
| `api_key` | (leer) | API-Schlüssel (leer für lokal) |
| `system_message` | (langer Text) | System-Prompt |
| `mcp_server_url` | `http://localhost:9988` | MCP-Server-URL |
| `memory_tokens` | `4000` | Speichergrenze in Token×4 Byte |
| `blacklist` | `Amara.org,QTTS` | Kommagetrennte gesperrte Wörter |

### [tts]
| Parameter | Standard | Beschreibung |
|-----------|---------|-------------|
| `tts_engine` | `kokoro` | TTS-Engine |
| `volume` | `0.50` | Lautstärke 0-1 |

### [wakeword]
| Parameter | Standard | Beschreibung |
|-----------|---------|-------------|
| `wakeword` | `erika` | Wake-Wort |
| `sensitivity` | `0.01` | Empfindlichkeit 0-1 |

### [resources]
| Parameter | Standard | Beschreibung |
|-----------|---------|-------------|
| `cpu_max` | `75` | CPU-Schwellenwert % |
| `ram_max` | `99` | RAM-Schwellenwert % |
| `gpu_max` | `75` | GPU-Schwellenwert % |
| `vram_max` | `99` | VRAM-Schwellenwert % |
| `resource_timeout` | `30` | Warte-Timeout Sekunden |

### [llamacpp]
| Parameter | Beschreibung |
|-----------|-------------|
| `llama_server_path` | Pfad zur llama.cpp-Ausführbaren |
| `llama_server_arguments` | Befehlszeilenargumente |

### [events]
| Parameter | Standard | Beschreibung |
|-----------|---------|-------------|
| `reminder_advance` | `3600` | Erinnerungsvorlauf in Sekunden (1 Stunde) |

### [gui]
| Parameter | Standard | Beschreibung |
|-----------|---------|-------------|
| `x`, `y` | auto | Fensterposition |
| `width`, `height` | `200`, `32` | Fenstergröße |
| `font_family` | `Segoe UI` | GUI-Schriftart |
| `font_size` | `10` | Schriftgröße |
