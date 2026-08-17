"""Proactive Agent Plugin — analyzes profile and performs background actions.
Connects to VASS PluginServer for ai_query, notify, tts_enqueue, idle and resource checks.
"""
import configparser
import datetime
import json
import os
import socket
import threading
import time
import uuid


class ProactiveAgentPlugin:
    def __init__(self):
        self._host = "localhost"
        self._port = 8765
        self._sock = None
        self._sock_lock = threading.Lock()
        self._config = self._load_config()
        self._running = True
        self._pending = []
        self._actions_path = os.path.join(
            self._resolve_root(), "Allowed_root", "private_agent_actions.json")
        self._last_action_ts = 0
        self._today_count_val, self._today_messages = self._load_today_state()
        self._lang = "en"

    def _load_config(self) -> dict:
        cfg = configparser.ConfigParser()
        ini_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "settings.ini")
        if not os.path.exists(ini_path):
            example = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "settings.example.ini")
            if os.path.exists(example):
                import shutil
                shutil.copy(example, ini_path)
        if os.path.exists(ini_path):
            cfg.read(ini_path, encoding="utf-8")
        action_types = cfg.get("agent", "action_types", fallback="notify,say")
        return {
            "interval_min": cfg.getint("agent", "interval_min", fallback=60),
            "max_actions_per_day": cfg.getint("agent", "max_actions_per_day", fallback=5),
            "action_types": [t.strip().lower() for t in action_types.split(",")],
            "notify_on_idle": cfg.getboolean("agent", "notify_on_idle", fallback=True),
            "idle_seconds": cfg.getint("agent", "idle_seconds", fallback=300),
            "cpu_max": cfg.getint("agent", "cpu_max", fallback=20),
            "ram_max": cfg.getint("agent", "ram_max", fallback=70),
            "gpu_max": cfg.getint("agent", "gpu_max", fallback=30),
            "vram_max": cfg.getint("agent", "vram_max", fallback=30),
            "prefix": cfg.get("agent", "prefix", fallback="Agent"),
            "include_profile": cfg.getboolean("agent", "include_profile", fallback=True),
            "include_history": cfg.getboolean("agent", "include_history", fallback=True),
            "include_rss": cfg.getboolean("agent", "include_rss", fallback=True),
            "include_world_events": cfg.getboolean("agent", "include_world_events", fallback=True),
        }

    def _load_manifest(self) -> dict:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "plugin_manifest.json"), encoding="utf-8") as f:
            return json.load(f)

    def run(self):
        manifest = self._load_manifest()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self._sock.connect((self._host, self._port))
        except ConnectionRefusedError:
            print("[Agent] VASS not running. Exiting.")
            return

        hello = json.dumps({
            "type": "hello",
            "name": manifest["name"],
            "version": manifest["version"],
            "min_app": manifest["min_app"],
            "subscribe": manifest["subscriptions"],
        }) + "\n"
        self._sock.sendall(hello.encode("utf-8"))
        print(f"[Agent] Connected to VASS on {self._host}:{self._port}")

        self._lang = self._send_app_info().get("language", "en")

        threading.Thread(target=self._agent_loop, daemon=True).start()

        buf = b""
        while self._running:
            with self._sock_lock:
                pass
            time.sleep(0.05)
            with self._sock_lock:
                try:
                    self._sock.settimeout(0.5)
                    data = self._sock.recv(4096)
                except socket.timeout:
                    continue
                except (ConnectionResetError, OSError):
                    print("[Agent] Disconnected. Exiting.")
                    break
                if not data:
                    print("[Agent] Server closed connection. Exiting.")
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue
                    self._on_message(msg)

        self._running = False
        self._sock.close()

    def _on_message(self, msg):
        if msg.get("type") == "error":
            print(f"[Agent] Server error: {msg.get('msg', 'unknown')}")

    def _agent_loop(self):
        while self._running:
            try:
                self._check_and_act()
            except Exception as e:
                print(f"[Agent] Loop error: {e}")
            interval = self._config["interval_min"] * 60
            for _ in range(int(interval)):
                if not self._running:
                    break
                time.sleep(1)

    def _check_and_act(self):
        if not self._should_act():
            return

        profile = self._load_profile()
        if not profile:
            return

        history = self._send_history_check()

        rss_items = []
        if self._config.get("include_rss", True):
            rss_items = self._send_rss_check()

        world_events = {}
        if self._config.get("include_world_events", True):
            world_events = self._load_world_events()

        action = self._analyze(profile, history, rss_items, self._today_messages, world_events)
        if not action:
            return

        msg = action.get("message", "")
        if msg in self._today_messages:
            return

        self._execute(action)
        self._log_action(action)
        self._today_count_val += 1
        self._today_messages.add(msg)

    def _should_act(self):
        if not self._is_idle():
            return False
        if self._today_count() >= self._config.get("max_actions_per_day", 5):
            return False
        if time.time() - self._last_action_ts < 300:
            return False
        return True

    def _is_idle(self):
        idle = self._send_idle_check()
        if idle is None:
            return False
        if idle["input_idle_seconds"] < self._config["idle_seconds"]:
            return False
        res = self._send_resource_check()
        if res is None:
            return False
        cpu = res.get("cpu", -1)
        ram = res.get("ram", -1)
        gpu = res.get("gpu", -1)
        vram = res.get("vram", -1)
        if cpu > self._config["cpu_max"]:
            return False
        if ram > self._config["ram_max"]:
            return False
        if gpu >= 0 and gpu > self._config["gpu_max"]:
            return False
        if vram >= 0 and vram > self._config["vram_max"]:
            return False
        return True

    def _load_profile(self):
        path = os.path.join(self._resolve_root(), "Allowed_root", "private_profile.json")
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _today_count(self):
        return self._today_count_val

    def _load_today_state(self):
        today = time.strftime("%Y-%m-%d")
        try:
            with open(self._actions_path, encoding="utf-8") as f:
                actions = json.load(f)
            max_entries = self._config.get("max_actions_per_day", 5) * 3
            if len(actions) > max_entries:
                actions = actions[-max_entries:]
                os.makedirs(os.path.dirname(self._actions_path), exist_ok=True)
                with open(self._actions_path, "w", encoding="utf-8") as f:
                    json.dump(actions, f, ensure_ascii=False, indent=2)
            today_actions = [a for a in actions if a.get("ts", "").startswith(today)]
            return len(today_actions), {a.get("message", "") for a in today_actions}
        except Exception:
            return 0, set()

    def _load_actions(self):
        try:
            with open(self._actions_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _filter_past_dates(self, profile, today_iso):
        """Remove entries with dates before today_iso from profile."""
        if not profile:
            return profile
        result = json.loads(json.dumps(profile))  # deep copy
        health = result.get("health", {})
        if "appointments" in health:
            health["appointments"] = [
                a for a in health["appointments"]
                if a.get("date", "") >= today_iso
            ]
        if "doctors" in health:
            health["doctors"] = [
                d for d in health["doctors"]
                if d.get("date", today_iso) >= today_iso
            ]
        finance = result.get("finance", {})
        if "subscriptions" in finance:
            finance["subscriptions"] = [
                s for s in finance["subscriptions"]
                if s.get("date", "") >= today_iso
            ]
        if "recent_expenses" in finance:
            finance["recent_expenses"] = [
                e for e in finance["recent_expenses"]
                if e.get("date", "") >= today_iso
            ]
        if "routines" in result:
            result["routines"] = [
                r for r in result["routines"]
                if any(d >= today_iso for d in r.get("days", []))
            ]
        return result

    def _load_world_events(self):
        path = os.path.join(self._resolve_root(), "Allowed_root", "private_world_events.json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return {}
        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)
        events = {}
        all_events = data.get("events", {})
        for d in (yesterday.isoformat(), today.isoformat()):
            if d in all_events:
                day = all_events[d]
                sig_items = [a for a in day.get("articles", [])
                             if a.get("significance") in ("high", "medium")]
                if sig_items or day.get("summary"):
                    events[d] = {
                        "summary": day.get("summary", ""),
                        "articles": sig_items[:10],
                        "categories": day.get("categories", []),
                    }
        return events

    def _analyze(self, profile, history=None, rss_items=None, today_messages=None, world_events=None):
        today = time.strftime("%Y-%m-%d (%A) %H:%M")
        today_iso = time.strftime("%Y-%m-%d")

        profile_section = ""
        if self._config.get("include_profile", True):
            filtered = self._filter_past_dates(profile, today_iso)
            profile_section = (
                f"=== USER PROFILE ===\n"
                f"{json.dumps(filtered, ensure_ascii=False, indent=2)}\n\n"
            )

        history_section = ""
        if self._config.get("include_history", True) and history:
            lines = [f"{m.get('role', '?')}: {m.get('content', '')[:500]}" for m in history[-10:]]
            history_section = (
                f"=== RECENT CONVERSATIONS ===\n"
                f"Recent conversations:\n" + "\n".join(lines) + "\n\n"
            )

        rss_section = ""
        if self._config.get("include_rss", True) and rss_items:
            lines = [f"- {i['source']}: {i['title']}" + (f"  [{', '.join(i['tags'])}]" if i.get('tags') else "") for i in rss_items]
            rss_section = (
                f"=== RECENT RSS ARTICLES ===\n"
                + "\n".join(lines) + "\n\n"
            )

        world_section = ""
        if self._config.get("include_world_events", True) and world_events:
            lines = []
            for date_str in sorted(world_events):
                day = world_events[date_str]
                if day.get("summary"):
                    lines.append(f"[{date_str}] {day['summary']}")
                for a in day.get("articles", []):
                    lines.append(f"- {a['title']} ({a.get('source', '?')}) [{a.get('significance', '?')}]")
            if lines:
                world_section = (
                    f"=== WORLD EVENTS (high/medium significance) ===\n"
                    + "\n".join(lines) + "\n\n"
                )

        already_sent = ""
        if today_messages:
            bullet = "\n".join(f"- {m}" for m in today_messages)
            already_sent = (
                f"=== ALREADY SENT TODAY (DO NOT REPEAT) ===\n"
                f"{bullet}\n\n"
            )

        sections = []
        if profile_section: sections.append("USER PROFILE")
        if history_section: sections.append("RECENT CONVERSATIONS")
        if rss_section: sections.append("RSS ARTICLES")
        if world_section: sections.append("WORLD EVENTS")
        sections.append("ALREADY SENT TODAY")
        considering = " and ".join(f'"{s}"' for s in sections)

        prompt = (
            f"You are a personal assistant with deep knowledge of the user's profile and recent activity.\n\n"
            f"Today is {today} (ISO: {today_iso}).\n\n"
            f"Considering {considering} (which includes past advices you already gave me), "
            f"give me ONE new useful advice you haven't given before.\n\n"
            f"You can suggest:\n"
            #f"- A routine to do now (check time against routines)\n"
            f"- A medication reminder (check health.medications)\n"
            #f"- An expiring subscription (compare dates against today)\n"
            f"- A recurring expense pattern insight\n"
            f"- Someone to contact (check contacts)\n"
            f"- A follow-up from recent conversations\n"
            f"- An RSS article matching user interests/preferences\n"
            f"- A recommendation based on tech/hobby interests\n"
            f"- An upcoming medical appointment\n"
            f"- A health insight based on conditions\n"
            f"- A sleep reminder if user has early appointments tomorrow\n"
            f"- A notification about important world events the user might care about"
            f"- An event that will most likely occur based on world events."
            f"- A common pattern in world events the user might find interesting or useful\n\n"
            f"RULES:\n"
            f"- DO NOT repeat anything in ALREADY SENT TODAY\n"
            f"- ONLY use dates >= {today_iso} (past dates are ignored)\n"
            f"- ONLY suggest ONE thing\n"
            f"- Return a single JSON object: {{\"action\":\"notify\",\"message\":\"...\",\"trigger\":\"...\"}}\n\n"
            f"Examples:\n"
            f'{{"action":"notify","message":"La tua subscription Netflix scade domani, ricordati di rinnovarla","trigger":"finance"}}\n'
            f'{{"action":"notify","message":"Hai parlato di tastiere meccaniche, controlla le nuove offerte","trigger":"preferences"}}\n'
            f'{{"action":"notify","message":"Your Kiba vaccination is scheduled for tomorrow at 10am","trigger":"health"}}\n\n'
            f"{profile_section}"
            f"{history_section}"
            f"{rss_section}"
            f"{world_section}"
            f"{already_sent}"
        )
        response = self._send_ai_query(prompt, temperature=0.1, max_tokens=99999)
        if response is None:
            return {}
        raw = (response or "").strip()
        if raw.upper() == "NONE" or not raw:
            return {}
        if raw.startswith("```"):
            raw = raw.strip("`").strip()
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed[0] if parsed else {}
            return parsed
        except json.JSONDecodeError:
            return {}

    def _send_ai_query(self, prompt, temperature=0.1, max_tokens=300):
        rid = str(uuid.uuid4())
        msg = json.dumps({
            "type": "cmd",
            "cmd": "ai_query",
            "request_id": rid,
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "extra_body": {"disable_thinking": True},
        }) + "\n"
        resp = self._send_and_wait(rid, msg, "ai_response", timeout=1800)
        if resp is None:
            return None
        return resp.get("response", "")

    def _send_history_check(self):
        rid = str(uuid.uuid4())
        msg = json.dumps({
            "type": "cmd", "cmd": "conversation_history",
            "request_id": rid, "limit": 10,
        }) + "\n"
        resp = self._send_and_wait(rid, msg, "history_response", timeout=10)
        if resp is None:
            return []
        return resp.get("history", [])

    def _send_rss_check(self):
        rid = str(uuid.uuid4())
        msg = json.dumps({
            "type": "cmd", "cmd": "rss_items",
            "request_id": rid, "limit": 10,
        }) + "\n"
        resp = self._send_and_wait(rid, msg, "rss_response", timeout=10)
        if resp is None:
            return []
        return resp.get("items", [])

    def _send_app_info(self):
        rid = str(uuid.uuid4())
        msg = json.dumps({
            "type": "cmd", "cmd": "app_info",
            "request_id": rid,
        }) + "\n"
        resp = self._send_and_wait(rid, msg, "app_info_response", timeout=5)
        if resp is None:
            return {"language": "en"}
        return resp

    def _execute(self, action):
        action_type = action.get("action", "")
        message = action.get("message", "")
        if not message:
            return

        prefix = f"[{self._config['prefix']}] "
        full_msg = prefix + message

        allowed = self._config.get("action_types", ["notify"])
        if action_type not in allowed:
            return

        if action_type == "notify":
            self._send_cmd("notify", {"text": full_msg, "priority": 5})

        elif action_type == "say":
            if not self._config.get("notify_on_idle", True):
                return
            if not self._can_say():
                return
            self._send_cmd("tts_enqueue", {"text": full_msg, "defer_if_busy": True})

    def _can_say(self):
        idle = self._send_idle_check()
        if idle is None:
            return False
        return idle["input_idle_seconds"] > 60

    def _send_idle_check(self):
        rid = str(uuid.uuid4())
        msg = json.dumps({"type": "cmd", "cmd": "idle_check", "request_id": rid}) + "\n"
        return self._send_and_wait(rid, msg, "idle_response")

    def _send_resource_check(self):
        rid = str(uuid.uuid4())
        msg = json.dumps({"type": "cmd", "cmd": "resource_check", "request_id": rid}) + "\n"
        return self._send_and_wait(rid, msg, "resource_response")

    def _send_and_wait(self, rid, msg_str, expected_type, timeout=15):
        with self._sock_lock:
            try:
                self._sock.sendall(msg_str.encode("utf-8"))
            except Exception as e:
                print(f"[Agent] Send failed: {e}")
                return None
            deadline = time.time() + timeout
            buf = b""
            while time.time() < deadline:
                try:
                    self._sock.settimeout(1.0)
                    data = self._sock.recv(4096)
                except socket.timeout:
                    continue
                except Exception:
                    break
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    try:
                        resp = json.loads(line.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue
                    if resp.get("type") == expected_type and resp.get("request_id") == rid:
                        return resp
                    self._pending.append(resp)
            print(f"[Agent] {expected_type} timed out")
            return None

    def _log_action(self, action):
        actions = self._load_actions()
        actions.append({
            "action": action.get("action", ""),
            "message": action.get("message", ""),
            "trigger": action.get("trigger", ""),
            "ts": time.strftime("%Y-%m-%dT%H:%M"),
        })
        max_entries = self._config.get("max_actions_per_day", 5) * 3
        if len(actions) > max_entries:
            actions = actions[-max_entries:]
        os.makedirs(os.path.dirname(self._actions_path), exist_ok=True)
        with open(self._actions_path, "w", encoding="utf-8") as f:
            json.dump(actions, f, ensure_ascii=False, indent=2)

    def _send_cmd(self, cmd, params=None):
        msg = json.dumps({
            "type": "cmd", "cmd": cmd, **(params or {})
        }) + "\n"
        try:
            with self._sock_lock:
                self._sock.sendall(msg.encode("utf-8"))
        except Exception as e:
            print(f"[Agent] Send failed: {e}")

    @staticmethod
    def _resolve_root():
        return os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


if __name__ == "__main__":
    plugin = ProactiveAgentPlugin()
    plugin.run()
