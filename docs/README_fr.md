# VASS — Logiciel d'assistant vocal

## Qu'est-ce que VASS

VASS est un assistant vocal pour Windows, macOS et Linux. Il répond aux commandes vocales, exécute des scripts, gère les événements et les rappels, lit et répond aux e-mails, et interagit avec une IA locale ou distante via une API compatible OpenAI. Il héberge également un serveur MCP qui donne à l'IA un accès direct aux fichiers, au navigateur, au calendrier, aux e-mails, aux actualités et aux outils système.

**Mot de réveil par défaut :** « Erika » (configurable)

**Version actuelle :** 0.8.7

**Fonctionnalités clés :**
- Reconnaissance vocale via Whisper (faster-whisper) avec VAD Silero et plancher de bruit adaptatif
- Synthèse vocale naturelle via Kokoro TTS avec une chaîne de repli en plusieurs étapes
- IA locale ou distante (llama.cpp, OpenAI, tout serveur compatible) avec démarrage automatique facultatif de llama.cpp
- Scripting VASScript pour l'automatisation du bureau avec plus de 70 fonctions intégrées
- Gestion des événements et des plannings avec interface d'édition (rappels, procédures automatisées)
- Minuteur multilingue (activé par la voix, 5 simultanés)
- Serveur MCP avec plus de 50 outils pour l'orchestration de l'IA (navigateur, e-mail, actualités, calendrier, lieux, fichiers, système)
- Mémoire permanente avec classification automatique, résumé et injection du profil utilisateur
- Client e-mail intégré : Gmail, IMAP, POP3 avec file d'attente, contacts et e-mails envoyés par l'IA
- Système de plugins : plugins internes et externes via une socket TCP locale
- Centre de notifications avec routage par type d'événement
- Visionneuse d'historique de conversation avec actions par message
- Prise en charge de 9 langues
- Protection contre le dépassement du contexte (truncate ou résumé par l'IA)
- Sélection du périphérique audio (entrée/sortie)
- Appel d'outils multi-tours pour les tâches d'IA complexes
- Système météo à 3 sources avec base de géolocalisation de 200 000 villes
- Commandes vocales différées (« éteindre dans 5 minutes »)
- Indicateur d'activité en temps réel des outils MCP dans l'interface
- Compression heuristique du contexte avec prise en charge multilingue des mots vides
- Comptage précis des jetons du contexte (tiktoken)
- Environnement d'exécution sandbox des scripts avec autorisation SHA-256 et journalisation d'audit
- Passerelle de sécurité pour les outils en ligne sensibles (consentement, limite de débit, journal d'audit)
- Démarrage automatique facultatif au lancement du système

---

## Prérequis

- **Python 3.13** ou supérieur
- **Serveur IA** (llama.cpp ou compatible OpenAI) déjà installé et configuré sur le système. VASS peut démarrer automatiquement llama.cpp s'il est configuré, mais **n'installe PAS llama.cpp et ne télécharge PAS les modèles d'IA** : vous devez les obtenir séparément.
- **Connexion Internet** (pour le téléchargement des modèles TTS/STT et l'IA distante)
- **GPU NVIDIA recommandé** pour l'IA locale (CPU possible mais lent)
- **Microphone fonctionnel**
- Windows 10+, macOS 12+ ou Linux moderne

---

## Installation

### Installation graphique (recommandée)

Téléchargez l'installateur depuis la [page des versions](https://github.com/logicheneurali/vass/releases) et exécutez-le. L'assistant installera Python, VASS, llama.cpp et un modèle d'IA automatiquement — aucune configuration manuelle requise.

### Installation guidée

Téléchargez ou clonez le projet, puis entrez dans le dossier et exécutez le script :

```bash
cd vass
python install.py
```

> **Remarque :** l'installation guidée configure VASS mais **n'installe PAS le serveur d'IA ni les modèles**.
> Vous devez disposer d'un serveur compatible OpenAI déjà en cours d'exécution (llama.cpp, Ollama, LM Studio, Groq, OpenAI, etc.)
> ou configurer llama.cpp dans les paramètres de VASS (qui peut le démarrer automatiquement).

**Remarque :** la procédure d'installation guidée est encore expérimentale et peut ne pas fonctionner sur tous les systèmes. Si vous rencontrez des problèmes, utilisez la procédure d'installation manuelle ci-dessous.

L'assistant vous guidera à travers :
1. Sélection de la langue
2. Vérification des prérequis (Python 3.13+, pip)
3. Dossier de destination
4. Configuration des paramètres (URL de l'IA, modèle, mot de réveil)
5. Copie des fichiers
6. Création de l'environnement virtuel Python (.venv)
7. Installation des dépendances pip
8. Création du fichier settings.ini
9. Création du lanceur

### Installation manuelle

```bash
# Clone or copy files to the desired folder
cd VASS

# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate
# or (macOS/Linux)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Chromium for Playwright (web searches)
playwright install chromium

# Create config/settings.ini (copy from config/settings.example.ini)
```

---

## Configuration

Tous les paramètres se trouvent dans `config/settings.ini` (le modèle est `config/settings.example.ini`). Voici les plus importants :

| Section | Paramètre | Description |
|---------|-----------|-------------|
| `[locale]` | `language` | Langue (it/en/de/fr/es/pt/ja/ko/zh) |
| `[wakeword]` | `wakeword` | Mot de réveil (par défaut : erika) |
| `[wakeword]` | `sensitivity` | Sensibilité de détection du mot de réveil |
| `[commands]` | `similarity` | Seuil de correspondance floue des commandes vocales (par défaut 0.6) |
| `[commands]` | `word_learning_enabled` | Apprendre de nouveaux mots prononcés au fil du temps (true/false) |
| `[ai]` | `url` | URL du serveur d'IA compatible OpenAI |
| `[ai]` | `model` | Nom du modèle d'IA |
| `[ai]` | `system_message` | Personnalité de l'assistant |
| `[ai]` | `api_key` | Clé API (stockée dans le trousseau du système si définie) |
| `[ai]` | `mcp_server_url` | URL du serveur MCP intégré (par défaut `http://localhost:9988`) |
| `[ai]` | `memory_tokens` | Taille maximale de la mémoire |
| `[ai]` | `context_length` | Nombre maximal de jetons de contexte (0 = auto) |
| `[ai]` | `overflow_strategy` | Gestion du dépassement du contexte : `truncate` ou `summarize` |
| `[ai]` | `allow_ai_scripts` | Autoriser l'IA à exécuter des scripts VASScript (true/false) |
| `[llamacpp]` | `llama_server_path` | Emplacement du serveur llama.cpp |
| `[llamacpp]` | `llama_autostart` | Démarrer llama.cpp automatiquement avec VASS (true/false) |
| `[resources]` | `cpu_max`, `ram_max`, `gpu_max`, `vram_max` | Limites de ressources qui conditionnent les opérations de l'IA |
| `[events]` | `reminder_advance` | Secondes avant un événement où le rappel est émis (par défaut 3600) |
| `[audio]` | `input_device`, `output_device` | Sélection du périphérique audio (-1 = défaut du système) |
| `[audio]` | `input_volume`, `output_volume` | Niveaux de volume d'entrée/sortie (0-1) |
| `[audio]` | `app_volume` | Volume TTS principal (remplace l'ancien `[tts] volume`) |
| `[google]` | — | Intégration Google Calendar / Gmail / Google Home |
| `[startup]` | `app_autostart` | Démarrer VASS automatiquement à la connexion (true/false) |
| `[debug]` | `debug_enabled` | Écrire un journal verbeux dans `log/debug.log` (true/false) |

Les paramètres sont automatiquement rechargés s'ils sont modifiés pendant que VASS est en cours d'exécution.

---

## Utilisation quotidienne

### Démarrage

Double-cliquez sur `vass.bat` (Windows) ou `vass.sh`/`vass.command` (macOS/Linux).

Ou depuis le terminal :
```bash
cd VASS
.venv\Scripts\python vass.py    # Windows
.venv/bin/python vass.py         # macOS/Linux
```

> **Remarque :** au premier lancement, les modèles de reconnaissance vocale (Whisper) et de synthèse vocale (Kokoro) sont téléchargés automatiquement depuis HuggingFace. Le premier démarrage peut prendre plusieurs minutes (téléchargement d'environ 2 à 4 Go). Cela ne se produit qu'une seule fois.

### Mot de réveil

Le mot de réveil est **configurable** par l'utilisateur dans le fichier `config/settings.ini` et peut être n'importe quel mot ou courte phrase. La valeur par défaut est « **Erika** ».

Lorsque VASS détecte le mot de réveil, il émet un bip pour signaler qu'il est prêt à recevoir la commande. Parlez après le bip.

Exemples :
- *« Erika »* (attendre le bip), puis *« quel temps fait-il ? »*
- *« Erika »* (attendre le bip), puis *« lis les dernières nouvelles »*
- *« Erika »* (attendre le bip), puis *« qu'est-ce que l'intelligence artificielle ? »*
- *« Erika »* (attendre le bip), puis *« traduis en italien bonjour tout le monde »*
- *« Erika »* (attendre le bip), puis *« recette pâtes carbonara »*

### Modes : Chat et Transcription

VASS peut fonctionner selon deux modes, sélectionnables depuis le menu contextuel (bouton ≡ à droite du bouton principal) :

- **Chat** `[C]` — L'application reconnaît les commandes vocales et exécute des actions (scripts, commandes système) ou interagit avec l'IA. La réponse est lue via TTS.
- **Transcription** `[T]` — Au lieu d'interpréter les commandes, VASS transcrit fidèlement ce que l'utilisateur dit après le mot de réveil (toujours après le bip). Le texte est ensuite collé dans l'application active, faisant de VASS un système de dictée.

Le mode actuel est affiché sur le bouton principal : `[C]` pour Chat, `[T]` pour Transcription. Le dernier mode utilisé est restauré au redémarrage.

### Mode mémoire

Depuis le menu de l'interface ou en cliquant sur le bouton principal :
- **Complet** — L'IA reçoit le résumé de la mémoire et votre profil utilisateur
- **Limité** — L'IA ne reçoit que l'historique récent
- **Aucun** — Aucun contexte historique

### Commandes vocales

Les commandes sont configurées dans `config/commands.ini` (format INI standard, `phrase = action`), également modifiables via l'éditeur graphique (`python src/commands_editor.py`). Les fichiers spécifiques à la langue `config/commands_{lang}.ini` sont chargés par-dessus le fichier de base. Chaque ligne est une paire **phrase = action** : la phrase est le motif à reconnaître (peut inclure `{variables}`), l'action est ce qui doit être exécuté.

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

#### Comment fonctionne la correspondance

1. **Reconnaissance floue** : une correspondance exacte n'est pas requise. VASS compare la phrase prononcée à tous les motifs à l'aide d'un algorithme de similarité (`difflib`). Le motif ayant obtenu le score le plus élevé au-dessus du seuil (par défaut `0.6`, configurable dans `config/settings.ini` sous `[commands] similarity`) est activé.

2. **Variables `{name}`** : capturent les mots prononcés à cette position. Exemple : dire *« cherche des chats sur internet »* capture `term = "cats on the internet"`.

3. **Variables échappées `{escaped_name}`** : identiques aux variables normales, mais le texte capturé est encodé en URL (les espaces deviennent `%20`). Utile pour les recherches web.

4. **Commandes différées** : un suffixe `{duration}` (par ex. *« éteindre dans 5 minutes »*) planifie l'exécution de la commande après le temps indiqué via le système de minuteur.

5. **Apprentissage des mots** : s'il est activé, VASS enregistre la façon dont vous prononcez les mots pour améliorer la reconnaissance au fil du temps.

6. **Repli sur l'IA** : si aucune commande ne dépasse le seuil de similarité, la phrase est envoyée à l'IA pour obtenir une réponse en langage naturel.

#### Alternatives par virgules (produit cartésien)

Vous pouvez spécifier plusieurs alternatives pour chaque position de mot à l'aide de virgules. Les **espaces** séparent les positions de mots, les **virgules** séparent les alternatives au sein d'une position. VASS génère toutes les combinaisons possibles (produit cartésien).

```ini
# Single position: alternatives for the preposition
click the,on text {text}
```
Génère 2 motifs : `click the text {text}`, `click on text {text}`.

```ini
# Two positions: each position has its own alternatives
aa,xx bb,cc {var}
```
Génère 4 motifs : `aa bb {var}`, `aa cc {var}`, `xx bb {var}`, `xx cc {var}` (2x2 = 4).

```ini
# Mixed: fixed word + alternatives
turn on,off {device}
```
Génère 2 motifs : `turn on {device}`, `turn off {device}` (pas d'espace entre `on` et `off` -> même position).

La phrase prononcée est comparée à tous les motifs générés. La meilleure correspondance floue l'emporte.

#### Types d'action

| Préfixe | Exemple | Comportement |
|--------|---------|----------|
| `script:` | `script:search` | Exécute `scripts/search.vass`. Les variables capturées deviennent `$param1`, `$param2`, etc. |
| `vasscript:` | `vasscript:events` | Identique à `script:` (préfixe alternatif) |
| Commande | `shutdown /s` | Exécutée directement comme commande système |

#### Noms de sections

Les noms de sections comme `[general]` et `[system]` sont simplement des catégories d'organisation — ils n'affectent pas la correspondance. La **clé** (la phrase à reconnaître) est ce qui compte.

### Créer des scripts VASScript

Ouvrez l'éditeur de scripts depuis le menu de l'interface ou exécutez :
```bash
python src/scripts_editor.py
```

Tous les scripts sont placés dans le dossier `scripts/` avec une extension `.vass`.

**Autorisation** : avant d'exécuter un script nouveau ou modifié, VASS affiche une fenêtre contextuelle demandant la permission. Les scripts sont vérifiés via un hash SHA-256 (stocké dans le trousseau du système) : si un fichier de script est modifié après avoir été autorisé, les permissions sont automatiquement révoquées et la fenêtre réapparaîtra à la prochaine exécution. La permission peut être accordée par fonction ou pour l'ensemble du script. Cela garantit qu'aucun script ne peut s'exécuter sur votre machine sans votre consentement explicite.

Consultez le fichier [Référence VASCRIPT](../Allowed_root/VASCRIPT_REFERENCE.md) pour la référence complète du langage.

### Événements et rappels

Les événements sont gérés via le fichier `Allowed_root/events.json`. Un rappel vocal est émis 1 heure à l'avance (configurable via `[events] reminder_advance`).

Les plannings (procédures automatisées) se trouvent dans `Allowed_root/schedules.json` et déclenchent l'exécution de commandes avec notification TTS. Drapeaux supplémentaires : `silent`, `run_on_startup`, `check_already_running`, `wait_for_completion`.

### Système de plugins

VASS expose un serveur TCP local (`localhost:8765`) que les plugins utilisent pour communiquer avec l'application : TTS, notifications, requêtes IA, éléments RSS, chat, interfaces déclaratives, et plus encore. Les **plugins internes** (inclus avec VASS) ne peuvent pas être supprimés ; les **plugins externes** peuvent être activés, désactivés et supprimés depuis l'interface (menu Plugins).

Plugins internes inclus : mise en pause automatique du bruit, agent proactif, profil utilisateur, lecteur RSS, événements mondiaux, bot Telegram. Plugins externes disponibles sur le disque : générateur d'images, éditeur d'actualités, visionneuse de chronologie.

Consultez le guide [PLUGIN_DEV_fr.md](PLUGIN_DEV_fr.md) pour le protocole complet et la création de vos propres plugins (également disponible dans `PLUGIN_DEV_{en,it,de,es,pt,ja,ko,zh}.md`).

### E-mail

Configurez un ou plusieurs comptes dans Paramètres → Mail (Gmail via OAuth, ou IMAP/POP3 avec SSL/TLS). Les messages entrants sont détectés et notifiés ; l'IA peut rechercher, lire, répondre, transférer et envoyer des e-mails — mais les e-mails envoyés sont toujours placés dans une **file d'attente** que vous devez approuver et envoyer depuis la boîte d'envoi. Les contacts sont stockés de manière chiffrée.

---

## Interface graphique

- **Bouton principal** — Cliquez pour changer d'état (à l'écoute/en pause). Molette de la souris pour le volume. Glissez pour déplacer la fenêtre.
- **Barre de volume** (verte, en haut) — Affiche le volume TTS actuel
- **Barre multi-états** — Affiche l'utilisation de la mémoire, le volume ou la progression du script/activité selon le contexte
- **Centre de notifications** (cloche) — Onglets par type avec actions sur les messages et tout marquer comme lu
- **Indicateur d'outil** — Icône en temps réel montrant l'outil MCP utilisé par l'IA
- **Bouton micro** — Saisie vocale directe en mode chat
- **Menu Plugins** — Gérer les plugins, leurs paramètres et leurs interfaces
- **Boîte de dialogue des paramètres** — Configuration complète depuis l'interface (menu Paramètres)
- **Estompage automatique** — La fenêtre devient semi-transparente en inactivité et en plein écran
- **Écran de démarrage** — Progression du chargement au lancement
- **Thème** — Thème partagé entre l'application et tous les éditeurs

### Raccourcis

| Touche | Action |
|-------|--------|
| `Ctrl+S` | Enregistrer (dans les éditeurs) |
| Clic sur le bouton | Changer d'état |
| Molette sur le bouton | Régler le volume |
| Clic droit | Menu contextuel |
| Clic du milieu sur le bouton | Quitter |

---

## Dépannage

> **Important :** cette application dépend fortement du modèle d'IA utilisé. Des modèles inefficaces ou inadaptés à l'utilisation des outils MCP peuvent compromettre le fonctionnement.

### VASS ne démarre pas
- Vérifiez Python 3.13+ : `python --version`
- Vérifiez que `.venv` existe et contient les dépendances
- Consultez `log/debug.log` (activez `[debug] debug_enabled = true`) et `log/crash.log`

### Le micro ne fonctionne pas
- Vérifiez que le micro est connecté et n'est pas utilisé par d'autres applications
- Vérifiez les autorisations système pour le micro
- Sous Windows : Paramètres → Confidentialité → Microphone

### L'IA ne répond pas
- Vérifiez que le serveur d'IA est en cours d'exécution sur `http://127.0.0.1:8080/v1`
- Vérifiez `[ai] url` dans `config/settings.ini`
- Si vous utilisez llama.cpp, vérifiez que le modèle existe et que `[llamacpp] llama_server_path` est correct
- Consultez `log/llamacpp.log` pour les erreurs llama.cpp

### L'OCR ne reconnaît pas le texte à l'écran
- Augmentez la taille de la police ou le contraste du texte à l'écran
- EasyOCR fonctionne mieux avec de grandes polices et un contraste élevé
- La langue de l'OCR s'adapte automatiquement à la locale configurée

### L'IA ne peut pas utiliser un outil
- Certains outils en ligne requièrent votre consentement (passerelle de sécurité) — vérifiez le panneau InfoPanel pour les demandes en attente
- Vérifiez que le serveur MCP est accessible sur `http://localhost:9988` (voir `[ai] mcp_server_url`)
- Consultez `log/mcp_server.log` pour les erreurs MCP

---

## Fichiers importants

| Fichier | Description |
|------|-------------|
| `config/settings.ini` | Configuration principale |
| `config/commands.ini` | Commandes vocales de base (plus `commands_{lang}.ini`) |
| `config/notifications.ini` | Routage des notifications par type d'événement |
| `scripts/*.vass` | Vos scripts VASScript |
| `Allowed_root/events.json` | Vos événements et rappels |
| `Allowed_root/schedules.json` | Procédures automatisées |
| `Allowed_root/memory.json` | Historique des conversations et mémoire |
| `Allowed_root/private_profile.json` | Profil utilisateur injecté dans le contexte de l'IA |
| `plugins/` | Plugins internes et externes |
| `log/debug.log` | Journal de débogage verbeux (lorsqu'il est activé) |
| `log/crash.log` | Journal des plantages |
| `log/faulthandler.log` | Sortie du gestionnaire de fautes |
| `log/llamacpp.log` | Journal du serveur llama.cpp |
