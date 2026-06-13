import json
import math
import re
import subprocess
import threading
import time

from utils import call_with_retry, execute_mcp_tool_calls, init_mcp


_SIDE_EFFECT_FUNCTIONS = {"ai", "say", "run", "screen_search", "screen_click", "screen_highlight", "listen", "sendtext", "setactivewindow", "addevent", "listevents", "removeevent", "readinfo", "writeinfo", "clipboardget", "clipboardset", "savetags", "timer_start", "timer_list", "timer_cancel", "notify", "inject", "inject_memory", "fetch_text", "search_web", "gcal_today", "gcal_tomorrow", "gcal_add", "gcal_search", "google_home_command", "google_home_ask", "get_weather"}


def _is_int_str(s):
    try:
        int(s)
        return True
    except (ValueError, TypeError):
        return False


def _is_float_str(s):
    try:
        float(s)
        return "." in str(s) or "e" in str(s).lower()
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

    def __init__(self, app, script_name="inline", auth_callback=None, line_callback=None):
        self.app = app
        self.script_name = script_name
        self.auth_callback = auth_callback
        self.line_callback = line_callback
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
            from PIL import Image, ImageEnhance, ImageFilter, ImageOps
            pil_img = Image.fromarray(frame[:, :, :3])
            pil_img = ImageOps.grayscale(pil_img)
            pil_img = ImageEnhance.Contrast(pil_img).enhance(2.0)
            pil_img = pil_img.filter(ImageFilter.SHARPEN)
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

        if name == "ifcontains":
            cond_raw = args[:2]
            cond = _eval_all(cond_raw)
            var_val = cond[0] if cond else ""
            search = cond[1] if len(cond) > 1 else ""
            if search in var_val and len(args) > 2:
                return self._evaluate(args[2])
            if search not in var_val and len(args) > 3:
                return self._evaluate(args[3])
            return ""

        if name == "ifempty":
            var_val = self._evaluate(args[0]) if args else ""
            if not var_val and len(args) > 1:
                return self._evaluate(args[1])
            if var_val and len(args) > 2:
                return self._evaluate(args[2])
            return ""

        if name in ("ifgreater", "ifless", "ifgreaterequal", "iflessequal"):
            a_str = self._evaluate(args[0]) if args else "0"
            b_str = self._evaluate(args[1]) if len(args) > 1 else "0"
            if _is_int_str(b_str) and _is_int_str(a_str):
                a, b = int(a_str), int(b_str)
            elif _is_float_str(b_str) and _is_float_str(a_str):
                a, b = float(a_str), float(b_str)
            else:
                a, b = a_str, b_str
            if name == "ifgreater":
                cond = a > b
            elif name == "ifless":
                cond = a < b
            elif name == "ifgreaterequal":
                cond = a >= b
            else:
                cond = a <= b
            if cond and len(args) > 2:
                return self._evaluate(args[2])
            if not cond and len(args) > 3:
                return self._evaluate(args[3])
            return ""

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
            use_memory = len(evaluated) > 1 and evaluated[1].strip().lower() in ("true", "1", "yes", "memory")

            system_content = ""
            if use_memory:
                now = time.strftime("%Y-%m-%d %H:%M:%S")
                base = self.app.system_message or ""
                from i18n import t as _ti18n
                date_prefix = _ti18n("ai.date_prefix", self.app.language)
                system_content = f"{base}\n\n{date_prefix}{now}".strip()

                memory_content = self.app._build_memory_content()
                from main import MCP_PROMPT, _load_vascript_reference
                vas_ref = _load_vascript_reference()
                tools_block = MCP_PROMPT + vas_ref if self.app.allow_ai_scripts else ""
                system_content = memory_content + system_content + tools_block

            messages = [{"role": "system", "content": system_content}] if system_content else []
            messages.append({"role": "user", "content": prompt})

            mcp, tools = init_mcp(self.app.mcp_server_url, timeout=120, log_prefix="[VASScript]")

            kwargs = dict(
                model=self.app.ai_model,
                messages=messages,
                temperature=0.7,
                extra_body={"disable_thinking": True},
            )
            if tools:
                kwargs["tools"] = tools

            msg = call_with_retry(lambda: self.app.openai_client.chat.completions.create(**kwargs), log_prefix="[VASScript]").choices[0].message
            msg = execute_mcp_tool_calls(messages, msg, mcp, tools, self.app.openai_client, self.app.ai_model, log_prefix="[VASScript]")

            return msg.content or ""

        if name == "say":
            text = evaluated[0] if evaluated else ""
            speed = float(_tof(evaluated[1])) if len(evaluated) > 1 else 1.0
            self._do_say(text, speed)
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
            try:
                import base64
                encoded = base64.b64encode(cmd.encode("utf-16-le")).decode("ascii")
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-EncodedCommand", encoded],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=30
                )
                output = (result.stdout or "").strip()
                if result.stderr:
                    stderr = result.stderr.strip()
                    if stderr:
                        output = (output + "\n" + stderr).strip()
                return output or f"exit code: {result.returncode}"
            except Exception as e:
                return f"error: {e}"

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
            import sys
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
            lang_codes = self._ocr_langs()
            if VASScript._ocr_reader is None or VASScript._ocr_active_langs != lang_codes:
                import easyocr
                VASScript._ocr_reader = easyocr.Reader(
                    lang_codes, gpu=True, verbose=False
                )
                VASScript._ocr_active_langs = lang_codes
            results = VASScript._ocr_reader.readtext(frame)
            import difflib as _difflib
            matches = []
            for bbox, text, conf in results:
                ratio = _difflib.SequenceMatcher(None, query.lower(), text.lower()).ratio()
                if ratio >= 0.80:
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

        if name == "sendtext":
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

        if name == "setactivewindow":
            name_arg = evaluated[0] if evaluated else ""
            if name_arg:
                from window_manager import set_active_window
                return "ok" if set_active_window(name_arg) else "not found"
            return "not found"

        if name == "addevent":
            d = evaluated[0] if evaluated else ""
            t = evaluated[1] if len(evaluated) > 1 else "00:00"
            dur = evaluated[2] if len(evaluated) > 2 else "60"
            desc = evaluated[3] if len(evaluated) > 3 else ""
            recur = evaluated[4] if len(evaluated) > 4 else ""
            return self._manage_events("add", d, t, dur, desc, recur)

        if name == "listevents":
            until = evaluated[0] if evaluated else ""
            return self._manage_events("list", until)

        if name == "removeevent" or name == "delevent":
            ename = evaluated[0] if evaluated else ""
            date = evaluated[1] if len(evaluated) > 1 else ""
            time_arg = evaluated[2] if len(evaluated) > 2 else ""
            return self._manage_events("remove", ename, date, time_arg)

        if name == "readinfo":
            vid = evaluated[0] if evaluated else ""
            return self._manage_info("read", vid)

        if name == "writeinfo":
            text = evaluated[0] if evaluated else ""
            return self._manage_info("write", text)

        if name == "clipboardget":
            try:
                import pyperclip
                return pyperclip.paste()
            except Exception:
                return ""

        if name == "clipboardset":
            text = evaluated[0] if evaluated else ""
            try:
                import pyperclip
                pyperclip.copy(text)
                return "ok"
            except Exception:
                return "error"

        if name == "savetags":
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
            return self.app.notification_manager.add(text, priority)

        if name == "inject":
            text = evaluated[0] if evaluated else ""
            self.app.inject_context(text)
            return "ok"

        if name == "inject_memory":
            text = evaluated[0] if evaluated else ""
            return self.app.inject_memory(text)

        if name == "fetch_text":
            url = evaluated[0] if evaluated else ""
            return self._fetch_web(url, "webfetch")

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

        if name == "getdatetime":
            from datetime import datetime
            lang = (evaluated[0] if evaluated else "").strip().lower()
            now = datetime.now()
            if not lang:
                return now.strftime("%Y-%m-%d %H:%M")
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
                return f"{day} {mn} {year} {hm}"
            elif lang in ("en", "fr"):
                return f"{mn} {day}, {year} {hm}"
            elif lang == "de":
                return f"{day}. {mn} {year} {hm}"
            elif lang == "es":
                return f"{day} de {mn} de {year} {hm}"
            elif lang == "pt":
                return f"{day} de {mn} de {year} {hm}"
            elif lang == "ja":
                return f"{year}年{now.month}月{day}日 {hm}"
            elif lang == "ko":
                return f"{year}년 {now.month}월 {day}일 {hm}"
            elif lang == "zh":
                return f"{year}年{now.month}月{day}日 {hm}"
            return now.strftime("%Y-%m-%d %H:%M")

        if name == "prettyevents":
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

        if name == "print":
            text = evaluated[0] if evaluated else ""
            print(f"[VASScript] {text}", flush=True)
            return ""

        if name == "readfile":
            filepath = evaluated[0] if evaluated else ""
            if not filepath:
                return "error: path required"
            import os as _os
            base = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "Allowed_root")
            p = _os.path.normpath(_os.path.join(base, filepath))
            if not p.startswith(_os.path.normpath(base)):
                return "error: access denied"
            try:
                with open(p, encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                return f"error: {e}"

        raise ValueError(f"unknown function: {name}()")

    def _manage_memory_tags(self, tags):
        from pathlib import Path
        vass_root = Path(__file__).resolve().parent.parent
        allowed_root = vass_root / "Allowed_root"

        TAG_WEIGHTS = {
            "personal_data": 10, "health": 10, "finance": 10,
            "family": 10, "pets": 10,
            "contacts": 8,
            "preferences": 7, "personal_interests": 7, "purchases": 7,
            "orders": 6, "bills": 6, "invoices": 6, "work": 6, "education": 6,
            "favorite_music": 5, "food": 5, "home": 5, "personal_means_of_transport": 5,
            "deliveries": 4, "travel": 4, "tech": 4, "events": 4,
            "sales": 3, "generic": 1,
        }
        MIN_RELEVANCE = 10

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
        from utils import init_mcp

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
                    pass
            if normalized_date is None:
                return f"error: invalid date format '{start_date}'. Use YYYY-MM-DD."
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
                ratio = difflib.SequenceMatcher(None, event_name.lower(), e.get("description", "").lower()).ratio()
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
        from utils import init_mcp
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
                return "\n".join(parts)
            return str(result)
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
            elif result.get("audio") and play_audio:
                gh.play_audio_response(result["audio"], output_device)
            elif result.get("text") and play_audio:
                self.app.tts.enqueue(result["text"])
            gh.close()

        threading.Thread(target=_run_gh, daemon=True).start()
        return "ok"

    def _do_say(self, text, speed=1.0):
        self.app.tts.speak_nowait(text, speed)
        self.app.tts._tts_done.wait()

    def _do_weather(self, location=""):
        import urllib.request, urllib.parse, json
        try:
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
            result = {
                "city": city,
                "region": region,
                "country": country,
                "temperature": temp_c,
                "feels_like": feels_c,
                "humidity": humidity,
                "description": desc,
                "wind_speed": wind_speed,
                "wind_direction": wind_dir,
                "observation_time": obs_time,
                "temperature_unit_system": "Celsius",
            }
            result_json = json.dumps(result, ensure_ascii=False)
            self.vars["temperature"] = str(temp_c)
            self.vars["feels_like"] = str(feels_c)
            self.vars["temperature_unit_system"] = "Celsius"
            self.vars["humidity"] = str(humidity)
            self.vars["weather_description"] = desc
            self.vars["wind_speed"] = str(wind_speed)
            self.vars["wind_direction"] = wind_dir
            self.vars["weather_city"] = city
            return result_json
        except Exception as e:
            return f'{{"error": "{str(e)}"}}'

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
        else:
            expr, consumed = self._parse_expr(tokens, 0)
            if consumed < len(tokens):
                raise ValueError(f"unexpected token after expression: '{tokens[consumed]}'")
            if expr:
                self._evaluate(expr)
