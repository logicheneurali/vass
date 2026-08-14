# Guide de développement des plugins VASS

Document technique décrivant le protocole de communication entre les plugins et
le PluginServer de VASS, ainsi que les règles de création de nouveaux plugins.

Références au code :

- Serveur : `src/plugin_server.py` (thread daemon `PluginServer`)
- Émission d'événements : `src/main.py` (broadcast de `state` et `audio`)
- Rendu de l'interface déclarative : `src/gui.py` (ligne 3367 et suivantes)
- Exemples de plugins : `plugins/internal/noise_auto_pause/`, `plugins/external/news_publisher/`

---

## 1. Architecture

VASS expose un **serveur TCP sur `localhost:8765`** qui s'exécute en tant que thread daemon
dans le processus principal (`PluginServer`). Les plugins sont des **processus séparés**
(le démarrage automatique les lance avec `subprocess.Popen` sur `plugin.py`) qui se connectent
au serveur via une socket.

Le serveur a deux rôles :

- **Exécute les commandes** reçues des plugins (TTS, notifications, IA, état de VASS…).
- **Diffuse des événements** aux plugins qui les ont demandés
  (`state` à chaque changement d'état, `audio` à chaque trame audio).

```
┌──────────────┐   broadcast (state/audio)   ┌──────────────────┐
│   VASS app   │ ───────────────────────────▶ │  Plugin (process)│
│  PluginServer│ ◀─────────────────────────── │                  │
│  :8765 (TCP) │      cmd + request_id        │                  │
└──────────────┘       resp. *_response       └──────────────────┘
```

## 2. Transport et protocole

- **Hôte/port :** `localhost:8765` (configurable uniquement dans le code).
- **Format :** un objet JSON par ligne, chaque message se termine par `\n`
  (`json.dumps(...) + "\n"`, `ensure_ascii=False`, UTF-8).
- **Mémoire tampon :** le serveur met en tampon les données entrantes et découpe sur `\n` ;
  les plugins doivent faire de même côté client.
- **Identification :** les messages de requête incluent un `request_id` (UUID) qui est
  renvoyé dans la réponse ; le client l'utilise pour faire correspondre les réponses asynchrones.
- **Débogage :** avec `python vass.py --debug`, le serveur journalise les messages
  reçus (`<= received: ...`, `execute: ...`).

## 3. Handshake

Immédiatement après la connexion, le plugin doit envoyer le message `hello` :

```json
{"type": "hello", "name": "my_plugin", "version": "1.0.0",
 "min_app": "0.8.0", "subscribe": ["state", "audio"]}
```

| Champ | Requis | Description |
|---|---|---|
| `type` | oui | `"hello"` |
| `name` | oui | Identifiant du plugin (doit correspondre au dossier et au manifeste) |
| `version` | oui | Version du plugin |
| `min_app` | oui | Version minimale de VASS requise ; si la version de l'application est inférieure, le serveur répond `error` et ferme la connexion |
| `subscribe` | non | Liste des types d'événements diffusés à recevoir (`"state"`, `"audio"`) |

Exemple Python :

```python
hello = json.dumps({
    "type": "hello",
    "name": manifest["name"],
    "version": manifest["version"],
    "min_app": manifest["min_app"],
    "subscribe": manifest["subscriptions"],
}) + "\n"
self._sock.sendall(hello.encode("utf-8"))
```

## 4. Messages plugin → serveur

Toutes les commandes ont la forme :

```json
{"type": "cmd", "cmd": "<command>", ...parameters}
```

### 4.1 Commandes sans réponse (fire-and-forget)

| cmd | Paramètres | Effet |
|---|---|---|
| `set_state` | `state` (p. ex. `"listening"`, `"paused"`) | Définit l'état de VASS. Si `state="listening"`, réinitialise également le plancher de bruit de la reconnaissance vocale |
| `tts_enqueue` | `text`, `speed` (défaut `0.9`) | Prononce le texte. Le texte est **automatiquement traduit** dans la langue de l'application s'il n'est pas en anglais ; la file d'attente TTS utilise `defer_if_busy=True` |
| `notify` | `text`, `priority` (défaut `5`), `data` | Affiche une notification de bureau. Le texte est traduit comme ci-dessus |
| `ui_register` | `schema` (voir §6) | Enregistre une interface déclarative associée au plugin |
| `ui_state` | `values` (dict clé→valeur) | Met à jour l'état de l'interface du plugin (interrogé par la GUI toutes les 1 s) |

### 4.2 Commandes requête/réponse

Elles doivent inclure `request_id` ; le serveur répond avec le **type** `*_response`
en utilisant le même `request_id`.

| cmd | Paramètres | Type de réponse | Champs de la réponse |
|---|---|---|---|
| `tts_to_file` | `text`, `output_path`, `speed` | `tts_file_response` | `duration_sec`, `output_path` |
| `ai_query` | `prompt`, `temperature` (0.1), `max_tokens` (300), `extra_body` | `ai_response` | `response` (chaîne) |
| `chat_text` | `prompt` | `chat_response` | `response` (passe par tout le pipeline VASS : mémoire, profil, outils) |
| `idle_check` | — | `idle_response` | `input_idle_seconds` |
| `resource_check` | — | `resource_response` | `cpu`, `ram`, `gpu`, `vram` |
| `conversation_history` | `limit` (défaut 10) | `history_response` | `history` (liste de `{"role": …}`) |
| `app_info` | — | `app_info_response` | `language`, `version`, `debug`, `state` |
| `rss_items` | `limit` (défaut 10) | `rss_response` | `items` (liste de `{title, source, summary, guid, link, pubDate}`) |
| `ui_list` | — | `ui_list_response` | `uis` (liste des noms de plugins enregistrés) |

Remarques importantes :

- `ai_query` et `chat_text` s'exécutent sur un thread dédié : la réponse peut arriver
  plus tard (ne bloquez pas la boucle d'événements sur `recv`).
- `ai_query` est sérialisé par un sémaphore (un seul appel IA à la fois).
- Si le client OpenAI n'est pas disponible, `ai_query` répond avec une chaîne JSON
  `{"error": …}` dans `response`.
- `tts_to_file` génère le fichier WAV au chemin donné et renvoie la
  durée en secondes.

Modèle client pour les requêtes synchrones :

```python
def _send_and_wait(self, cmd, params, expected_type, timeout=120):
    rid = str(uuid.uuid4())
    params = params or {}
    params["request_id"] = rid
    self._send_cmd(cmd, params)
    deadline = time.time() + timeout
    while time.time() < deadline:
        with self._lock:
            resp = self._pending_responses.pop(rid, None)
        if resp and resp.get("type") == expected_type:
            return resp
        time.sleep(0.1)
    return None
```

## 5. Messages serveur → plugin

### 5.1 Diffusion (uniquement vers les plugins abonnés)

| type | Champs | Quand |
|---|---|---|
| `state` | `state`, `prev`, `source` | À chaque changement d'état de VASS (`listening`, `paused`, `playing`, …) |
| `audio` | `rms`, `noise_floor`, `auto_paused`, `listening` | À chaque trame audio capturée |

### 5.2 Messages directs

| type | Champs | Quand |
|---|---|---|
| `error` | `msg` | Rejet du handshake (version `min_app` non satisfaite) ou erreurs du serveur |
| `cmd` avec `cmd="ui_action"` | `action` (`{key, event, values, selected}`) | L'utilisateur interagit avec l'interface déclarative du plugin depuis la GUI |

Le `_on_message` du plugin doit gérer au minimum les types `error`, `audio`,
`state` et les commandes `cmd` (`ui_action`), en suivant le modèle existant :

```python
def _on_message(self, msg):
    msg_type = msg.get("type", "")
    if msg_type == "error":
        print(f"[Plugin] Server error: {msg.get('msg', 'unknown')}")
    elif msg_type == "cmd" and msg.get("cmd") == "ui_action":
        self._handle_ui_action(msg.get("action") or {})
    elif msg_type in ("ai_response", "tts_file_response", "rss_response",
                      "chat_response", "app_info_response", ...):
        rid = msg.get("request_id", "")
        if rid:
            with self._lock:
                self._pending_responses[rid] = msg
```

## 6. Interface déclarative (`ui_register`)

Le plugin décrit son interface avec un schéma JSON ; la GUI la rend
automatiquement. L'état circule dans les deux sens :

- **Plugin → GUI :** `ui_state` avec `values`.
- **GUI → Plugin :** `ui_action` lorsque l'utilisateur appuie sur des boutons ou modifie des valeurs.

Schéma :

```json
{
  "id": "my_plugin",
  "title_it": "Italian title",
  "title": "English title",
  "sections": [
    {
      "title_it": "Section title (IT)",
      "title": "Section title",
      "rows": [
        {"kind": "toggle", "key": "flag",   "label_it": "Attivo", "label": "Enabled", "value": true, "instant": true},
        {"kind": "slider", "key": "level",  "label_it": "Livello", "label": "Level",  "min": 0, "max": 100, "value": 50, "instant": false},
        {"kind": "text",   "key": "name",   "label_it": "Nome",    "label": "Name",   "value": ""},
        {"kind": "combo",  "key": "mode",   "label_it": "Modo",    "label": "Mode",   "options": ["a", "b", "c"], "value": "a"},
        {"kind": "button", "key": "run",    "label_it": "Esegui",  "label": "Run"},
        {"kind": "list",   "key": "items",  "label_it": "Elementi", "label": "Items",
         "columns": [{"key": "name", "label_it": "Nome", "label": "Name"}],
         "items": [{"id": "1", "name": "uno"}]},
        {"kind": "label",  "key": "status", "text": "ready"}
      ]
    }
  ]
}
```

Types de lignes :

| kind | Propriétés spécifiques | Événement envoyé |
|---|---|---|
| `toggle` | `value` (bool), `instant` (bool) | `toggle` |
| `slider` | `min`, `max`, `value`, `instant` | `slider` |
| `text` | `value` | — (inclus dans `values` lorsqu'un bouton est cliqué) |
| `combo` | `options[]`, `value` | — (idem) |
| `button` | — | `button` |
| `list` | `columns[]`, `items[]` (avec `id`) | `select` avec `selected` = identifiant de l'élément |
| `label` | `text` | — |

Règles de synchronisation :

- `toggle`/`slider` avec `instant:true` envoient immédiatement le `ui_action` correspondant.
- Les widgets « mis en tampon » (`text`, `combo`, toggles/sliders non instantanés) sont
  collectés dans `values` et envoyés avec l'action du bouton.
- La GUI interroge `get_plugin_uis()` chaque seconde et applique l'état envoyé par
  le plugin (`ui_state`).

## 7. Configuration et réglages de la GUI

Chaque plugin possède son propre `settings.ini` (copié depuis `settings.example.ini` s'il
est manquant). Le plugin le lit avec sa propre méthode `_load_config()`.

**Règle importante :** les sections `[gui.<field>]` définissent les champs affichés dans la
boîte de dialogue de configuration de la GUI. Chaque champ indique dans quelle section INI
« normale » la valeur est écrite (`section`). Les clés GUI ne doivent jamais être placées
dans les sections normales.

```ini
[schedule]
interval_hours = 6

[gui.interval_hours]
type = dropdown
options = 1|2|4|6|8|12|24
label = Interval (hours)
label_it = Intervallo (ore)
section = schedule
```

Types de champs pris en charge (`get_plugin_config` dans `plugin_server.py`) :

| type | Propriétés |
|---|---|
| `slider` | `min_value`, `max_value`, `step`, `decimals` |
| `dropdown` | `options` (séparés par des barres verticales) |
| `text` | — |
| `note` | `note` / `note_<lang>` (information uniquement, n'écrit pas de valeurs) |

Chaque champ accepte `label` et `label_<lang>` pour la localisation et `section`
pour indiquer la section INI cible.

La GUI écrit les valeurs avec `PluginServer.set_plugin_value(name, section, key, value)` ;
le plugin doit les recharger (par exemple en relisant le fichier INI à la prochaine utilisation).

## 8. Structure et cycle de vie du plugin

### Arborescence des répertoires

```
plugins/
├── plugins.json                  # enabled/disabled (gitignored)
├── plugins.json.example
├── internal/<name>/              # system plugins — NOT removable
│   ├── plugin.py
│   ├── plugin_manifest.json
│   ├── settings.ini
│   └── settings.example.ini
└── external/<name>/              # user plugins — removable from the GUI
    └── (same files)
```

### `plugin_manifest.json`

```json
{
  "name": "my_plugin",
  "version": "1.0.0",
  "min_app": "0.8.0",
  "platform": "*",
  "description": "English description",
  "description_it": "Descrizione in italiano",
  "subscriptions": ["state", "audio"],
  "depends_on": ["rss_reader"]
}
```

| Champ | Description |
|---|---|
| `name` | Doit correspondre au dossier du plugin |
| `version` | Version du plugin |
| `min_app` | Version minimale de VASS |
| `platform` | `"*"` |
| `description` / `description_<lang>` | Descriptions localisées |
| `subscriptions` | Types de diffusion à recevoir (`state`, `audio`) |
| `depends_on` | Liste des plugins qui doivent être activés avant le chargement |

### `plugins/plugins.json`

```json
{
  "port": 8765,
  "plugins": {
    "my_plugin": {"enabled": true}
  }
}
```

### Cycle de vie

1. Au démarrage, `PluginServer.run()` lance automatiquement les plugins avec
   `enabled: true`, en les triant selon `depends_on` (les dépendances démarrent en premier ;
   un plugin dont des dépendances manquent reste `blocked`).
2. Chaque plugin démarre comme `subprocess.Popen([python, plugin.py], cwd=<dir>)`.
3. Au maximum **2 tentatives de démarrage** sont effectuées (puis le compteur se réinitialise).
4. `enable_plugin`/`disable_plugin`/`stop_plugin`/`start_plugin` contrôlent l'état
   d'exécution ; `remove_plugin` (externe uniquement) supprime le répertoire et l'entrée
   de configuration.
5. `get_plugins_status` renvoie pour chaque plugin : `enabled`, `running`,
   `status` (`running|blocked|error|stopped|disabled`), `missing_deps`.

## 9. Guide pas à pas : créer un plugin

Créez un plugin minimal qui utilise l'état de VASS et l'IA.

### Étape 1 — Dossier et manifeste

Créez `plugins/external/hello_plugin/` avec :

`plugin_manifest.json` :

```json
{
  "name": "hello_plugin",
  "version": "1.0.0",
  "min_app": "0.8.0",
  "platform": "*",
  "description": "Example plugin",
  "description_it": "Plugin di esempio",
  "subscriptions": ["state"],
  "depends_on": []
}
```

### Étape 2 — Paramètres

`settings.example.ini` :

```ini
[general]
greeting = Hello from VASS

[gui.greeting]
type = text
label = Greeting message
label_it = Messaggio di saluto
section = general
```

### Étape 3 — `plugin.py`

Squelette complet suivant le modèle des plugins existants :

```python
"""Example VASS plugin — standalone process connected via TCP socket."""
import json
import os
import socket
import threading
import time
import uuid
import configparser


class HelloPlugin:
    def __init__(self):
        self._host = "localhost"
        self._port = 8765
        self._sock = None
        self._buf = b""
        self._lock = threading.Lock()
        self._pending_responses = {}
        self._config = self._load_config()

    def _load_config(self):
        cfg = configparser.ConfigParser()
        ini = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.ini")
        if not os.path.exists(ini):
            ex = ini.replace("settings.ini", "settings.example.ini")
            if os.path.exists(ex):
                import shutil
                shutil.copy(ex, ini)
        if os.path.exists(ini):
            cfg.read(ini, encoding="utf-8")
        return {"greeting": cfg.get("general", "greeting", fallback="Ciao da VASS")}

    def _load_manifest(self):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "plugin_manifest.json"), encoding="utf-8") as f:
            return json.load(f)

    def run(self):
        manifest = self._load_manifest()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self._sock.connect((self._host, self._port))
        except ConnectionRefusedError:
            print("[HelloPlugin] VASS not running. Exiting.")
            return

        hello = json.dumps({
            "type": "hello", "name": manifest["name"],
            "version": manifest["version"], "min_app": manifest["min_app"],
            "subscribe": manifest["subscriptions"],
        }) + "\n"
        self._sock.sendall(hello.encode("utf-8"))

        # Greet as soon as connected
        threading.Thread(target=self._greet, daemon=True).start()

        while True:
            try:
                data = self._sock.recv(4096)
            except (ConnectionResetError, OSError):
                break
            if not data:
                break
            self._buf += data
            while b"\n" in self._buf:
                line, self._buf = self._buf.split(b"\n", 1)
                try:
                    msg = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                self._on_message(msg)

    def _on_message(self, msg):
        msg_type = msg.get("type", "")
        if msg_type == "error":
            print(f"[HelloPlugin] Server error: {msg.get('msg')}")
        elif msg_type == "state":
            print(f"[HelloPlugin] State -> {msg.get('state')}")
        elif msg_type == "cmd" and msg.get("cmd") == "ui_action":
            self._handle_ui_action(msg.get("action") or {})
        else:
            rid = msg.get("request_id", "")
            if rid:
                with self._lock:
                    self._pending_responses[rid] = msg

    def _greet(self):
        time.sleep(2)
        self._send_cmd("tts_enqueue", {"text": self._config["greeting"]})

    def _send_cmd(self, cmd, params=None):
        msg = json.dumps({"type": "cmd", "cmd": cmd, **(params or {})}) + "\n"
        try:
            self._sock.sendall(msg.encode("utf-8"))
        except Exception as e:
            print(f"[HelloPlugin] Send failed: {e}")

    def _send_and_wait(self, cmd, params, expected_type, timeout=120):
        rid = str(uuid.uuid4())
        params = params or {}
        params["request_id"] = rid
        self._send_cmd(cmd, params)
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                resp = self._pending_responses.pop(rid, None)
            if resp and resp.get("type") == expected_type:
                return resp
            time.sleep(0.1)
        return None

    def _handle_ui_action(self, action):
        key = action.get("key", "")
        if key == "speak" and action.get("event") == "button":
            self._greet()


if __name__ == "__main__":
    HelloPlugin().run()
```

### Étape 4 — Activer et tester

1. Ajoutez à `plugins/plugins.json` :
   ```json
   "hello_plugin": {"enabled": true}
   ```
2. Démarrez VASS (`python vass.py --debug`). Le serveur lance automatiquement le plugin ;
   dans le journal, vous verrez `Hello from 'hello_plugin'` et `State -> listening`
   à chaque changement d'état.
3. Vérifiez l'audio : le plugin prononce le message configuré.

## 10. Débogage et résolution de problèmes

| Symptôme | Cause probable | Solution |
|---|---|---|
| `Port 8765 already in use` | Une autre instance de VASS est en cours d'exécution | Fermez l'autre instance |
| `App version X < required Y` | `min_app` dans le manifeste dépasse la version de VASS | Abaissez `min_app` ou mettez à jour VASS |
| Plugin `error` avec `socket_missing`/`process_missing` | Processus actif mais socket non connectée (ou l'inverse) | Vérifiez le `log.txt` du plugin ; redémarrez-le |
| Pas de réponse à `ai_query` | Client OpenAI indisponible ou délai d'attente dépassé | Vérifiez `[ai]` dans `settings.ini` ; augmentez `timeout` |
| Le plugin ne démarre pas | Dépendances désactivées | Activez les plugins dans `depends_on` |
| Les modifications du code ne s'appliquent pas | Le processus est toujours en cours d'exécution | Redémarrez le plugin depuis la GUI |
| Texte TTS traduit de manière inattendue | `tts_enqueue`/`notify` traduisent dans la langue de l'application si ≠ EN | Utilisez `tts_to_file` pour contourner la traduction |

---

## Annexe — Schéma récapitulatif

```
PLUGIN ──▶ SERVER (cmd)

  hello                       {name, version, min_app, subscribe}
  set_state                   {state}
  tts_enqueue                 {text, speed}
  notify                      {text, priority, data}
  ui_register                 {schema}
  ui_state                    {values}
  tts_to_file            ─▶   tts_file_response   {request_id, duration_sec, output_path}
  ai_query               ─▶   ai_response         {request_id, response}
  chat_text              ─▶   chat_response       {request_id, response}
  idle_check             ─▶   idle_response       {request_id, input_idle_seconds}
  resource_check         ─▶   resource_response   {request_id, cpu, ram, gpu, vram}
  conversation_history   ─▶   history_response    {request_id, history}
  app_info               ─▶   app_info_response   {request_id, language, version, debug, state}
  rss_items              ─▶   rss_response        {request_id, items}
  ui_list                ─▶   ui_list_response    {request_id, uis}

SERVER ──▶ PLUGIN

  state (broadcast, subscribe)  {state, prev, source}
  audio (broadcast, subscribe)  {rms, noise_floor, auto_paused, listening}
  error (direct)                {msg}
  cmd:ui_action (direct)        {action: {key, event, values, selected}}
```
