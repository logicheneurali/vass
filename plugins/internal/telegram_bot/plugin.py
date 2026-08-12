"""Telegram Bot Plugin — send AI requests to VASS from Telegram.
Uses outbound HTTPS long polling to api.telegram.org (getUpdates),
so no inbound ports are opened on the machine running VASS.
"""
import configparser
import html
import json
import os
import re
import socket
import threading
import time
import uuid
from datetime import datetime

import requests


def _split_text(text, limit=4000):
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        cut = text[:limit]
        if len(text) > limit:
            idx = max(cut.rfind(" "), cut.rfind("\n"))
            if idx > limit // 2:
                cut = cut[:idx]
        chunks.append(cut)
        text = text[len(cut):].lstrip()
    return chunks


class TelegramBotPlugin:
    def __init__(self):
        self._host = "localhost"
        self._port = 8765
        self._sock = None
        self._running = True
        self._config = self._load_config()
        self._offset = None
        self._language = self._config.get("language", "it")
        self._pending = {}
        self._pending_lock = threading.Lock()
        self._pending_request = {}
        self._unlocked = {}
        self._fail = {}
        self._blocked_until = {}

    # ── Config ──────────────────────────────────────────────────

    def _load_config(self) -> dict:
        cfg = configparser.ConfigParser()
        base = os.path.dirname(os.path.abspath(__file__))
        ini_path = os.path.join(base, "settings.ini")
        if not os.path.exists(ini_path):
            example = os.path.join(base, "settings.example.ini")
            if os.path.exists(example):
                import shutil
                shutil.copy(example, ini_path)
        if os.path.exists(ini_path):
            cfg.read(ini_path, encoding="utf-8")
        raw_ids = cfg.get("telegram", "allowed_chat_ids", fallback="").strip()
        allowed = set()
        for x in raw_ids.replace(";", ",").split(","):
            x = x.strip()
            if x.lstrip("-").isdigit():
                allowed.add(int(x))
        return {
            "bot_token": cfg.get("telegram", "bot_token", fallback="").strip(),
            "allowed_chat_ids": allowed,
            "language": cfg.get("telegram", "language", fallback="it"),
            "reply_timeout": cfg.getint("telegram", "reply_timeout", fallback=240),
            "pin": cfg.get("telegram", "pin", fallback="").strip(),
            "session_hours": cfg.getint("telegram", "session_hours", fallback=24),
        }

    def _load_manifest(self) -> dict:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "plugin_manifest.json"), encoding="utf-8") as f:
            return json.load(f)

    def _log(self, msg):
        """Log to a file — plugin stdout is not captured by PluginServer."""
        try:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "log.txt"), "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {msg}\n")
        except Exception:
            pass

    # ── Daily greeting ───────────────────────────────────────────

    @staticmethod
    def _resolve_root():
        return os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    def _daily_greeting_text(self):
        now = datetime.now()
        if self._language == "it":
            wd = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì",
                  "sabato", "domenica")[now.weekday()]
            ms = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
                  "luglio", "agosto", "settembre", "ottobre", "novembre",
                  "dicembre")[now.month - 1]
            return f"Oggi è {wd} {now.day} {ms} {now.year}."
        wd = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
              "Saturday", "Sunday")[now.weekday()]
        ms = ("January", "February", "March", "April", "May", "June", "July",
              "August", "September", "October", "November",
              "December")[now.month - 1]
        return f"Today is {wd} {now.day} {ms} {now.year}."

    def _send_daily_greeting(self):
        """Send the once-a-day greeting to all authorized chats (persisted, so
        restarts do not re-send it within the same calendar day)."""
        today = time.strftime("%Y-%m-%d")
        path = os.path.join(self._resolve_root(), "Allowed_root",
                            "private_telegram_greeting.txt")
        try:
            with open(path, encoding="utf-8") as f:
                if f.read().strip() == today:
                    return
        except Exception:
            pass
        chats = self._config["allowed_chat_ids"]
        if not chats:
            self._log("Daily greeting skipped: whitelist empty")
            return
        msg = self._daily_greeting_text()
        for cid in chats:
            self._send_message(cid, msg)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(today)
        except Exception:
            pass
        self._log(f"Daily greeting sent to {len(chats)} chat(s)")

    # ── Telegram API ────────────────────────────────────────────

    def _api(self, method, payload=None, timeout=40):
        url = f"https://api.telegram.org/bot{self._config['bot_token']}/{method}"
        if payload is None:
            r = requests.get(url, timeout=timeout)
        else:
            r = requests.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()

    def _send_message(self, chat_id, text):
        for chunk in _split_text(text):
            try:
                self._api("sendMessage", {
                    "chat_id": chat_id,
                    "text": html.escape(chunk),
                    "parse_mode": "HTML",
                })
            except Exception as e:
                print(f"[Telegram] sendMessage failed: {e}")

    def _tr(self, key):
        table = {
            "welcome": {
                "it": 'Bot collegato a VASS.\nScrivi una richiesta (es. "quali sono le notizie di oggi?") oppure /stato per lo stato dell\'assistente.',
                "en": 'Connected to VASS.\nSend a request (e.g. "what are today\'s news?") or /stato for assistant status.',
            },
            "status": {
                "it": "VASS: stato = {state}\nLingua: {lang}\nVersione: {version}",
                "en": "VASS: state = {state}\nLanguage: {lang}\nVersion: {version}",
            },
            "timeout": {
                "it": "Nessuna risposta da VASS entro {sec}s (occupato o errore).",
                "en": "No response from VASS within {sec}s (busy or error).",
            },
            "bootstrap": {
                "it": "Bot VASS: il tuo chat_id è {chat_id}.\nPer abilitare questa chat, aggiungi il numero ad allowed_chat_ids in plugins/internal/telegram_bot/settings.ini, poi riavvia il plugin (o VASS).",
                "en": "VASS bot: your chat_id is {chat_id}.\nTo enable this chat, add the number to allowed_chat_ids in plugins/internal/telegram_bot/settings.ini, then restart the plugin (or VASS).",
            },
            "pin_request": {
                "it": "Chat bloccata. Invia il PIN a 6 cifre per sbloccarla. La tua richiesta sarà eseguita subito dopo lo sblocco.",
                "en": "Chat locked. Send the 6-digit PIN to unlock it. Your request will be executed right after unlocking.",
            },
            "pin_ok": {
                "it": "Chat sbloccata per {hours} ore.",
                "en": "Chat unlocked for {hours} hours.",
            },
            "pin_wrong": {
                "it": "PIN errato. Tentativi rimasti: {left}.",
                "en": "Wrong PIN. Attempts left: {left}.",
            },
            "pin_blocked": {
                "it": "Troppi tentativi. Riprova tra {minutes} minuti.",
                "en": "Too many attempts. Try again in {minutes} minutes.",
            },
        }
        entry = table.get(key, {})
        return entry.get(self._language, entry.get("en", ""))

    # ── Message handling ────────────────────────────────────────

    def _is_unlocked(self, chat_id):
        if not self._config.get("pin"):
            return True
        until = self._unlocked.get(chat_id, 0)
        if time.time() < until:
            return True
        self._unlocked.pop(chat_id, None)
        return False

    def _handle_pin(self, chat_id, text):
        now = time.time()
        blocked_until = self._blocked_until.get(chat_id, 0)
        if blocked_until > now:
            remaining = int(blocked_until - now)
            self._send_message(chat_id, self._tr("pin_blocked").format(minutes=remaining // 60))
            return
        if not re.fullmatch(r"\d{6}", text):
            self._send_message(chat_id, self._tr("pin_request"))
            return
        if text == self._config["pin"]:
            hours = self._config.get("session_hours", 24)
            self._unlocked[chat_id] = now + hours * 3600
            self._fail[chat_id] = 0
            self._blocked_until.pop(chat_id, None)
            self._log(f"Chat {chat_id} unlocked for {hours}h")
            self._send_message(chat_id, self._tr("pin_ok").format(hours=hours))
            pending = None
            with self._pending_lock:
                pending = self._pending_request.pop(chat_id, None)
            if pending:
                self._log(f"Executing stored request from chat {chat_id}")
                self._send_cmd("chat_text", {"prompt": pending,
                                             "request_id": self._new_req(chat_id)})
        else:
            fails = self._fail.get(chat_id, 0) + 1
            self._fail[chat_id] = fails
            self._log(f"Wrong PIN attempt {fails}/3 from chat {chat_id}")
            with self._pending_lock:
                self._pending_request.pop(chat_id, None)
            if fails >= 3:
                self._blocked_until[chat_id] = now + 600
                self._fail[chat_id] = 0
                self._send_message(chat_id, self._tr("pin_blocked").format(minutes=10))
            else:
                self._send_message(chat_id, self._tr("pin_wrong").format(left=3 - fails))

    def _new_req(self, chat_id):
        rid = str(uuid.uuid4())
        with self._pending_lock:
            self._pending[rid] = (chat_id, time.time())
        return rid

    def _handle_message(self, msg):
        chat_id = msg.get("chat", {}).get("id")
        if not chat_id:
            return
        text = (msg.get("text") or "").strip()
        allowed = self._config["allowed_chat_ids"]
        if chat_id not in allowed:
            self._log(f"Ignored message from unauthorized chat {chat_id}: {text[:60]!r}")
            if not allowed:
                self._log(f"Whitelist empty - sending bootstrap to {chat_id}")
                self._send_message(chat_id, self._tr("bootstrap").format(chat_id=chat_id))
            return
        if not text:
            return
        if not self._is_unlocked(chat_id):
            if not re.fullmatch(r"\d{6}", text):
                with self._pending_lock:
                    self._pending_request[chat_id] = text
                self._log(f"Stored pending request from chat {chat_id} ({len(text)} chars)")
            self._handle_pin(chat_id, text)
            return
        print(f"[Telegram] Chat {chat_id}: {text[:100]}")
        self._log(f"Chat {chat_id}: {text[:100]}")
        if text == "/start":
            self._send_message(chat_id, self._tr("welcome"))
        elif text == "/stato":
            self._send_cmd("app_info", {"request_id": self._new_req(chat_id)})
        else:
            self._send_cmd("chat_text", {"prompt": text, "request_id": self._new_req(chat_id)})

    def _handle_server_msg(self, msg):
        mtype = msg.get("type")
        rid = msg.get("request_id", "")
        chat_id = None
        with self._pending_lock:
            entry = self._pending.pop(rid, None)
            if entry:
                chat_id = entry[0]
        if mtype == "chat_response" and chat_id is not None:
            self._send_message(chat_id, msg.get("response") or "(vuoto)")
        elif mtype == "app_info_response" and chat_id is not None:
            self._send_message(chat_id, self._tr("status").format(
                state=msg.get("state", "?"),
                lang=msg.get("language", "?"),
                version=msg.get("version", "?"),
            ))

    def _purge_stale(self):
        now = time.time()
        timeout = self._config.get("reply_timeout", 240)
        stale = []
        with self._pending_lock:
            for rid, (chat_id, ts) in self._pending.items():
                if now - ts > timeout:
                    stale.append((rid, chat_id))
            for rid, _ in stale:
                del self._pending[rid]
        for rid, chat_id in stale:
            self._send_message(chat_id, self._tr("timeout").format(sec=timeout))

    # ── Loops ───────────────────────────────────────────────────

    def _poll_loop(self):
        while self._running:
            try:
                self._config = self._load_config()
                self._language = self._config.get("language", "it")
                self._send_daily_greeting()
                updates = self._api("getUpdates", {
                    "timeout": 30,
                    "offset": self._offset,
                    "allowed_updates": ["message"],
                })
                for upd in updates.get("result", []):
                    self._offset = upd["update_id"] + 1
                    self._handle_message(upd.get("message") or {})
            except requests.exceptions.Timeout:
                continue
            except requests.exceptions.ConnectionError as e:
                print(f"[Telegram] Connection error: {e}")
                self._log(f"Connection error: {e}")
                time.sleep(5)
            except requests.exceptions.HTTPError as e:
                print(f"[Telegram] API error: {e}")
                self._log(f"API error: {e}")
                time.sleep(10)
            except Exception as e:
                print(f"[Telegram] Poll error: {e}")
                self._log(f"Poll error: {e}")
                time.sleep(5)
            finally:
                self._purge_stale()

    def _send_cmd(self, cmd, params=None):
        msg = json.dumps({
            "type": "cmd", "cmd": cmd, **(params or {})
        }) + "\n"
        try:
            self._sock.sendall(msg.encode("utf-8"))
        except Exception as e:
            print(f"[Telegram] Send to VASS failed: {e}")

    def run(self):
        if not self._config["bot_token"]:
            msg = "[Telegram] No bot_token in settings.ini - bot disabled. " \
                  "Create a bot with @BotFather and set the token."
            print(msg)
            self._log(msg)
            return
        manifest = self._load_manifest()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self._sock.connect((self._host, self._port))
        except ConnectionRefusedError:
            print("[Telegram] VASS not running. Exiting.")
            self._log("VASS not running. Exiting.")
            return

        hello = json.dumps({
            "type": "hello",
            "name": manifest["name"],
            "version": manifest["version"],
            "min_app": manifest["min_app"],
            "subscribe": manifest["subscriptions"],
        }) + "\n"
        self._sock.sendall(hello.encode("utf-8"))
        print(f"[Telegram] Connected to VASS on {self._host}:{self._port}")
        self._log(f"Connected to VASS on {self._host}:{self._port}. Polling Telegram...")

        threading.Thread(target=self._poll_loop, daemon=True).start()

        buf = b""
        while self._running:
            try:
                self._sock.settimeout(1.0)
                data = self._sock.recv(4096)
            except socket.timeout:
                continue
            except (ConnectionResetError, OSError):
                print("[Telegram] Disconnected from VASS. Exiting.")
                break
            if not data:
                print("[Telegram] VASS closed connection. Exiting.")
                break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    msg = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                self._handle_server_msg(msg)

        self._running = False
        self._sock.close()


if __name__ == "__main__":
    plugin = TelegramBotPlugin()
    plugin.run()
