import json
import math
import os
import re
import shlex
import subprocess
import sys
import threading
import time

from utils import get_project_root, call_with_retry, execute_mcp_tool_calls, init_mcp, fuzzy_ratio, log_exc


_SIDE_EFFECT_FUNCTIONS = {"ai", "say", "run", "launch_app", "close", "screen_search", "screen_click", "screen_highlight", "listen", "sendtext", "send_text", "setactivewindow", "set_active_window", "addevent", "add_event", "listevents", "list_events", "removeevent", "delevent", "remove_event", "delete_event", "readinfo", "read_info", "writeinfo", "write_info", "clipboardget", "clipboard_get", "clipboardset", "clipboard_set", "savetags", "save_tags", "timer_start", "timer_list", "timer_cancel", "notify", "form", "inject", "inject_memory", "compress_memory", "fetch_text", "fetch_json", "search_web", "gcal_today", "gcal_tomorrow", "gcal_add", "gcal_search", "google_home_command", "google_home_ask", "get_weather", "getidle", "get_idle", "rss_fetch", "readfile", "read_file", "writefile", "write_file", "readstate", "read_state", "writestate", "write_state", "prettyevents", "pretty_events", "getdatetime", "get_datetime", "tonum", "to_num", "ifcontains", "if_contains", "ifempty", "if_empty", "ifequals", "if_equals", "ifgreater", "if_greater", "ifless", "if_less", "ifgreaterequal", "if_greater_equal", "iflessequal", "if_less_equal", "foreach"}


def _is_int_str(s):
    try:
        int(s)
        return True
    except (ValueError, TypeError):
        return False


def _is_float_str(s):
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


def _gh_disable_google_services(app):
    for key in ["calendar_enabled", "calendar_sync_enabled", "gmail_enabled", "google_home_enabled"]:
        app.settings[key] = "false"
    print("[GoogleAuth] Auto-disabled all Google services due to auth error")


def _validate_recur(recur):
    import re
    return bool(re.match(r"^\d+[hdm]$", recur))


def _recur_label(recur):
    import re
    m = re.match(r"^(\d+)([hdm])$", recur)
    if not m:
        return recur
    num, unit = m.group(1), m.group(2)
    labels = {"h": "ora" if num == "1" else "ore", "d": "giorno", "m": "mese" if num == "1" else "mesi"}
    suffix = labels.get(unit, unit)
    if unit == "d":
        return f"{num} {suffix}" if num != "1" else "giorno"
    return f"{num} {suffix}"


class VASScript:
    _ocr_reader = None
    _ocr_active_langs = None
    _weather_cache = {}
    _weather_cache_ttl = 900
    _fetch_cache = {}
    _fetch_cache_ttl = 300
    _search_cache = {}
    _search_cache_ttl = 600
    _state = {}
    _state_lock = threading.Lock()

    def __init__(self, app, script_name="inline", auth_callback=None, line_callback=None, silent=False):
        self.app = app
        self.script_name = script_name
        self.auth_callback = auth_callback
        self.line_callback = line_callback
        self._silent = silent
        self.vars = {}
        self.vars["_lang"] = getattr(app, "language", "en")
        from i18n import t
        lang = getattr(app, "language", "en")
        self.vars["_exec_message"] = t("scripts.exec_message", lang)
        self.vars["_tr_ok"] = t("scripts.tr_ok", lang)
        self.vars["_tr_fail"] = t("scripts.tr_fail", lang)
        self._running = False
        self._auth_all = False

    def _ocr_langs(self):
        lang = getattr(self.app, "language", "en")
        lang_map = {
            "it": ["it", "en"], "en": ["en"], "de": ["de", "en"],
            "fr": ["fr", "en"], "es": ["es", "en"], "pt": ["pt", "en"],
            "ja": ["ja", "en"], "ko": ["ko", "en"], "zh": ["ch_sim", "en"],
        }
        return lang_map.get(lang, ["en"])

    @staticmethod
    def _preprocess_screen(frame):
        import numpy as np
        try:
            from PIL import Image, ImageEnhance, ImageOps
            pil_img = Image.fromarray(frame[:, :, :3])
            pil_img = ImageOps.grayscale(pil_img)
            pil_img = ImageEnhance.Contrast(pil_img).enhance(2.0)
            pil_img = ImageOps.autocontrast(pil_img, cutoff=2)
            return np.stack([np.array(pil_img)] * 3, axis=-1)
        except Exception:
            return frame

    def execute(self, script_text):
        lines = script_text.strip().split("\n")
        total = len(lines)
        self._running = True
        for i, line in enumerate(lines):
            if not self._running:
                break
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if self.line_callback:
                self.line_callback(i + 1, total)
            result = self._execute_line(line)
            if line.strip() and not line.strip().startswith("#"):
                if getattr(self.app, 'debug_enabled', False):
                    rstr = str(result) if result else "(empty)"
                    print(f"[VASScript] {line.strip()} -> {rstr}")

    def execute_file(self, path):
        with open(path, encoding="utf-8") as f:
            self.execute(f.read())

    def stop(self):
        self._running = False

    def _tokenize(self, line):
        tokens = []
        i = 0
        while i < len(line):
            c = line[i]
            if c in "()=,":
                tokens.append(c)
                i += 1
            elif c == "$":
                j = i + 1
                while j < len(line) and (line[j].isalnum() or line[j] == "_"):
                    j += 1
                tokens.append(line[i:j])
                i = j
            elif c == '"' or c == "'":
                quote = c
                j = i + 1
                while j < len(line):
                    if line[j] == "\\":
                        j += 2
                        continue
                    if line[j] == quote:
                        break
                    j += 1
                tokens.append(line[i : j + 1])
                i = j + 1
            elif c.isalpha() or c == "_":
                j = i
                while j < len(line) and (line[j].isalnum() or line[j] == "_"):
                    j += 1
                tokens.append(line[i:j])
                i = j
            elif c.isdigit() or (c == "-" and i + 1 < len(line) and line[i + 1].isdigit()):
                j = i + 1 if c == "-" else i
                while j < len(line) and (line[j].isdigit() or line[j] == "."):
                    j += 1
                tokens.append(line[i:j])
                i = j
            elif not c.isspace():
                tokens.append(c)
                i += 1
            else:
                i += 1
        return tokens

    def _parse_expr(self, tokens, pos):
        if pos >= len(tokens):
            return None, pos
        token = tokens[pos]

        if token.startswith("$"):
            var_name = token[1:]
            if pos + 1 < len(tokens) and tokens[pos + 1] == "(":
                func_name = var_name
                args = []
                pos += 2
                while pos < len(tokens) and tokens[pos] != ")":
                    if tokens[pos] == ",":
                        pos += 1
                        continue
                    arg, pos = self._parse_expr(tokens, pos)
                    if arg is not None:
                        args.append(arg)
                if pos < len(tokens) and tokens[pos] == ")":
                    pos += 1
                return ("call", func_name, args), pos
            while pos + 2 < len(tokens) and tokens[pos + 1] == "." and tokens[pos + 2][0].isalpha():
                var_name += "." + tokens[pos + 2]
                pos += 2
            return ("var", var_name), pos + 1

        if token.startswith('"') or token.startswith("'"):
            return ("str", token[1:-1]), pos + 1

        if token.replace(".", "").isdigit():
            return ("num", token), pos + 1

        if pos + 1 < len(tokens) and tokens[pos + 1] == "(":
            func_name = token
            args = []
            pos += 2
            while pos < len(tokens) and tokens[pos] != ")":
                if tokens[pos] == ",":
                    pos += 1
                    continue
                arg, pos = self._parse_expr(tokens, pos)
                if arg is not None:
                    args.append(arg)
            if pos < len(tokens) and tokens[pos] == ")":
                pos += 1
            return ("call", func_name, args), pos

        return ("ident", token), pos + 1

    def _sub_vars(self, text):
        def _repl(m):
            name = m.group(1)
            if name.startswith("$"):
                name = name[1:]
                if "." in name:
                    return self._resolve_dotted_var(name)
                return self.vars.get(name, m.group(0))
            if "." in name:
                return m.group(0)
            return self.vars.get(name, m.group(0))
        return re.sub(r"\{(\$?\w+(?:\.\w+)*)\}", _repl, text)

    def _resolve_dotted_var(self, path):
        parts = path.split(".")
        val = self.vars.get(parts[0], "")
        if not val:
            return ""
        for part in parts[1:]:
            try:
                obj = json.loads(val) if isinstance(val, str) else val
                val = obj.get(part, "")
            except Exception:
                return ""
        if isinstance(val, dict) or isinstance(val, list):
            return json.dumps(val, ensure_ascii=False)
        return str(val)

    def _evaluate(self, node):
        if node is None:
            return ""
        typ = node[0]
        if typ == "str":
            return self._sub_vars(node[1])
        if typ == "num":
            return str(node[1])
        if typ == "var":
            name = node[1]
            if "." in name:
                return self._resolve_dotted_var(name)
            return self.vars.get(name, "")
        if typ == "ident":
            name = node[1]
            if name in self.vars:
                return self.vars[name]
            return name
        if typ == "call":
            return self._call_function(node[1], node[2])
        return ""

    def _call_function(self, name, args):
        name = name.lower()

        # Lazy-evaluate functions: evaluate all non-branch args up front
        # but keep raw AST nodes for branch selections.
        def _eval_all(nodes):
            return [self._evaluate(n) for n in nodes]

        if name in ("ifcontains", "if_contains"):
            cond_raw = args[:2]
            cond = _eval_all(cond_raw)
            var_val = cond[0] if cond else ""
            search = cond[1] if len(cond) > 1 else ""
            if search in var_val and len(args) > 2:
                return self._evaluate(args[2])
            if search not in var_val and len(args) > 3:
                return self._evaluate(args[3])
            return ""

        if name in ("ifempty", "if_empty"):
            var_val = self._evaluate(args[0]) if args else ""
            if not var_val and len(args) > 1:
                return self._evaluate(args[1])
            if var_val and len(args) > 2:
                return self._evaluate(args[2])
            return ""

        if name in ("ifgreater", "ifless", "ifgreaterequal", "iflessequal", "ifequals", "if_greater", "if_less", "if_greater_equal", "if_less_equal", "if_equals"):
            a_str = self._evaluate(args[0]) if args else "0"
            b_str = self._evaluate(args[1]) if len(args) > 1 else "0"
            if name in ("ifequals", "if_equals"):
                a, b = a_str, b_str
            elif _is_int_str(b_str) and _is_int_str(a_str):
                a, b = int(a_str), int(b_str)
            elif _is_float_str(b_str) and _is_float_str(a_str):
                a, b = float(a_str), float(b_str)
            else:
                a, b = a_str, b_str
            if name in ("ifgreater", "if_greater"):
                cond = a > b
            elif name in ("ifless", "if_less"):
                cond = a < b
            elif name in ("ifgreaterequal", "if_greater_equal"):
                cond = a >= b
            elif name in ("iflessequal", "if_less_equal"):
                cond = a <= b
            else:
                cond = a == b
            if cond and len(args) > 2:
                return self._evaluate(args[2])
            if not cond and len(args) > 3:
                return self._evaluate(args[3])
            return ""

        if name == "foreach":
            data_str = self._evaluate(args[0]) if args else "[]"
            json_path = self._evaluate(args[1]) if len(args) > 1 else ""
            var_name = self._evaluate(args[2]) if len(args) > 2 else "item"
            try:
                data = json.loads(data_str)
            except Exception:
                return "error: invalid JSON in foreach"
            if json_path:
                for part in json_path.split("."):
                    if isinstance(data, dict):
                        data = data.get(part, [])
                    else:
                        data = []
                        break
            if isinstance(data, dict):
                data = data.get("data", data) if "data" in data else [data]
            if isinstance(data, dict):
                data = [data]
            if not isinstance(data, list):
                return f"error: path '{json_path}' does not resolve to an array in foreach"
            saved = self.vars.get(var_name)
            results = []
            for item in data:
                item_str = json.dumps(item, ensure_ascii=False) if isinstance(item, (dict, list)) else str(item)
                self.vars[var_name] = item_str
                if len(args) > 3:
                    result = self._evaluate(args[3])
                    if result:
                        results.append(str(result))
                if not self._running:
                    break
            if saved is not None:
                self.vars[var_name] = saved
            elif var_name in self.vars:
                del self.vars[var_name]
            return "\n".join(results) if results else ""

        evaluated = _eval_all(args)

        def _tof(v):
            try: return float(v)
            except Exception: return 0.0

        if name in _SIDE_EFFECT_FUNCTIONS and not self._auth_all and self.auth_callback:
            result = self.auth_callback(self.script_name, name)
            if result == "deny":
                self._running = False
                return ""
            if result == "all":
                self._auth_all = True

        if name == "ai":
            prompt = evaluated[0] if evaluated else ""
            explicit_memory = len(evaluated) > 1
            use_memory = explicit_memory and evaluated[1].strip().lower() in ("true", "1", "yes", "memory")

            if not explicit_memory and getattr(self.app, 'auto_context_selection', False):
                import tool_groups
                use_memory = tool_groups.needs_memory(prompt, self.app.language)
                if getattr(self.app, 'debug_enabled', False):
                    print(f"[DEBUG] needs_memory({prompt[:80]}) = {use_memory}  (lang={self.app.language})")

            mcp, tools = init_mcp(self.app.mcp_server_url, timeout=120, log_prefix="[VASScript]")

            if tools and not self.app.allow_ai_scripts:
                tools = [t for t in tools if t["function"]["name"] not in ("interact", "script")]

            import tool_groups
            explicit_groups = [str(evaluated[i]).strip() for i in range(2, len(evaluated)) if evaluated[i]]
            if explicit_groups:
                tools = tool_groups.resolve_tool_names(explicit_groups, tools,
                                                        getattr(self.app, 'debug_enabled', False))
            elif tools:
                groups = tool_groups.select_tool_groups(prompt, self.app.language)
                tools = tool_groups.resolve_tool_names(groups, tools,
                                                        getattr(self.app, 'debug_enabled', False))

            system_content = ""
            if use_memory:
                now = time.strftime("%Y-%m-%d (%A) %H:%M:%S")
                base = self.app.system_message or ""
                from i18n import t as _ti18n
                date_prefix = _ti18n("ai.date_prefix", self.app.language)
                system_content = f"{base}\n\n{date_prefix}{now}".strip()

                memory_content = self.app.memory.build_content(prompt)
                from prompts import MCP_PROMPT, append_tool_descriptions, _load_vascript_reference
                tools_block = append_tool_descriptions(MCP_PROMPT, tools) if tools else MCP_PROMPT
                if self.app.allow_ai_scripts:
                    vas_ref = _load_vascript_reference()
                    tools_block += vas_ref
                system_content = system_content + memory_content + tools_block

            messages = [{"role": "system", "content": system_content}] if system_content else []
            messages.append({"role": "user", "content": prompt})

            kwargs = dict(
                model=self.app.ai_model,
                messages=messages,
                temperature=0.7,
                extra_body={"disable_thinking": True},
            )
            if tools:
                kwargs["tools"] = tools

            if getattr(self.app, 'debug_enabled', False):
                if messages:
                    sys_txt = messages[0].get("content", "")
                    sys_len = len(sys_txt)
                    print(f"[Debug] --- [VASScript] AI Request ---")
                    print(f"[Debug] [VASScript] System ({sys_len} chars):\n{sys_txt[:1000]}{'...[truncated]' if sys_len > 1000 else ''}")
                usr_txt = messages[-1].get("content", "") if messages else prompt
                print(f"[Debug] [VASScript] User ({len(usr_txt)} chars):\n{usr_txt}")

            self.app._ai_lock.acquire()
            try:
                msg = call_with_retry(lambda: self.app.openai_client.chat.completions.create(**kwargs), log_prefix="[VASScript]").choices[0].message
                msg = execute_mcp_tool_calls(messages, msg, mcp, tools, self.app.openai_client, self.app.ai_model, log_prefix="[VASScript]", gui=self.app.gui)
            except Exception as e:
                print(f"[VASScript] AI error: {e}")
                return f"error: {e}"
            finally:
                self.app._ai_lock.release()

            resp = msg.content or ""
            if getattr(self.app, 'debug_enabled', False):
                print(f"[Debug] --- [VASScript] AI Response ({len(resp)} chars) ---\n{resp}")

            return resp

        if name == "ai_raw":
            prompt = evaluated[0] if evaluated else ""
            messages = [{"role": "user", "content": prompt}]
            kwargs = dict(
                model=self.app.ai_model,
                messages=messages,
                temperature=0.3,
                extra_body={"disable_thinking": True},
            )
            self.app._ai_lock.acquire()
            try:
                msg = call_with_retry(
                    lambda: self.app.openai_client.chat.completions.create(**kwargs),
                    retries=2, delays=(1, 2), log_prefix="[VASScript]"
                ).choices[0].message
            except Exception as e:
                print(f"[VASScript] AI raw error: {e}")
                return f"error: {e}"
            finally:
                self.app._ai_lock.release()
            resp = msg.content or ""
            return resp

        if name == "say":
            text = evaluated[0] if evaluated else ""
            if not text.strip():
                return ""
            if self._silent:
                return ""
            speed = float(_tof(evaluated[1])) if len(evaluated) > 1 else 1.0
            self._do_say(text, speed)
            return ""

        if name == "say_async":
            text = evaluated[0] if evaluated else ""
            self.app.tts.enqueue(text)
            return ""

        if name == "listen":
            prompt = evaluated[0] if evaluated else ""
            if prompt:
                self._do_say(prompt)
            result = self.app._listen_once()
            return result

        if name == "exit":
            self._running = False
            return ""

        if name == "wait":
            secs = float(evaluated[0]) if evaluated else 0
            time.sleep(secs)
            return ""

        if name == "trim":
            return (evaluated[0] if evaluated else "").strip()

        if name == "len":
            return str(len(evaluated[0] if evaluated else ""))

        if name in ("tonum", "to_num"):
            val = evaluated[0] if evaluated else ""
            try:
                f = float(val)
                return str(int(f)) if f == int(f) else str(f)
            except (ValueError, TypeError):
                return val

        if name == "add":
            try:
                a = float(evaluated[0]) if evaluated else 0
                b = float(evaluated[1]) if len(evaluated) > 1 else 0
                result = a + b
                return str(int(result)) if result == int(result) else str(result)
            except (ValueError, TypeError):
                return "0"

        if name == "sub":
            try:
                a = float(evaluated[0]) if evaluated else 0
                b = float(evaluated[1]) if len(evaluated) > 1 else 0
                result = a - b
                return str(int(result)) if result == int(result) else str(result)
            except (ValueError, TypeError):
                return "0"

        if name == "mul":
            try:
                a = float(evaluated[0]) if evaluated else 0
                b = float(evaluated[1]) if len(evaluated) > 1 else 1
                result = a * b
                return str(int(result)) if result == int(result) else str(result)
            except (ValueError, TypeError):
                return "0"

        if name == "div":
            try:
                a = float(evaluated[0]) if evaluated else 0
                b = float(evaluated[1]) if len(evaluated) > 1 else 1
                result = a / b if b != 0 else 0
                return str(int(result)) if result == int(result) else str(result)
            except (ValueError, TypeError):
                return "0"

        if name == "contains":
            text = evaluated[0] if evaluated else ""
            substr = evaluated[1] if len(evaluated) > 1 else ""
            return str(substr in text)

        if name == "equals":
            a = evaluated[0] if evaluated else ""
            b = evaluated[1] if len(evaluated) > 1 else ""
            return str(a == b)

        if name == "run":
            cmd = evaluated[0] if evaluated else ""
            deny_list = [
                "remove-item", "rm ", "del ", "format-", "clear-", "stop-",
                "restart-computer", "shutdown", "stop-computer", "rm -rf"
            ]
            cmd_lower = cmd.lower()
            for bad in deny_list:
                if bad in cmd_lower:
                    return f"error: command blocked by security policy (contains '{bad}')"
            print(f"[Security] run() executing: {cmd[:200]}")
            try:
                if sys.platform == "win32":
                    result = subprocess.run(
                        ["powershell", "-NoProfile", "-Command", cmd],
                        capture_output=True, text=True, encoding="utf-8", errors="replace",
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        timeout=30,
                        cwd=os.path.join(get_project_root(), "Allowed_root")
                    )
                else:
                    result = subprocess.run(
                        cmd, shell=True,
                        capture_output=True, text=True, encoding="utf-8", errors="replace",
                        timeout=30,
                        cwd=os.path.join(get_project_root(), "Allowed_root")
                    )
                output = (result.stdout or "").strip()
                if result.stderr:
                    stderr = result.stderr.strip()
                    if stderr:
                        output = (output + "\n" + stderr).strip()
                return output or ("ok" if result.returncode == 0 else f"error: exit code {result.returncode}")
            except Exception as e:
                return f"error: {e}"

        if name == "launch_app":
            query = evaluated[0] if evaluated else ""
            args = evaluated[1] if len(evaluated) > 1 else ""
            if not str(query).strip():
                return "error: no app name specified"
            from app_launcher import launch
            return launch(str(query), str(args))

        if name == "close":
            target = evaluated[0] if evaluated else ""
            timeout_val = float(evaluated[1]) if len(evaluated) > 1 else 5.0
            if not str(target).strip():
                return "false"
            from app_launcher import close_app
            return close_app(str(target), timeout_val)

        if name == "list_apps":
            from app_launcher import list_apps as _list_apps
            apps = _list_apps()
            out = [{"name": a["name"], "path": a["path"]} for a in apps]
            return json.dumps(out, ensure_ascii=False)

        if name == "screen_highlight":
            cx = int(_tof(evaluated[0])) if evaluated else 0
            cy = int(_tof(evaluated[1])) if len(evaluated) > 1 else 0
            w = int(_tof(evaluated[2])) if len(evaluated) > 2 else 100
            h = int(_tof(evaluated[3])) if len(evaluated) > 3 else 50
            dur = _tof(evaluated[4]) if len(evaluated) > 4 else 1.0
            self.app.gui.show_highlight(cx - w // 2, cy - h // 2, w, h, dur)
            return ""

        if name == "screen_click":
            from pynput.mouse import Button, Controller
            if not evaluated:
                Controller().click(Button.left)
                return "ok"
            x = int(_tof(evaluated[0])) if evaluated else 0
            y = int(_tof(evaluated[1])) if len(evaluated) > 1 else 0
            if sys.platform == "win32":
                import ctypes
                dc = ctypes.windll.user32.GetDC(0)
                dpi = ctypes.windll.gdi32.GetDeviceCaps(dc, 88)
                ctypes.windll.user32.ReleaseDC(0, dc)
                if dpi != 96:
                    scale = dpi / 96.0
                    x = int(x / scale)
                    y = int(y / scale)
            mouse = Controller()
            try:
                cx, cy = mouse.position
                dist = math.hypot(x - cx, y - cy)
                dur = max(0.05, min(0.5, dist * dist / 80000))
                steps = max(5, int(dur * 60))
                for i in range(1, steps + 1):
                    t = i / steps
                    t = t * (2 - t)
                    wx = int(cx + (x - cx) * t)
                    wy = int(cy + (y - cy) * t)
                    mouse.position = (wx, wy)
                    time.sleep(dur / steps)
                time.sleep(0.05)
                mouse.position = (x, y)
                mouse.click(Button.left)
            except Exception as e:
                return f"errore click: {e}"
            return "ok"

        if name == "screen_search":
            query = evaluated[0] if evaluated else ""
            if not query:
                return ""
            import mss
            import numpy as np
            with mss.MSS() as sct:
                monitor = sct.monitors[1]
                img = sct.grab(monitor)
                frame = np.array(img)
            frame = self._preprocess_screen(frame)
            if getattr(self.app, 'debug_enabled', False):
                import uuid, os as _os
                _os.makedirs("log", exist_ok=True)
                from PIL import Image as _PILImage
                debug_path = _os.path.join("log", f"ocr_debug_{uuid.uuid4().hex[:6]}.png")
                _PILImage.fromarray(frame[:,:,:3]).save(debug_path)
                print(f"[OCR Debug] Saved preprocessed image: {debug_path}")
            lang_codes = self._ocr_langs()
            if VASScript._ocr_reader is None or VASScript._ocr_active_langs != lang_codes:
                import easyocr
                VASScript._ocr_reader = easyocr.Reader(
                    lang_codes, gpu=True, verbose=False
                )
                VASScript._ocr_active_langs = lang_codes
            results = VASScript._ocr_reader.readtext(frame)
            matches = []
            for bbox, text, conf in results:
                ql = query.lower()
                tl = text.lower()
                if ql in tl:
                    ratio = 1.0
                else:
                    ratio = fuzzy_ratio(ql, tl)
                    if ratio < 0.70:
                        continue
                xs = [p[0] for p in bbox]
                ys = [p[1] for p in bbox]
                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)
                cx = (min_x + max_x) / 2
                cy = (min_y + max_y) / 2
                matches.append({
                    "text": text,
                    "x": int(cx),
                    "y": int(cy),
                    "w": int(max_x - min_x),
                    "h": int(max_y - min_y),
                    "ratio": ratio,
                })
            if matches:
                matches.sort(key=lambda m: m["ratio"], reverse=True)
                best = matches[0]
                self.vars["_sx"] = str(best["x"])
                self.vars["_sy"] = str(best["y"])
                self.vars["_sw"] = str(best["w"])
                self.vars["_sh"] = str(best["h"])
            else:
                self.vars["_sx"] = ""
                self.vars["_sy"] = ""
                self.vars["_sw"] = ""
                self.vars["_sh"] = ""
            return json.dumps(matches, ensure_ascii=False)

        if name in ("sendtext", "send_text"):
            text = evaluated[0] if evaluated else ""
            if text:
                from pynput.keyboard import Controller, Key
                import random as _random
                kb = Controller()
                for ch in text:
                    if ch == "\n":
                        kb.press(Key.enter)
                        kb.release(Key.enter)
                    elif ch == "\t":
                        kb.press(Key.tab)
                        kb.release(Key.tab)
                    else:
                        kb.press(ch)
                        kb.release(ch)
                    time.sleep(_random.uniform(0.10, 0.15))
            return "ok"

        if name in ("setactivewindow", "set_active_window"):
            name_arg = evaluated[0] if evaluated else ""
            if name_arg:
                from window_manager import set_active_window
                return "ok" if set_active_window(name_arg) else "not found"
            return "not found"

        if name in ("addevent", "add_event"):
            d = evaluated[0] if evaluated else ""
            t = evaluated[1] if len(evaluated) > 1 else "00:00"
            dur = evaluated[2] if len(evaluated) > 2 else "60"
            desc = evaluated[3] if len(evaluated) > 3 else ""
            recur = evaluated[4] if len(evaluated) > 4 else ""
            return self._manage_events("add", d, t, dur, desc, recur)

        if name in ("listevents", "list_events"):
            until = evaluated[0] if evaluated else ""
            return self._manage_events("list", until)

        if name in ("removeevent", "delevent", "remove_event", "delete_event"):
            ename = evaluated[0] if evaluated else ""
            date = evaluated[1] if len(evaluated) > 1 else ""
            time_arg = evaluated[2] if len(evaluated) > 2 else ""
            return self._manage_events("remove", ename, date, time_arg)

        if name in ("readinfo", "read_info"):
            vid = evaluated[0] if evaluated else ""
            return self._manage_info("read", vid)

        if name in ("writeinfo", "write_info"):
            text = evaluated[0] if evaluated else ""
            return self._manage_info("write", text)

        if name in ("readstate", "read_state"):
            key = evaluated[0] if evaluated else ""
            with VASScript._state_lock:
                val = VASScript._state.get(key, "")
            if getattr(self.app, 'debug_enabled', False):
                print(f"[VASScript] readstate({key!r}) -> {val!r}")
            return val

        if name in ("writestate", "write_state"):
            key = evaluated[0] if evaluated else ""
            val = evaluated[1] if len(evaluated) > 1 else ""
            if key:
                with VASScript._state_lock:
                    VASScript._state[key] = val
                if getattr(self.app, 'debug_enabled', False):
                    print(f"[VASScript] writestate({key!r}, {val!r}) -> ok")
                return "ok"
            return "error: key required"

        if name in ("clipboardget", "clipboard_get"):
            try:
                import pyperclip
                return pyperclip.paste()
            except Exception:
                return ""

        if name in ("clipboardset", "clipboard_set"):
            text = evaluated[0] if evaluated else ""
            try:
                import pyperclip
                pyperclip.copy(text)
                return "ok"
            except Exception:
                return "error"

        if name in ("savetags", "save_tags"):
            tags = evaluated[0] if evaluated else ""
            return self._manage_memory_tags(tags)

        if name == "timer_start":
            dur = evaluated[0] if evaluated else ""
            return self.app.timer_manager.start(dur)

        if name == "timer_list":
            return self.app.timer_manager.list_all()

        if name == "timer_cancel":
            tid = evaluated[0] if evaluated else ""
            return self.app.timer_manager.cancel(tid)

        if name == "notify":
            text = evaluated[0] if evaluated else ""
            priority = int(evaluated[1]) if len(evaluated) > 1 and evaluated[1].strip().isdigit() else 1
            link = evaluated[2] if len(evaluated) > 2 else ""
            data = {"type": "script"}
            if link:
                data["link"] = link
            return self.app.notification_manager.add(text, priority, data=data)

        if name == "form":
            title = evaluated[0] if evaluated else ""
            fields = evaluated[1:]
            return self.app.gui.request_form(title, fields)

        if name == "inject":
            text = evaluated[0] if evaluated else ""
            self.app.inject_context(text)
            return "ok"

        if name == "inject_memory":
            text = evaluated[0] if evaluated else ""
            return self.app.inject_memory(text)

        if name == "compress_memory":
            try:
                self.app._trim_memory_if_needed(force=True)
                return "ok: memory compression completed"
            except Exception as e:
                return f"error: {e}"

        if name == "fetch_text":
            url = evaluated[0] if evaluated else ""
            return self._fetch_web(url, "webfetch")

        if name == "fetch_json":
            url = evaluated[0] if evaluated else ""
            return self._fetch_json(url)

        if name == "search_web":
            query = evaluated[0] if evaluated else ""
            return self._fetch_web(query, "websearch")

        if name == "gcal_today":
            if not self._gcal_enabled():
                return "error: Google Calendar is not enabled (calendar_enabled=false in settings.ini)"
            return self._gcal_list("today")

        if name == "gcal_tomorrow":
            if not self._gcal_enabled():
                return "error: Google Calendar is not enabled (calendar_enabled=false in settings.ini)"
            return self._gcal_list("tomorrow")

        if name == "gcal_add":
            if not self._gcal_enabled():
                return "error: Google Calendar is not enabled (calendar_enabled=false in settings.ini)"
            summary = evaluated[0] if evaluated else ""
            start = evaluated[1] if len(evaluated) > 1 else ""
            end = evaluated[2] if len(evaluated) > 2 else ""
            desc = evaluated[3] if len(evaluated) > 3 else ""
            return self._gcal_add(summary, start, end, desc)

        if name == "gcal_search":
            if not self._gcal_enabled():
                return "error: Google Calendar is not enabled (calendar_enabled=false in settings.ini)"
            query = evaluated[0] if evaluated else ""
            return self._gcal_search(query)

        if name == "google_home_command":
            mute = evaluated[1].strip().lower() == "false" if len(evaluated) > 1 else False
            return self._gh_exec(evaluated[0] if evaluated else "", play_audio=not mute)

        if name == "google_home_ask":
            mute = evaluated[1].strip().lower() == "false" if len(evaluated) > 1 else False
            return self._gh_exec(evaluated[0] if evaluated else "", play_audio=not mute)

        if name == "get_weather":
            loc = evaluated[0] if evaluated else ""
            return self._do_weather(loc)

        if name in ("getidle", "get_idle"):
            if hasattr(self.app, 'idle_tracker') and self.app.idle_tracker:
                seconds = self.app.idle_tracker.get_total_idle_seconds()
                if getattr(self.app, 'debug_enabled', False):
                    import time as _t
                    input_idle = self.app.idle_tracker.get_input_idle_seconds()
                    voice_idle = _t.time() - self.app.idle_tracker._last_voice_ts
                    fullscreen = self.app.idle_tracker._is_fullscreen()
                    print(f"[VASScript] getidle() -> input={input_idle:.1f}s voice={voice_idle:.1f}s fullscreen={fullscreen} total={seconds:.1f}s")
            else:
                try:
                    from idle_tracker import IdleTracker
                    seconds = IdleTracker().get_total_idle_seconds()
                except ImportError:
                    seconds = -1
            return '{"idle_seconds": ' + f'{seconds:.1f}' + '}'

        if name in ("getdatetime", "get_datetime"):
            from datetime import datetime
            lang = (evaluated[0] if evaluated else "").strip().lower()
            now = datetime.now()
            ts = int(now.timestamp())
            if not lang:
                dt_str = now.strftime("%Y-%m-%d %H:%M")
            else:
                months = {
                    "it": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
                           "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"],
                    "en": ["January", "February", "March", "April", "May", "June",
                           "July", "August", "September", "October", "November", "December"],
                    "de": ["Januar", "Februar", "März", "April", "Mai", "Juni",
                           "Juli", "August", "September", "Oktober", "November", "Dezember"],
                    "fr": ["janvier", "février", "mars", "avril", "mai", "juin",
                           "juillet", "août", "septembre", "octobre", "novembre", "décembre"],
                    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                           "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
                    "pt": ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
                           "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"],
                }
                m = months.get(lang, months["en"])
                mn = m[now.month - 1]
                day = str(now.day)
                year = str(now.year)
                hm = now.strftime("%H:%M")
                if lang == "it":
                    dt_str = f"{day} {mn} {year} {hm}"
                elif lang in ("en", "fr"):
                    dt_str = f"{mn} {day}, {year} {hm}"
                elif lang == "de":
                    dt_str = f"{day}. {mn} {year} {hm}"
                elif lang == "es":
                    dt_str = f"{day} de {mn} de {year} {hm}"
                elif lang == "pt":
                    dt_str = f"{day} de {mn} de {year} {hm}"
                elif lang == "ja":
                    dt_str = f"{year}年{now.month}月{day}日 {hm}"
                elif lang == "ko":
                    dt_str = f"{year}년 {now.month}월 {day}일 {hm}"
                elif lang == "zh":
                    dt_str = f"{year}年{now.month}月{day}日 {hm}"
                else:
                    dt_str = now.strftime("%Y-%m-%d %H:%M")
            result = {
                "datetime": dt_str,
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M"),
                "hour": now.strftime("%H"),
                "minute": now.strftime("%M"),
                "timestamp": str(ts),
                "year": str(now.year),
                "month": str(now.month),
                "day": str(now.day),
            }
            self.vars["datetime"] = dt_str
            self.vars["date"] = now.strftime("%Y-%m-%d")
            self.vars["time"] = now.strftime("%H:%M")
            self.vars["hour"] = now.strftime("%H")
            self.vars["minute"] = now.strftime("%M")
            self.vars["timestamp"] = str(ts)
            self.vars["year"] = str(now.year)
            self.vars["month"] = str(now.month)
            self.vars["day"] = str(now.day)
            return json.dumps(result)

        if name in ("prettyevents", "pretty_events"):
            raw = evaluated[0] if evaluated else "[]"
            try:
                events = json.loads(raw)
                if isinstance(events, dict):
                    events = [events]
            except Exception:
                return raw
            from datetime import datetime as _dt
            from i18n import t as _t
            lang = getattr(self.app, "language", "en")
            tr = lambda k: _t(f"events.time_refs.{k}", lang)
            now = _dt.now()
            parsed = []
            for ev in events:
                edate = ev.get("date", "")
                etime = ev.get("time", "")
                desc = ev.get("description", "")
                dur = ev.get("duration", 0)
                recur = ev.get("recur", "")
                try:
                    dt = _dt.strptime(f"{edate} {etime}", "%Y-%m-%d %H:%M")
                    dt_ts = dt.timestamp()
                except Exception:
                    dt_ts = 0
                    dt = None
                parsed.append((dt_ts, dt, desc, dur, recur, etime))
            parsed.sort(key=lambda x: x[0])
            lines = []
            for dt_ts, dt, desc, dur, recur, etime in parsed:
                if dt is None:
                    relative = tr("unknown_date")
                else:
                    diff = dt_ts - now.timestamp()
                    if diff < 0:
                        relative = tr("expired")
                    elif diff < 3600:
                        m = int(diff // 60)
                        relative = f"{tr('in')} {m} {tr('minute_s')}" if m > 1 else f"{tr('in')} 1 {tr('minute_s')}"
                    elif diff < 86400:
                        h = int(diff // 3600)
                        m = int((diff % 3600) // 60)
                        if m > 0:
                            relative = f"{tr('in')} {h}{tr('hour_h')}{m:02d}"
                        else:
                            relative = f"{tr('in')} {h} {tr('hour_s')}" if h > 1 else f"{tr('in')} 1 {tr('hour_s').rstrip('s')}"
                    elif diff < 604800:
                        d = int(diff // 86400)
                        relative = tr("tomorrow") if d == 1 else f"{tr('in')} {d} {tr('days')}"
                    elif diff < 2592000:
                        w = int(diff // 604800)
                        relative = f"{tr('in')} 1 {tr('week_s')}" if w == 1 else f"{tr('in')} {w} {tr('weeks')}"
                    else:
                        m = int(diff // 2592000)
                        relative = f"{tr('in')} 1 {tr('month_s')}" if m == 1 else f"{tr('in')} {m} {tr('months')}"
                time_str = dt.strftime("%H:%M") if dt else etime
                line = f"{relative} {tr('at')} {time_str} - {desc} ({dur} {tr('minute_s')})"
                if recur:
                    line += f" [{tr('every')} {_recur_label(recur)}]"
                lines.append(line)
            return "\n".join(lines)

        if name == "filter_json":
            raw = evaluated[0] if evaluated else "[]"
            fmt = evaluated[1] if len(evaluated) > 1 else "{item}"
            filters = [f.strip() for f in evaluated[2:] if f.strip()]
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    if "data" in data and isinstance(data["data"], list):
                        data = data["data"]
                    else:
                        data = [data]
            except Exception:
                return raw
            import re as _re
            def _fj_nested(item, key, default=""):
                parts = key.split(".")
                val = item
                for p in parts:
                    if isinstance(val, dict):
                        val = val.get(p)
                    else:
                        return default
                    if val is None:
                        return default
                return str(val)
            for f in filters:
                m = _re.match(r'^([\w.]+)\s*(>=|<=|>|<|=)\s*(.*)$', f)
                if not m:
                    continue
                key, op, val = m.group(1), m.group(2), m.group(3).strip()
                filtered = []
                for item in data:
                    field_val = _fj_nested(item, key)
                    try:
                        fv = float(val)
                        ff = float(field_val)
                        numeric = True
                    except (ValueError, TypeError):
                        numeric = False
                    if numeric and op != "=":
                        cond = (
                            (op == ">=" and ff >= fv) or
                            (op == "<=" and ff <= fv) or
                            (op == ">" and ff > fv) or
                            (op == "<" and ff < fv)
                        )
                    elif numeric and op == "=":
                        cond = ff == fv
                    elif op == "=":
                        cond = field_val.lower() == val.lower()
                    else:
                        cond = (
                            (op == ">=" and field_val >= val) or
                            (op == "<=" and field_val <= val) or
                            (op == ">" and field_val > val) or
                            (op == "<" and field_val < val)
                        )
                    if cond:
                        filtered.append(item)
                data = filtered
            if not data:
                return ""
            lines = []
            for item in data:
                try:
                    lines.append(fmt.format(**item))
                except (KeyError, ValueError, AttributeError):
                    lines.append(_re.sub(r'\{([\w.]+)\}', lambda m: _fj_nested(item, m.group(1)), fmt))
            return "\n".join(lines)

        if name == "print":
            text = evaluated[0] if evaluated else ""
            print(f"[VASScript] {text}", flush=True)
            return ""

        if name in ("readfile", "read_file"):
            filepath = evaluated[0] if evaluated else ""
            if not filepath:
                return "error: path required"
            import os as _os
            base = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "Allowed_root")
            p = _os.path.normpath(_os.path.join(base, filepath))
            if not p.startswith(_os.path.normpath(base)):
                return "error: access denied"
            try:
                with open(p, encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                return f"error: {e}"

        if name in ("writefile", "write_file"):
            filepath = evaluated[0] if evaluated else ""
            content = evaluated[1] if len(evaluated) > 1 else ""
            if not filepath:
                return "error: path required"
            import os as _os
            base = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "Allowed_root")
            p = _os.path.normpath(_os.path.join(base, filepath))
            if not p.startswith(_os.path.normpath(base)):
                return "error: access denied"
            try:
                _os.makedirs(_os.path.dirname(p), exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(content)
                return f"ok: wrote {len(content)} bytes to {filepath}"
            except Exception as e:
                return f"error: {e}"

        if name == "rss_fetch":
            return "error: rss_fetch is deprecated — RSS polling is now handled by the rss_reader plugin"

        raise ValueError(f"unknown function: {name}()")

    def _manage_memory_tags(self, tags):
        from pathlib import Path
        vass_root = Path(__file__).resolve().parent.parent
        allowed_root = vass_root / "Allowed_root"

        DEFAULT_TAGS = {
            "personal_data": 10, "health": 10, "finance": 10,
            "family": 10, "pets": 10,
            "contacts": 8,
            "preferences": 7, "personal_interests": 7, "purchases": 7,
            "orders": 6, "bills": 6, "invoices": 6, "work": 6, "education": 6,
            "favorite_music": 5, "food": 5, "home": 5, "personal_means_of_transport": 5,
            "deliveries": 4, "travel": 4, "tech": 4, "events": 4,
            "sales": 3, "generic": 1,
        }
        cfg_path = allowed_root / "tags_config.json"
        TAG_WEIGHTS = DEFAULT_TAGS
        MIN_RELEVANCE = 10
        if cfg_path.exists():
            try:
                with open(cfg_path, encoding="utf-8") as f:
                    cfg = json.loads(f.read())
                    TAG_WEIGHTS = cfg.get("tags", DEFAULT_TAGS)
                    MIN_RELEVANCE = cfg.get("min_relevance", 10)
            except Exception:
                log_exc()

        tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()]
        if not tag_list:
            return "error: no valid tags"
        invalid = [t for t in tag_list if t not in TAG_WEIGHTS]
        if invalid:
            return f"error: invalid tags: {', '.join(invalid)}. Available: {', '.join(sorted(TAG_WEIGHTS.keys()))}"

        relevance = sum(TAG_WEIGHTS[t] for t in tag_list)
        if relevance < MIN_RELEVANCE:
            return f"skipped: relevance {relevance} < {MIN_RELEVANCE}"

        tags_path = allowed_root / "memory_tags.json"
        try:
            data = json.loads(tags_path.read_text(encoding="utf-8"))
        except Exception:
            data = {"entries": []}

        import datetime
        ts = time.time()
        entry = {
            "id": str(int(ts * 1000)),
            "tags": tag_list,
            "relevance": relevance,
            "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        data["entries"].append(entry)
        tags_path.parent.mkdir(parents=True, exist_ok=True)
        tags_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return f"ok: {len(tag_list)} tags, relevance {relevance}"

    def _manage_info(self, action, arg):
        from pathlib import Path
        vass_root = Path(__file__).resolve().parent.parent
        memory_dir = vass_root / "Allowed_root" / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)

        if action == "read":
            import re
            safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', arg)
            resolved_memory = memory_dir.resolve()
            file_path = (resolved_memory / f"{safe_name}.json").resolve()
            if not str(file_path).startswith(str(resolved_memory) + os.sep) and file_path != resolved_memory / f"{safe_name}.json":
                return json.dumps({"error": "access denied", "id": arg}, ensure_ascii=False)
            if not file_path.exists():
                return json.dumps({"error": "not found", "id": arg}, ensure_ascii=False)
            with open(str(file_path), encoding="utf-8") as f:
                data = json.load(f)
            return data.get("info", "")

        if action == "write":
            import time as _time
            vid = str(int(_time.time() * 1000))
            file_path = memory_dir / f"{vid}.json"
            with open(str(file_path), "w", encoding="utf-8") as f:
                json.dump({"info": arg}, f, ensure_ascii=False, indent=2)
            return vid

        return "error: unknown action"

    def _manage_events(self, action, *args):
        import difflib
        from datetime import date as _date

        mcp, _ = init_mcp(self.app.mcp_server_url, timeout=10)
        if not mcp:
            return "error: MCP not available"

        try:
            raw = mcp.call_tool("read_file", {"path": "events.json"})
            text = raw.get("content", [{}])[0].get("text", "{}")
            data = json.loads(text)
        except Exception:
            data = {"events": []}

        events = data.get("events", [])

        if action == "add":
            start_date, start_time, duration_str, description = args[:4]
            recur = args[4] if len(args) > 4 else ""
            if not start_date or not start_time or not start_date.strip() or not start_time.strip():
                return f"error: date and time required. Received: date='{start_date}' time='{start_time}'"
            if not description or not description.strip():
                return "error: description required"
            if recur and not _validate_recur(recur):
                return f"error: invalid recurrence format '{recur}'. Use like '1d', '7d', '2h', '1m'"
            import datetime as _dt
            normalized_date = None
            try:
                _dt.datetime.strptime(start_date, "%Y-%m-%d")
                normalized_date = start_date
            except ValueError:
                pass
            if normalized_date is None:
                try:
                    import dateparser
                    parsed = dateparser.parse(start_date, languages=["it", "en"])
                    if parsed:
                        normalized_date = parsed.strftime("%Y-%m-%d")
                except Exception:
                    log_exc()
            if normalized_date is None:
                return f"error: invalid date format '{start_date}'. Use YYYY-MM-DD."
            # Verify day-of-week matches if description mentions a day name
            _wd_it = {"lunedì": 0, "martedì": 1, "mercoledì": 2, "giovedì": 3,
                      "venerdì": 4, "sabato": 5, "domenica": 6}
            _wd_en = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                      "friday": 4, "saturday": 5, "sunday": 6}
            parsed_dt = _dt.datetime.strptime(normalized_date, "%Y-%m-%d")
            desc_lower = description.lower()
            for name, wd in {**_wd_it, **_wd_en}.items():
                if name in desc_lower:
                    if parsed_dt.weekday() != wd:
                        actual = parsed_dt.strftime("%A")
                        return (f"error: the date {normalized_date} is a {actual}, not a {name}. "
                                f"Please correct the date to match {name}.")
                    break
            try:
                dt = _dt.datetime.strptime(start_time, "%H:%M")
                normalized_time = dt.strftime("%H:%M")
            except ValueError:
                try:
                    import dateparser
                    parsed = dateparser.parse(start_time, languages=["it", "en"])
                    if parsed:
                        normalized_time = parsed.strftime("%H:%M")
                    else:
                        raise ValueError
                except Exception:
                    return f"error: invalid time format '{start_time}'. Use HH:MM."
            try:
                duration = int(duration_str) if duration_str else 60
            except (ValueError, TypeError):
                import re
                d = duration_str.lower() if duration_str else ""
                m = re.search(r"(\d+)", d)
                mins = int(m.group(1)) if m else 60
                if any(w in d for w in ("ora", "hour", "hr", "h")):
                    mins *= 60
                duration = mins
            name = f"{description}_{normalized_date}_{normalized_time}".replace(" ", "_").lower()
            event = {
                "name": name,
                "date": normalized_date,
                "time": normalized_time,
                "duration": duration,
                "description": description
            }
            if recur:
                event["recur"] = recur
            events.append(event)
            data["events"] = events
            try:
                result = mcp.call_tool("write_file", {"path": "events.json", "content": json.dumps(data, ensure_ascii=False, indent=2)})
                if result.get("isError"):
                    return f"error: failed to save event: {result.get('content', [{}])[0].get('text', 'unknown error')}"
            except Exception as e:
                return f"error: failed to save event: {e}"
            # Enqueue for memory tagging
            if hasattr(self.app, 'memory') and self.app.memory.is_source_enabled("events"):
                classify_content = (
                    f"Event: {description}\n"
                    f"Date: {normalized_date} {normalized_time}\n"
                    f"Duration: {duration} min"
                )
                self.app.memory.enqueue_external(classify_content, name, "events")
            return f"ok: added '{name}'"

        if action == "list":
            until_date = args[0] if args else ""
            today = _date.today().isoformat()
            filtered = []
            for e in events:
                edate = e.get("date", "")
                if not edate:
                    continue
                try:
                    edate_norm = _date.fromisoformat(edate)
                except ValueError:
                    try:
                        import dateparser
                        parsed = dateparser.parse(edate, languages=["it", "en"])
                        if parsed:
                            edate_norm = parsed.date()
                        else:
                            continue
                    except Exception:
                        continue
                if edate_norm.isoformat() < today:
                    continue
                if until_date and edate_norm.isoformat() > until_date:
                    continue
                out = {
                    "description": e.get("description", ""),
                    "date": e.get("date", ""),
                    "time": e.get("time", ""),
                    "duration": e.get("duration", 0),
                    "name": e.get("name", ""),
                }
                if e.get("recur"):
                    out["recur"] = e["recur"]
                if "notify" in e:
                    out["notify"] = e["notify"]
                filtered.append(out)
            filtered.sort(key=lambda e: (e.get("date", ""), e.get("time", "")))
            return json.dumps(filtered, ensure_ascii=False)

        if action == "remove":
            event_name, date, time_arg = args[0] if args else "", args[1] if len(args) > 1 else "", args[2] if len(args) > 2 else ""
            if not events:
                return "not found: no events"
            matches = []
            for e in events:
                ratio = fuzzy_ratio(event_name, e.get("description", ""))
                if ratio >= 0.75:
                    matches.append((ratio, e))
            if not matches:
                return f"not found: no event matching '{event_name}'"
            if date or time_arg:
                matches = [(r, e) for r, e in matches
                           if (not date or e.get("date") == date)
                           and (not time_arg or e.get("time") == time_arg)]
                if not matches:
                    return f"not found: no event matching '{event_name}' at {date or 'any date'} {time_arg or 'any time'}"
            if len(matches) > 1 and not date and not time_arg:
                lines = [f"  - '{e.get('description')}' on {e.get('date')} at {e.get('time')}" for _, e in matches]
                return "Multiple events match. Specify date and time to disambiguate:\n" + "\n".join(lines)
            best = max(matches, key=lambda x: x[0])
            removed = best[1]
            events = [e for e in events if e != removed]
            data["events"] = events
            try:
                result = mcp.call_tool("write_file", {"path": "events.json", "content": json.dumps(data, ensure_ascii=False, indent=2)})
                if result.get("isError"):
                    return f"error: failed to save removal: {result.get('content', [{}])[0].get('text', 'unknown error')}"
            except Exception as e:
                return f"error: failed to save removal: {e}"
            return f"ok: removed '{removed.get('description')}' on {removed.get('date')} at {removed.get('time')}"

        return "error: unknown action"

    def _fetch_web(self, param, tool_name):
        if not param:
            return "error: url/query required"
        cache, ttl = (VASScript._fetch_cache, VASScript._fetch_cache_ttl) if tool_name == "webfetch" else (VASScript._search_cache, VASScript._search_cache_ttl)
        cache_key = param.strip().lower()
        now = time.time()
        if cache_key in cache:
            ts, cached_result = cache[cache_key]
            if now - ts < ttl:
                return cached_result
        from utils import get_project_root, init_mcp
        mcp, _ = init_mcp(self.app.mcp_server_url, timeout=60)
        if not mcp:
            return "error: MCP not available"
        try:
            arg = {"webfetch": "url", "websearch": "query"}[tool_name]
            result = mcp.call_tool(tool_name, {arg: param})
            if isinstance(result, dict) and "content" in result:
                parts = []
                for item in result["content"]:
                    if isinstance(item, dict) and item.get("type") == "text":
                        parts.append(item.get("text", ""))
                result = "\n".join(parts)
            final = str(result) if result else ""
            if final and not final.startswith("error:"):
                cache[cache_key] = (now, final)
            return final
        except Exception as e:
            return f"error: {e}"

    def _fetch_json(self, url):
        if not url:
            return "error: url required"
        cache_key = url.strip().lower()
        now = time.time()
        if cache_key in VASScript._fetch_cache:
            ts, cached = VASScript._fetch_cache[cache_key]
            if now - ts < VASScript._fetch_cache_ttl:
                return cached
        try:
            import httpx
            accept_headers = ["application/json", "application/vnd.api+json", "*/*"]
            last_exc = None
            for accept in accept_headers:
                try:
                    r = httpx.get(url, timeout=30, follow_redirects=True,
                                  headers={"Accept": accept, "User-Agent": "vass/1.0"})
                    r.raise_for_status()
                    data = json.loads(r.text)
                    result = json.dumps(data, ensure_ascii=False)
                    VASScript._fetch_cache[cache_key] = (now, result)
                    return result
                except httpx.HTTPStatusError as e:
                    last_exc = e
                    if e.response.status_code != 406:
                        raise
                    continue
            raise last_exc
        except Exception as e:
            return f"error: {e}"

    def _gcal_enabled(self):
        return self.app.settings.get("calendar_enabled", "false").lower() == "true"

    def _gcal_list(self, when):
        from google_calendar import GoogleCalendar
        gcal = GoogleCalendar()
        if when == "today":
            return gcal.list_today()
        return gcal.list_tomorrow()

    def _gcal_add(self, summary, start, end, desc):
        from google_calendar import GoogleCalendar
        gcal = GoogleCalendar()
        return gcal.add_event(summary, start, end, desc)

    def _gcal_search(self, query):
        from google_calendar import GoogleCalendar
        gcal = GoogleCalendar()
        return gcal.search_events(query)

    def _gh_enabled(self):
        return self.app.settings.get("google_home_enabled", "false").lower() == "true"

    def _gh_exec(self, text, play_audio=True):
        if not self._gh_enabled():
            return "error: Google Home is not enabled (google_home_enabled=false in settings.ini)"
        model_id = self.app.settings.get("google_home_model_id", "")
        device_id = self.app.settings.get("google_home_device_id", "")
        if not model_id or not device_id:
            return "error: Google Home model_id or device_id not configured"
        import threading
        from google_home import GoogleHome
        output_device = int(self.app.settings.get("output_device", -1))
        output_device = None if output_device < 0 else output_device

        def _run_gh():
            gh = GoogleHome(model_id, device_id, self.app.language)
            result = gh.send_text_query(text)
            if "error" in result:
                err = result["error"]
                print(f"[GoogleHome] Error: {err}")
                if play_audio:
                    if err == "auth_expired":
                        self.app.tts.enqueue("Credenziali Google scadute. Apri Impostazioni per riautorizzare.")
                        _gh_disable_google_services(self.app)
                    elif err == "not_authenticated":
                        self.app.tts.enqueue("Google non configurato. Esegui la configurazione da Impostazioni.")
                        _gh_disable_google_services(self.app)
                    elif err == "timeout":
                        self.app.tts.enqueue("Google Home non risponde. Riprova.")
                    elif err == "service_unavailable":
                        self.app.tts.enqueue("Servizio Google Home non disponibile al momento.")
                    else:
                        self.app.tts.enqueue("Comando Google Home non riuscito.")
                if hasattr(self.app, 'command_executor'):
                    self.app.command_executor.track_command_outcome(text, False)
            elif result.get("audio"):
                from google_home import _classify_gh_response
                ok = _classify_gh_response(result["audio"], self.app.language)
                if hasattr(self.app, 'command_executor'):
                    self.app.command_executor.track_command_outcome(text, ok)
                if play_audio:
                    av = getattr(self.app, "app_volume", 1.0)
                    gh.play_audio_response(result["audio"], output_device, av)
            elif result.get("text"):
                if play_audio:
                    self.app.tts.enqueue(result["text"])
                if hasattr(self.app, 'command_executor'):
                    self.app.command_executor.track_command_outcome(text, True)
            gh.close()

        threading.Thread(target=_run_gh, daemon=True).start()
        return "ok"

    def _do_say(self, text, speed=1.0):
        done = threading.Event()
        self.app.tts.enqueue(text, speed, on_done=done.set)
        done.wait()

    @staticmethod
    def _parse_time_variants(raw_str, day_str=""):
        if not raw_str:
            return "", "", ""
        import re, time
        from datetime import date

        # ISO format: "2026-06-28T05:30:00" or "2026-06-28 05:30:00"
        m_iso = re.match(r'(\d{4})-(\d{2})-(\d{2})[T ](\d{1,2}):(\d{2})', raw_str)
        if m_iso:
            year, month, day = int(m_iso[1]), int(m_iso[2]), int(m_iso[3])
            h, minute = int(m_iso[4]), int(m_iso[5])
            h24 = f"{h:02d}:{minute:02d}"
            ampm = "AM" if h < 12 else "PM"
            h12 = 12 if h == 0 else (h if h <= 12 else h - 12)
            ampm_str = f"{h12}:{minute:02d} {ampm}"
            dt = time.mktime(time.struct_time((year, month, day, h, minute, 0, 0, 0, -1)))
            return ampm_str, h24, str(int(dt))

        # AM/PM format: "05:30 AM"
        m = re.match(r'(\d{1,2}):(\d{2})\s*(AM|PM)', raw_str, re.IGNORECASE)
        if m:
            h, minute, ampm = int(m.group(1)), int(m.group(2)), m.group(3).upper()
            if ampm == "PM" and h != 12:
                h += 12
            elif ampm == "AM" and h == 12:
                h = 0
            h24 = f"{h:02d}:{minute:02d}"
            if day_str:
                m_date = re.match(r'(\d{4})-(\d{2})-(\d{2})', day_str)
                if m_date:
                    y, m, d = int(m_date[1]), int(m_date[2]), int(m_date[3])
                else:
                    today = date.today()
                    y, m, d = today.year, today.month, today.day
            else:
                today = date.today()
                y, m, d = today.year, today.month, today.day
            dt = time.mktime(time.struct_time((y, m, d, h, minute, 0, 0, 0, -1)))
            return raw_str, h24, str(int(dt))

        return raw_str, raw_str, ""

    _geonames_loaded = False
    _geonames_index = {}

    @classmethod
    def _download_geonames(cls):
        import urllib.request, zipfile, tempfile, os, shutil
        url = "https://download.geonames.org/export/dump/cities500.zip"
        dest = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "config", "cities500.txt")
        try:
            print("[Geonames] Downloading cities500.zip (~3 MB)...")
            with tempfile.TemporaryDirectory() as tmp:
                zip_path = os.path.join(tmp, "cities500.zip")
                urllib.request.urlretrieve(url, zip_path)
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extract("cities500.txt", tmp)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.move(os.path.join(tmp, "cities500.txt"), dest)
            print("[Geonames] cities500.txt ready")
            return True
        except Exception as e:
            print(f"[Geonames] Download failed: {e}")
            return False

    @classmethod
    def _load_geonames(cls):
        if cls._geonames_loaded:
            return
        import os
        path = os.path.join(get_project_root(), "config", "cities500.txt")
        if not os.path.exists(path):
            if not cls._download_geonames() or not os.path.exists(path):
                cls._geonames_loaded = True
                return
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    parts = line.strip().split("\t")
                    if len(parts) >= 6:
                        name = parts[1].lower()
                        lat = float(parts[4])
                        lon = float(parts[5])
                        country = parts[8] if len(parts) > 8 else ""
                        cls._geonames_index[name] = (lat, lon, country)
            cls._geonames_loaded = True
            print(f"[Geonames] Loaded {len(cls._geonames_index)} cities")
        except Exception:
            cls._geonames_loaded = True

    @classmethod
    def _resolve_coordinates(cls, location):
        cls._load_geonames()
        if not cls._geonames_index:
            return None
        key = location.strip().lower()
        if key in cls._geonames_index:
            lat, lon, country = cls._geonames_index[key]
            return (lat, lon, country)
        best, best_r = None, 0
        for name in cls._geonames_index:
            r = fuzzy_ratio(key, name)
            if r > best_r:
                best_r = r
                best = name
        if best and best_r >= 0.85:
            lat, lon, country = cls._geonames_index[best]
            return (lat, lon, country)
        return None

    def _get_cached_weather(self, cache_key):
        now = time.time()
        if cache_key in VASScript._weather_cache:
            ts, cached = VASScript._weather_cache[cache_key]
            if now - ts < VASScript._weather_cache_ttl:
                self._set_weather_vars(cached)
                return json.dumps(cached, ensure_ascii=False)
        return None

    def _set_weather_vars(self, result):
        self.vars["temperature"] = str(result["temperature"])
        self.vars["feels_like"] = str(result["feels_like"])
        self.vars["temperature_unit_system"] = result.get("temperature_unit_system", "Celsius")
        self.vars["humidity"] = str(result["humidity"])
        self.vars["weather_description"] = result.get("description", "")
        self.vars["wind_speed"] = str(result["wind_speed"])
        self.vars["wind_direction"] = result.get("wind_direction", "")
        self.vars["weather_city"] = result.get("city", "")
        self.vars["sunrise"] = result.get("sunrise", "")
        self.vars["sunrise_24h"] = result.get("sunrise_24h", "")
        self.vars["sunrise_timestamp"] = result.get("sunrise_timestamp", "")
        self.vars["sunset"] = result.get("sunset", "")
        self.vars["sunset_24h"] = result.get("sunset_24h", "")
        self.vars["sunset_timestamp"] = result.get("sunset_timestamp", "")
        self.vars["observation_time"] = result.get("observation_time", "")
        self.vars["observation_time_24h"] = result.get("observation_time_24h", "")
        self.vars["observation_time_timestamp"] = result.get("observation_time_timestamp", "")

    def _cache_and_return_weather(self, cache_key, result):
        VASScript._weather_cache[cache_key] = (time.time(), result)
        self._set_weather_vars(result)
        return json.dumps(result, ensure_ascii=False)

    @staticmethod
    def _wmo_description(code):
        codes = {
            0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Fog", 48: "Rime fog",
            51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
            56: "Light freezing drizzle", 57: "Dense freezing drizzle",
            61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
            66: "Light freezing rain", 67: "Heavy freezing rain",
            71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
            77: "Snow grains",
            80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
            85: "Slight snow showers", 86: "Heavy snow showers",
            95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
        }
        return codes.get(int(code), f"Unknown ({code})")

    @staticmethod
    def _degrees_compass(deg):
        dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        return dirs[round(float(deg) / 22.5) % 16]

    def _weather_wttr(self, location):
        import urllib.request, urllib.parse, json
        encoded = urllib.parse.quote(location.strip()) if location.strip() else ""
        base = f"https://wttr.in/{encoded}" if encoded else "https://wttr.in/"
        url = f"{base}?format=j1"
        r = urllib.request.urlopen(url, timeout=10)
        data = json.loads(r.read().decode())
        nearest = (data.get("nearest_area") or [{}])[0]
        city = (nearest.get("areaName") or [{}])[0].get("value", "")
        region = (nearest.get("region") or [{}])[0].get("value", "")
        country = (nearest.get("country") or [{}])[0].get("value", "")
        cc = (data.get("current_condition") or [{}])[0]
        temp_c = float(cc.get("temp_C", 0))
        feels_c = float(cc.get("FeelsLikeC", 0))
        humidity = int(cc.get("humidity", 0))
        desc = (cc.get("weatherDesc") or [{}])[0].get("value", "")
        wind_speed = float(cc.get("windspeedKmph", 0))
        wind_dir = cc.get("winddir16Point", "")
        obs_time = cc.get("observation_time", "")
        weather_day = (data.get("weather") or [{}])[0]
        date_str = weather_day.get("date", "")
        astro = weather_day.get("astronomy", [{}])[0] or {}
        sr_raw = astro.get("sunrise", "")
        ss_raw = astro.get("sunset", "")
        sr, sr_24h, sr_ts = VASScript._parse_time_variants(sr_raw, date_str)
        ss, ss_24h, ss_ts = VASScript._parse_time_variants(ss_raw, date_str)
        ot, ot_24h, ot_ts = VASScript._parse_time_variants(obs_time, date_str)
        return {
            "city": city, "region": region, "country": country,
            "temperature": temp_c, "feels_like": feels_c, "humidity": humidity,
            "description": desc, "wind_speed": wind_speed, "wind_direction": wind_dir,
            "observation_time": ot, "observation_time_24h": ot_24h, "observation_time_timestamp": ot_ts,
            "temperature_unit_system": "Celsius",
            "sunrise": sr, "sunrise_24h": sr_24h, "sunrise_timestamp": sr_ts,
            "sunset": ss, "sunset_24h": ss_24h, "sunset_timestamp": ss_ts,
        }

    def _weather_openmeteo(self, lat, lon):
        import urllib.request, json
        url = (f"https://api.open-meteo.com/v1/forecast"
               f"?latitude={lat}&longitude={lon}"
               f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,wind_direction_10m"
               f"&daily=sunrise,sunset&timezone=auto&forecast_days=1")
        r = urllib.request.urlopen(url, timeout=10)
        data = json.loads(r.read().decode())
        cur = data.get("current", {})
        daily = data.get("daily", {})
        sunrise = (daily.get("sunrise") or [""])[0]
        sunset = (daily.get("sunset") or [""])[0]
        desc = self._wmo_description(cur.get("weather_code", 0))
        wind_dir = self._degrees_compass(cur.get("wind_direction_10m", 0))
        import re as _re
        sr_raw = _re.sub(r"T", " ", sunrise) if sunrise else ""
        ss_raw = _re.sub(r"T", " ", sunset) if sunset else ""
        sr, sr_24h, sr_ts = VASScript._parse_time_variants(sr_raw)
        ss, ss_24h, ss_ts = VASScript._parse_time_variants(ss_raw)
        obs_ts = int(time.time())
        ot = time.strftime("%I:%M %p", time.localtime(obs_ts))
        ot_24h = time.strftime("%H:%M", time.localtime(obs_ts))
        return {
            "city": "", "region": "", "country": "",
            "temperature": cur.get("temperature_2m", 0),
            "feels_like": cur.get("apparent_temperature", 0),
            "humidity": cur.get("relative_humidity_2m", 0),
            "description": desc,
            "wind_speed": cur.get("wind_speed_10m", 0),
            "wind_direction": wind_dir,
            "observation_time": ot, "observation_time_24h": ot_24h, "observation_time_timestamp": str(obs_ts),
            "temperature_unit_system": "Celsius",
            "sunrise": sr, "sunrise_24h": sr_24h, "sunrise_timestamp": sr_ts,
            "sunset": ss, "sunset_24h": ss_24h, "sunset_timestamp": ss_ts,
        }

    def _weather_metno(self, lat, lon):
        import urllib.request, json
        url = f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat}&lon={lon}"
        req = urllib.request.Request(url, headers={"User-Agent": "VASS/0.5 github.com/logicheneurali/vass"})
        r = urllib.request.urlopen(req, timeout=10)
        data = json.loads(r.read().decode())
        ts = data.get("properties", {}).get("timeseries", [])
        if not ts:
            raise RuntimeError("No timeseries data")
        inst = ts[0].get("data", {}).get("instant", {}).get("details", {})
        temp_c = inst.get("air_temperature", 0)
        humidity = inst.get("relative_humidity", 0)
        wind_speed = inst.get("wind_speed", 0) * 3.6
        wind_dir_deg = inst.get("wind_from_direction", 0)
        wind_dir = self._degrees_compass(wind_dir_deg)
        desc = "N/A"
        sym = ts[0].get("data", {}).get("next_1_hours", {}).get("summary", {}).get("symbol_code", "")
        if sym:
            desc = sym.replace("_", " ").title()
        sun_ts = ts[0].get("data", {}).get("next_6_hours", {}).get("details", {})
        sr_raw = sun_ts.get("sunrise", "")
        ss_raw = sun_ts.get("sunset", "")
        import re as _re
        sr_raw = _re.sub(r"T", " ", sr_raw) if sr_raw else ""
        ss_raw = _re.sub(r"T", " ", ss_raw) if ss_raw else ""
        sr, sr_24h, sr_ts = VASScript._parse_time_variants(sr_raw)
        ss, ss_24h, ss_ts = VASScript._parse_time_variants(ss_raw)
        obs_ts = int(time.time())
        ot = time.strftime("%I:%M %p", time.localtime(obs_ts))
        ot_24h = time.strftime("%H:%M", time.localtime(obs_ts))
        return {
            "city": "", "region": "", "country": "",
            "temperature": temp_c, "feels_like": temp_c, "humidity": humidity,
            "description": desc, "wind_speed": wind_speed, "wind_direction": wind_dir,
            "observation_time": ot, "observation_time_24h": ot_24h, "observation_time_timestamp": str(obs_ts),
            "temperature_unit_system": "Celsius",
            "sunrise": sr, "sunrise_24h": sr_24h, "sunrise_timestamp": sr_ts,
            "sunset": ss, "sunset_24h": ss_24h, "sunset_timestamp": ss_ts,
        }

    def _do_weather(self, location=""):
        import urllib.request, urllib.parse, json
        cache_key = location.strip().lower() or "__auto__"
        cached = self._get_cached_weather(cache_key)
        if cached is not None:
            return cached
        # Prefer coordinate-based sources (Open-Meteo, met.no): more reliable
        # than wttr.in, which can return stale/wrong data while still succeeding.
        coords = self._resolve_coordinates(location) if location.strip() else None
        if coords:
            lat, lon, _ = coords
            try:
                result = self._weather_openmeteo(lat, lon)
                return self._cache_and_return_weather(cache_key, result)
            except Exception as e:
                print(f"[Weather] Open-Meteo failed: {e}")
            try:
                result = self._weather_metno(lat, lon)
                return self._cache_and_return_weather(cache_key, result)
            except Exception as e:
                print(f"[Weather] met.no failed: {e}")
        try:
            result = self._weather_wttr(location)
            return self._cache_and_return_weather(cache_key, result)
        except Exception as e:
            print(f"[Weather] wttr.in failed: {e}")
        if not coords and not location.strip():
            return '{"error": "wttr.in auto-location failed, no geonames fallback available"}'
        return '{"error": "all weather sources failed"}'

    def _execute_line(self, line):
        tokens = self._tokenize(line)
        if not tokens:
            return

        if tokens[0].startswith("$") and len(tokens) > 1 and tokens[1] == "=":
            var_name = tokens[0][1:]
            expr, consumed = self._parse_expr(tokens, 2)
            if consumed < len(tokens):
                raise ValueError(f"unexpected token after expression: '{tokens[consumed]}'")
            value = self._evaluate(expr)
            self.vars[var_name] = value
            return value
        else:
            expr, consumed = self._parse_expr(tokens, 0)
            if consumed < len(tokens):
                raise ValueError(f"unexpected token after expression: '{tokens[consumed]}'")
            if expr:
                return self._evaluate(expr)
