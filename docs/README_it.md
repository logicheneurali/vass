# VASS — Software assistente vocale

## Cos'è VASS

VASS è un assistente vocale per Windows, macOS e Linux. Risponde ai comandi vocali, esegue script, gestisce eventi e promemoria, legge e risponde alle email e interagisce con un'AI locale o remota tramite un'API OpenAI-compatibile. Ospita inoltre un server MCP che dà all'AI accesso diretto a file, browser, calendario, email, notizie e strumenti di sistema.

**Wake word predefinita:** "Erika" (configurabile)

**Versione attuale:** 0.8.7

**Caratteristiche principali:**
- Riconoscimento vocale tramite Whisper (faster-whisper) con Silero VAD e noise floor adattivo
- Sintesi vocale naturale tramite Kokoro TTS con una catena di fallback a più livelli
- AI locale o remota (llama.cpp, OpenAI, qualsiasi server compatibile) con avvio automatico opzionale di llama.cpp
- Scripting VASScript per l'automazione del desktop con 70+ funzioni integrate
- Gestione di eventi e operazioni pianificate con editor GUI (promemoria, procedure automatizzate)
- Timer multilingua a comando vocale (5 simultanei)
- Server MCP con 50+ tool per l'orchestrazione dell'AI (browser, email, notizie, calendario, luoghi, file, sistema)
- Memoria permanente con classificazione automatica, riassunto e iniezione del profilo utente
- Client email integrato: Gmail, IMAP, POP3 con coda, contatti ed email inviate dall'AI
- Sistema di plugin: plugin interni ed esterni tramite socket TCP locale
- Centro notifiche con instradamento per tipo di evento
- Visualizzatore della cronologia delle conversazioni con azioni per messaggio
- Supporto per 9 lingue
- Protezione dall'overflow del contesto (troncamento o riassunto AI)
- Selezione del dispositivo audio (input/output)
- Tool calling multi-turn per task AI complessi
- Sistema meteo a 3 sorgenti con database di geolocalizzazione di 200K città
- Comandi vocali ritardati ("spegni tra 5 minuti")
- Indicatore dell'attività dei tool MCP in tempo reale nella GUI
- Compressione euristica del contesto con supporto multilingue per le stopword
- Conteggio del contesto accurato al token (tiktoken)
- Sandbox per l'esecuzione degli script con autorizzazione SHA-256 e audit logging
- Cancello di sicurezza per i tool online sensibili (consenso, limite di frequenza, log di controllo)
- Avvio automatico di sistema opzionale

---

## Requisiti

- **Python 3.13** o superiore
- **Server AI** (llama.cpp o OpenAI-compatibile) già installato e configurato sul sistema. VASS può avviare automaticamente llama.cpp se configurato, ma **NON installa llama.cpp né scarica i modelli AI**: devi procurarteli separatamente.
- **Connessione internet** (per il download dei modelli TTS/STT e per l'AI remota)
- **GPU NVIDIA consigliata** per l'AI locale (la CPU è possibile ma lenta)
- **Microfono funzionante**
- Windows 10+, macOS 12+ o Linux moderno

---

## Installazione

### Installazione grafica (consigliata)

Scarica l'installer dalla [pagina Releases](https://github.com/logicheneurali/vass/releases) ed eseguilo. Il wizard installerà Python, VASS, llama.cpp e un modello AI automaticamente — nessuna configurazione manuale necessaria.

### Installazione guidata

Scarica o clona il progetto, poi entra nella cartella ed esegui lo script:

```bash
cd vass
python install.py
```

> **Nota:** l'installazione guidata configura VASS ma **NON installa il server AI né i modelli**.
> Devi avere un server OpenAI-compatibile già in esecuzione (llama.cpp, Ollama, LM Studio, Groq, OpenAI, ecc.)
> oppure configurare llama.cpp nelle impostazioni di VASS (che può avviarlo automaticamente).

**Nota:** la procedura di installazione guidata è ancora sperimentale e potrebbe non funzionare su tutti i sistemi. In caso di problemi, utilizza la procedura di installazione manuale qui sotto.

Il wizard ti guiderà attraverso:
1. Scelta della lingua
2. Verifica dei prerequisiti (Python 3.13+, pip)
3. Cartella di destinazione
4. Configurazione dei parametri (URL AI, modello, wake word)
5. Copia dei file
6. Creazione dell'ambiente virtuale Python (.venv)
7. Installazione delle dipendenze pip
8. Creazione del file settings.ini
9. Creazione del lanciatore

### Installazione manuale

```bash
# Clona o copia i file nella cartella desiderata
cd VASS

# Crea l'ambiente virtuale
python -m venv .venv

# Attiva (Windows)
.venv\Scripts\activate
# oppure (macOS/Linux)
source .venv/bin/activate

# Installa le dipendenze
pip install -r requirements.txt

# Installa Chromium per Playwright (ricerche web)
playwright install chromium

# Crea config/settings.ini (copia da config/settings.example.ini)
```

---

## Configurazione

Tutte le impostazioni si trovano in `config/settings.ini` (il modello è `config/settings.example.ini`). Ecco le più importanti:

| Sezione | Parametro | Descrizione |
|---------|-----------|-------------|
| `[locale]` | `language` | Lingua (it/en/de/fr/es/pt/ja/ko/zh) |
| `[wakeword]` | `wakeword` | Wake word (predefinita: erika) |
| `[wakeword]` | `sensitivity` | Sensibilità del rilevamento della wake word |
| `[commands]` | `similarity` | Soglia di corrispondenza fuzzy dei comandi vocali (predefinita 0.6) |
| `[commands]` | `word_learning_enabled` | Impara nuove parole pronunciate nel tempo (true/false) |
| `[ai]` | `url` | URL del server AI OpenAI-compatibile |
| `[ai]` | `model` | Nome del modello AI |
| `[ai]` | `system_message` | Personalità dell'assistente |
| `[ai]` | `api_key` | Chiave API (archiviata nel keyring di sistema se impostata) |
| `[ai]` | `mcp_server_url` | URL del server MCP incluso (predefinito `http://localhost:9988`) |
| `[ai]` | `memory_tokens` | Dimensione massima della memoria |
| `[ai]` | `context_length` | Token massimi di contesto (0 = automatico) |
| `[ai]` | `overflow_strategy` | Gestione dell'overflow del contesto: `truncate` o `summarize` |
| `[ai]` | `allow_ai_scripts` | Consenti all'AI di eseguire script VASScript (true/false) |
| `[llamacpp]` | `llama_server_path` | Percorso del server llama.cpp |
| `[llamacpp]` | `llama_autostart` | Avvia automaticamente llama.cpp con VASS (true/false) |
| `[resources]` | `cpu_max`, `ram_max`, `gpu_max`, `vram_max` | Limiti delle risorse che regolano le operazioni AI |
| `[events]` | `reminder_advance` | Secondi prima di un evento in cui viene emesso il promemoria (predefinito 3600) |
| `[audio]` | `input_device`, `output_device` | Selezione del dispositivo audio (-1 = predefinito di sistema) |
| `[audio]` | `input_volume`, `output_volume` | Livelli del volume di input/output (0-1) |
| `[audio]` | `app_volume` | Volume TTS principale (sostituisce il vecchio `[tts] volume`) |
| `[google]` | — | Integrazione con Google Calendar / Gmail / Google Home |
| `[startup]` | `app_autostart` | Avvia VASS automaticamente all'accesso (true/false) |
| `[debug]` | `debug_enabled` | Scrive un log dettagliato in `log/debug.log` (true/false) |

Le impostazioni vengono ricaricate automaticamente se modificate mentre VASS è in esecuzione.

---

## Utilizzo quotidiano

### Avvio

Fai doppio clic su `vass.bat` (Windows) o `vass.sh`/`vass.command` (macOS/Linux).

Oppure dal terminale:
```bash
cd VASS
.venv\Scripts\python vass.py    # Windows
.venv/bin/python vass.py         # macOS/Linux
```

> **Nota:** al primo avvio, i modelli di riconoscimento vocale (Whisper) e di sintesi vocale (Kokoro) vengono scaricati automaticamente da HuggingFace. Il primo avvio può richiedere diversi minuti (~2-4 GB di download). Questo avviene una sola volta.

### Wake word

La wake word è **configurabile** dall'utente nel file `config/settings.ini` e può essere qualsiasi parola o frase breve. Quella predefinita è "**Erika**".

Quando VASS rileva la wake word, emette un bip per segnalare che è pronto a ricevere il comando. Parla dopo il bip.

Esempi:
- *"Erika"* (attendere il bip), poi *"che tempo fa?"*
- *"Erika"* (attendere il bip), poi *"leggi le ultime notizie"*
- *"Erika"* (attendere il bip), poi *"cos'è l'intelligenza artificiale?"*
- *"Erika"* (attendere il bip), poi *"traduci in italiano buongiorno a tutti"*
- *"Erika"* (attendere il bip), poi *"ricetta pasta alla carbonara"*

### Modalità: Chat e Trascrizione

VASS può funzionare in due modalità, selezionabili dal menu a comparsa (bottone ≡ a destra del pulsante principale):

- **Chat** `[C]` — L'applicazione riconosce i comandi vocali ed esegue azioni (script, comandi di sistema) oppure interagisce con l'AI. La risposta viene letta tramite TTS.
- **Trascrizione** `[T]` — Invece di interpretare i comandi, VASS trascrive fedelmente ciò che l'utente dice dopo la wake word (sempre dopo il bip). Il testo viene poi incollato nell'applicazione attiva, rendendo VASS un sistema di dettatura del testo.

La modalità corrente è mostrata sul pulsante principale: `[C]` per Chat, `[T]` per Trascrizione. L'ultima modalità usata viene ripristinata al riavvio.

### Modalità memoria

Dal menu GUI o cliccando sul pulsante principale:
- **Full** — L'AI riceve il riassunto della memoria e il tuo profilo utente
- **Limited** — L'AI riceve solo la cronologia recente
- **None** — Nessun contesto storico

### Comandi vocali

I comandi sono configurati in `config/commands.ini` (formato INI standard, `frase = azione`), modificabili anche tramite l'editor GUI (`python src/commands_editor.py`). I file specifici per lingua `config/commands_{lang}.ini` vengono caricati in aggiunta al file di base. Ogni riga è una coppia **frase = azione**: la frase è il pattern da riconoscere (può includere `{variabili}`), l'azione è ciò che viene eseguito.

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

#### Come funziona la corrispondenza

1. **Riconoscimento fuzzy**: non è richiesta una corrispondenza esatta. VASS confronta la frase pronunciata con tutti i pattern usando un algoritmo di similarità (`difflib`). Viene attivato il pattern con il punteggio più alto al di sopra della soglia (predefinita `0.6`, configurabile in `config/settings.ini` alla voce `[commands] similarity`).

2. **Variabili `{name}`**: catturano le parole pronunciate in quella posizione. Esempio: dicendo *"cerca gatti su internet"* viene catturato `term = "gatti su internet"`.

3. **Variabili escaped `{escaped_name}`**: come le variabili normali, ma il testo catturato viene codificato in URL (gli spazi diventano `%20`). Utile per le ricerche web.

4. **Comandi ritardati**: un suffisso `{duration}` (ad es. *"spegni tra 5 minuti"*) pianifica l'esecuzione del comando dopo il tempo indicato tramite il sistema dei timer.

5. **Apprendimento delle parole**: se abilitato, VASS registra come pronunci le parole per migliorare il riconoscimento nel tempo.

6. **Fallback all'AI**: se nessun comando supera la soglia di similarità, la frase viene inviata all'AI per una risposta in linguaggio naturale.

#### Alternative con virgole (prodotto cartesiano)

Puoi specificare più alternative per ogni posizione della parola usando le virgole. Gli **spazi** separano le posizioni delle parole, le **virgole** separano le alternative all'interno di una posizione. VASS genera tutte le combinazioni possibili (prodotto cartesiano).

```ini
# Posizione singola: alternative per la preposizione
click the,on text {text}
```
Genera 2 pattern: `click the text {text}`, `click on text {text}`.

```ini
# Due posizioni: ogni posizione ha le sue alternative
aa,xx bb,cc {var}
```
Genera 4 pattern: `aa bb {var}`, `aa cc {var}`, `xx bb {var}`, `xx cc {var}` (2x2 = 4).

```ini
# Misto: parola fissa + alternative
turn on,off {device}
```
Genera 2 pattern: `turn on {device}`, `turn off {device}` (nessuno spazio tra `on` e `off` -> stessa posizione).

La frase pronunciata viene confrontata con tutti i pattern generati. Vince la migliore corrispondenza fuzzy.

#### Tipi di azione

| Prefisso | Esempio | Comportamento |
|--------|---------|----------|
| `script:` | `script:search` | Esegue `scripts/search.vass`. Le variabili catturate diventano `$param1`, `$param2`, ecc. |
| `vasscript:` | `vasscript:events` | Come `script:` (prefisso alternativo) |
| Comando | `shutdown /s` | Eseguito direttamente come comando di sistema |

#### Nomi delle sezioni

I nomi delle sezioni come `[general]` e `[system]` sono solo categorie organizzative — non influenzano la corrispondenza. Ciò che conta è la **chiave** (la frase da riconoscere).

### Creare script VASScript

Apri l'editor degli script dal menu GUI oppure esegui:
```bash
python src/scripts_editor.py
```

Tutti gli script vanno nella cartella `scripts/` con estensione `.vass`.

**Autorizzazione**: prima di eseguire uno script nuovo o modificato, VASS mostra un popup che chiede il permesso. Gli script sono verificati tramite hash SHA-256 (archiviato nel keyring di sistema): se un file script viene modificato dopo essere stato autorizzato, i permessi vengono revocati automaticamente e il popup riapparirà alla prossima esecuzione. Il permesso può essere concesso per singola funzione o per l'intero script. Questo garantisce che nessuno script possa essere eseguito sul tuo computer senza il tuo consenso esplicito.

Vedi il file [Riferimento VASCRIPT](../Allowed_root/VASCRIPT_REFERENCE.md) per il riferimento completo del linguaggio.

### Eventi e promemoria

Gli eventi vengono gestiti tramite il file `Allowed_root/events.json`. Un promemoria vocale viene emesso 1 ora prima (configurabile tramite `[events] reminder_advance`).

Le operazioni pianificate (procedure automatizzate) sono in `Allowed_root/schedules.json` e attivano l'esecuzione di comandi con notifica TTS. Flag aggiuntivi: `silent`, `run_on_startup`, `check_already_running`, `wait_for_completion`.

### Sistema di plugin

VASS espone un server TCP locale (`localhost:8765`) che i plugin usano per comunicare con l'app: TTS, notifiche, query AI, elementi RSS, chat, UI dichiarative e altro. I **plugin interni** (inclusi in VASS) non possono essere rimossi; i **plugin esterni** possono essere abilitati, disabilitati e rimossi dalla GUI (menu Plugin).

Plugin interni inclusi: pausa automatica del rumore, agente proattivo, profilo utente, lettore RSS, eventi mondiali, bot Telegram. Plugin esterni disponibili su disco: generatore di immagini, editore di notizie, visualizzatore di timeline.

Vedi la guida [PLUGIN_DEV_it.md](PLUGIN_DEV_it.md) per il protocollo completo e per creare i tuoi plugin (disponibile anche in `PLUGIN_DEV_{en,de,fr,es,pt,ja,ko,zh}.md`).

### Email

Configura uno o più account in Impostazioni → Posta (Gmail tramite OAuth, oppure IMAP/POP3 con SSL/TLS semplice). I messaggi in arrivo vengono rilevati e notificati; l'AI può cercare, leggere, rispondere, inoltrare e inviare email — ma le email inviate vengono sempre messe in una **coda** che devi approvare e spedire dalla posta in uscita. I contatti sono archiviati in modo crittografato.

---

## Interfaccia GUI

- **Pulsante principale** — Clic per cambiare stato (in ascolto/in pausa). Rotella del mouse per il volume. Trascina per spostare la finestra.
- **Barra del volume** (verde, in alto) — Mostra il volume TTS corrente
- **Barra multi-stato** — Mostra l'utilizzo della memoria, il volume o l'avanzamento di script/attività a seconda del contesto
- **Centro notifiche** (campanella) — Schede per tipo con azioni sui messaggi e segna-tutto-come-letto
- **Indicatore dei tool** — Icona in tempo reale che mostra il tool MCP in uso dall'AI
- **Pulsante mic** — Input vocale diretto in modalità chat
- **Menu plugin** — Gestisci plugin, impostazioni dei plugin e UI dei plugin
- **Finestra di dialogo Impostazioni** — Configurazione completa dalla GUI (menu Impostazioni)
- **Auto-fade** — La finestra diventa semitrasparente quando è inattiva e in fullscreen
- **Schermata iniziale** — Avanzamento del caricamento all'avvio
- **Tema** — Tema condiviso tra l'app e tutti gli editor

### Scorciatoie

| Tasto | Azione |
|-------|--------|
| `Ctrl+S` | Salva (negli editor) |
| Clic sul pulsante | Cambia stato |
| Rotella sul pulsante | Regola il volume |
| Tasto destro | Menu contestuale |
| Clic centrale sul pulsante | Esci |

---

## Risoluzione dei problemi

> **Importante:** Questa applicazione dipende fortemente dal modello AI utilizzato. Modelli inefficaci o non adatti all'uso dei tool MCP potrebbero comprometterne il funzionamento.

### VASS non si avvia
- Verifica Python 3.13+: `python --version`
- Verifica che `.venv` esista e contenga le dipendenze
- Controlla `log/debug.log` (abilita `[debug] debug_enabled = true`) e `log/crash.log`

### Il microfono non funziona
- Verifica che il microfono sia collegato e non in uso da altre app
- Controlla i permessi di sistema per il microfono
- Su Windows: Impostazioni → Privacy → Microfono

### L'AI non risponde
- Verifica che il server AI sia in esecuzione su `http://127.0.0.1:8080/v1`
- Controlla `[ai] url` in `config/settings.ini`
- Se usi llama.cpp, verifica che il modello esista e che `[llamacpp] llama_server_path` sia corretto
- Controlla `log/llamacpp.log` per gli errori di llama.cpp

### L'OCR non riconosce il testo sullo schermo
- Aumenta la dimensione del font o il contrasto del testo sullo schermo
- EasyOCR funziona meglio con font grandi e alto contrasto
- La lingua dell'OCR si adatta automaticamente al locale configurato

### L'AI non riesce a usare un tool
- Alcuni tool online richiedono il tuo consenso (cancello di sicurezza) — controlla l'InfoPanel per le richieste in sospeso
- Verifica che il server MCP sia raggiungibile su `http://localhost:9988` (vedi `[ai] mcp_server_url`)
- Controlla `log/mcp_server.log` per gli errori MCP

---

## File importanti

| File | Descrizione |
|------|-------------|
| `config/settings.ini` | Configurazione principale |
| `config/commands.ini` | Comandi vocali di base (più `commands_{lang}.ini`) |
| `config/notifications.ini` | Instradamento delle notifiche per tipo di evento |
| `scripts/*.vass` | I tuoi script VASScript |
| `Allowed_root/events.json` | I tuoi eventi e promemoria |
| `Allowed_root/schedules.json` | Procedure automatizzate |
| `Allowed_root/memory.json` | Cronologia delle conversazioni e memoria |
| `Allowed_root/private_profile.json` | Profilo utente iniettato nel contesto AI |
| `plugins/` | Plugin interni ed esterni |
| `log/debug.log` | Log di debug dettagliato (se abilitato) |
| `log/crash.log` | Log dei crash |
| `log/faulthandler.log` | Output del fault handler |
| `log/llamacpp.log` | Log del server llama.cpp |
