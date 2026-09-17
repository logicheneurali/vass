"""User Profile Plugin — builds structured profile from permanent memory.
Connects to VASS PluginServer for ai_query, idle and resource checks.
"""
import configparser
import json
import os
import socket
import threading
import time
import uuid

_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log.txt")
_MAX_LOG = 100_000


def _log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [UserProfile] {msg}"
    print(line)
    try:
        if os.path.isfile(_LOG_PATH) and os.path.getsize(_LOG_PATH) > _MAX_LOG:
            with open(_LOG_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
            with open(_LOG_PATH, "w", encoding="utf-8") as f:
                f.writelines(lines[-len(lines)//2:])
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


_UI_SCHEMA = {"id": "user_profile", "title_it": "Profilo utente",
              "title": "User Profile", "sections": []}


def _format_list(value) -> list:
    """Render any profile value (str/number/bool/list/dict) into display rows."""
    if value is None:
        return []
    if isinstance(value, bool):
        return [{"value": "yes" if value else "no"}]
    if isinstance(value, str):
        return [{"value": value}] if value.strip() else []
    if isinstance(value, (int, float)):
        return [{"value": str(value)}]
    if isinstance(value, list):
        if not value:
            return []
        first = value[0]
        if isinstance(first, dict):
            return value
        return [{"value": str(v)} for v in value]
    if isinstance(value, dict):
        return [{"key": k, "value": str(v)} for k, v in value.items()]
    return [{"value": str(value)}]


def _format_label(value) -> str:
    """Render any profile value into a single-line display string."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if isinstance(value, dict):
        return ", ".join(f"{k}: {v}" for k, v in value.items())
    return str(value)


def _empty(value):
    if value is None:
        return True
    if isinstance(value, (str, list, dict)):
        return len(value) == 0
    if isinstance(value, bool):
        return False
    return False


# Section definitions: (schema_key, title_it, title, rows, data_fn, predicate).
# data_fn(profile) -> the raw section data; predicate(data) -> True to show section.
_SECTIONS = [
    ("informazioni_personali", "Informazioni personali", "Personal",
     [
        {"kind": "text", "key": "profile_name", "label_it": "Nome", "label": "Name"},
        {"kind": "text", "key": "profile_location", "label_it": "Ubicazione",
         "label": "Location"},
        {"kind": "text", "key": "profile_age", "label_it": "Età", "label": "Age"},
        {"kind": "label", "key": "profile_family", "label_it": "Familia",
         "label": "Family"},
        {"kind": "label", "key": "profile_pets", "label_it": "Animals",
         "label": "Pets"},
        {"kind": "button", "key": "refresh", "label_it": "Aggiorna", "label": "Refresh"},
        {"kind": "label", "key": "profile_empty", "label_it": "(profilo vuoto)",
         "label": "(profile empty)"},
     ],
     lambda p: p.get("personal", {}),
     lambda d: not _empty(d)),
    ("salute", "Salute", "Health",
     [
        {"kind": "list", "key": "health_conditions", "label_it": "Condizioni",
         "label": "Conditions",
         "columns": [{"key": "value", "label_it": "Condizione", "label": "Condition"}]},
        {"kind": "list", "key": "health_medications", "label_it": "Farmaci",
         "label": "Medications",
         "columns": [{"key": "name", "label_it": "Farmaco", "label": "Medicine"},
                     {"key": "dosage", "label_it": "Dosaggio", "label": "Dosage"},
                     {"key": "frequency", "label_it": "Freqenza", "label": "Frequency"}]},
        {"kind": "list", "key": "health_doctors", "label_it": "Medici",
         "label": "Doctors",
         "columns": [{"key": "name", "label_it": "Nome", "label": "Name"},
                     {"key": "specialty", "label_it": "Specialità", "label": "Specialty"}]},
        {"kind": "list", "key": "health_appointments", "label_it": "Appuntamenti",
         "label": "Appointments",
         "columns": [{"key": "description", "label_it": "Descrizione",
                      "label": "Description"},
                     {"key": "date", "label_it": "Data", "label": "Date"}]},
     ],
     lambda p: p.get("health", {}),
     lambda d: not (_empty(d.get("conditions")) and _empty(d.get("medications"))
                    and _empty(d.get("doctors")) and _empty(d.get("appointments")))),
    ("finanza", "Finanza", "Finance",
     [
        {"kind": "list", "key": "finance_subscriptions", "label_it": "Sottoscrizioni",
         "label": "Subscriptions",
         "columns": [{"key": "name", "label_it": "Nome", "label": "Name"},
                     {"key": "amount", "label_it": "Importo", "label": "Amount"},
                     {"key": "date", "label_it": "Data", "label": "Date"}]},
        {"kind": "list", "key": "finance_recent_expenses", "label_it": "Spese recenti",
         "label": "Recent expenses",
         "columns": [{"key": "description", "label_it": "Descrizione",
                      "label": "Description"},
                     {"key": "amount", "label_it": "Importo", "label": "Amount"},
                     {"key": "date", "label_it": "Data", "label": "Date"}]},
     ],
     lambda p: p.get("finance", {}),
     lambda d: not (_empty(d.get("subscriptions")) and _empty(d.get("recent_expenses")))),
    ("preferenze", "Preferenze", "Preferences",
     [
        {"kind": "label", "key": "pref_food", "label_it": "Cibo", "label": "Food"},
        {"kind": "label", "key": "pref_tech", "label_it": "Tecnologia", "label": "Tech"},
        {"kind": "label", "key": "pref_habits", "label_it": "Abitudini", "label": "Habits"},
        {"kind": "label", "key": "pref_interests", "label_it": "Interessi",
         "label": "Interests"},
     ],
     lambda p: p.get("preferences", {}),
     lambda d: not (_empty(d.get("food")) and _empty(d.get("tech")) and _empty(d.get("habits"))
                    and _empty(d.get("interests")))),
    ("contatti", "Contatti", "Contacts",
     [
        {"kind": "list", "key": "contacts", "label_it": "Contatti", "label": "Contacts",
         "columns": [{"key": "name", "label_it": "Nome", "label": "Name"},
                     {"key": "role", "label_it": "Ruolo", "label": "Role"},
                     {"key": "context", "label_it": "Contesto", "label": "Context"}]},
     ],
     lambda p: p.get("contacts", []),
     lambda d: not _empty(d)),
    ("routine", "Routine", "Routines",
     [
        {"kind": "list", "key": "routines", "label_it": "Routine", "label": "Routines",
         "columns": [{"key": "task", "label_it": "Attività", "label": "Task"},
                     {"key": "time", "label_it": "Orario", "label": "Time"},
                     {"key": "days", "label_it": "Giorni", "label": "Days"}]},
     ],
     lambda p: p.get("routines", []),
     lambda d: not _empty(d)),
]


def _build_schema(profile):
    """Assemble the profile-viewer schema dynamically from the profile contents.

    A section appears only when its data predicate is satisfied, so the rendered
    dialog reflects exactly what private_profile.json currently contains.
    """
    schema = {"id": "user_profile", "title_it": "Profilo utente",
              "title": "User Profile", "sections": []}
    for key, title_it, title, rows, data_fn, pred in _SECTIONS:
        data = data_fn(profile)
        if pred(data):
            schema["sections"].append({"title_it": title_it, "title": title, "rows": rows})
    return schema


def _empty(value):
    if value is None:
        return True
    if isinstance(value, (str, list, dict)):
        return len(value) == 0
    if isinstance(value, bool):
        return False
    return False


class UserProfilePlugin:
    def __init__(self):
        self._host = "localhost"
        self._port = 8765
        self._sock = None
        self._sock_lock = threading.Lock()
        self._config = self._load_config()
        self._running = True
        self._pending = []

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
        return {
            "interval_min": cfg.getint("profile", "interval_min", fallback=60),
            "idle_seconds": cfg.getint("profile", "idle_seconds", fallback=300),
            "cpu_max": cfg.getint("profile", "cpu_max", fallback=20),
            "ram_max": cfg.getint("profile", "ram_max", fallback=70),
            "gpu_max": cfg.getint("profile", "gpu_max", fallback=30),
            "vram_max": cfg.getint("profile", "vram_max", fallback=30),
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
            _log(" VASS not running. Exiting.")
            return

        hello = json.dumps({
            "type": "hello",
            "name": manifest["name"],
            "version": manifest["version"],
            "min_app": manifest["min_app"],
            "subscribe": manifest["subscriptions"],
        }) + "\n"
        self._sock.sendall(hello.encode("utf-8"))
        _log(f" Connected to VASS on {self._host}:{self._port}")

        # Register the profile-viewer UI (schema built dynamically from the profile)
        # and push the initial profile state.
        profile = self._load_profile()
        self._dynamic_schema = _build_schema(profile)
        self._send_cmd("ui_register", {"schema": self._dynamic_schema})
        self._send_cmd("ui_state", {"values": self._render_profile_state()})

        threading.Thread(target=self._profile_loop, daemon=True).start()

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
                    _log(" Disconnected. Exiting.")
                    break
                if not data:
                    _log(" Server closed connection. Exiting.")
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
        msg_type = msg.get("type", "?")
        if msg_type != "audio":
            _log(f" <= received: type={msg_type} rid={msg.get('request_id','-')[:8]}")
        if msg_type == "error":
            _log(f" Server error: {msg.get('msg', 'unknown')}")
        elif msg_type == "cmd" and msg.get("cmd") == "ui_action":
            self._handle_ui_action(msg.get("action") or {})
        else:
            self._pending.append(msg)
            if len(self._pending) > 100:
                self._pending = self._pending[-50:]

    def _profile_loop(self):
        last_skip = ""
        while self._running:
            try:
                reason = self._maybe_build_profile()
                if reason and reason != last_skip:
                    _log(f" {reason}")
                    last_skip = reason
                elif reason is None:
                    last_skip = ""
            except Exception as e:
                _log(f" Profile loop error: {e}")
            interval = self._config["interval_min"] * 60
            for _ in range(int(interval)):
                if not self._running:
                    break
                time.sleep(1)

    def _maybe_build_profile(self):
        idle_reason = self._is_idle()
        if idle_reason:
            return idle_reason
        profile = self._load_profile()
        last = profile.get("last_updated", "")
        if last:
            try:
                import datetime
                last_dt = datetime.datetime.strptime(last, "%Y-%m-%d")
                days = (datetime.date.today() - last_dt.date()).days
                if days < 1:
                    return f"Skip: already updated today ({last})"
            except Exception:
                pass
        data = self._collect_data(profile)
        if not data.strip():
            return "Skip: no data (memory empty)"
        _log(f" Data collected: {len(data)} chars, calling AI...")
        new_sections = self._call_ai(data)
        if new_sections:
            if "error" not in new_sections:
                merged = self._merge(profile, new_sections)
                self._save_profile(merged)
                self._send_cmd("notify", {"text": "User profile updated", "priority": 4, "data": {"type": "profile"}})
                _log(" Profile updated and notification sent")
            else:
                _log(f" Skip: AI returned error: {new_sections.get('error')}")
        else:
            return "Skip: AI returned no sections (timeout/error/invalid JSON)"
        return None


    def _is_idle(self):
        idle = self._send_idle_check()
        if idle is None:
            return "Skip: idle check failed (server unreachable)"
        idle_s = idle["input_idle_seconds"]
        if idle_s < self._config["idle_seconds"]:
            return f"Skip: not idle ({idle_s}s < {self._config['idle_seconds']}s)"
        res = self._send_resource_check()
        if res is None:
            return "Skip: resource check failed"
        cpu = res.get("cpu", -1); ram = res.get("ram", -1)
        gpu = res.get("gpu", -1); vram = res.get("vram", -1)
        if cpu > self._config["cpu_max"]:
            return f"Skip: CPU too high ({cpu:.0f}% > {self._config['cpu_max']}%)"
        if ram > self._config["ram_max"]:
            return f"Skip: RAM too high ({ram:.0f}% > {self._config['ram_max']}%)"
        if gpu >= 0 and gpu > self._config["gpu_max"]:
            return f"Skip: GPU too high ({gpu:.0f}% > {self._config['gpu_max']}%)"
        if vram >= 0 and vram > self._config["vram_max"]:
            return f"Skip: VRAM too high ({vram:.0f}% > {self._config['vram_max']}%)"
        return None

    def _send_cmd(self, cmd, params=None):
        msg = json.dumps({
            "type": "cmd", "cmd": cmd, **(params or {})
        }, ensure_ascii=False) + "\n"
        with self._sock_lock:
            try:
                self._sock.sendall(msg.encode("utf-8"))
            except Exception as e:
                _log(f" Send '{cmd}' failed: {e}")

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
                _log(f" Send failed: {e}")
                return None
        deadline = time.time() + timeout
        while time.time() < deadline:
            for i, resp in enumerate(self._pending):
                if resp.get("type") == expected_type and resp.get("request_id") == rid:
                    return self._pending.pop(i)
            time.sleep(0.1)
        pending_types = [r.get("type") for r in self._pending[-5:]]
        _log(f" {expected_type} timed out (pending: {pending_types})")
        return None

    def _collect_data(self, existing_profile):
        root = self._resolve_root()
        parts = []
        if existing_profile:
            parts.append(f"Existing profile:\n{json.dumps(existing_profile, ensure_ascii=False, indent=2)}")

        mem_path = os.path.join(root, "Allowed_root", "memory.json")
        try:
            with open(mem_path, encoding="utf-8") as f:
                mem_data = json.load(f)
            sid = mem_data.get("summary_id", "")
            if sid:
                sf_path = os.path.join(root, "Allowed_root", "memory", f"{sid}.json")
                if os.path.exists(sf_path):
                    with open(sf_path, encoding="utf-8") as sf:
                        summary_text = json.load(sf).get("info", "")
                    parts.append(f"Summary:\n{summary_text}")
                    _log(f" Summary loaded: {len(summary_text)} chars")
        except Exception as e:
            _log(f" Error loading memory.json: {e}")

        tags_path = os.path.join(root, "Allowed_root", "memory_tags.json")
        try:
            with open(tags_path, encoding="utf-8") as f:
                tags_data = json.load(f)
            entries = tags_data.get("entries", [])
            if entries:
                lines = []
                for e in entries[-50:]:
                    src = e.get("source", "?")
                    tags = ", ".join(e.get("tags", []))
                    content = e.get("content", "")[:300]
                    if content:
                        lines.append(f"[{src}] [{tags}] {content}")
                parts.append("Recent external data:\n" + "\n".join(lines))
                _log(f" External data lines: {len(lines)}")
        except Exception as e:
            _log(f" Error loading memory_tags.json: {e}")

        return "\n\n".join(parts)

    def _call_ai(self, data):
        prompt = (
            "You are a profile builder. Based on the data below, extract or update "
            "user facts into this JSON structure. Be concise: max 200 chars per field. "
            "Return ONLY valid JSON, nothing else.\n\n"
            "CRITICAL: Include dates in YYYY-MM-DD format for all time-sensitive data:\n"
            "- finance: each expense/subscription MUST have a 'date' field\n"
            "- health: each appointment/event MUST have a 'date' field\n"
            "- routines: each task MUST include timing or days\n"
            "- Extract dates from filenames, file paths, and content text.\n"
            "- The 'ts' field is the SCAN date, NOT the event/purchase date. IGNORE IT.\n\n"
            "Sections:\n"
            "  personal: {name, family, pets, location}\n"
            "  health: {conditions: [], medications: [{name, dosage, frequency}], "
            "doctors: [{name, specialty}], appointments: [{description, date}]}\n"
            "  finance: {subscriptions: [{name, amount, date}], "
            "recent_expenses: [{description, amount, date}]}\n"
            "  preferences: {food: [], tech: [], habits: [], interests: []}\n"
            "  contacts: [{name, role, context}]\n"
            "  routines: [{task, time, days}]\n\n"
            "Example (with dates): "
            "{\"finance\": {\"subscriptions\": [{\"name\": \"Netflix\", \"amount\": \"19.99 EUR\", \"date\": \"2026-07-08\"}]}, "
            "\"health\": {\"appointments\": [{\"description\": \"ecografia tiroide\", \"date\": \"2026-07-06\"}]}, ...}\n\n"
            f"Data:\n{data[:8000]}"
        )
        _log(f" Calling AI with {len(data)} chars...")
        return self._send_ai_query(prompt, temperature=0.2, max_tokens=99999)

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
        raw = (resp.get("response", "") or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`").strip()
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def _merge(self, old, new):
        for section in new:
            if section in ("last_updated", "last_source_ids"):
                continue
            if section not in old:
                old[section] = new[section]
            elif isinstance(new[section], dict) and isinstance(old.get(section), dict):
                old[section].update(new[section])
            elif isinstance(new[section], list) and isinstance(old.get(section), list):
                existing = {str(v) for v in old[section]}
                for item in new[section]:
                    if str(item) not in existing:
                        old[section].append(item)
                        existing.add(str(item))
        old["last_updated"] = time.strftime("%Y-%m-%d")
        return old

    def _load_profile(self):
        path = os.path.join(self._resolve_root(), "Allowed_root", "private_profile.json")
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _render_profile_state(self) -> dict:
        """Build the ui_state dict that renders the profile viewer."""
        profile = self._load_profile()
        state = {}
        personal = profile.get("personal", {}) or {}
        health = profile.get("health", {}) or {}
        finance = profile.get("finance", {}) or {}
        prefs = profile.get("preferences", {}) or {}
        contacts = profile.get("contacts", []) or []
        routines = profile.get("routines", []) or []

        state["profile_name"] = _format_label(personal.get("name"))
        state["profile_location"] = _format_label(personal.get("location"))
        state["profile_age"] = _format_label(personal.get("age"))
        state["profile_family"] = _format_label(personal.get("family"))
        state["profile_pets"] = _format_label(personal.get("pets"))

        state["health_conditions"] = _format_list(health.get("conditions"))
        state["health_medications"] = _format_list(health.get("medications"))
        state["health_doctors"] = _format_list(health.get("doctors"))
        state["health_appointments"] = _format_list(health.get("appointments"))

        state["finance_subscriptions"] = _format_list(finance.get("subscriptions"))
        state["finance_recent_expenses"] = _format_list(finance.get("recent_expenses"))

        state["pref_food"] = _format_label(prefs.get("food"))
        state["pref_tech"] = _format_label(prefs.get("tech"))
        state["pref_habits"] = _format_label(prefs.get("habits"))
        state["pref_interests"] = _format_label(prefs.get("interests"))

        state["contacts"] = _format_list(contacts) or []
        state["routines"] = _format_list(routines) or []

        if not (personal or health or finance or prefs or contacts or routines):
            state["profile_empty"] = True
        return state

    def _handle_ui_action(self, action):
        """Handle UI actions from the profile viewer dialog."""
        key = action.get("key", "")
        event = action.get("event", "")
        if key == "refresh" and event in ("button", "click"):
            _log(" Refresh requested from profile viewer")
            self._send_cmd("ui_state", {"values": self._render_profile_state()})

    def _save_profile(self, data):
        path = os.path.join(self._resolve_root(), "Allowed_root", "private_profile.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _resolve_root():
        return os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


if __name__ == "__main__":
    plugin = UserProfilePlugin()
    plugin.run()
