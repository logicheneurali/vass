# VASS — Sprachassistenz-Software

## Was ist VASS

VASS ist ein Sprachassistent für Windows, macOS und Linux. Er reagiert auf Sprachbefehle, führt Skripte aus, verwaltet Ereignisse und Erinnerungen, liest und beantwortet E-Mails und interagiert über eine OpenAI-kompatible API mit einer lokalen oder entfernten KI. Außerdem hostet er einen MCP-Server, der der KI direkten Zugriff auf Dateien, Browser, Kalender, E-Mail, Nachrichten und Systemwerkzeuge gewährt.

**Standard-Weckwort:** „Erika" (konfigurierbar)

**Aktuelle Version:** 0.8.7

**Hauptfunktionen:**
- Spracherkennung über Whisper (faster-whisper) mit Silero VAD und adaptivem Rauschpegel
- Natürliche Sprachsynthese über Kokoro TTS mit einer mehrstufigen Fallback-Kette
- Lokale oder entfernte KI (llama.cpp, OpenAI, jeder kompatible Server) mit optionalem llama.cpp-Autostart
- VASScript-Skripting für Desktop-Automatisierung mit über 70 integrierten Funktionen
- Ereignis- und Zeitplanverwaltung mit Editor-GUI (Erinnerungen, automatisierte Abläufe)
- Mehrsprachiger Countdown-Timer (sprachgesteuert, 5 gleichzeitig)
- MCP-Server mit über 50 Werkzeugen für die KI-Orchestrierung (Browser, E-Mail, Nachrichten, Kalender, Orte, Dateien, System)
- Dauerhaftes Gedächtnis mit automatischer Klassifizierung, Zusammenfassung und Benutzerprofil-Injektion
- Integrierter E-Mail-Client: Gmail, IMAP, POP3 mit Warteschlange, Kontakten und KI-verfassten E-Mails
- Plugin-System: interne und externe Plugins über einen lokalen TCP-Socket
- Benachrichtigungszentrale mit Weiterleitung nach Ereignistyp
- Gesprächsverlauf-Viewer mit Aktionen pro Nachricht
- Unterstützung von 9 Sprachen
- Kontextüberlauf-Schutz (truncate oder KI-Zusammenfassung)
- Audio-Geräteauswahl (Eingang/Ausgang)
- Mehrturn-Tool-Aufrufe für komplexe KI-Aufgaben
- Wettersystem mit 3 Quellen und Geodatenbank für 200.000 Städte
- Zeitversetzte Sprachbefehle („in 5 Minuten herunterfahren")
- Echtzeit-Anzeige der MCP-Tool-Aktivität in der GUI
- Heuristische Kontextkomprimierung mit mehrsprachiger Stoppwort-Unterstützung
- Token-genaue Kontextzählung (tiktoken)
- Skript-Sandbox mit SHA-256-Autorisierung und Audit-Protokollierung
- Sicherheitstor für sensible Online-Werkzeuge (Zustimmung, Ratenlimit, Audit-Protokoll)
- Optionaler Autostart des Betriebssystems

---

## Voraussetzungen

- **Python 3.13** oder höher
- **KI-Server** (llama.cpp oder OpenAI-kompatibel) bereits auf dem System installiert und konfiguriert. VASS kann llama.cpp bei Bedarf automatisch starten, **installiert aber weder llama.cpp noch lädt es KI-Modelle herunter**: Sie müssen diese separat beschaffen.
- **Internetverbindung** (für TTS/STT-Modell-Downloads und entfernte KI)
- **NVIDIA-GPU empfohlen** für lokale KI (CPU möglich, aber langsam)
- **Funktionierendes Mikrofon**
- Windows 10+, macOS 12+ oder modernes Linux

---

## Installation

### Grafische Installation (empfohlen)

Laden Sie den Installer von der [Releases-Seite](https://github.com/logicheneurali/vass/releases) herunter und führen Sie ihn aus. Der Assistent installiert Python, VASS, llama.cpp und ein KI-Modell automatisch — keine manuelle Einrichtung erforderlich.

### Geführte Installation

Laden Sie das Projekt herunter oder klonen Sie es, wechseln Sie dann in den Ordner und führen Sie das Skript aus:

```bash
cd vass
python install.py
```

> **Hinweis:** Die geführte Installation richtet VASS ein, **installiert aber weder den KI-Server noch Modelle**.
> Sie müssen bereits einen OpenAI-kompatiblen Server verwenden (llama.cpp, Ollama, LM Studio, Groq, OpenAI usw.)
> oder llama.cpp in den VASS-Einstellungen konfigurieren (dann kann es automatisch gestartet werden).

**Hinweis:** Die geführte Installation ist noch experimentell und funktioniert möglicherweise nicht auf allen Systemen. Wenn Probleme auftreten, verwenden Sie das unten beschriebene manuelle Installationsverfahren.

Der Assistent führt Sie durch:
1. Sprachauswahl
2. Prüfung der Voraussetzungen (Python 3.13+, pip)
3. Zielordner
4. Parameterkonfiguration (KI-URL, Modell, Weckwort)
5. Dateikopie
6. Erstellung der Python- virtuellen Umgebung (.venv)
7. Installation der pip-Abhängigkeiten
8. Erstellung der Datei settings.ini
9. Erstellung des Starters

### Manuelle Installation

```bash
# Dateien in den gewünschten Ordner klonen oder kopieren
cd VASS

# Virtuelle Umgebung erstellen
python -m venv .venv

# Aktivieren (Windows)
.venv\Scripts\activate
# oder (macOS/Linux)
source .venv/bin/activate

# Abhängigkeiten installieren
pip install -r requirements.txt

# Chromium für Playwright installieren (Websuche)
playwright install chromium

# config/settings.ini erstellen (Kopie von config/settings.example.ini)
```

---

## Konfiguration

Alle Einstellungen befinden sich in `config/settings.ini` (die Vorlage ist `config/settings.example.ini`). Hier sind die wichtigsten:

| Abschnitt | Parameter | Beschreibung |
|---------|-----------|-------------|
| `[locale]` | `language` | Sprache (it/en/de/fr/es/pt/ja/ko/zh) |
| `[wakeword]` | `wakeword` | Weckwort (Standard: erika) |
| `[wakeword]` | `sensitivity` | Erkennungsempfindlichkeit des Weckworts |
| `[commands]` | `similarity` | Ähnlichkeitsschwelle für den Sprachbefehlsabgleich (Standard 0.6) |
| `[commands]` | `word_learning_enabled` | Neue gesprochene Wörter im Laufe der Zeit lernen (true/false) |
| `[ai]` | `url` | URL des OpenAI-kompatiblen KI-Servers |
| `[ai]` | `model` | Name des KI-Modells |
| `[ai]` | `system_message` | Persönlichkeit des Assistenten |
| `[ai]` | `api_key` | API-Schlüssel (bei Einstellung im System-Keyring gespeichert) |
| `[ai]` | `mcp_server_url` | URL des gebündelten MCP-Servers (Standard `http://localhost:9988`) |
| `[ai]` | `memory_tokens` | Maximale Gedächtnisgröße |
| `[ai]` | `context_length` | Max. Kontext-Tokens (0 = automatisch) |
| `[ai]` | `overflow_strategy` | Behandlung von Kontextüberlauf: `truncate` oder `summarize` |
| `[ai]` | `allow_ai_scripts` | Der KI erlauben, VASScript-Skripte auszuführen (true/false) |
| `[llamacpp]` | `llama_server_path` | Speicherort des llama.cpp-Servers |
| `[llamacpp]` | `llama_autostart` | llama.cpp mit VASS automatisch starten (true/false) |
| `[resources]` | `cpu_max`, `ram_max`, `gpu_max`, `vram_max` | Ressourcengrenzen, die KI-Operationen beschränken |
| `[events]` | `reminder_advance` | Sekunden vor einem Ereignis, in denen die Erinnerung ausgegeben wird (Standard 3600) |
| `[audio]` | `input_device`, `output_device` | Audio-Geräteauswahl (-1 = Systemstandard) |
| `[audio]` | `input_volume`, `output_volume` | Eingangs-/Ausgangslautstärke (0-1) |
| `[audio]` | `app_volume` | Hauptlautstärke für TTS (ersetzt das alte `[tts] volume`) |
| `[google]` | — | Google-Kalender / Gmail / Google-Home-Integration |
| `[startup]` | `app_autostart` | VASS beim Anmelden automatisch starten (true/false) |
| `[debug]` | `debug_enabled` | Ein ausführliches Protokoll nach `log/debug.log` schreiben (true/false) |

Einstellungen werden automatisch neu geladen, wenn sie geändert werden, während VASS läuft.

---

## Tägliche Verwendung

### Start

Doppelklicken Sie auf `vass.bat` (Windows) oder `vass.sh`/`vass.command` (macOS/Linux).

Oder vom Terminal aus:
```bash
cd VASS
.venv\Scripts\python vass.py    # Windows
.venv/bin/python vass.py         # macOS/Linux
```

> **Hinweis:** Beim ersten Start werden die Modelle für Spracherkennung (Whisper) und Sprachsynthese (Kokoro) automatisch von HuggingFace heruntergeladen. Der erste Start kann mehrere Minuten dauern (~2-4 GB Download). Dies geschieht nur einmal.

### Weckwort

Das Weckwort ist vom Benutzer **konfigurierbar** in der Datei `config/settings.ini` und kann jedes Wort oder jede kurze Phrase sein. Der Standard ist „**Erika**".

Wenn VASS das Weckwort erkennt, gibt es einen Piepton aus, um zu signalisieren, dass es bereit ist, den Befehl entgegenzunehmen. Sprechen Sie nach dem Piepton.

Beispiele:
- *„Erika"* (auf den Piepton warten), dann *„wie ist das Wetter?"*
- *„Erika"* (auf den Piepton warten), dann *„lies die neuesten Nachrichten"*
- *„Erika"* (auf den Piepton warten), dann *„was ist künstliche Intelligenz?"*
- *„Erika"* (auf den Piepton warten), dann *„übersetze ins Italienische guten Morgen zusammen"*
- *„Erika"* (auf den Piepton warten), dann *„Rezept Pasta Carbonara"*

### Modi: Chat und Transkription

VASS kann in zwei Modi betrieben werden, die über das Popup-Menü auswählbar sind (≡-Schaltfläche rechts neben der Hauptschaltfläche):

- **Chat** `[C]` — Die Anwendung erkennt Sprachbefehle und führt Aktionen aus (Skripte, Systembefehle) oder interagiert mit der KI. Die Antwort wird per TTS vorgelesen.
- **Transkription** `[T]` — Statt Befehle zu interpretieren, transkribiert VASS getreu, was der Benutzer nach dem Weckwort sagt (immer nach dem Piepton). Der Text wird dann in die aktive Anwendung eingefügt, wodurch VASS zu einem Textdiktatsystem wird.

Der aktuelle Modus wird auf der Hauptschaltfläche angezeigt: `[C]` für Chat, `[T]` für Transkription. Der zuletzt verwendete Modus wird beim Neustart wiederhergestellt.

### Gedächtnismodus

Über das GUI-Menü oder durch Klicken auf die Hauptschaltfläche:
- **Voll** — Die KI erhält die Gedächtniszusammenfassung und Ihr Benutzerprofil
- **Begrenzt** — Die KI erhält nur den jüngsten Verlauf
- **Keine** — Kein historischer Kontext

### Sprachbefehle

Befehle werden in `config/commands.ini` konfiguriert (Standard-INI-Format, `phrase = action`), auch über den GUI-Editor bearbeitbar (`python src/commands_editor.py`). Sprachspezifische Dateien `config/commands_{lang}.ini` werden zusätzlich zur Basisdatei geladen. Jede Zeile ist ein **Phrase = Aktion**-Paar: die Phrase ist das zu erkennende Muster (kann `{variables}` enthalten), die Aktion das, was ausgeführt wird.

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

#### So funktioniert der Abgleich

1. **Fuzzy-Erkennung**: Eine exakte Übereinstimmung ist nicht erforderlich. VASS vergleicht die gesprochene Phrase mit allen Mustern mithilfe eines Ähnlichkeitsalgorithmus (`difflib`). Das Muster mit der höchsten Punktzahl über der Schwelle (Standard `0.6`, konfigurierbar in `config/settings.ini` unter `[commands] similarity`) wird aktiviert.

2. **Variablen `{name}`**: erfassen die gesprochenen Wörter an dieser Position. Beispiel: *„suche Katzen im Internet"* erfasst `term = "Katzen im Internet"`.

3. **Maskierte Variablen `{escaped_name}`**: wie normale Variablen, aber der erfasste Text wird URL-kodiert (Leerzeichen werden zu `%20`). Nützlich für Websuchen.

4. **Zeitversetzte Befehle**: Ein `{duration}`-Suffix (z. B. *„in 5 Minuten herunterfahren"*) plant den Befehl ein, sodass er nach der angegebenen Zeit über das Timer-System ausgeführt wird.

5. **Wortlernen**: Wenn aktiviert, zeichnet VASS auf, wie Sie Wörter aussprechen, um die Erkennung im Laufe der Zeit zu verbessern.

6. **KI-Fallback**: Wenn kein Befehl die Ähnlichkeitsschwelle überschreitet, wird die Phrase zur natürlichen Antwort an die KI gesendet.

#### Komma-Alternativen (kartesisches Produkt)

Sie können mehrere Alternativen für jede Wortposition mithilfe von Kommas angeben. **Leerzeichen** trennen Wortpositionen, **Kommas** trennen Alternativen innerhalb einer Position. VASS generiert alle möglichen Kombinationen (kartesisches Produkt).

```ini
# Einzelne Position: Alternativen für die Präposition
click the,on text {text}
```
Erzeugt 2 Muster: `click the text {text}`, `click on text {text}`.

```ini
# Zwei Positionen: jede Position hat ihre eigenen Alternativen
aa,xx bb,cc {var}
```
Erzeugt 4 Muster: `aa bb {var}`, `aa cc {var}`, `xx bb {var}`, `xx cc {var}` (2x2 = 4).

```ini
# Gemischt: festes Wort + Alternativen
turn on,off {device}
```
Erzeugt 2 Muster: `turn on {device}`, `turn off {device}` (kein Leerzeichen zwischen `on` und `off` -> gleiche Position).

Die gesprochene Phrase wird mit allen generierten Mustern verglichen. Die beste Fuzzy-Übereinstimmung gewinnt.

#### Aktionstypen

| Präfix | Beispiel | Verhalten |
|--------|---------|----------|
| `script:` | `script:search` | Führt `scripts/search.vass` aus. Erfasste Variablen werden zu `$param1`, `$param2` usw. |
| `vasscript:` | `vasscript:events` | Wie `script:` (alternatives Präfix) |
| Befehl | `shutdown /s` | Wird direkt als Systembefehl ausgeführt |

#### Abschnittsnamen

Abschnittsnamen wie `[general]` und `[system]` sind nur organisatorische Kategorien — sie beeinflussen den Abgleich nicht. Der **Schlüssel** (die zu erkennende Phrase) ist das, worauf es ankommt.

### Erstellen von VASScript-Skripten

Öffnen Sie den Skript-Editor über das GUI-Menü oder führen Sie Folgendes aus:
```bash
python src/scripts_editor.py
```

Alle Skripte gehören in den Ordner `scripts/` mit der Erweiterung `.vass`.

**Autorisierung**: Vor der Ausführung eines neuen oder geänderten Skripts zeigt VASS ein Popup, das um Erlaubnis bittet. Skripte werden über SHA-256-Hash (im System-Keyring gespeichert) verifiziert: Wenn eine Skriptdatei nach der Autorisierung geändert wird, werden die Berechtigungen automatisch widerrufen, und das Popup erscheint bei der nächsten Ausführung erneut. Die Erlaubnis kann pro Funktion oder für das gesamte Skript erteilt werden. Dadurch wird sichergestellt, dass kein Skript ohne Ihre ausdrückliche Zustimmung auf Ihrem Rechner ausgeführt werden kann.

Siehe die Datei [VASCRIPT_REFERENCE.md](../Allowed_root/VASCRIPT_REFERENCE.md) für die vollständige Sprachreferenz.

### Ereignisse und Erinnerungen

Ereignisse werden über die Datei `Allowed_root/events.json` verwaltet. Eine Sprach-Erinnerung wird 1 Stunde im Voraus ausgegeben (konfigurierbar über `[events] reminder_advance`).

Zeitpläne (automatisierte Abläufe) befinden sich in `Allowed_root/schedules.json` und lösen die Ausführung von Befehlen mit TTS-Benachrichtigung aus. Zusätzliche Flags: `silent`, `run_on_startup`, `check_already_running`, `wait_for_completion`.

### Plugin-System

VASS stellt einen lokalen TCP-Server (`localhost:8765`) bereit, über den Plugins mit der App kommunizieren: TTS, Benachrichtigungen, KI-Abfragen, RSS-Einträge, Chat, deklarative UIs und mehr. **Interne Plugins** (mit VASS gebündelt) können nicht entfernt werden; **externe Plugins** können über die GUI (Menü Plugins) aktiviert, deaktiviert und entfernt werden.

Gebündelte interne Plugins: automatische Pause bei Rauschen, proaktiver Agent, Benutzerprofil, RSS-Reader, Weltereignisse, Telegram-Bot. Externe Plugins auf der Festplatte verfügbar: Bildgenerator, Nachrichten-Publisher, Zeitachsen-Viewer.

Siehe die Anleitung [PLUGIN_DEV_de.md](PLUGIN_DEV_de.md) für das vollständige Protokoll und die Erstellung eigener Plugins (auch verfügbar als `PLUGIN_DEV_{en,it,fr,es,pt,ja,ko,zh}.md`).

### E-Mail

Konfigurieren Sie ein oder mehrere Konten unter Einstellungen → E-Mail (Gmail über OAuth oder IMAP/POP3 mit einfachem SSL/TLS). Eingehende Nachrichten werden erkannt und gemeldet; die KI kann E-Mails suchen, lesen, beantworten, weiterleiten und senden — gesendete E-Mails landen jedoch immer in einer **Warteschlange**, die Sie über den Ausgang bestätigen und versenden müssen. Kontakte werden verschlüsselt gespeichert.

---

## GUI-Oberfläche

- **Hauptschaltfläche** — Klicken, um den Zustand zu ändern (hört zu/pausiert). Mausrad für Lautstärke. Ziehen, um das Fenster zu verschieben.
- **Lautstärkebalken** (grün, oben) — Zeigt die aktuelle TTS-Lautstärke
- **Mehrzustandsleiste** — Zeigt je nach Kontext Speichernutzung, Lautstärke oder Skript-/Aktivitätsfortschritt
- **Benachrichtigungszentrale** (Glocke) — Registerkarten pro Typ mit Nachrichtenaktionen und Alle-als-gelesen-markieren
- **Tool-Anzeige** — Echtzeit-Symbol, das das von der KI verwendete MCP-Tool anzeigt
- **Mikrofon-Schaltfläche** — Direkte Spracheingabe im Chat-Modus
- **Plugin-Menü** — Plugins, Plugin-Einstellungen und Plugin-UIs verwalten
- **Einstellungsdialog** — Vollständige Konfiguration über die GUI (Menü Einstellungen)
- **Auto-Ausblenden** — Das Fenster wird im Ruhezustand und im Vollbildmodus halbtransparent
- **Splash-Screen** — Ladefortschritt beim Start
- **Design** — Gemeinsames Design für die App und alle Editoren

### Tastenkürzel

| Taste | Aktion |
|-------|--------|
| `Ctrl+S` | Speichern (in Editoren) |
| Schaltflächenklick | Zustand ändern |
| Mausrad auf Schaltfläche | Lautstärke anpassen |
| Rechtsklick | Kontextmenü |
| Mittelklick auf Schaltfläche | Beenden |

---

## Fehlerbehebung

> **Wichtig:** Diese Anwendung hängt stark vom verwendeten KI-Modell ab. Ineffektive Modelle oder Modelle, die nicht für die MCP-Tool-Nutzung geeignet sind, können die Funktionalität beeinträchtigen.

### VASS startet nicht
- Python 3.13+ prüfen: `python --version`
- Sicherstellen, dass `.venv` existiert und die Abhängigkeiten enthält
- `log/debug.log` prüfen (`[debug] debug_enabled = true` aktivieren) und `log/crash.log`

### Mikrofon funktioniert nicht
- Prüfen, ob das Mikrofon angeschlossen und nicht von anderen Apps verwendet wird
- Systemberechtigungen für das Mikrofon prüfen
- Unter Windows: Einstellungen → Datenschutz → Mikrofon

### KI antwortet nicht
- Prüfen, ob der KI-Server unter `http://127.0.0.1:8080/v1` läuft
- `[ai] url` in `config/settings.ini` prüfen
- Bei Verwendung von llama.cpp prüfen, ob das Modell existiert und `[llamacpp] llama_server_path` korrekt ist
- `log/llamacpp.log` auf llama.cpp-Fehler prüfen

### OCR erkennt Bildschirmtext nicht
- Schriftgröße oder Textkontrast auf dem Bildschirm erhöhen
- EasyOCR funktioniert am besten mit großen Schriften und hohem Kontrast
- Die OCR-Sprache passt sich automatisch an die konfigurierte Sprache an

### Die KI kann ein Tool nicht verwenden
- Einige Online-Werkzeuge erfordern Ihre Zustimmung (Sicherheitstor) — prüfen Sie das InfoPanel auf ausstehende Anfragen
- Prüfen, ob der MCP-Server unter `http://localhost:9988` erreichbar ist (siehe `[ai] mcp_server_url`)
- `log/mcp_server.log` auf MCP-Fehler prüfen

---

## Wichtige Dateien

| Datei | Beschreibung |
|------|-------------|
| `config/settings.ini` | Hauptkonfiguration |
| `config/commands.ini` | Basis-Sprachbefehle (plus `commands_{lang}.ini`) |
| `config/notifications.ini` | Benachrichtigungsweiterleitung nach Ereignistyp |
| `scripts/*.vass` | Ihre VASScript-Skripte |
| `Allowed_root/events.json` | Ihre Ereignisse und Erinnerungen |
| `Allowed_root/schedules.json` | Automatisierte Abläufe |
| `Allowed_root/memory.json` | Gesprächsverlauf und Gedächtnis |
| `Allowed_root/private_profile.json` | Benutzerprofil, das in den KI-Kontext eingefügt wird |
| `plugins/` | Interne und externe Plugins |
| `log/debug.log` | Ausführliches Debug-Protokoll (wenn aktiviert) |
| `log/crash.log` | Absturzprotokoll |
| `log/faulthandler.log` | Ausgabe des Fehlerbehandlers |
| `log/llamacpp.log` | llama.cpp-Serverprotokoll |
