"""PluginServer — TCP server for socket-based plugin communication.
Plugins are separate processes that connect via localhost TCP.
The server broadcasts events and executes commands from plugins.
"""
import json
import os
import select
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from configparser import ConfigParser
from pathlib import Path
from activity_tracker import get_tracker


class PluginServer(threading.Thread):
    """TCP server for plugin communication. Runs as a daemon thread."""

    def __init__(self, app, port: int = 8765):
        super().__init__(daemon=True)
        self._app = app
        self._port = port
        self._sock = None
        self._clients = {}          # socket -> {"name", "subscribe", "version"}
        self._buffers = {}         # socket -> bytearray (incomplete messages)
        self._processes = {}        # name -> subprocess.Popen
        self._start_attempts = {}   # name -> count (for retry limit)
        self._lock = threading.Lock()
        self._ai_semaphore = threading.Semaphore(1)
        self._running = False
        self._plugin_dir = self._resolve_path("plugins")

    # ── Thread run ──────────────────────────────────────────────

    @staticmethod
    def _port_in_use(port):
        """Return True if another process is already listening on the port."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect(("localhost", port))
            s.close()
            return True
        except Exception:
            return False

    def run(self):
        self._running = True
        if self._port_in_use(self._port):
            print(f"[PluginServer] Port {self._port} already in use — "
                  f"another VASS instance is running")
            self._notify_port_conflict()
            return
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._sock.bind(("localhost", self._port))
            self._sock.listen(5)
            print(f"[PluginServer] Listening on localhost:{self._port}")
        except OSError as e:
            print(f"[PluginServer] Bind failed: {e}")
            self._notify_port_conflict()
            return

        self._auto_start_plugins()

        while self._running:
            try:
                readable, _, _ = select.select(
                    [self._sock] + list(self._clients.keys()), [], [], 1.0)
            except Exception:
                continue

            for sock in readable:
                try:
                    if sock is self._sock:
                        self._accept()
                    else:
                        self._receive(sock)
                except Exception as e:
                    print(f"[PluginServer] Loop error: {e}")
                    self._remove_client(sock)

        self._sock.close()

    def stop(self):
        self._running = False
        # Terminate all plugin subprocesses to avoid orphan processes
        # that keep the port busy across restarts.
        for name in list(self._processes.keys()):
            try:
                self.stop_plugin(name)
            except Exception:
                pass
        if self._sock:
            self._sock.close()

    def _notify_port_conflict(self):
        """Warn the user (GUI thread) that another VASS instance holds the port."""
        app = self._app
        gui = getattr(app, "gui", None) if app else None
        if not gui:
            return
        try:
            from i18n import t
            lang = getattr(app, "language", "it")
            title = t("plugins.port_conflict_title", lang)
            msg = t("plugins.port_conflict_msg", lang)

            def _show():
                from PySide6.QtWidgets import QMessageBox, QApplication
                QMessageBox.warning(None, title, msg)
                QApplication.quit()

            gui.schedule_signal.emit(_show)
        except Exception as e:
            print(f"[PluginServer] Port conflict notification failed: {e}")

    # ── Broadcast ───────────────────────────────────────────────

    def broadcast(self, event_type: str, data: dict):
        """Send event to all subscribed clients."""
        msg = json.dumps({"type": event_type, **data}, ensure_ascii=False) + "\n"
        msg_bytes = msg.encode("utf-8")
        with self._lock:
            dead = []
            for sock, info in self._clients.items():
                if event_type not in info.get("subscribe", []):
                    continue
                try:
                    sock.sendall(msg_bytes)
                except Exception:
                    dead.append(sock)
            for sock in dead:
                self._remove_client(sock)

    # ── Internal: accept / receive ──────────────────────────────

    def _accept(self):
        try:
            sock, addr = self._sock.accept()
            with self._lock:
                self._clients[sock] = {"name": "pending", "subscribe": [], "version": "?"}
            print(f"[PluginServer] Connection from {addr}")
        except Exception:
            return

    def _receive(self, sock):
        try:
            data = sock.recv(4096)
        except Exception:
            self._remove_client(sock)
            return

        if not data:
            self._remove_client(sock)
            return

        buf = self._buffers.get(sock, b"") + data
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            try:
                msg = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                print(f"[PluginServer] JSON decode failed, len={len(line)} "
                      f"preview={line[:200]}")
                self._buffers[sock] = buf
                return

            if self._app and getattr(self._app, 'debug_enabled', False):
                msg_preview = {k: v for k, v in msg.items()}
                if 'text' in msg_preview:
                    msg_preview['text'] = msg_preview['text'][:60]
                print(f"[PluginServer] <= received: {json.dumps(msg_preview, ensure_ascii=False)}")

            msg_type = msg.get("type", "")

            if msg_type == "hello":
                self._handle_hello(sock, msg)
            elif msg_type == "cmd":
                self._execute(msg, sock)

        self._buffers[sock] = buf

    # ── Handshake ───────────────────────────────────────────────

    def _handle_hello(self, sock, msg):
        name = msg.get("name", "unknown")
        version = msg.get("version", "0.0.0")
        min_app = msg.get("min_app", "0.0.0")
        subscribe = msg.get("subscribe", [])

        app_ver = getattr(self._app, 'app_version', '0.0.0')

        # Version check
        if self._version_cmp(app_ver, min_app) < 0:
            try:
                err = json.dumps({
                    "type": "error",
                    "msg": f"App version {app_ver} < required {min_app}"
                }) + "\n"
                sock.sendall(err.encode())
            except Exception:
                pass
            sock.close()
            print(f"[PluginServer] Rejected '{name}': app {app_ver} < {min_app}")
            return

        with self._lock:
            self._clients[sock] = {
                "name": name, "version": version,
                "subscribe": subscribe}

        name_out = msg.get("name", "unknown")
        print(f"[PluginServer] Hello from '{name_out}' v{version}, "
              f"subscriptions: {subscribe}")

    # ── Execute commands ────────────────────────────────────────

    def _execute(self, msg, sock=None):
        cmd = msg.get("cmd", "")
        try:
            if self._app and getattr(self._app, 'debug_enabled', False):
                print(f"[PluginServer] execute: {cmd} {msg.get('state','')} {msg.get('source','')}")
            if cmd == "set_state":
                self._app.set_state(msg["state"], detail="auto")
                if self._app.voice_recognition and msg["state"] == "listening":
                    self._app.voice_recognition.reset_noise_floor()
            elif cmd == "tts_enqueue":
                text = self._maybe_translate(msg["text"])
                router = getattr(self._app, "notification_router", None)
                if router is not None:
                    router.emit("plugins", text,
                                tts_kwargs={"speed": msg.get("speed", 0.9),
                                            "defer_if_busy": True})
                else:
                    self._app.tts.enqueue(
                        text, speed=msg.get("speed", 0.9), defer_if_busy=True)
            elif cmd == "tts_to_file" and sock:
                text = msg.get("text", "")
                output_path = msg.get("output_path", "")
                speed = msg.get("speed", 0.9)
                dur = self._app.tts.generate_to_file(text, output_path, speed)
                reply = json.dumps({
                    "type": "tts_file_response",
                    "request_id": msg.get("request_id", ""),
                    "duration_sec": dur,
                    "output_path": output_path,
                }, ensure_ascii=False) + "\n"
                sock.sendall(reply.encode("utf-8"))
            elif cmd == "notify":
                text = self._maybe_translate(msg["text"])
                router = getattr(self._app, "notification_router", None)
                if router is not None:
                    router.emit("plugins", text,
                                priority=msg.get("priority", 5),
                                data=msg.get("data", None))
                else:
                    self._app.notification_manager.add(
                        text, priority=msg.get("priority", 5),
                        data=msg.get("data", None))
            elif cmd == "ai_query" and sock:
                threading.Thread(
                    target=self._handle_ai_query,
                    args=(msg, sock),
                    daemon=True,
                ).start()
            elif cmd == "chat_text" and sock:
                threading.Thread(
                    target=self._handle_chat_text,
                    args=(msg, sock),
                    daemon=True,
                ).start()
            elif cmd == "idle_check" and sock:
                if hasattr(self._app, 'idle_tracker') and self._app.idle_tracker:
                    input_idle = self._app.idle_tracker.get_total_idle_seconds()
                else:
                    from idle_tracker import IdleTracker
                    input_idle = IdleTracker().get_total_idle_seconds()
                reply = json.dumps({
                    "type": "idle_response",
                    "request_id": msg.get("request_id", ""),
                    "input_idle_seconds": input_idle,
                }, ensure_ascii=False) + "\n"
                sock.sendall(reply.encode("utf-8"))
                print(f"[PluginServer] idle_check => {input_idle:.1f}s")
            elif cmd == "resource_check" and sock:
                from resource_monitor import check_resources
                try:
                    res_ok, res_data = check_resources(
                        {"cpu_max": 100, "ram_max": 100, "gpu_max": 100, "vram_max": 100})
                except Exception:
                    res_data = {}
                reply = json.dumps({
                    "type": "resource_response",
                    "request_id": msg.get("request_id", ""),
                    "cpu": res_data.get("cpu", -1),
                    "ram": res_data.get("ram", -1),
                    "gpu": res_data.get("gpu", -1),
                    "vram": res_data.get("vram", -1),
                }, ensure_ascii=False) + "\n"
                sock.sendall(reply.encode("utf-8"))
                print(f"[PluginServer] resource_check => cpu={res_data.get('cpu',-1)} "
                      f"ram={res_data.get('ram',-1)} gpu={res_data.get('gpu',-1)} "
                      f"vram={res_data.get('vram',-1)}")
            elif cmd == "conversation_history" and sock:
                limit = msg.get("limit", 10)
                history = self._load_conversation_history(limit)
                reply = json.dumps({
                    "type": "history_response",
                    "request_id": msg.get("request_id", ""),
                    "history": history,
                }, ensure_ascii=False) + "\n"
                sock.sendall(reply.encode("utf-8"))
            elif cmd == "app_info" and sock:
                reply = json.dumps({
                    "type": "app_info_response",
                    "request_id": msg.get("request_id", ""),
                    "language": getattr(self._app, 'language', 'en'),
                    "version": getattr(self._app, 'app_version', '?'),
                    "debug": getattr(self._app, 'debug_enabled', False),
                    "state": getattr(self._app, 'state', '?'),
                }, ensure_ascii=False) + "\n"
                sock.sendall(reply.encode("utf-8"))
            elif cmd == "rss_items" and sock:
                limit = msg.get("limit", 10)
                items = self._load_rss_cache(limit)
                reply = json.dumps({
                    "type": "rss_response",
                    "request_id": msg.get("request_id", ""),
                    "items": items,
                }, ensure_ascii=False) + "\n"
                sock.sendall(reply.encode("utf-8"))
        except Exception as e:
            print(f"[PluginServer] Execute '{cmd}' failed: {e}")

    def _maybe_translate(self, text):
        """Translate text if app language is not English."""
        lang = getattr(self._app, 'language', 'en')
        if not lang or lang == 'en':
            return text
        lang_names = {
            "it": "Italian", "de": "German", "fr": "French", "es": "Spanish",
            "pt": "Portuguese", "ja": "Japanese", "ko": "Korean", "zh": "Chinese",
        }
        lang_name = lang_names.get(lang, lang)
        try:
            prompt = (
                f"Translate this text to {lang_name}. "
                f"Return ONLY the translation, nothing else — no quotes, no explanations:\n\n{text}"
            )
            result = self._call_ai(prompt, temperature=0.1, max_tokens=len(text) * 2,
                                    extra_body={"disable_thinking": True})
            if result and not result.startswith('{'):
                return result.strip()
        except Exception as e:
            print(f"[PluginServer] Translation failed: {e}")
        return text

    def _call_ai(self, prompt, temperature=0.1, max_tokens=300, extra_body=None):
        """Proxy LLM call for plugins. Blocks until response received."""
        if not self._app or not self._app.openai_client:
            print(f"[PluginServer] _call_ai: openai_client is None, returning error")
            return json.dumps({"error": "OpenAI client not available"})
        body = {"temperature": temperature, "max_tokens": max_tokens}
        if extra_body:
            body["extra_body"] = extra_body
        tracker = get_tracker(); tracker.start("Plugin AI", "plugin")
        t0 = time.time()
        print(f"[PluginServer] _call_ai: model={self._app.ai_model} url={self._app.ai_url} prompt_len={len(prompt)} max_tokens={max_tokens}")
        try:
            from utils import call_with_retry
            resp = call_with_retry(
                lambda: self._app.openai_client.chat.completions.create(
                    model=self._app.ai_model,
                    messages=[{"role": "user", "content": prompt}],
                    **body,
                ),
                retries=1, delays=(3,), log_prefix="[PluginServer]"
            )
            dur = time.time() - t0
            content = resp.choices[0].message.content or ""
            print(f"[PluginServer] _call_ai: OK in {dur:.1f}s response_len={len(content)}")
            return content
        except Exception as e:
            dur = time.time() - t0
            print(f"[PluginServer] _call_ai: FAILED in {dur:.1f}s: {e}")
            return json.dumps({"error": str(e)})
        finally:
            tracker.end("Plugin AI")

    def _handle_ai_query(self, msg, sock):
        """Execute an AI query in a background thread so the select loop stays responsive."""
        with self._ai_semaphore:
            try:
                response = self._call_ai(
                    msg["prompt"],
                    temperature=msg.get("temperature", 0.1),
                    max_tokens=msg.get("max_tokens", 300),
                    extra_body=msg.get("extra_body", None),
                )
                reply = json.dumps({
                    "type": "ai_response",
                    "request_id": msg.get("request_id", ""),
                    "response": response,
                }, ensure_ascii=False) + "\n"
                try:
                    sock.sendall(reply.encode("utf-8"))
                except Exception:
                    pass
            except Exception as e:
                print(f"[PluginServer] _handle_ai_query error: {e}")

    def _handle_chat_text(self, msg, sock):
        """Forward text through the full VASS chat pipeline (memory, profile,
        tools, voice commands) and send the final response back to the caller.
        The reply callback may fire on a different thread — sendall is safe."""
        app = self._app
        if app is None or not hasattr(app, "chat_remote"):
            reply = json.dumps({
                "type": "chat_response",
                "request_id": msg.get("request_id", ""),
                "response": "VASS chat pipeline not available",
            }, ensure_ascii=False) + "\n"
            try:
                sock.sendall(reply.encode("utf-8"))
            except Exception:
                pass
            return
        prompt = (msg.get("prompt") or "").strip()
        if not prompt:
            reply = json.dumps({
                "type": "chat_response",
                "request_id": msg.get("request_id", ""),
                "response": "Empty prompt",
            }, ensure_ascii=False) + "\n"
            try:
                sock.sendall(reply.encode("utf-8"))
            except Exception:
                pass
            return

        def _reply(text):
            reply = json.dumps({
                "type": "chat_response",
                "request_id": msg.get("request_id", ""),
                "response": text,
            }, ensure_ascii=False) + "\n"
            try:
                sock.sendall(reply.encode("utf-8"))
            except Exception:
                pass

        try:
            app.chat_remote(prompt, reply_cb=_reply)
        except Exception as e:
            print(f"[PluginServer] _handle_chat_text error: {e}")
            _reply(f"Error: {e}")

    # ── Auto-start plugins ──────────────────────────────────────

    def _auto_start_plugins(self):
        config = self._load_config()
        plugins_enabled = config.get("plugins", {})
        print(f"[PluginServer] Auto-start: {len(plugins_enabled)} plugins in config")
        # Sort: plugins with no dependencies first, then those that depend on already-started ones
        names = list(plugins_enabled.keys())
        started = set()
        for name in sorted(names, key=lambda n: len(self._load_manifest(n).get("depends_on", []))):
            cfg = plugins_enabled[name]
            print(f"[PluginServer]   {name}: enabled={cfg.get('enabled', False)}")
            if not cfg.get("enabled", False):
                continue
            deps_ok, missing = self._check_deps(name)
            if not deps_ok:
                print(f"[PluginServer]   '{name}' blocked: requires {missing}")
                continue
            self.start_plugin(name)
            started.add(name)

    def start_plugin(self, name):
        """Start a plugin subprocess. Public — callable from UI."""
        attempts = self._start_attempts.get(name, 0)
        if attempts >= 2:
            print(f"[PluginServer] '{name}': max 2 attempts reached, reset to retry")
            self._start_attempts[name] = 0
            attempts = 0

        self._start_attempts[name] = attempts + 1

        for category in ("internal", "external"):
            plugin_dir = os.path.join(self._plugin_dir, category, name)
            if not os.path.isdir(plugin_dir):
                continue
            main_file = os.path.join(plugin_dir, "plugin.py")
            if not os.path.isfile(main_file):
                continue
            try:
                print(f"[PluginServer] Starting plugin '{name}' "
                      f"(attempt {attempts + 1}/2)...")
                proc = subprocess.Popen(
                    [sys.executable, main_file],
                    cwd=plugin_dir,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                self._processes[name] = proc
                self._start_attempts[name] = 0
                return True
            except Exception as e:
                print(f"[PluginServer] Failed to start '{name}': {e}")
                return False

        print(f"[PluginServer] Plugin '{name}' not found")
        return False

    def stop_plugin(self, name):
        """Stop a plugin subprocess and disconnect its client."""
        # Kill the subprocess
        proc = self._processes.pop(name, None)
        if proc:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
            except Exception as e:
                print(f"[PluginServer] Error stopping '{name}': {e}")

        # Disconnect client socket
        with self._lock:
            for sock, info in list(self._clients.items()):
                if info.get("name") == name:
                    try:
                        sock.close()
                    except Exception:
                        pass
                    del self._clients[sock]
                    self._buffers.pop(sock, None)

        self._start_attempts.pop(name, None)
        print(f"[PluginServer] Plugin '{name}' stopped")

    def enable_plugin(self, name):
        """Enable plugin in config and start it."""
        deps_ok, missing = self._check_deps(name)
        if not deps_ok:
            print(f"[PluginServer] Cannot enable '{name}': requires {missing}")
            return
        config = self._load_config()
        config.setdefault("plugins", {})
        config["plugins"].setdefault(name, {})
        config["plugins"][name]["enabled"] = True
        self._save_config(config)
        self.start_plugin(name)

    def disable_plugin(self, name):
        """Disable plugin in config and stop it."""
        self.stop_plugin(name)
        config = self._load_config()
        config.setdefault("plugins", {})
        config["plugins"].setdefault(name, {})
        config["plugins"][name]["enabled"] = False
        self._save_config(config)

    def is_plugin_running(self, name):
        """Check process liveness AND socket connection."""
        proc = self._processes.get(name)
        process_alive = proc is not None and proc.poll() is None
        with self._lock:
            socket_alive = any(info.get("name") == name for info in self._clients.values())
        return process_alive and socket_alive

    def _plugin_process_alive(self, name):
        proc = self._processes.get(name)
        return proc is not None and proc.poll() is None

    def _plugin_socket_alive(self, name):
        with self._lock:
            return any(info.get("name") == name for info in self._clients.values())

    def discover_plugins(self, lang="en"):
        """Scan for all plugins with valid manifests. Returns list of dicts."""
        plugins = []
        for category in ("internal", "external"):
            cat_dir = os.path.join(self._plugin_dir, category)
            if not os.path.isdir(cat_dir):
                continue
            for entry in sorted(os.listdir(cat_dir)):
                plugin_dir = os.path.join(cat_dir, entry)
                if not os.path.isdir(plugin_dir):
                    continue
                manifest_path = os.path.join(plugin_dir, "plugin_manifest.json")
                if not os.path.isfile(manifest_path):
                    continue
                try:
                    with open(manifest_path, encoding="utf-8") as f:
                        manifest = json.load(f)
                except Exception:
                    continue
                desc = manifest.get(f"description_{lang}", manifest.get("description", ""))
                plugins.append({
                    "name": manifest.get("name", entry),
                    "version": manifest.get("version", "?"),
                    "description": desc,
                    "category": category,
                    "min_app": manifest.get("min_app", "?"),
                    "subscriptions": manifest.get("subscriptions", []),
                    "depends_on": manifest.get("depends_on", []),
                })
        return plugins

    def _load_manifest(self, name):
        """Read a plugin's manifest without starting the process."""
        for category in ("internal", "external"):
            path = os.path.join(self._plugin_dir, category, name,
                                "plugin_manifest.json")
            if os.path.isfile(path):
                try:
                    with open(path, encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass
        return {}

    def _check_deps(self, name):
        """Check if all dependencies are enabled. Returns (ok, missing_list)."""
        config = self._load_config()
        enabled_map = config.get("plugins", {})
        manifest = self._load_manifest(name)
        deps = manifest.get("depends_on", [])
        missing = [d for d in deps if not enabled_map.get(d, {}).get("enabled")]
        return len(missing) == 0, missing

    def get_plugins_status(self, lang="en"):
        """Return full status of all discovered plugins for UI display."""
        config = self._load_config()
        enabled_map = config.get("plugins", {})
        discovered = self.discover_plugins(lang)
        result = []
        for p in discovered:
            name = p["name"]
            enabled = enabled_map.get(name, {}).get("enabled", False)
            process_alive = self._plugin_process_alive(name)
            socket_alive = self._plugin_socket_alive(name)
            deps_ok, missing_deps = self._check_deps(name)

            if process_alive and socket_alive:
                status = "running"
                tooltip_detail = ""
            elif enabled and not deps_ok:
                status = "blocked"
                tooltip_detail = ""
            elif process_alive and not socket_alive:
                status = "error"
                tooltip_detail = "socket_missing"
            elif socket_alive and not process_alive:
                status = "error"
                tooltip_detail = "process_missing"
            elif enabled:
                status = "stopped"
                tooltip_detail = ""
            else:
                status = "disabled"
                tooltip_detail = ""

            result.append({
                **p,
                "enabled": enabled,
                "running": process_alive and socket_alive,
                "status": status,
                "missing_deps": missing_deps,
                "tooltip_detail": tooltip_detail,
            })
        return result

    # ── Plugin config ──────────────────────────────────────────

    def _find_plugin_dir(self, name):
        """Return the plugin directory path for a given plugin name."""
        for category in ("internal", "external"):
            d = os.path.join(self._plugin_dir, category, name)
            if os.path.isdir(d) and os.path.isfile(os.path.join(d, "plugin.py")):
                return d
        return None

    def get_plugin_config(self, name, lang="en"):
        """Read a plugin's settings.ini and return values + GUI field definitions.
        Returns {values: {section: {key: val}}, fields: [...]} or None if not found."""
        plugin_dir = self._find_plugin_dir(name)
        if not plugin_dir:
            return None
        ini_path = os.path.join(plugin_dir, "settings.ini")
        if not os.path.isfile(ini_path):
            return None

        cfg = ConfigParser(interpolation=None)
        cfg.read(ini_path, encoding="utf-8")

        values = {}
        fields = []

        for section in cfg.sections():
            if section.startswith("gui."):
                fname = section[4:]
                ft = cfg.get(section, "type", fallback="text")
                lkey = f"label_{lang}"
                label = cfg.get(section, lkey, fallback=cfg.get(section, "label", fallback=fname))
                target_section = cfg.get(section, "section", fallback="")
                field = {
                    "key": fname,
                    "type": ft,
                    "label": label,
                    "section": target_section,
                }
                if ft == "slider":
                    field["min_value"] = cfg.getfloat(section, "min_value", fallback=0)
                    field["max_value"] = cfg.getfloat(section, "max_value", fallback=1)
                    field["step"] = cfg.getfloat(section, "step", fallback=0.01)
                    field["decimals"] = cfg.getint(section, "decimals", fallback=2)
                elif ft == "dropdown":
                    opts = cfg.get(section, "options", fallback="")
                    field["options"] = [o.strip() for o in opts.split("|") if o.strip()]
                elif ft == "note":
                    field["note"] = cfg.get(section, f"note_{lang}",
                                            fallback=cfg.get(section, "note", fallback=""))
                fields.append(field)
            else:
                values[section] = {}
                for key, val in cfg.items(section):
                    values[section][key] = val

        return {"values": values, "fields": fields}

    def set_plugin_value(self, name, section, key, value):
        """Write a single value into a plugin's settings.ini."""
        plugin_dir = self._find_plugin_dir(name)
        if not plugin_dir:
            return False
        ini_path = os.path.join(plugin_dir, "settings.ini")
        cfg = ConfigParser(interpolation=None)
        if os.path.isfile(ini_path):
            cfg.read(ini_path, encoding="utf-8")
        if not cfg.has_section(section):
            cfg.add_section(section)
        cfg.set(section, key, str(value))
        try:
            tmp = tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", delete=False,
                dir=plugin_dir, prefix="settings_", suffix=".ini")
            cfg.write(tmp)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp.close()
            shutil.move(tmp.name, ini_path)
            return True
        except Exception as e:
            print(f"[PluginServer] Failed to save {ini_path}: {e}")
            return False

    # ── Helpers ─────────────────────────────────────────────────

    def _remove_client(self, sock):
        name = "unknown"
        with self._lock:
            if sock in self._clients:
                name = self._clients[sock]["name"]
                del self._clients[sock]
            self._buffers.pop(sock, None)
        try:
            sock.close()
        except Exception:
            pass
        print(f"[PluginServer] Client disconnected: {name}")

    def _load_config(self):
        config_path = os.path.join(self._plugin_dir, "plugins.json")
        try:
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)
            print(f"[PluginServer] Config loaded: {config_path}")
            return data
        except FileNotFoundError:
            print(f"[PluginServer] Config not found: {config_path}")
        except Exception as e:
            print(f"[PluginServer] Config error: {e}")
        return {}

    def _save_config(self, data):
        """Atomically write plugins.json."""
        config_path = os.path.join(self._plugin_dir, "plugins.json")
        try:
            tmp = tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", delete=False,
                dir=self._plugin_dir, prefix="plugins_", suffix=".json")
            json.dump(data, tmp, indent=2, ensure_ascii=False)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp.close()
            shutil.move(tmp.name, config_path)
        except Exception as e:
            print(f"[PluginServer] Failed to save config: {e}")
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)

    @staticmethod
    def _load_rss_cache(limit=10):
        """Read recent items from RSS cache file."""
        try:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            cache_path = os.path.join(root, "Allowed_root", "rss_cache.json")
            if not os.path.isfile(cache_path):
                return []
            with open(cache_path, encoding="utf-8") as f:
                data = json.load(f)
            feeds = data.get("feeds", {})
            items = []
            for feed_id, entry in feeds.items():
                for item in entry.get("items", []):
                    if not item.get("seen", False):
                        items.append({
                            "title": item.get("title", ""),
                            "source": item.get("source", ""),
                            "summary": item.get("summary", "")[:300],
                            "guid": item.get("guid", ""),
                            "link": item.get("link", ""),
                            "pubDate": item.get("pubDate", ""),
                        })
            items.sort(key=lambda x: x.get("pubDate", ""), reverse=True)
            return items[:limit]
        except Exception:
            return []

    @staticmethod
    def _load_conversation_history(limit=10):
        """Read conversation history from persistent memory.json files."""
        try:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            mem_path = os.path.join(root, "Allowed_root", "memory.json")
            if not os.path.isfile(mem_path):
                return []
            with open(mem_path, encoding="utf-8") as f:
                mem = json.load(f)
            ids = mem.get("history", [])
            result = []
            for mid in reversed(ids):
                mf = os.path.join(root, "Allowed_root", "memory", f"{mid}.json")
                if not os.path.isfile(mf):
                    continue
                try:
                    with open(mf, encoding="utf-8") as f:
                        entry = json.load(f)
                    info = json.loads(entry.get("info", "{}"))
                    if isinstance(info, dict) and "role" in info:
                        result.append(info)
                except Exception:
                    pass
                if len(result) >= limit:
                    break
            return list(reversed(result))
        except Exception:
            return []

    @staticmethod
    def _version_cmp(v1: str, v2: str) -> int:
        p1 = [int(x) for x in v1.split(".")]
        p2 = [int(x) for x in v2.split(".")]
        for i in range(max(len(p1), len(p2))):
            a = p1[i] if i < len(p1) else 0
            b = p2[i] if i < len(p2) else 0
            if a > b:
                return 1
            if a < b:
                return -1
        return 0

    @staticmethod
    def _resolve_path(*parts: str) -> str:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, *parts)
