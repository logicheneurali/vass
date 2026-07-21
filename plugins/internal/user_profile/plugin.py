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
            print("[UserProfile] VASS not running. Exiting.")
            return

        hello = json.dumps({
            "type": "hello",
            "name": manifest["name"],
            "version": manifest["version"],
            "min_app": manifest["min_app"],
            "subscribe": manifest["subscriptions"],
        }) + "\n"
        self._sock.sendall(hello.encode("utf-8"))
        print(f"[UserProfile] Connected to VASS on {self._host}:{self._port}")

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
                    print("[UserProfile] Disconnected. Exiting.")
                    break
                if not data:
                    print("[UserProfile] Server closed connection. Exiting.")
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
            print(f"[UserProfile] Server error: {msg.get('msg', 'unknown')}")

    def _profile_loop(self):
        while self._running:
            try:
                self._maybe_build_profile()
            except Exception as e:
                print(f"[UserProfile] Profile loop error: {e}")
            interval = self._config["interval_min"] * 60
            for _ in range(int(interval)):
                if not self._running:
                    break
                time.sleep(1)

    def _maybe_build_profile(self):
        if not self._is_idle():
            return
        profile = self._load_profile()
        last = profile.get("last_updated", "")
        if last:
            try:
                import datetime
                last_dt = datetime.datetime.strptime(last, "%Y-%m-%d")
                days = (datetime.date.today() - last_dt.date()).days
                if days < 1:
                    return
            except Exception:
                pass
        data = self._collect_data(profile)
        if not data.strip():
            return
        new_sections = self._call_ai(data)
        if new_sections:
            merged = self._merge(profile, new_sections)
            self._save_profile(merged)

    def _is_idle(self):
        idle = self._send_idle_check()
        if idle is None:
            return False
        idle_s = idle["input_idle_seconds"]
        if idle_s < self._config["idle_seconds"]:
            return False
        res = self._send_resource_check()
        if res is None:
            return False
        cpu = res.get("cpu", -1); ram = res.get("ram", -1)
        gpu = res.get("gpu", -1); vram = res.get("vram", -1)
        if cpu > self._config["cpu_max"]:
            return False
        if ram > self._config["ram_max"]:
            return False
        if gpu >= 0 and gpu > self._config["gpu_max"]:
            return False
        if vram >= 0 and vram > self._config["vram_max"]:
            return False
        return True

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
                print(f"[UserProfile] Send failed: {e}")
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
            print(f"[UserProfile] {expected_type} timed out")
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
                    print(f"[UserProfile] Summary loaded: {len(summary_text)} chars")
        except Exception as e:
            print(f"[UserProfile] Error loading memory.json: {e}")

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
                print(f"[UserProfile] External data lines: {len(lines)}")
        except Exception as e:
            print(f"[UserProfile] Error loading memory_tags.json: {e}")

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
        print(f"[UserProfile] Calling AI with {len(data)} chars...")
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
