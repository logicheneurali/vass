"""Script queue and execution engine for VASS — serializes VASScript invocations."""
import json
import os
import threading
import time
from collections import deque
import configparser

from i18n import t


class ScriptQueue:
    """FIFO serial script execution queue.  One script runs at a time;
    additional requests are queued and processed in order."""

    def __init__(self, app, execute_impl):
        self.app = app
        self._execute_impl = execute_impl
        self._queue = deque()
        self._lock = threading.Lock()
        self._active_engine = None
        self._running = False
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()

    def enqueue(self, name_or_code=None, code=None, params=None, result_callback=None, source="", transcribed_text=None, silent=False):
        item = (name_or_code, code, params, result_callback, source, transcribed_text, silent)
        with self._lock:
            self._queue.append(item)
            qlen = len(self._queue)
        if qlen == 1:
            self.app.set_state("running_script", silent_gui=silent)
        elif qlen > 1:
            print(f"[ScriptQueue] Queued {source or 'script'} (position {qlen})")

    def cancel_current(self):
        with self._lock:
            engine = self._active_engine
        if engine:
            engine.stop()

    def cancel_all(self):
        with self._lock:
            self._queue.clear()
            engine = self._active_engine
        if engine:
            engine.stop()

    def _worker(self):
        while True:
            if self.app.state in ("waiting", "waiting_resources", "playing", "recording"):
                time.sleep(0.1)
                continue
            with self._lock:
                if not self._queue:
                    item = None
                else:
                    item = self._queue.popleft()
            if item is None:
                time.sleep(0.1)
                continue
            name_or_code, code, params, result_callback, source, transcribed_text, silent = item
            self._execute_impl(name_or_code, code, params, result_callback, self, transcribed_text, silent)
            time.sleep(0.1)


class ScriptRunner:
    def __init__(self, app):
        self._app = app
        self.queue = ScriptQueue(app, self._execute_script_impl)

    def enqueue(self, name_or_code=None, code=None, params=None,
                result_callback=None, source="", transcribed_text=None,
                silent=False):
        self.queue.enqueue(name_or_code, code, params, result_callback,
                           source, transcribed_text, silent=silent)

    def cancel_current(self):
        self.queue.cancel_current()

    def cancel_all(self):
        self.queue.cancel_all()

    def watch_queue(self):
        app = self._app
        queue_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "exec_queue.json")
        result_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "exec_result.json")
        while app.running:
            time.sleep(1)
            try:
                if not os.path.exists(queue_path):
                    continue
                with open(queue_path, "r", encoding="utf-8") as f:
                    request = json.load(f)
                request_id = request.get("id")
                script_name = request.get("script", "")
                code = request.get("code", "")
                if not request_id or (not script_name and not code):
                    continue
                os.remove(queue_path)

                label = script_name or "inline"
                print(f"[ScriptQueue] Enqueued: {label}")

                def _write_result(r):
                    result = {"id": request_id, "result": r}
                    with open(result_path, "w", encoding="utf-8") as f:
                        json.dump(result, f)
                    print(f"[ScriptQueue] Completed: {label} -> {r.get('status')}")

                self.enqueue(name_or_code=script_name if script_name else None,
                             result_callback=_write_result, code=code or None)
            except Exception as e:
                print(f"[Watch] Script queue watcher error: {e}")

    def _execute_script_impl(self, name_or_code, code, params, result_callback,
                              queue, transcribed_text=None, silent=False):
        app = self._app
        import json as _json
        script_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
        if code is not None:
            script_name = "inline"
            is_file = False
        elif name_or_code:
            script_path = os.path.join(script_dir, f"{name_or_code}.vass")
            is_file = os.path.exists(script_path)
            script_name = name_or_code if is_file else "inline"
        else:
            err_msg = t("scripts.not_found", app.language).replace("{name}", "inline")
            if result_callback:
                result_callback({"status": "error", "detail": err_msg})
            return

        def _auth_get(script):
            try:
                import keyring
                raw = keyring.get_password("vass-auth", script)
                return _json.loads(raw) if raw else {}
            except Exception:
                return {}

        def _auth_set(script, data):
            import keyring
            if is_file and script_path:
                try:
                    import hashlib
                    with open(script_path, "rb") as f:
                        data["_hash"] = hashlib.sha256(f.read()).hexdigest()
                except Exception:
                    pass
            keyring.set_password("vass-auth", script, _json.dumps(data))

        def _migrate_auth_ini():
            ini_path = os.path.join(script_dir, "auth.ini")
            if not os.path.exists(ini_path):
                return
            cfg = configparser.ConfigParser()
            cfg.read(ini_path)
            migrated = False
            for sec in cfg.sections():
                existing = _auth_get(sec)
                for opt in cfg.options(sec):
                    if cfg.getboolean(sec, opt):
                        existing[opt] = True
                _auth_set(sec, existing)
                migrated = True
            if migrated:
                os.remove(ini_path)
                print(f"[Auth] Migrato auth.ini in Credential Manager")

        _migrate_auth_ini()

        def _load_auth(func_name=None):
            data = _auth_get(script_name)
            if is_file and script_path and "_hash" in data:
                try:
                    import hashlib
                    with open(script_path, "rb") as f:
                        current_hash = hashlib.sha256(f.read()).hexdigest()
                    if current_hash != data["_hash"]:
                        import keyring
                        keyring.delete_password("vass-auth", script_name)
                        return None
                except Exception:
                    pass
            if data.get("_all_"):
                return "all"
            if func_name and data.get(func_name):
                return "function"
            return None

        def _save_auth(func_name, allow_all=False):
            data = _auth_get(script_name)
            if allow_all:
                data["_all_"] = True
            else:
                data[func_name] = True
            _auth_set(script_name, data)

        def _auth_callback(name, func):
            cached = _load_auth(func)
            if cached in ("all", "function"):
                return cached
            result = app.gui.request_auth(name, func)
            if result == "function":
                _save_auth(func)
            elif result == "all":
                _save_auth(func, allow_all=True)
            elif result == "once":
                result = "function"
            return result

        code_text = None
        if code is not None:
            code_text = code.replace('\u2018', "'").replace('\u2019', "'").replace('\u201c', '"').replace('\u201d', '"')
            print(f"[VASScript] Esecuzione inline ({len(code_text)} chars):")
            for line in code_text.strip().split("\n"):
                print(f"  {line}")
        elif is_file:
            with open(script_path, encoding="utf-8") as f:
                code_text = f.read()
            print(f"[VASScript] Esecuzione file: {script_path}")
        else:
            err_msg = t("scripts.not_found", app.language).replace("{name}", name_or_code or "inline")
            print(f"[VASScript] {err_msg}")
            if result_callback:
                result_callback({"status": "not_found", "script": name_or_code, "detail": err_msg, "message": err_msg})
            else:
                app.tts.enqueue(err_msg)
            with queue._lock:
                if len(queue._queue) == 0:
                    app.set_state("listening", silent_gui=silent)
            return

        if code_text:
            from script_engine import VASScript
            app.set_state("running_script", silent_gui=silent)
            script_error = None
            engine = None
            try:
                engine = VASScript(
                    app, script_name=script_name, silent=silent, auth_callback=_auth_callback,
                    line_callback=lambda c, t: [
                        app.set_state("running_script", f"{c}/{t}", silent_gui=silent),
                        (None if silent else app.gui.memory_bar.set_value(c, 1, t))
                    ]
                )
                queue._active_engine = engine
                if params:
                    engine.vars.update(params)
                engine.execute(code_text)
                output_vars = {k: v for k, v in engine.vars.items() if not k.startswith("_")}
                if result_callback:
                    result_callback({"status": "ok", "script": script_name, "vars": output_vars, "message": "Script executed successfully."})
            except Exception as e:
                script_error = str(e)
                print(f"[VASScript] Error: {script_error}")
                if result_callback:
                    result_callback({"status": "error", "script": script_name, "detail": script_error, "message": "Script failed: " + script_error})
            finally:
                queue._active_engine = None
                with queue._lock:
                    if len(queue._queue) == 0:
                        app.set_state("listening", silent_gui=silent)

            if script_error and not result_callback:
                app.tts.enqueue(f"Errore script: {script_error}")
