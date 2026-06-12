# VASS — Software assistente vocale

## Cos'è VASS

VASS è un assistente vocale per Windows, macOS e Linux. Risponde a comandi vocali, esegue script, gestisce eventi e promemoria, e interagisce con un'AI locale o remota via API OpenAI-compatibile.

**Wake word predefinita:** "Erika"

**Caratteristiche principali:**
- Riconoscimento vocale via Whisper (faster-whisper) con noise floor adattivo
- Sintesi vocale naturale via Kokoro TTS con catena di fallback a 4 livelli
- AI locale o remota (llama.cpp, OpenAI, qualsiasi server compatibile)
- Scripting VASScript per automazione desktop con 25+ funzioni integrate
- Gestione eventi e operazioni pianificate con editor GUI
- Timer multilingua a comando vocale (5 simultanei)
- Server MCP con 21 tool per orchestrazione AI
- Memoria permanente con classificazione automatica e riassunto
- Visualizzatore cronologia conversazioni con azioni per messaggio
- Supporto 9 lingue
- Protezione overflow contesto (troncamento o riassunto AI)
- Selezione dispositivo audio (input/output)
- Tool calling multi-turn per task AI complessi


---

## Requisiti

- **Python 3.13** o superiore
- **Server AI** (llama.cpp o OpenAI-compatibile) già installato e configurato sul sistema. VASS può avviare automaticamente llama.cpp se configurato, ma **non installa llama.cpp né scarica i modelli AI**: devi procurarteli separatamente.
- **Connessione internet** (per download modelli TTS/STT e AI remota)
- **GPU NVIDIA consigliata** per AI locale (CPU possibile ma lenta)
- **Microfono** funzionante
- Windows 10+, macOS 12+, o Linux moderno

---

## Installazione

### Installazione guidata

Scarica o clona il progetto, poi entra nella cartella ed esegui lo script:

```bash
cd vass
python install.py
```

> **Nota:** l'installazione guidata configura VASS ma **NON installa il server AI né i modelli**.
> Devi avere un server OpenAI-compatibile già attivo (llama.cpp, Ollama, LM Studio, Groq, OpenAI, ecc.)
> oppure configurare llama.cpp nelle impostazioni di VASS (che può avviarlo automaticamente).

**Nota:** la procedura di installazione guidata e ancora sperimentale e potrebbe non funzionare su tutti i sistemi. In caso di problemi, utilizza la procedura di installazione manuale qui sotto.

Il wizard ti guiderà attraverso:
1. Scelta della lingua
2. Verifica dei prerequisiti (Python 3.13+, pip)
3. Cartella di destinazione
4. Configurazione parametri (URL AI, modello, wake word)
5. Copia dei file
6. Creazione ambiente virtuale Python (.venv)
7. Installazione dipendenze pip
8. Creazione file settings.ini
9. Creazione lanciatore

### Installazione manuale

```bash
# Clona o copia i file nella cartella desiderata
cd VASS

# Crea ambiente virtuale
python -m venv .venv

# Attiva (Windows)
.venv\Scripts\activate
# oppure (macOS/Linux)
source .venv/bin/activate

# Installa dipendenze
pip install -r requirements.txt

# Installa Chromium per Playwright (ricerche web)
playwright install chromium

# Crea settings.ini (copia da settings.ini di esempio)
```

---

## Configurazione

Il file `settings.ini` contiene tutte le impostazioni. Ecco le più importanti:

| Sezione | Parametro | Descrizione |
|---------|-----------|-------------|
| `[locale]` | `language` | Lingua (it/en/de/fr/es/pt/ja/ko/zh) |
| `[ai]` | `url` | URL server AI OpenAI-compatibile |
| `[ai]` | `model` | Nome del modello AI |
| `[ai]` | `system_message` | Personalità dell'assistente |
| `[ai]` | `memory_tokens` | Dimensione massima memoria |
| `[wakeword]` | `wakeword` | Parola di attivazione (default: erika) |
| `[wakeword]` | `sensitivity` | Sensibilità rilevamento (0-1) |
| `[tts]` | `volume` | Volume TTS (0-1) |

Le impostazioni vengono ricaricate automaticamente se modificate mentre VASS è in esecuzione.

---

## Utilizzo quotidiano

### Avvio

Doppio clic su `vass.bat` (Windows) o `vass.sh`/`vass.command` (macOS/Linux).

Oppure da terminale:
```bash
cd VASS
.venv\Scripts\python vass.py    # Windows
.venv/bin/python vass.py         # macOS/Linux
```

> **Nota:** alla prima esecuzione, i modelli di riconoscimento vocale (Whisper) e sintesi vocale (Kokoro) vengono scaricati automaticamente da HuggingFace. Il primo avvio può richiedere diversi minuti (~2-4 GB di download). Questo avviene solo la prima volta.

### Wake word

La parola di attivazione (wake word) è **modificabile** dall'utente nel file `settings.ini` e può essere qualunque parola o frase breve. Di default è "**Erika**".

Quando VASS rileva la wake word, emette un bip per segnalare che è pronto a ricevere il comando. Parla dopo il bip.

Esempi:
- *"Erika"* (attendere il bip), poi *"che tempo fa?"*
- *"Erika"* (attendere il bip), poi *"leggi le ultime notizie"*
- *"Erika"* (attendere il bip), poi *"cosa è l'intelligenza artificiale?"*
- *"Erika"* (attendere il bip), poi *"traduci in inglese buongiorno a tutti"*
- *"Erika"* (attendere il bip), poi *"ricetta pasta alla carbonara"*

### Modalità: Chat e Trascrizione

VASS può funzionare in due modalità, selezionabili dal menu a comparsa (bottone ≡ a destra del pulsante principale):

- **Chat** `[C]` — L'applicazione riconosce comandi vocali ed esegue azioni (script, comandi di sistema) oppure interagisce con l'AI. La risposta viene letta tramite TTS.
- **Trascrizione** `[T]` — Invece di interpretare comandi, VASS trascrive fedelmente ciò che l'utente pronuncia dopo la wake word (sempre dopo il bip). Il testo viene poi incollato nell'applicazione attiva, rendendo VASS un sistema di dettatura testi.

La modalità corrente è indicata sul pulsante principale: `[C]` per Chat, `[T]` per Trascrizione. L'ultima modalità utilizzata viene ripristinata al riavvio.

### Modalità memoria

Dal menu GUI o cliccando sul pulsante principale:
- **Full** — L'AI riceve il riepilogo della memoria
- **Limited** — L'AI riceve solo la cronologia recente
- **None** — Nessun contesto storico

### Comandi vocali

I comandi si configurano nel file `commands.ini` (formato INI standard), modificabile anche tramite l'editor GUI (`python commands_editor.py`). Ogni riga è una coppia **frase = azione**: la frase è il pattern da riconoscere (può includere `{variabili}`), l'azione è cosa eseguire.

```ini
[general]
cerca {termine} = script:ricerca
apri {programma} = start {programma}
cerca online {escaped_terms} = start firefox "https://duckduckgo.com?q={escaped_terms}"
che ore sono = script:data_e_ora

[system]
spegni sistema = shutdown /s /t 60
blocca tutto = rundll32.exe user32.dll,LockWorkStation
```

#### Come funziona il matching

1. **Riconoscimento fuzzy**: non serve una corrispondenza esatta. VASS confronta la frase pronunciata con tutti i pattern usando un algoritmo di similarità (`difflib`). Il pattern con il punteggio più alto sopra la soglia (default `0.75`, configurabile in `settings.ini`) viene attivato.

2. **Variabili `{nome}`**: catturano le parole pronunciate in quella posizione. Esempio: dicendo *"cerca gatti su internet"* il sistema cattura `termine = "gatti su internet"`.

3. **Variabili escaped `{escaped_nome}`**: come le variabili normali, ma il testo catturato viene codificato in formato URL (gli spazi diventano `%20`). Utile per ricerche web.

4. **Fallback all'AI**: se nessun comando supera la soglia di similarità, la frase viene inviata all'AI per una risposta in linguaggio naturale.

#### Tipi di azioni

| Prefisso | Esempio | Comportamento |
|----------|---------|---------------|
| `script:` | `script:ricerca` | Esegue `scripts/ricerca.vass`. Le variabili catturate diventano `$param1`, `$param2`, ecc. |
| `vasscript:` | `vasscript:eventi` | Come `script:` (prefisso alternativo) |
| URL | `https://...` | Aperto nel browser predefinito |
| Comando | `shutdown /s` | Eseguito direttamente come comando di sistema |

#### Nomi delle sezioni

I nomi delle sezioni come `[general]` e `[system]` sono solo categorie organizzative — non influenzano il matching. Ciò che conta è la **chiave** (la frase da riconoscere).

### Creare script VASScript

Apri l'editor script dal menu GUI o esegui:
```bash
python scripts_editor.py
```

Tutti gli script vanno nella cartella `scripts/` con estensione `.vass`.

Vedi il file `VASCRIPT_REFERENCE.md` per il riferimento completo del linguaggio.

### Eventi e promemoria

Gli eventi vengono gestiti dal file `events.json`. Un promemoria vocale viene emesso 1 ora prima (configurabile).

Le schedulazioni (procedure automatiche) sono in `schedule.json` e attivano l'esecuzione di comandi con notifica TTS.

---

## Interfaccia GUI

- **Pulsante principale** — Clic per cambiare stato (listening/paused). Rotella mouse per volume. Trascina per spostare la finestra.
- **Barra volume** (verde, in alto) — Mostra il volume TTS corrente
- **Barra multi-stato** — Mostra utilizzo memoria, volume, o progresso script a seconda del contesto
- **Auto-fade** — La finestra diventa semitrasparente quando sei inattivo e in fullscreen

### Scorciatoie

| Tasto | Azione |
|-------|--------|
| `Ctrl+S` | Salva (negli editor) |
| Pulsante clic | Cambia stato |
| Rotella sul pulsante | Regola volume |
| Tasto destro | Menu contestuale |
| Tasto "Leggi" negli script | Legge lo script con TTS |

---

## Risoluzione problemi

> **Importante:** Questa applicazione dipende fortemente dal modello AI utilizzato. Modelli poco efficaci o non adatti all'uso dei tool MCP potrebbero comprometterne il funzionamento.

### VASS non si avvia
- Verifica Python 3.13+: `python --version`
- Verifica che `.venv` esista e contenga le dipendenze
- Controlla `debug.log` per errori

### Il microfono non funziona
- Verifica che il microfono sia collegato e non in uso da altre app
- Controlla i permessi di sistema per il microfono
- Su Windows: Impostazioni → Privacy → Microfono

### L'AI non risponde
- Verifica che il server AI sia in esecuzione su `http://127.0.0.1:8080/v1`
- Controlla `[ai] url` in `settings.ini`
- Se usi llama.cpp, verifica che il modello esista nella cartella `models/`

### L'OCR non riconosce il testo sullo schermo
- Aumenta la dimensione del font o il contrasto del testo sullo schermo
- EasyOCR funziona meglio con font grandi e alto contrasto
- La lingua OCR si adatta automaticamente al locale configurato

---

## File importanti

| File | Descrizione |
|------|-------------|
| `settings.ini` | Configurazione principale |
| `commands.ini` | Comandi vocali personalizzati |
| `scripts/*.vass` | I tuoi script VASScript |
| `events.json` | I tuoi eventi e promemoria |
| `schedule.json` | Procedure automatizzate |
| `memory.json` | Cronologia conversazioni |
| `debug.log` | Log di debug |
| `vass.log` | Log applicazione |
