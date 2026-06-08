# VASS — Logiciel assistant vocal

## Qu'est-ce que VASS

VASS est un assistant vocal pour Windows, macOS et Linux. Il répond aux commandes vocales, exécute des scripts, gère des événements et des rappels, et interagit avec une IA locale ou distante via une API compatible OpenAI.

**Mot d'activation par défaut :** "Erika"

**Fonctionnalités principales :**
- Reconnaissance vocale via Whisper (faster-whisper)
- Synthèse vocale naturelle via Kokoro TTS
- IA locale ou distante (llama.cpp, OpenAI, tout serveur compatible)
- Scripting VASScript pour l'automatisation du bureau
- Gestion des événements et rappels
- Serveur MCP avec 15 outils pour l'orchestration IA
- Historique des conversations
- Support de 9 langues (italien, anglais, allemand, français, espagnol, portugais, japonais, coréen, chinois)

---

## Prérequis

- **Python 3.13** ou supérieur
- **Serveur IA** (llama.cpp ou compatible OpenAI) déjà installé et configuré sur le système. VASS peut démarrer automatiquement llama.cpp s'il est configuré, mais **n'installe PAS llama.cpp ni ne télécharge les modèles IA** : vous devez vous les procurer séparément.
- **Connexion internet** (pour le téléchargement des modèles et l'IA distante)
- **GPU NVIDIA recommandé** pour l'IA locale (CPU possible mais lent)
- **Microphone** fonctionnel
- Windows 10+, macOS 12+ ou Linux moderne

---

## Installation

### Installation guidée

Téléchargez ou clonez le projet, puis entrez dans le dossier et exécutez le script :

```bash
cd vass
python install.py
```

> **Note :** l'installation guidée configure VASS mais **n'installe PAS le serveur IA ni les modèles**.
> Vous devez déjà disposer d'un serveur compatible OpenAI en cours d'exécution (llama.cpp, Ollama, LM Studio, Groq, OpenAI, etc.)
> ou configurer llama.cpp dans les paramètres de VASS (qui peut le démarrer automatiquement).

**Note :** la procedure d’installation guidee est encore experimentale et peut ne pas fonctionner sur tous les systemes. En cas de probleme, utilisez la procedure d’installation manuelle ci-dessous.

L'assistant vous guidera à travers :
1. Choix de la langue
2. Vérification des prérequis (Python 3.13+, pip)
3. Dossier de destination
4. Configuration des paramètres (URL IA, modèle, mot d'activation)
5. Copie des fichiers
6. Création de l'environnement virtuel Python (.venv)
7. Installation des dépendances pip
8. Création du fichier settings.ini
9. Création du lanceur

### Installation manuelle

```bash
# Cloner ou copier les fichiers dans le dossier souhaité
cd VASS

# Créer l'environnement virtuel
python -m venv .venv

# Activer (Windows)
.venv\Scripts\activate
# ou (macOS/Linux)
source .venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt

# Installer Chromium pour Playwright (recherches web)
playwright install chromium

# Créer settings.ini (copier depuis l'exemple settings.ini)
```

---

## Configuration

Le fichier `settings.ini` contient tous les paramètres. Voici les plus importants :

| Section | Paramètre | Description |
|---------|-----------|-------------|
| `[locale]` | `language` | Langue (it/en/de/fr/es/pt/ja/ko/zh) |
| `[ai]` | `url` | URL du serveur IA compatible OpenAI |
| `[ai]` | `model` | Nom du modèle IA |
| `[ai]` | `system_message` | Personnalité de l'assistant |
| `[ai]` | `memory_tokens` | Taille maximale de la mémoire |
| `[wakeword]` | `wakeword` | Mot d'activation (défaut : erika) |
| `[wakeword]` | `sensitivity` | Sensibilité de détection (0-1) |
| `[tts]` | `volume` | Volume TTS (0-1) |

Les paramètres sont rechargés automatiquement s'ils sont modifiés pendant l'exécution de VASS.

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

### Mot d'activation

Le mot d'activation est **configurable** par l'utilisateur dans le fichier `settings.ini` et peut être n'importe quel mot ou courte phrase. Par défaut, c'est "**Erika**".

Lorsque VASS détecte le mot d'activation, il émet un bip pour signaler qu'il est prêt à recevoir la commande. Parlez après le bip.

Exemples :
- *"Erika"* (attendre le bip), puis *"quel temps fait-il ?"*
- *"Erika"* (attendre le bip), puis *"lis les actualités"*
- *"Erika"* (attendre le bip), puis *"qu'est-ce que l'intelligence artificielle ?"*
- *"Erika"* (attendre le bip), puis *"traduis en anglais bonjour tout le monde"*
- *"Erika"* (attendre le bip), puis *"recette pâtes à la carbonara"*

### Modes : Chat et Transcription

VASS peut fonctionner dans deux modes, sélectionnables depuis le menu contextuel (bouton ≡ à droite du bouton principal) :

- **Chat** `[C]` — L'application reconnaît les commandes vocales et exécute des actions (scripts, commandes système) ou interagit avec l'IA. La réponse est lue via TTS.
- **Transcription** `[T]` — Au lieu d'interpréter les commandes, VASS transcrit fidèlement ce que l'utilisateur prononce après le mot d'activation (toujours après le bip). Le texte est ensuite collé dans l'application active, faisant de VASS un système de dictée de textes.

Le mode actuel est indiqué sur le bouton principal : `[C]` pour Chat, `[T]` pour Transcription. Le dernier mode utilisé est restauré au redémarrage.

### Mode mémoire

Depuis le menu GUI ou en cliquant sur le bouton principal :
- **Full** — L'IA reçoit le résumé de la mémoire
- **Limited** — L'IA reçoit uniquement l'historique récent
- **None** — Aucun contexte historique

### Commandes vocales

Les commandes sont configurées dans `commands.ini` (format INI standard), également modifiables via l'éditeur GUI (`python commands_editor.py`). Chaque ligne est une paire **phrase = action** : la phrase est le motif à reconnaître (peut inclure `{variables}`), l'action est ce qu'il faut exécuter.

```ini
[general]
cherche {terme} = script:recherche
ouvre {programme} = start {programme}
chercher en ligne {escaped_terms} = start firefox "https://duckduckgo.com?q={escaped_terms}"
quelle heure est-il = script:heure

[system]
éteindre le système = shutdown /s /t 60
verrouiller l'écran = rundll32.exe user32.dll,LockWorkStation
```

#### Comment fonctionne la correspondance

1. **Reconnaissance floue** : une correspondance exacte n'est pas nécessaire. VASS compare la phrase prononcée à tous les motifs à l'aide d'un algorithme de similarité (`difflib`). Le motif avec le score le plus élevé au-dessus du seuil (par défaut `0.75`, configurable dans `settings.ini`) est activé.

2. **Variables `{nom}`** : capturent les mots prononcés à cette position. Exemple : en disant *"cherche chats sur internet"*, le système capture `terme = "chats sur internet"`.

3. **Variables échappées `{escaped_nom}`** : identiques aux variables normales, mais le texte capturé est encodé en URL (les espaces deviennent `%20`). Utile pour les recherches web.

4. **Fallback IA** : si aucune commande ne dépasse le seuil de similarité, la phrase est envoyée à l'IA pour une réponse en langage naturel.

#### Types d'actions

| Préfixe | Exemple | Comportement |
|---------|---------|--------------|
| `script:` | `script:recherche` | Exécute `scripts/recherche.vass`. Les variables capturées deviennent `$param1`, `$param2`, etc. |
| `vasscript:` | `vasscript:evenements` | Identique à `script:` (préfixe alternatif) |
| URL | `https://...` | Ouvert dans le navigateur par défaut |
| Commande | `shutdown /s` | Exécutée directement comme commande système |

#### Noms des sections

Les noms de section comme `[general]` et `[system]` sont de simples catégories organisationnelles — ils n'affectent pas la correspondance. C'est la **clé** (la phrase à reconnaître) qui compte.

### Créer des scripts VASScript

Ouvrez l'éditeur de scripts depuis le menu GUI ou exécutez :
```bash
python scripts_editor.py
```

Tous les scripts vont dans le dossier `scripts/` avec l'extension `.vass`.

Voir le fichier `VASCRIPT_REFERENCE.md` pour la référence complète du langage.

### Événements et rappels

Les événements sont gérés via le fichier `events.json`. Un rappel vocal est émis 1 heure à l'avance (configurable).

Les planifications (procédures automatisées) sont dans `schedule.json` et déclenchent l'exécution de commandes avec notification TTS.

---

## Interface GUI

- **Bouton principal** — Cliquer pour changer d'état (listening/paused). Molette pour le volume. Glisser pour déplacer la fenêtre.
- **Barre de volume** (verte, en haut) — Affiche le volume TTS actuel
- **Barre multi-état** — Affiche l'utilisation mémoire, le volume ou la progression du script selon le contexte
- **Auto-fade** — La fenêtre devient semi-transparente lorsque vous êtes inactif et en plein écran

### Raccourcis

| Touche | Action |
|-------|--------|
| `Ctrl+S` | Sauvegarder (dans les éditeurs) |
| Clic bouton | Changer d'état |
| Molette sur bouton | Ajuster le volume |
| Clic droit | Menu contextuel |
| Bouton "Lire" dans scripts | Lit le script avec TTS |

---

## Dépannage

### VASS ne démarre pas
- Vérifiez Python 3.13+ : `python --version`
- Vérifiez que `.venv` existe et contient les dépendances
- Consultez `debug.log` pour les erreurs

### Le microphone ne fonctionne pas
- Vérifiez que le microphone est connecté et non utilisé par d'autres applications
- Vérifiez les autorisations système pour le microphone
- Sur Windows : Paramètres → Confidentialité → Microphone

### L'IA ne répond pas
- Vérifiez que le serveur IA fonctionne sur `http://127.0.0.1:8080/v1`
- Vérifiez `[ai] url` dans `settings.ini`
- Si vous utilisez llama.cpp, vérifiez que le modèle existe dans le dossier `models/`

### L'OCR ne reconnaît pas le texte à l'écran
- Augmentez la taille de police ou le contraste du texte à l'écran
- EasyOCR fonctionne mieux avec de grandes polices et un contraste élevé
- La langue OCR s'adapte automatiquement à la locale configurée

---

## Fichiers importants

| Fichier | Description |
|------|-------------|
| `settings.ini` | Configuration principale |
| `commands.ini` | Commandes vocales personnalisées |
| `scripts/*.vass` | Vos scripts VASScript |
| `events.json` | Vos événements et rappels |
| `schedule.json` | Procédures automatisées |
| `memory.json` | Historique des conversations |
| `debug.log` | Journal de débogage |
| `vass.log` | Journal d'application |
