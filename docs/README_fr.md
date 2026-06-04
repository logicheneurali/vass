# VASS — Assistant Vocal Intelligent

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

Dites "**Erika**". Lorsque VASS détecte le mot d'activation, il émet un bip pour signaler qu'il est prêt à recevoir votre commande. Parlez après le bip.

Exemples :
- *"Erika, quelle heure est-il ?"*
- *"Erika, cherche les dernières actualités"*
- *"Erika, rappelle-moi la réunion demain à 14h"*

### Mode mémoire

Depuis le menu GUI ou en cliquant sur le bouton principal :
- **Full** — L'IA reçoit le résumé de la mémoire
- **Limited** — L'IA reçoit uniquement l'historique récent
- **None** — Aucun contexte historique

### Commandes vocales

Les commandes sont configurées dans `commands.ini` au format INI standard. La clé est la phrase à reconnaître, la valeur est l'action :

```ini
[general]
cherche {terme} = script:recherche
ouvre {programme} = start {programme}
actualités = script:actualites
quelle heure est-il = script:heure

[system]
éteindre le système = shutdown /s /t 60
verrouiller l'écran = rundll32.exe user32.dll,LockWorkStation
```

- `{terme}`, `{programme}` — variables capturées depuis la voix
- `script:nomscript` — exécute `scripts/nomscript.vass`
- Préfixe alternatif : `vasscript:`

Si le motif contient des variables, leurs valeurs sont passées au script comme `$param1`, `$param2`, etc.

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
