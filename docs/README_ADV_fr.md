# VASS — Documentation Avancée

## Architecture générale

VASS est une application modulaire composée de plusieurs composants indépendants qui communiquent via des files d'attente basées sur fichiers, des signaux Qt et des appels directs.

```
┌─────────────────────────────────────────────────┐
│                    vass.py                       │
│              Orchestrateur principal             │
│  - Initialisation des composants                 │
│  - Boucle écoute/écriture                       │
│  - Gestion du fallback IA                       │
│  - Exécution des scripts                        │
│  - Watchdog des files de fichiers               │
└──────┬──────┬──────┬──────┬──────┬──────────────┘
       │      │      │      │      │
       ▼      ▼      ▼      ▼      ▼
  ┌────────┐┌─────┐┌─────┐┌────┐┌──────────┐
  │  gui.py││TTS  ││STT  ││Évé ││mcp_server│
  │  PySide││Eng. ││Whisp││Rap ││  15 outils│
  └────────┘└─────┘└─────┘└────┘└──────────┘
```

### Composants principaux

| Composant | Fichier | Responsabilité |
|-----------|------|---------------|
| Orchestrateur | `vass.py` (1313 lignes) | Initialisation, boucle principale, IA, scripts, mémoire |
| GUI | `gui.py` (832 lignes) | Fenêtre PySide6, barres, fondu, sous-fenêtres |
| TTS | `tts_engine.py` (138 lignes) | Kokoro TTS, lecture audio, volume |
| STT | `voice_recognition.py` (133 lignes) | faster-whisper, détection du mot d'activation |
| Interpréteur | `script_engine.py` (761 lignes) | Analyseur VASScript, évaluateur, 26 fonctions |
| Événements | `event_reminder.py` (280 lignes) | Surveillance événements/planifications, alertes TTS |
| Commandes | `command_executor.py` (184 lignes) | Correspondance floue de motifs, extraction de variables |
| Serveur MCP | `mcp_server/` | Serveur FastMCP, 15 outils, ACL basée IP |
| OCR | `script_engine.py:_preprocess_screen` | EasyOCR avec prétraitement |
| Inactivité | `idle_tracker.py` (67 lignes) | Détection d'inactivité multiplateforme |
| Ressources | `resource_monitor.py` (52 lignes) | Contrôle CPU/RAM/GPU/VRAM avant requêtes IA |
| Journal | `log_utils.py` (13 lignes) | Rotation des fichiers journaux |

---

## Pipeline audio

```
Microphone ──► sounddevice (callback) ──► file audio ──► Whisper (transcription)
                                                             │
                    ┌────────────────────────────────────────┤
                    ▼                                        ▼
         Détection "Erika" ?                      Transcription complète
                    │                                        │
                    ▼                                        ▼
               Bip (prêt pour la commande)                 Correspondance commands.ini ?
                    │                                  │            │
                    ▼                                  ▼            ▼
             Attente commande                     Commande    Aucune corr.
                    │                             trouvée
                    ▼                                  │            │
             Transcription                              ▼            ▼
                    │                          Exécuter action  Fallback IA
                    ▼
            Kokoro TTS ──► Haut-parleurs
```

### Détail du composant audio

- **Entrée** : `sounddevice.InputStream` avec callback à 16000 Hz mono
- **VAD** : webrtcvad pour filtrer le silence
- **Mot d'activation** : Whisper tiny model, cherche "erika" dans la transcription
- **Transcription** : Whisper medium model (configurable) après confirmation du mot d'activation
- **TTS** : Kokoro `KPipeline(lang_code='i')`, voix `if_sara`, génère WAV via nom de fichier UUID
- **Lecture** : `sounddevice.play()` avec événement `_tts_done` pour synchronisation

---

## VASScript — Langage de script

VASScript est un langage de script minimaliste pour l'automatisation du bureau. Exécution ligne par ligne, pas d'opérateurs arithmétiques, tout est une chaîne.

### Fonctions disponibles (26 au total)

#### IA et TTS
- `ai(prompt)` — Interroge l'IA, retourne du texte
- `say(texte, vitesse?)` — Synthèse vocale (vitesse : 0.5-1.5)
- `listen(prompt?)` — Enregistre la voix, retourne la transcription

#### Système
- `run(commande)` — Exécute PowerShell, retourne la sortie
- `wait(secondes)` — Met en pause l'exécution
- `exit()` — Termine le script
- `getdatetime()` — Date/heure actuelle "YYYY-MM-DD HH:MM"

#### Écran (OCR)
- `screen_search(recherche)` — Cherche du texte à l'écran, définit `$_sx`, `$_sy`, `$_sw`, `$_sh`
- `screen_click(x?, y?)` — Clic aux coordonnées
- `screen_highlight(x, y, l?, h?, dur?)` — Surbrillance de zone

#### Fenêtres et clavier
- `setActiveWindow(nom)` — Active la fenêtre par processus/titre
- `sendText(texte)` — Tape du texte avec délai humain

#### Événements
- `addevent(date, heure, durée, description, recur?)` — Ajoute un événement
- `listevents(jusqu_a_date)` — Liste les événements (JSON)
- `removeevent(nom)` — Supprime un événement (correspondance floue)
- `prettyevents(json)` — Formate les événements en texte lisible

#### Mémoire et presse-papiers
- `readinfo(id)` — Lit le fichier info
- `writeinfo(texte)` — Écrit le fichier info, retourne l'ID
- `clipboardget()` — Lit le presse-papiers
- `clipboardset(texte)` — Écrit le presse-papiers

#### Conditions
- `ifcontains(var, sous_chaîne, si_vrai, si_faux?)` — Contient sous-chaîne
- `ifempty(var, si_vide, si_plein?)` — Vérifie si vide

#### Utilitaires
- `trim(texte)` — Supprime les espaces
- `len(texte)` — Longueur de chaîne
- `contains(texte, sous_chaîne)` — Contient ? ("True"/"False")
- `equals(a, b)` — Égal ? ("True"/"False")

### Variables

```vascript
$nom = "Fabio"             # Assignation
$age = "54"                # Tout est chaîne
$resultat = ai("Bonjour")  # Résultat de fonction
say("Bonjour {$nom}!")     # Interpolation dans chaînes
say("Tu as {$age} ans")    # Aussi avec variables
```

**Note :** VASScript ne supporte PAS la concaténation avec `+`. Utilisez `{$var}` dans les chaînes.

### Variables globales de screen_search

`screen_search()` définit ces variables globales pour la première correspondance :
- `$_sx`, `$_sy` — coordonnées du centre
- `$_sw`, `$_sh` — largeur et hauteur

---

## Serveur MCP — 15 outils

Le serveur MCP expose 15 outils accessibles à l'IA sur `http://localhost:9988`.

### Système de fichiers
- `read_file(chemin)` — Lit un fichier dans Allowed_root
- `write_file(chemin, contenu)` — Écrit un fichier dans Allowed_root

### Web
- `browse(url)` — Télécharge une page (statique, httpx+BeautifulSoup)
- `websearch(recherche)` — Recherche sur DuckDuckGo via Playwright
- `webfetch(url)` — Charge une page rendue JS via Playwright

### Calcul et temps
- `calculate(expression)` — Évalue des expressions mathématiques (AST, sécurisé)
- `current_time()` — Date/heure actuelle
- `disk_space()` — Espace disque disponible

### Exécution
- `execute(commande)` — Exécute des commandes (liste blanche)
- `script(nom_script)` — Exécute un fichier VASScript
- `interact(code)` — Exécute du VASScript en ligne

### Mémoire et presse-papiers
- `readinfo(id)` — Lit le fichier info
- `writeinfo(texte)` — Écrit le fichier info
- `clipboardget()` — Lit le presse-papiers
- `clipboardset(texte)` — Écrit le presse-papiers

### Authentification

ACL basée IP via `mcp_server/config/tools.yaml`. Chaque outil a une liste blanche/noire. Refus par défaut.

### Communication script → VASS

Les outils `script` et `interact` utilisent une IPC basée sur fichiers :
1. Écrit la requête dans `scripts/exec_queue.json`
2. VASS lit la file (polling 1s)
3. Exécute le script
4. Écrit le résultat dans `scripts/exec_result.json`
5. Le client MCP lit le résultat

---

## Système de mémoire

### Structure

```
Allowed_root/
  memory.json          # Index : {"history": [id1, id2], "summary_id": "id3"}
  memory/
    1780394454383.json  # Entrée unique : {"info": "chaîne JSON"}
    1780427888604.json
    archive/
      2026-06/          # Archive mensuelle
```

### Flux

1. Chaque échange IA (utilisateur+assistant) est sauvegardé comme fichier JSON dans `memory/`
2. `memory.json` suit les 20 derniers ID
3. Après 5 sauvegardes, les fichiers non référencés vont dans `archive/{YYYY-MM}/`
4. Les archives de plus de 6 mois sont supprimées
5. Quand la mémoire dépasse `memory_tokens * 4` octets, la compression IA est déclenchée :
   - Les anciens messages sont résumés par l'IA
   - Le résumé est sauvegardé comme entrée `summary_id`
   - Les fichiers originaux sont archivés

---

## Événements et planifications

### events.json
```json
{
  "events": [{
    "date": "2026-06-15",
    "time": "14:30",
    "duration": 60,
    "description": "Réunion d'équipe",
    "recur": "7d",
    "notify": "2026-06-15 13:30:00"
  }]
}
```
- `recur` : "1d"=quotidien, "7d"=hebdomadaire, "1m"=mensuel, "2h"=toutes les 2 heures
- `notify` : horodatage de l'envoi de la notification

### schedule.json
```json
{
  "schedules": [{
    "date": "2026-06-05",
    "time": "08:00",
    "duration": 5,
    "description": "Sauvegarde",
    "recur": "1d",
    "command": "powershell",
    "arguments": "-File backup.ps1"
  }]
}
```
- Comme les événements mais déclenchent l'exécution de commandes
- Notification TTS au début et à la fin
- Validation des commandes contre un motif sécurisé (`.exe`, `.bat`, `.ps1`, `.py`, `.cmd`, `.vbs`)

---

## Dépendances

### Cœur (13)
| Paquet | Utilisation |
|-----------|-----|
| `sounddevice` | Entrée/sortie audio |
| `numpy` | Tableaux pour audio et images |
| `faster-whisper` | Reconnaissance vocale STT |
| `webrtcvad` | Détection d'activité vocale |
| `kokoro` | Synthèse vocale TTS |
| `torch` | Deep learning (Kokoro, Whisper, EasyOCR) |
| `soundfile` | Écriture de fichiers WAV |
| `openai` | Client API compatible OpenAI |
| `mcp[cli]` | Serveur MCP FastMCP |
| `pynput` | Contrôle souris/clavier |
| `PySide6` | GUI Qt6 |
| `keyring` | Gestionnaire d'identifiants Windows |
| `httpx` | Client HTTP pour IA et web |

### Web et OCR (6)
| Paquet | Utilisation |
|-----------|-----|
| `beautifulsoup4` | Analyse HTML pages statiques |
| `lxml` | Moteur XML/HTML rapide |
| `playwright` | Navigateur headless pour pages JS |
| `mss` | Captures d'écran rapides |
| `easyocr` | Reconnaissance de texte à l'écran |
| `pillow` | Traitement d'images |

### Utilitaires (5)
| Paquet | Utilisation |
|-----------|-----|
| `pyyaml` | Configuration du serveur MCP |
| `structlog` | Journalisation structurée MCP |
| `uvicorn` | Serveur HTTP MCP |
| `psutil` | Surveillance des ressources |
| `misaki` | Tokenisation Kokoro |
| `dateparser` | Analyse de dates en langage naturel |

---

## Mécanismes internes

### Modèle de threading

- **Thread principal** : GUI Qt (boucle d'événements)
- **Thread audio** : callback sounddevice
- **Thread VASS** : boucle écoute/transcription
- **Threads watchdog** : `_watch_commands_file`, `_watch_settings_file`, `_watch_script_queue`
- **Éphémères** : lecture TTS, fallback IA, exécution de script

### Mécanismes de verrouillage

- `_trim_lock` — Protège les opérations mémoire
- `_script_engine_lock` — Protège le moteur actif
- `_tts_done` (Event) — Synchronise la fin du TTS
- `state_lock` — Protège l'état de l'application

### IPC basée sur fichiers

**exec_queue.json / exec_result.json** :
- Le serveur MCP écrit les requêtes d'exécution de script
- VASS interroge (1s), exécute, écrit le résultat
- Timeout : 60s pour les scripts fichier, 120s pour en ligne

### Watchdogs de fichiers

VASS surveille les modifications de :
- `settings.ini` — rechargement automatique
- `commands.ini` — rechargement automatique
- `events.json` / `schedule.json` — recalcul de la prochaine alerte

### Stockage des identifiants

- Windows : Windows Credential Manager via `keyring`
- macOS : Trousseau
- Linux : D-Bus Secret Service ou fichier
- Utilisé pour : clé API IA, permissions de script VASScript (par fonction)

### Système i18n

- `locales/*.json` : 9 langues, 215+ clés chacune
- Fichier `i18n.py` : recherche `t(key, lang)`
- Référence : `it.json`
- Tous les fichiers alignés automatiquement

### Rotation des journaux

- `debug.log` : max 500 Ko → `.1`, `.2`
- `mcp_server/LOG/` : max 1 Mo → `.1`, `.2`
- Utilitaire : `log_utils.py`

---

## Configuration avancée

### [ai]
| Paramètre | Défaut | Description |
|-----------|---------|-------------|
| `url` | `http://127.0.0.1:8080/v1` | Endpoint API |
| `model` | `Qwen3-8B-Q4_K_M` | Nom du modèle |
| `api_key` | (vide) | Clé API (vide pour local) |
| `system_message` | (texte long) | Prompt système |
| `mcp_server_url` | `http://localhost:9988` | URL du serveur MCP |
| `memory_tokens` | `4000` | Limite mémoire en tokens×4 octets |
| `blacklist` | `Amara.org,QTTS` | Mots bloqués séparés par virgule |

### [tts]
| Paramètre | Défaut | Description |
|-----------|---------|-------------|
| `tts_engine` | `kokoro` | Moteur TTS |
| `volume` | `0.50` | Volume 0-1 |

### [wakeword]
| Paramètre | Défaut | Description |
|-----------|---------|-------------|
| `wakeword` | `erika` | Mot d'activation |
| `sensitivity` | `0.01` | Sensibilité 0-1 |

### [resources]
| Paramètre | Défaut | Description |
|-----------|---------|-------------|
| `cpu_max` | `75` | Seuil CPU % |
| `ram_max` | `99` | Seuil RAM % |
| `gpu_max` | `75` | Seuil GPU % |
| `vram_max` | `99` | Seuil VRAM % |
| `resource_timeout` | `30` | Délai d'attente secondes |

### [llamacpp]
| Paramètre | Description |
|-----------|-------------|
| `llama_server_path` | Chemin de l'exécutable llama.cpp |
| `llama_server_arguments` | Arguments de ligne de commande |

### [events]
| Paramètre | Défaut | Description |
|-----------|---------|-------------|
| `reminder_advance` | `3600` | Avance du rappel en secondes (1 heure) |

### [gui]
| Paramètre | Défaut | Description |
|-----------|---------|-------------|
| `x`, `y` | auto | Position de la fenêtre |
| `width`, `height` | `200`, `32` | Dimensions de la fenêtre |
| `font_family` | `Segoe UI` | Police GUI |
| `font_size` | `10` | Taille de police |
