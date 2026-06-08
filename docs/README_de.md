# VASS — Intelligenter Sprachassistent

## Was ist VASS

VASS ist ein Sprachassistent für Windows, macOS und Linux. Er reagiert auf Sprachbefehle, führt Skripte aus, verwaltet Ereignisse und Erinnerungen und interagiert mit einer lokalen oder entfernten KI über eine OpenAI-kompatible API.

**Standard-Wake-Wort:** "Erika"

**Hauptfunktionen:**
- Spracherkennung via Whisper (faster-whisper)
- Natürliche Sprachsynthese via Kokoro TTS
- Lokale oder entfernte KI (llama.cpp, OpenAI, jeder kompatible Server)
- VASScript-Scripting für Desktop-Automatisierung
- Ereignis- und Erinnerungsverwaltung
- MCP-Server mit 15 Tools für KI-Orchestrierung
- Gesprächsverlauf
- Unterstützung für 9 Sprachen (Italienisch, Englisch, Deutsch, Französisch, Spanisch, Portugiesisch, Japanisch, Koreanisch, Chinesisch)

---

## Voraussetzungen

- **Python 3.13** oder höher
- **KI-Server** (llama.cpp oder OpenAI-kompatibel) bereits auf dem System installiert und konfiguriert. VASS kann llama.cpp automatisch starten, falls konfiguriert, **installiert llama.cpp jedoch NICHT und lädt keine KI-Modelle herunter**: Sie müssen diese separat beziehen.
- **Internetverbindung** (für Modell-Downloads und entfernte KI)
- **NVIDIA-GPU empfohlen** für lokale KI (CPU möglich, aber langsam)
- **Funktionierendes Mikrofon**
- Windows 10+, macOS 12+ oder modernes Linux

---

## Installation

### Geführte Installation

Projekt herunterladen oder klonen, dann den Ordner betreten und das Skript ausführen:

```bash
cd vass
python install.py
```

> **Hinweis:** die geführte Installation richtet VASS ein, installiert aber **NICHT den KI-Server oder die Modelle**.
> Sie müssen bereits einen OpenAI-kompatiblen Server betreiben (llama.cpp, Ollama, LM Studio, Groq, OpenAI, etc.)
> oder llama.cpp in den VASS-Einstellungen konfigurieren (der ihn automatisch starten kann).

**Hinweis:** Die gefuhrte Installation ist noch experimentell und funktioniert moglicherweise nicht auf allen Systemen. Bei Problemen verwenden Sie die manuelle Installation unten.

Der Assistent führt Sie durch:
1. Sprachauswahl
2. Prüfung der Voraussetzungen (Python 3.13+, pip)
3. Zielordner
4. Parameterkonfiguration (KI-URL, Modell, Wake-Wort)
5. Dateikopie
6. Erstellung einer virtuellen Python-Umgebung (.venv)
7. Installation der pip-Abhängigkeiten
8. Erstellung der settings.ini-Datei
9. Erstellung des Startprogramms

### Manuelle Installation

```bash
# Klonen oder kopieren Sie die Dateien in den gewünschten Ordner
cd VASS

# Virtuelle Umgebung erstellen
python -m venv .venv

# Aktivieren (Windows)
.venv\Scripts\activate
# oder (macOS/Linux)
source .venv/bin/activate

# Abhängigkeiten installieren
pip install -r requirements.txt

# Chromium für Playwright installieren (Websuchen)
playwright install chromium

# settings.ini erstellen (von Beispiel-settings.ini kopieren)
```

---

## Konfiguration

Die Datei `settings.ini` enthält alle Einstellungen. Hier die wichtigsten:

| Abschnitt | Parameter | Beschreibung |
|---------|-----------|-------------|
| `[locale]` | `language` | Sprache (it/en/de/fr/es/pt/ja/ko/zh) |
| `[ai]` | `url` | URL des OpenAI-kompatiblen KI-Servers |
| `[ai]` | `model` | Name des KI-Modells |
| `[ai]` | `system_message` | Persönlichkeit des Assistenten |
| `[ai]` | `memory_tokens` | Maximale Speichergröße |
| `[wakeword]` | `wakeword` | Wake-Wort (Standard: erika) |
| `[wakeword]` | `sensitivity` | Erkennungsempfindlichkeit (0-1) |
| `[tts]` | `volume` | TTS-Lautstärke (0-1) |

Einstellungen werden automatisch neu geladen, wenn sie geändert werden, während VASS läuft.

---

## Tägliche Nutzung

### Start

Doppelklick auf `vass.bat` (Windows) oder `vass.sh`/`vass.command` (macOS/Linux).

Oder vom Terminal aus:
```bash
cd VASS
.venv\Scripts\python vass.py    # Windows
.venv/bin/python vass.py         # macOS/Linux
```

### Wake-Wort

Das Wake-Wort ist vom Benutzer in der Datei `settings.ini` **konfigurierbar** und kann ein beliebiges Wort oder eine kurze Phrase sein. Standardmäßig ist es "**Erika**".

Wenn VASS das Wake-Wort erkennt, gibt es einen Signalton aus, der anzeigt, dass es bereit ist, den Befehl zu empfangen. Sprechen Sie nach dem Signalton.

Beispiele:
- *"Erika"* (auf Signalton warten), dann *"wie ist das wetter?"*
- *"Erika"* (auf Signalton warten), dann *"lies die nachrichten"*
- *"Erika"* (auf Signalton warten), dann *"was ist künstliche intelligenz?"*
- *"Erika"* (auf Signalton warten), dann *"übersetze in englisch guten morgen an alle"*
- *"Erika"* (auf Signalton warten), dann *"rezept spaghetti carbonara"*

### Modi: Chat und Transkription

VASS kann in zwei Modi betrieben werden, die über das Popup-Menü (≡-Taste rechts neben der Haupttaste) ausgewählt werden können:

- **Chat** `[C]` — Die Anwendung erkennt Sprachbefehle und führt Aktionen aus (Skripte, Systembefehle) oder interagiert mit der KI. Die Antwort wird per TTS vorgelesen.
- **Transkription** `[T]` — Anstatt Befehle zu interpretieren, transkribiert VASS getreu, was der Benutzer nach dem Wake-Wort sagt (immer nach dem Signalton). Der Text wird dann in die aktive Anwendung eingefügt, wodurch VASS zu einem Textdiktiersystem wird.

Der aktuelle Modus wird auf der Hauptschaltfläche angezeigt: `[C]` für Chat, `[T]` für Transkription. Der zuletzt verwendete Modus wird beim Neustart wiederhergestellt.

### Speichermodus

Über das GUI-Menü oder durch Klicken auf die Hauptschaltfläche:
- **Full** — Die KI erhält die Speicherzusammenfassung
- **Limited** — Die KI erhält nur den kürzlichen Verlauf
- **None** — Kein historischer Kontext

### Sprachbefehle

Befehle werden in `commands.ini` (Standard-INI-Format) konfiguriert, auch bearbeitbar über den GUI-Editor (`python commands_editor.py`). Jede Zeile ist ein **Satz = Aktion**-Paar: der Satz ist das zu erkennende Muster (kann `{Variablen}` enthalten), die Aktion ist das, was ausgeführt werden soll.

```ini
[general]
suche nach {begriff} = script:suche
öffne {programm} = start {programm}
online suchen nach {escaped_terms} = start firefox "https://duckduckgo.com?q={escaped_terms}"
wie spät ist es = script:uhrzeit

[system]
system herunterfahren = shutdown /s /t 60
bildschirm sperren = rundll32.exe user32.dll,LockWorkStation
```

#### Wie das Matching funktioniert

1. **Fuzzy-Erkennung**: eine exakte Übereinstimmung ist nicht erforderlich. VASS vergleicht den gesprochenen Satz mit allen Mustern mithilfe eines Ähnlichkeitsalgorithmus (`difflib`). Das Muster mit der höchsten Punktzahl über dem Schwellenwert (Standard `0.75`, konfigurierbar in `settings.ini`) wird aktiviert.

2. **Variablen `{name}`**: erfassen die gesprochenen Wörter an dieser Position. Beispiel: Wenn man *"suche katzen im internet"* sagt, erfasst das System `begriff = "katzen im internet"`.

3. **Escaped-Variablen `{escaped_name}`**: wie normale Variablen, aber der erfasste Text wird URL-kodiert (Leerzeichen werden zu `%20`). Nützlich für Websuchen.

4. **KI-Fallback**: Wenn kein Befehl den Ähnlichkeitsschwellenwert überschreitet, wird der Satz zur natürlichen Sprachbeantwortung an die KI gesendet.

#### Aktionstypen

| Präfix | Beispiel | Verhalten |
|--------|----------|-----------|
| `script:` | `script:suche` | Führt `scripts/suche.vass` aus. Erfasste Variablen werden zu `$param1`, `$param2`, usw. |
| `vasscript:` | `vasscript:ereignisse` | Wie `script:` (alternativer Präfix) |
| URL | `https://...` | Im Standardbrowser geöffnet |
| Befehl | `shutdown /s` | Direkt als Systembefehl ausgeführt |

#### Namen der Sektionen

Sektionsnamen wie `[general]` und `[system]` sind nur organisatorische Kategorien — sie beeinflussen das Matching nicht. Entscheidend ist der **Schlüssel** (der zu erkennende Satz).

### VASScript-Skripte erstellen

Öffnen Sie den Skript-Editor aus dem GUI-Menü oder führen Sie aus:
```bash
python scripts_editor.py
```

Alle Skripte gehören in den Ordner `scripts/` mit der Erweiterung `.vass`.

Siehe die Datei `VASCRIPT_REFERENCE.md` für die vollständige Sprachreferenz.

### Ereignisse und Erinnerungen

Ereignisse werden über die Datei `events.json` verwaltet. Eine Spracherinnerung wird 1 Stunde im Voraus ausgegeben (konfigurierbar).

Zeitpläne (automatisierte Abläufe) befinden sich in `schedule.json` und lösen die Befehlsausführung mit TTS-Benachrichtigung aus.

---

## GUI-Oberfläche

- **Hauptschaltfläche** — Klicken zum Ändern des Status (listening/paused). Mausrad für Lautstärke. Ziehen zum Verschieben des Fensters.
- **Lautstärkebalken** (grün, oben) — Zeigt die aktuelle TTS-Lautstärke an
- **Mehrzustandsbalken** — Zeigt Speichernutzung, Lautstärke oder Skriptfortschritt je nach Kontext
- **Auto-Fade** — Das Fenster wird halbtransparent, wenn Sie inaktiv und im Vollbildmodus sind

### Tastenkombinationen

| Taste | Aktion |
|-------|--------|
| `Strg+S` | Speichern (in Editoren) |
| Schaltflächenklick | Status ändern |
| Mausrad auf Schaltfläche | Lautstärke anpassen |
| Rechtsklick auf ≡-Taste | Popup-Menü |
| "Lesen"-Taste in Skripten | Liest das Skript mit TTS vor |

---

## Fehlerbehebung

### VASS startet nicht
- Python 3.13+ prüfen: `python --version`
- Prüfen, ob `.venv` existiert und Abhängigkeiten enthält
- `debug.log` auf Fehler prüfen

### Mikrofon funktioniert nicht
- Prüfen, ob das Mikrofon angeschlossen und nicht von anderen Apps verwendet wird
- Systemberechtigungen für das Mikrofon prüfen
- Unter Windows: Einstellungen → Datenschutz → Mikrofon

### KI antwortet nicht
- Prüfen, ob der KI-Server unter `http://127.0.0.1:8080/v1` läuft
- `[ai] url` in `settings.ini` prüfen
- Bei Verwendung von llama.cpp prüfen, ob das Modell im Ordner `models/` existiert

### OCR erkennt keinen Text auf dem Bildschirm
- Schriftgröße oder Textkontrast auf dem Bildschirm erhöhen
- EasyOCR funktioniert am besten mit großen Schriften und hohem Kontrast
- Die OCR-Sprache passt sich automatisch an das konfigurierte Gebietsschema an

---

## Wichtige Dateien

| Datei | Beschreibung |
|------|-------------|
| `settings.ini` | Hauptkonfiguration |
| `commands.ini` | Benutzerdefinierte Sprachbefehle |
| `scripts/*.vass` | Ihre VASScript-Skripte |
| `events.json` | Ihre Ereignisse und Erinnerungen |
| `schedule.json` | Automatisierte Abläufe |
| `memory.json` | Gesprächsverlauf |
| `debug.log` | Debug-Protokoll |
| `vass.log` | Anwendungsprotokoll |
