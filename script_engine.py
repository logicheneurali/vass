import json
import math
import re
import subprocess
import threading
import time

from utils import call_with_retry, execute_mcp_tool_calls, init_mcp


_SIDE_EFFECT_FUNCTIONS = {"ai", "say", "run", "screen_search", "screen_click", "screen_highlight", "listen", "sendtext", "setactivewindow", "addevent", "listevents", "removeevent", "readinfo", "writeinfo", "clipboardget", "clipboardset"}


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
            from PIL import Image, ImageEnhance
            pil_img = Image.fromarray(frame[:, :, :3])
            enhancer = ImageEnhance.Contrast(pil_img)
            pil_img = enhancer.enhance(1.5)
            return np.array(pil_img)
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
            self._execute_line(line)

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
            return ("var", token[1:]), pos + 1

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
            return self.vars.get(name, m.group(0))
        return re.sub(r"\{(\$?\w+)\}", _repl, text)

    def _evaluate(self, node):
        if node is None:
            return ""
        typ = node[0]
        if typ == "str":
            return self._sub_vars(node[1])
        if typ == "num":
            return str(node[1])
        if typ == "var":
            return self.vars.get(node[1], "")
        if typ == "ident":
            return self.vars.get(node[1], node[1])
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
            messages = [{"role": "user", "content": prompt}]

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
            t = threading.Thread(target=self._do_say, args=(text, speed), daemon=True)
            t.start()
            t.join()
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

        if name == "removeevent":
            ename = evaluated[0] if evaluated else ""
            return self._manage_events("remove", ename)

        if name == "readinfo":
            vid = evaluated[0] if evaluated else ""
            return self._manage_info("read", vid)

        if name == "writeinfo":
            text = evaluated[0] if evaluated else ""
            return self._manage_info("write", text)

        if name == "clipboardget":
            import subprocess as _sp, sys as _sys
            try:
                if _sys.platform == "win32":
                    r = _sp.run(
                        ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                        capture_output=True, text=True,
                        creationflags=_sp.CREATE_NO_WINDOW, timeout=10
                    )
                    return r.stdout.strip()
                elif _sys.platform == "darwin":
                    r = _sp.run(["pbpaste"], capture_output=True, text=True, timeout=10)
                    return r.stdout.strip()
                else:
                    r = _sp.run(["xclip", "-o", "-selection", "clipboard"], capture_output=True, text=True, timeout=10)
                    return r.stdout.strip()
            except Exception:
                return ""

        if name == "clipboardset":
            text = evaluated[0] if evaluated else ""
            import subprocess as _sp, sys as _sys
            if _sys.platform == "win32":
                import base64 as _b64
                encoded = _b64.b64encode(text.encode("utf-16-le")).decode("ascii")
                _sp.run(
                    ["powershell", "-NoProfile", "-EncodedCommand",
                     f"Set-Clipboard -Value ([System.Text.Encoding]::Unicode.GetString([System.Convert]::FromBase64String('{encoded}')))"],
                    capture_output=True, text=True,
                    creationflags=_sp.CREATE_NO_WINDOW, timeout=10
                )
            elif _sys.platform == "darwin":
                _sp.run(["pbcopy"], input=text, text=True, timeout=10)
            else:
                _sp.run(["xclip", "-selection", "clipboard"], input=text, text=True, timeout=10)
            return "ok"

        if name == "getdatetime":
            from datetime import datetime
            return datetime.now().strftime("%Y-%m-%d %H:%M")

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

        raise ValueError(f"unknown function: {name}()")

    def _manage_info(self, action, arg):
        from pathlib import Path
        vass_root = Path(__file__).resolve().parent
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
            event_name = args[0] if args else ""
            if not events:
                return "not found: no events"
            best_idx = 0
            best_ratio = 0
            for i, e in enumerate(events):
                ratio = difflib.SequenceMatcher(None, event_name.lower(), e["name"].lower()).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_idx = i
            if best_ratio >= 0.8:
                removed = events.pop(best_idx)
                data["events"] = events
                try:
                    result = mcp.call_tool("write_file", {"path": "events.json", "content": json.dumps(data, ensure_ascii=False, indent=2)})
                    if result.get("isError"):
                        return f"error: failed to save removal: {result.get('content', [{}])[0].get('text', 'unknown error')}"
                except Exception as e:
                    return f"error: failed to save removal: {e}"
                return f"ok: removed '{removed['name']}'"
            nearest = events[best_idx]["name"] if events else "none"
            return f"not found: best match '{nearest}' ratio {best_ratio:.2f}"

        return "error: unknown action"

    def _do_say(self, text, speed=1.0):
        self.app.tts.speak(text, speed)
        self.app.tts._tts_done.wait()

    def _execute_line(self, line):
        tokens = self._tokenize(line)
        if not tokens:
            return

        if tokens[0].startswith("$") and len(tokens) > 1 and tokens[1] == "=":
            var_name = tokens[0][1:]
            expr, _ = self._parse_expr(tokens, 2)
            value = self._evaluate(expr)
            self.vars[var_name] = value
        else:
            expr, _ = self._parse_expr(tokens, 0)
            if expr:
                self._evaluate(expr)
