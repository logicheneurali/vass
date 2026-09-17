"""llama.cpp Server Plugin — Manages llama-server lifecycle.

Connects to VASS PluginServer for commands and state notifications.
Handles: start, stop, restart, health checks, model auto-selection.
"""
import configparser
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime

_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log.txt")
_MAX_LOG = 100_000


def _log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [LlamaCppServer] {msg}"
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

_UI_SCHEMA = {
    "id": "llamacpp_server",
    "title_it": "llama.cpp Server",
    "title": "llama.cpp Server",
    "sections": [{
        "title_it": "Stato server",
        "title": "Server Status",
        "rows": [
            {"kind": "button", "key": "btn_start",
             "label_it": "Avvia", "label": "Start",
             "action": "llama_start"},
            {"kind": "button", "key": "btn_stop",
             "label_it": "Ferma", "label": "Stop",
             "action": "llama_stop"},
            {"kind": "button", "key": "btn_restart",
             "label_it": "Riavvia", "label": "Restart",
             "action": "llama_restart"},
            {"kind": "label", "key": "server_status",
             "label_it": "Stato", "label": "Status"},
        ]
    }]
}
# NOTE: Configuration fields (llama_server_path, llama_server_working_directory,
# llama_server_arguments, llama_autostart) are managed via settings.ini
# and the gear icon — NOT in the status UI dialog.


class LlmacppServerPlugin:
    """Manages llama.cpp server lifecycle."""

    def __init__(self):
        self._host = "localhost"
        self._port = 8765
        self._config = self._load_config()
        self._manifest = self._load_manifest()
        self._running = True
        self._lock = threading.Lock()
        self._server_proc = None
        self._server_pid = None  # PID of externally-managed server
        self._socket = None
        self._thread = None
        self._restart_count = 0
        self._last_restart_time = 0
        self._ready = False
        self._current_model = ""
        self._context_length = 0
        self._last_health_check = 0
        self._ctx_size = 0

    # ── Config / Manifest ─────────────────────────────────────

    def _load_config(self) -> dict:
        """Load settings.ini and read config."""
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
            "enabled": cfg.getboolean("server", "enabled", fallback=True),
            "llama_server_path": cfg.get("server", "llama_server_path", fallback="").strip(),
            "llama_server_working_directory": cfg.get("server", "llama_server_working_directory", fallback="").strip(),
            "llama_server_arguments": cfg.get("server", "llama_server_arguments", fallback="").strip(),
            "llama_autostart": cfg.getboolean("server", "llama_autostart", fallback=False),
            "model_auto_select": cfg.getboolean("server", "model_auto_select", fallback=True),
            "port": cfg.getint("server", "port", fallback=8080),
            "health_poll_interval": cfg.getint("health", "poll_interval", fallback=10),
            "health_ready_timeout": cfg.getint("health", "ready_timeout", fallback=60),
            "health_max_restarts": cfg.getint("health", "max_restarts", fallback=3),
            "health_restart_cooldown": cfg.getint("health", "restart_cooldown", fallback=30),
        }

    def _load_manifest(self) -> dict:
        """Load plugin_manifest.json."""
        manifest_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "plugin_manifest.json")
        try:
            with open(manifest_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"name": "llamacpp_server", "version": "1.0.0"}

    def _resolve_root(self) -> str:
        """Resolve the VASS project root directory."""
        return os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))))

    # ── Server lifecycle ──────────────────────────────────────

    def _find_server_pid(self) -> int:
        """Find PID of a running llama-server process. Returns None if not found."""
        import psutil
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if 'llama-server' in cmdline:
                    return proc.info['pid']
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return None

    def _kill_process_by_pid(self, pid: int) -> bool:
        """Kill a process by PID. Returns True if successful."""
        import psutil
        try:
            proc = psutil.Process(pid)
            proc.terminate()  # SIGTERM
            try:
                proc.wait(timeout=3)
            except psutil.TimeoutExpired:
                proc.kill()  # SIGKILL
                try:
                    proc.wait(timeout=2)
                except psutil.TimeoutExpired:
                    _log(f"Process {pid} refused to die")
                    return False
            return True
        except psutil.NoSuchProcess:
            return True
        except Exception as e:
            _log(f"Error killing process {pid}: {e}")
            return False

    def _external_server_on_port(self) -> bool:
        """True if a llama-server is already listening on the configured port.

        Detects servers started outside this plugin (e.g. an external router on
        the default 8080) so we can monitor instead of launching a conflicting
        second instance. Uses /v1/health first (router always answers it), then
        falls back to /v1/models.
        """
        import urllib.request
        port = self._config["port"]
        for path in ("/v1/health", "/v1/models"):
            url = f"http://localhost:{port}{path}"
            try:
                with urllib.request.urlopen(url, timeout=2) as resp:
                    if resp.status < 400:
                        _log(f"External llama-server detected on port {port} ({path})")
                        return True
            except Exception:
                pass
        return False

    def _is_process_running(self, name: str) -> bool:
        """Check if a process with the given name is running on the system."""
        try:
            if sys.platform == "win32":
                r = subprocess.run(["tasklist"], capture_output=True, text=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
                return name.lower() in r.stdout.lower()
            else:
                r = subprocess.run(["pgrep", "-f", name], capture_output=True)
                return r.returncode == 0
        except Exception:
            return False

    def _is_server_running(self) -> bool:
        """Check if llama-server process is running (managed by this plugin)."""
        if self._server_proc is None:
            return False
        return self._server_proc.poll() is None

    def _start_server(self) -> tuple:
        """Start llama-server subprocess. Returns (proc, status_string).
        
        If a llama-server is already running (externally started), detects the
        model via /v1/models API without restarting the server — same as legacy.
        """
        path = self._config["llama_server_path"]
        _log(f"Config: path={path}, enabled={self._config['enabled']}")

        if not path:
            return None, "path not configured"

        base_path = path
        exe = os.path.join(base_path, "llama-server.exe"
                           if sys.platform == "win32" else "llama-server")

        if not os.path.isfile(exe):
            # Linux fallback: try to find llama-server in PATH
            if sys.platform != "win32":
                found = shutil.which("llama-server")
                if found:
                    base_path = os.path.dirname(found)
                    exe = found
            if not os.path.isfile(exe):
                _log(f"llama-server not found in {path} (and not in PATH)")
                return None, f"llama-server not found in {path} (and not in PATH)"

        # Check if a llama-server is already listening on the configured port
        # (started externally — e.g. a router). If so, monitor only; do NOT
        # launch a conflicting second instance.
        if self._external_server_on_port():
            _log(f"External llama-server detected on port {self._config['port']} — monitoring only")
            if self._wait_for_ready(timeout=15):
                return None, "already running"
            else:
                return None, "already running but not responding"

        # Check if a llama-server is already running (externally or managed)
        if self._is_process_running("llama-server"):
            _log("llama-server already running — detecting model...")
            # Find PID so we can kill it later
            pid = self._find_server_pid()
            if pid:
                _log(f"Found existing server PID: {pid}")
            # Connect to existing server and discover model
            if self._wait_for_ready(timeout=15):
                # Store PID for later kill
                with self._lock:
                    self._server_pid = pid
                    self._server_proc = None  # External process, no Popen object
                return None, "already running"
            else:
                return None, "already running but not responding"

        if self._is_server_running():
            return None, "already running"

        cwd = self._config["llama_server_working_directory"].strip() or base_path
        args = self._config["llama_server_arguments"].strip()
        cmd = [exe] + (args.split() if args else [])

        _log(f"Starting: {' '.join(cmd)} (cwd={cwd})")

        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

        log_dir = os.path.join(self._resolve_root(), "log")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "llamacpp.log")
        log_file = open(log_path, "a", encoding="utf-8")
        log_file.write(f"--- llama.cpp started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        log_file.write(f"Command: {' '.join(cmd)}\nWorking dir: {cwd}\n\n")
        log_file.flush()

        proc = subprocess.Popen(cmd, cwd=cwd, creationflags=creationflags,
                                stdout=log_file, stderr=subprocess.STDOUT)
        return proc, "started"

    def _stop_server(self) -> str:
        """Stop llama-server process. Returns status string."""
        with self._lock:
            # If server is externally-managed (no Popen object), kill by PID
            if self._server_proc is None and self._server_pid:
                pid = self._server_pid
                _log(f"Stopping external server (PID {pid})...")
                self._server_pid = None  # Clear PID
                self._ready = False
                if self._kill_process_by_pid(pid):
                    _log("External server stopped")
                    return "stopped"
                _log("External server kill failed")
                return "stop failed"
            
            if self._server_proc is None:
                return "not running"

            try:
                self._server_proc.terminate()
                self._server_proc.wait(timeout=3)
                _log("Server stopped gracefully")
            except subprocess.TimeoutExpired:
                try:
                    self._server_proc.kill()
                    self._server_proc.wait(timeout=2)
                    _log("Server killed forcefully")
                except Exception:
                    _log("Error killing server")
            except Exception as e:
                _log(f"Error stopping server: {e}")
            finally:
                self._server_proc = None
                self._ready = False
                self._restart_count = 0
        return "stopped"

    def _wait_for_ready(self, timeout=None) -> bool:
        """Poll /v1/models until llama-server responds or timeout expires."""
        if timeout is None:
            timeout = self._config["health_ready_timeout"]

        ai_port = self._config["port"]
        url = f"http://localhost:{ai_port}/v1/models"
        deadline = time.time() + timeout

        while time.time() < deadline:
            try:
                import urllib.request
                with urllib.request.urlopen(url, timeout=2) as resp:
                    data = json.loads(resp.read())
                    models = data.get("data", [])
                if models:
                    _log("Server ready")
                    self._ready = True
                    # Extract model info
                    first_model = models[0]
                    if isinstance(first_model, dict):
                        self._current_model = first_model.get("id", "")
                        self._context_length = first_model.get(
                            "max_sequence_length",
                            first_model.get("context_length", 0))
                    return True
            except Exception:
                pass
            time.sleep(0.5)

        _log(f"Server did not become ready within {timeout}s")
        return False

    # ── Health checks ─────────────────────────────────────────

    def _check_server_health(self):
        """Periodic health check: restart if crashed."""
        with self._lock:
            if self._server_proc is None:
                return

            # Check if process is still alive
            if self._server_proc.poll() is not None:
                if not self._running:
                    return  # Expected stop

                # Server crashed — attempt restart with cooldown
                now = time.time()
                if now - self._last_restart_time < self._config["health_restart_cooldown"]:
                    return  # Cooldown not expired

                if self._restart_count >= self._config["health_max_restarts"]:
                    _log(f"Max restarts ({self._config['health_max_restarts']}) reached")
                    self._server_proc = None
                    return

                self._restart_count += 1
                self._last_restart_time = now
                _log(f"Server crashed, restart attempt {self._restart_count}")
                self._start_server_internal()

    def _start_server_internal(self):
        """Start server without running check (for restarts)."""
        proc, status = self._start_server()
        if proc:
            self._server_proc = proc
            if self._wait_for_ready():
                self._refresh_status()
            else:
                _log("Health restart: server did not become ready")
        else:
            _log(f"Restart failed: {status}")

    # ── PluginServer communication ────────────────────────────

    def _send_cmd(self, cmd, params=None, request_id=None):
        """Send a command to VASS PluginServer."""
        if not self._socket:
            return None

        msg = {"type": "cmd", "cmd": cmd}
        # notify: flatten params at top level (same as world_events, rss_reader)
        if cmd == "notify" and isinstance(params, dict):
            msg["text"] = params.get("text", "")
            if "priority" in params:
                msg["priority"] = params["priority"]
            if "data" in params:
                msg["data"] = params["data"]
        # ui_register, ui_state, set_state expect special fields at top level
        elif cmd == "ui_register" and isinstance(params, dict):
            if "schema" in params:
                msg["schema"] = params["schema"]
        elif cmd == "ui_state" and isinstance(params, dict):
            if "values" in params:
                msg["values"] = params["values"]
        elif cmd == "set_state" and isinstance(params, dict):
            msg.update(params)
        else:
            if params:
                msg["params"] = params
        if request_id:
            msg["request_id"] = request_id

        try:
            self._socket.sendall((json.dumps(msg) + "\n").encode())
            return request_id
        except Exception as e:
            _log(f"Send error: {e}")
            return None

    def _send_notify(self, text, priority=5, data=None):
        """Send a notification via PluginServer."""
        params = {"text": text, "priority": priority}
        if data:
            params["data"] = data
        return self._send_cmd("notify", params)

    def _send_state(self, state_data):
        """Send state update to main app via PluginServer."""
        self._send_cmd("set_state", state_data)

    def _send_ui_state(self, ui_state):
        """Send UI state update to PluginServer (for PluginUiDialog)."""
        self._send_cmd("ui_state", {"values": ui_state})

    # ── Connection to PluginServer ────────────────────────────

    def _connect(self) -> bool:
        """Connect to VASS PluginServer."""
        for attempt in range(10):
            _log(f"Connection attempt {attempt+1}/10...")
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((self._host, self._port))
                sock.settimeout(None)
                self._socket = sock

                # Send hello
                hello = {
                    "type": "hello",
                    "name": "llamacpp_server",
                    "version": "1.0.0",
                    "min_app": "0.6.8",
                    "subscribe": ["idle_check", "resource_check"],
                }
                sock.sendall((json.dumps(hello) + "\n").encode())
                _log("Connected to PluginServer")
                # Register UI schema
                self._send_cmd("ui_register", {"schema": _UI_SCHEMA})
                # Send initial state
                self._refresh_status()
                return True
            except Exception as e:
                _log(f"Connection attempt {attempt+1} failed: {e}")

            time.sleep(2)

        return False

    def _receive_message(self, sock, timeout=15):
        """Receive a JSON message from socket."""
        buffer = b""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                data = sock.recv(4096)
                if data:
                    buffer += data
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        try:
                            return json.loads(line.decode())
                        except json.JSONDecodeError:
                            continue
                else:
                    break
            except socket.timeout:
                continue
            except Exception:
                break
            time.sleep(0.1)
        return None

    def _message_loop(self):
        """Handle incoming messages from PluginServer."""
        while self._running and self._socket:
            try:
                msg = self._receive_message(self._socket, timeout=5)
                if not msg:
                    continue

                msg_type = msg.get("type", "")
                cmd = msg.get("cmd", "")

                if msg_type == "idle_check":
                    # Perform health check on idle
                    self._check_server_health()

                elif msg_type == "resource_check":
                    # Resource check — do nothing specific
                    pass

                elif msg_type == "cmd":
                    # Dispatch commands from PluginServer
                    if cmd == "llama_start":
                        _log("Received llama_start command")
                        self.cmd_start()
                    elif cmd == "llama_stop":
                        _log("Received llama_stop command")
                        self.cmd_stop()
                    elif cmd == "llama_restart":
                        _log("Received llama_restart command")
                        self.cmd_restart()
                    elif cmd == "llama_status":
                        status = self.cmd_status()
                        self._send_state(status)
                    elif cmd == "ui_action":
                        # UI interaction from settings editor
                        action = msg.get("action", {})
                        key = action.get("key", "")
                        event = action.get("event", "")
                        values = action.get("values", {})

                        if key == "btn_start" and event == "button":
                            _log("UI btn_start clicked")
                            self.cmd_start()
                        elif key == "btn_stop" and event == "button":
                            _log("UI btn_stop clicked")
                            self.cmd_stop()
                        elif key == "btn_restart" and event == "button":
                            _log("UI btn_restart clicked")
                            self.cmd_restart()
                        elif key == "llama_autostart" and event == "toggle":
                            # Toggle autostart — save config for future restarts
                            autostart = values.get("llama_autostart", False)
                            _log(f"UI autostart changed: {autostart}")
                            self._update_config("llama_autostart", autostart)
                        elif key in ("llama_server_path", "llama_server_working_directory",
                                     "llama_server_arguments") and event == "text":
                            # Text field changed — save config
                            _log(f"UI text changed: {key}={values.get(key, '')}")
                            self._update_config(key, values.get(key, ""))

                        self._refresh_status()
                    else:
                        _log(f"Unknown command: {cmd}")

            except Exception as e:
                if self._running:
                    _log(f"Message loop error: {e}")
                    time.sleep(1)

    # ── Main run loop ─────────────────────────────────────────

    def run(self):
        """Main plugin entry point: connect, start server, run message loop."""
        _log("Plugin starting...")
        _log(f"Config: enabled={self._config['enabled']}, autostart={self._config['llama_autostart']}")
        _log(f"Path: {self._config['llama_server_path']}, port={self._config['port']}")
        _log(f"health_interval={self._config['health_poll_interval']}s, max_restarts={self._config['health_max_restarts']}")

        if not self._config["enabled"]:
            _log("Plugin disabled in config, exiting")
            return

        # Connect to PluginServer
        if not self._connect():
            _log("Failed to connect to PluginServer — running standalone")
        else:
            _log("Registered with PluginServer")

        # Start server if autostart
        if self._config["llama_autostart"]:
            _log("Autostart enabled, launching server...")
            self._start_server_internal()
            self._wait_for_ready()

            # Send state notification
            if self._ready:
                _log(f"Server ready — model={self._current_model}, ctx={self._context_length}")
                self._send_state({
                    "llama_server_ready": True,
                    "llama_server_model": self._current_model,
                    "llama_context_length": self._context_length,
                })
                self._refresh_status()
                self._send_notify(
                    f"llama.cpp server started (autostart): "
                    f"{self._current_model}",
                    priority=4)
            else:
                _log("Server failed to become ready within timeout")
                self._send_notify(
                    "llama.cpp server failed to start (autostart)",
                    priority=6)
        else:
            _log("Autostart disabled — server not started")

        # Run message loop
        _log("Entering message loop...")
        try:
            self._message_loop()
        except Exception as e:
            _log(f"Run error: {e}")
        finally:
            _log("Cleaning up...")
            self.stop()

    def _update_config(self, key, value):
        """Update a config value in settings.ini."""
        ini_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "settings.ini")
        try:
            cfg = configparser.ConfigParser()
            cfg.read(ini_path, encoding="utf-8")
            if key in ("llama_autostart", "enabled", "model_auto_select"):
                cfg.set("server", key, str(bool(value)))
            else:
                cfg.set("server", key, str(value))
            with open(ini_path, "w", encoding="utf-8") as f:
                cfg.write(f)
            _log(f"Config updated: {key}={value}")
            # Update local config
            self._config[key] = value
        except Exception as e:
            _log(f"Config update failed: {e}")

    def _refresh_status(self):
        """Send updated UI state."""
        # Check if process is actually alive, not just self._ready flag
        proc_alive = (self._server_proc is not None
                      and self._server_proc.poll() is None)
        is_running = proc_alive or self._ready
        self._send_ui_state({
            "server_status": "running" if is_running else "stopped",
            "server_model": self._current_model,
            "llama_server_ready": self._ready,
            "llama_server_model": self._current_model,
            "llama_context_length": self._context_length,
        })

    def stop(self):
        """Stop the plugin and clean up."""
        self._running = False
        self._stop_server()
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

    # ── Manual commands (called via PluginServer) ─────────────

    def cmd_start(self):
        """Handle llama_start command."""
        result, status = self._start_server()
        if result:
            self._server_proc = result
            if self._wait_for_ready():
                self._refresh_status()
                self._send_notify("llama.cpp server started",
                                  priority=4)
            else:
                self._refresh_status()
                self._send_notify("llama.cpp server did not become ready",
                                  priority=6)
        elif status == "already running":
            # Externally managed server — PID already stored
            _log(f"Server already running (PID={self._server_pid})")
            self._refresh_status()
            self._send_notify("llama.cpp server already running",
                              priority=5)
        else:
            _log(f"Start failed: {status}")
            self._send_notify(f"llama.cpp start failed: {status}",
                              priority=6)
        return status

    def cmd_stop(self):
        """Handle llama_stop command."""
        status = self._stop_server()
        self._refresh_status()
        self._send_notify("llama.cpp server stopped", priority=4)
        return status

    def cmd_restart(self):
        """Handle llama_restart command."""
        self._stop_server()
        time.sleep(1)
        return self.cmd_start()

    def cmd_status(self):
        """Handle llama_status command."""
        return {
            "running": self._is_server_running(),
            "ready": self._ready,
            "model": self._current_model,
            "context_length": self._context_length,
            "restart_count": self._restart_count,
        }


if __name__ == "__main__":
    _log(f"Plugin subprocess started (pid={os.getpid()})")
    plugin = LlmacppServerPlugin()
    plugin.run()
