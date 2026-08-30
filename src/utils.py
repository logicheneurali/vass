import json
import os
import re
import subprocess
import sys
import time
import traceback
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import urlparse

SCRIPT_PREFIXES = ("vasscript:", "script:")

# ── Project path utilities ────────────────────────────────────────────────────

_PROJECT_ROOT = None


def get_project_root():
    """Return the VASS project root directory (cached)."""
    global _PROJECT_ROOT
    if _PROJECT_ROOT is None:
        _PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return _PROJECT_ROOT


def get_path(*parts):
    """Return path relative to project root. E.g. get_path('config', 'settings.ini')."""
    return os.path.join(get_project_root(), *parts)


# ── Generated-file extraction ─────────────────────────────────────────────────

_PATH_IN_TEXT_RE = re.compile(
    r'(?<![\w./\\])(?:[A-Za-z]:[\\/]|/)[^\s"\']+', re.IGNORECASE)


def _collect_file_paths(out, allowed_root, seen):
    """Extract generated file paths from a tool result string.

    Handles both JSON results (dict with a 'path' key, e.g. generate_svg,
    html_to_pdf, browser_download) and plain text ('Written N bytes to <path>'
    from write_file). Returns the list of newly found absolute paths that
    exist on disk and live under allowed_root. Results already present in
    `seen` are skipped.
    """
    found = []
    candidates = []
    if isinstance(out, str) and out.strip():
        try:
            data = json.loads(out)
            if isinstance(data, dict):
                p = data.get("path")
                if isinstance(p, str) and p.strip():
                    candidates.append(p)
        except (ValueError, TypeError):
            pass
        if not candidates:
            candidates = _PATH_IN_TEXT_RE.findall(out)
    root = os.path.abspath(allowed_root) if allowed_root else ""
    for p in candidates:
        p = p.strip().strip("\"'.,;")
        if not p:
            continue
        ap = os.path.abspath(os.path.normpath(p))
        try:
            os.path.relpath(ap, root)
        except ValueError:
            continue
        if not (ap == root or ap.startswith(root + os.sep)):
            continue
        if not os.path.isfile(ap):
            continue
        if ap in seen:
            continue
        seen.add(ap)
        found.append(ap)
    return found


# ── OS autostart (source of truth: OS registry / autostart files) ──────────────

def _autostart_command():
    vass_py = os.path.join(get_project_root(), "vass.py")
    if sys.platform == "win32":
        pw = sys.executable.replace("python.exe", "pythonw.exe")
        exe = pw if os.path.exists(pw) else sys.executable
        return f'"{exe}" "{vass_py}"'
    return f"{sys.executable} {vass_py}"


def _autostart_paths():
    if sys.platform == "win32":
        return ("winreg",)
    if sys.platform == "darwin":
        return ("plist", os.path.expanduser("~/Library/LaunchAgents/com.vass.assistant.plist"))
    return ("desktop", os.path.expanduser("~/.config/autostart/vass.desktop"))


def is_autostart_enabled():
    """Read the REAL autostart state from the OS (source of truth)."""
    kind, *rest = _autostart_paths()
    try:
        if kind == "winreg":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run")
            try:
                winreg.QueryValueEx(key, "VASS")
                return True
            except FileNotFoundError:
                return False
            finally:
                winreg.CloseKey(key)
        return os.path.exists(rest[0])
    except Exception:
        return False


def apply_autostart(enabled):
    """Register/unregister VASS at OS startup (Windows registry / macOS LaunchAgent / Linux autostart)."""
    kind, *rest = _autostart_paths()
    try:
        if kind == "winreg":
            import winreg
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                   r"Software\Microsoft\Windows\CurrentVersion\Run")
            try:
                if enabled:
                    winreg.SetValueEx(key, "VASS", 0, winreg.REG_SZ, _autostart_command())
                else:
                    try:
                        winreg.DeleteValue(key, "VASS")
                    except FileNotFoundError:
                        pass
            finally:
                winreg.CloseKey(key)
        elif kind == "plist":
            path = rest[0]
            if enabled:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.vass.assistant</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>{os.path.join(get_project_root(), "vass.py")}</string>
    </array>
    <key>RunAtLoad</key><true/>
</dict>
</plist>
""")
            else:
                try:
                    os.remove(path)
                except FileNotFoundError:
                    pass
        else:
            path = rest[0]
            if enabled:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(f"""[Desktop Entry]
Type=Application
Name=VASS
Exec={_autostart_command()}
X-GNOME-Autostart-enabled=true
""")
            else:
                try:
                    os.remove(path)
                except FileNotFoundError:
                    pass
        print(f"[Autostart] {'Enabled' if enabled else 'Disabled'} ({kind})")
    except Exception as e:
        print(f"[Autostart] Failed: {e}")


def log_exc(msg=""):
    """Log exception with timestamp and traceback to log/crash.log."""
    try:
        ts = time.strftime("[%Y-%m-%d %H:%M:%S]")
        os.makedirs(os.path.join(get_project_root(), "log"), exist_ok=True)
        path = os.path.join(get_project_root(), "log", "crash.log")
        with open(path, "a", encoding="utf-8") as f:
            if msg:
                f.write(f"\n{ts} {msg}\n")
            traceback.print_exc(file=f)
    except Exception:
        pass  # can't log if logging fails

# ── System / process utilities ───────────────────────────────────────────────

def is_process_running(name):
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


def kill_port(port):
    try:
        if sys.platform == "win32":
            r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            for line in r.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    pid = line.strip().split()[-1]
                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        elif sys.platform == "darwin":
            r = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True)
            for pid in r.stdout.strip().split():
                subprocess.run(["kill", "-9", pid])
        else:
            subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True)
    except Exception:
        pass


def kill_process(proc):
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
            proc.wait(timeout=2)
        except Exception:
            pass
    except Exception:
        pass


# ── Audio utility ────────────────────────────────────────────────────────────

def beep(volume=0.6, output_device=-1):
    import os
    import soundfile as sf
    import sounddevice as sd
    device = None if output_device < 0 else output_device
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sounds", "beep.wav")
    try:
        data, sr = sf.read(path)
        sd.play(data * volume, sr, device=device)
        sd.wait()
    except Exception as e:
        print(f"[Beep] Error: {e}")


# ── Clipboard utility ────────────────────────────────────────────────────────

def paste_text(text):
    import pyperclip
    try:
        pyperclip.copy(text)
    except Exception as e:
        print(f"[Paste] Clipboard copy failed: {e}")
        return
    try:
        from pynput.keyboard import Controller, Key
        kb = Controller()
        with kb.pressed(Key.ctrl):
            kb.press('v')
            kb.release('v')
    except Exception as e:
        # No display / Wayland / headless — text stays in clipboard
        print(f"[Paste] Hotkey failed (text in clipboard): {e}")


# ── String / text utilities ──────────────────────────────────────────────────

def parse_blacklist(raw):
    """Parse blacklist. Quoted items are literal phrases, unquoted are single words.
    Returns (words, phrases) where both are sets of lowercased strings.
    """
    words = set()
    phrases = set()
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if item.startswith('"') and item.endswith('"'):
            phrases.add(item[1:-1].lower())
        else:
            words.add(item.lower())
    return words, phrases


def generate_recurrences(date_str, time_str, recur, until_date_str, max_iter=366):
    """Generate future recurrence dates for a recurring event.
    Returns list of (date_str, time_str) tuples from the base date up to until_date.
    """
    import datetime
    results = []
    if not recur:
        return results
    m = re.match(r"^(\d+)([mhdwM])$", recur)
    if not m:
        return results
    num, unit = int(m.group(1)), m.group(2)
    try:
        dt = datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except ValueError:
        return results
    until = datetime.datetime.strptime(f"{until_date_str} 23:59", "%Y-%m-%d %H:%M")
    for _ in range(max_iter):
        if unit == "m":
            dt += datetime.timedelta(minutes=num)
        elif unit == "h":
            dt += datetime.timedelta(hours=num)
        elif unit == "d":
            dt += datetime.timedelta(days=num)
        elif unit == "w":
            dt += datetime.timedelta(weeks=num)
        elif unit == "M":
            month = dt.month + num - 1
            year = dt.year + month // 12
            month = month % 12 + 1
            day = min(dt.day, 28)
            dt = dt.replace(year=year, month=month, day=day)
        else:
            break
        if dt > until:
            break
        results.append((dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")))
    return results


def is_local_url(url):
    host = (urlparse(url).hostname or "").lower()
    return host in ("127.0.0.1", "localhost", "::1") or host.startswith("127.")


def strip_markdown(text):
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'`.*?`', '', text)
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)
    text = re.sub(r'_(.*?)_', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'^[\s]*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[\s]*\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    return text.strip()


# ── Script prefix utilities ──────────────────────────────────────────────────

def is_script_command(cmd):
    return any(cmd.startswith(p) for p in SCRIPT_PREFIXES)


def strip_script_prefix(cmd):
    for p in SCRIPT_PREFIXES:
        if cmd.startswith(p):
            return cmd[len(p):].strip()
    return cmd


def strip_think_tags(text):
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()


# ── Process launcher ─────────────────────────────────────────────────────────

def start_llama_server(path, working_directory="", arguments="", skip_if_running=True):
    if not path.strip():
        return None, "path not configured"
    exe = os.path.join(path.strip(), "llama-server.exe" if sys.platform == "win32" else "llama-server")
    if not os.path.isfile(exe):
        return None, f"llama-server not found in {path}"
    if skip_if_running and is_process_running("llama-server"):
        return None, "already running"
    cwd = working_directory.strip() or path.strip()
    args = arguments.strip()
    cmd = [exe] + (args.split() if args else [])
    print(f"[llama.cpp] Starting: {' '.join(cmd)} (cwd={cwd})")
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    log_dir = os.path.join(get_project_root(), "log")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "llamacpp.log")
    log_file = open(log_path, "w", encoding="utf-8")
    log_file.write(f"--- llama.cpp started at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    log_file.write(f"Command: {' '.join(cmd)}\nWorking dir: {cwd}\n\n")
    log_file.flush()
    proc = subprocess.Popen(cmd, cwd=cwd, creationflags=creationflags,
                            stdout=log_file, stderr=subprocess.STDOUT)
    return proc, "started"


# ── File / memory utilities ──────────────────────────────────────────────────

def cleanup_orphan_files(mem_dir, history_ids, summary_id):
    import shutil
    try:
        referenced = set(history_ids[-20:])
        if summary_id:
            referenced.add(summary_id)

        tags_path = os.path.join(os.path.dirname(mem_dir), "memory_tags.json")
        if os.path.exists(tags_path):
            try:
                with open(tags_path, encoding="utf-8") as f:
                    tags_data = json.load(f)
                for entry in tags_data.get("entries", []):
                    referenced.add(entry["id"])
            except Exception:
                pass

        archive_date = time.strftime("%Y-%m", time.localtime())
        archive_dir = os.path.join(mem_dir, "archive", archive_date)
        moved = 0
        for fname in os.listdir(mem_dir):
            if fname.endswith(".json"):
                fid = fname[:-5]
                if fid not in referenced:
                    try:
                        os.makedirs(archive_dir, exist_ok=True)
                        shutil.move(os.path.join(mem_dir, fname), os.path.join(archive_dir, fname))
                        moved += 1
                    except OSError:
                        pass
        if moved > 0:
            print(f"[Memory] Cleaned {moved} orphan files to archive/{archive_date}")
    except Exception:
        pass


# ── AI utilities ─────────────────────────────────────────────────────────────

def call_with_retry(fn, retries=4, delays=(1, 2, 4, 8), log_prefix="[AI]"):
    from openai import APIConnectionError
    for attempt in range(retries):
        try:
            return fn()
        except APIConnectionError:
            if attempt == retries - 1:
                raise
            delay = delays[attempt]
            print(f"{log_prefix} Connessione fallita, riprovo tra {delay}s ({attempt+2}/{retries})")
            time.sleep(delay)


class UsageCollector:
    """Accumulate prompt/completion token usage across multiple AI calls."""

    def __init__(self):
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.calls = 0

    def add(self, usage):
        if not usage:
            return
        try:
            self.prompt_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
            self.completion_tokens += int(getattr(usage, "completion_tokens", 0) or 0)
            self.calls += 1
        except Exception:
            pass

    def total(self):
        return self.prompt_tokens + self.completion_tokens


def execute_mcp_tool_calls(messages, msg, mcp, tools, openai_client, model, temperature=None, log_prefix="[AI]", gui=None, context_limit=0, file_links=None, usage=None):
    if not (msg.tool_calls and mcp and tools):
        return msg

    def _gate_online_tool(tool_name, tool_args, gui):
        """Security gate for AI online operations: audit + rate limit + consent.
        Returns None to proceed, or a message string for the AI if blocked."""
        from tool_auth import (SENSITIVE_TOOLS, ONLINE_TOOLS, audit, check_rate,
                               mark_call, tool_authorized, grant_tool)
        if tool_name not in ONLINE_TOOLS and tool_name not in SENSITIVE_TOOLS:
            return None
        allowed, wait = check_rate()
        if not allowed:
            audit(tool_name, tool_args, "rate_blocked")
            return ("Error: online operation limit exceeded (max per minute). "
                    "Wait a moment and retry.")
        if wait > 0:
            time.sleep(wait)
        mark_call()
        if tool_name in SENSITIVE_TOOLS and not tool_authorized(tool_name):
            result = "deny"
            if gui is not None and hasattr(gui, "request_auth"):
                result = gui.request_auth(tool_name, "MCP tool online", timeout=10)
            if result == "function":
                grant_tool(tool_name)
            elif result == "all":
                grant_tool(tool_name, allow_all=True)
            if result not in ("function", "all", "once"):
                audit(tool_name, tool_args, "denied")
                return ("Error: action blocked, authorization not granted "
                        "for the requested online operation.")
        return None

    def _trim_for_context():
        """Estimate prompt tokens (chars/3, conservative for non-OpenAI tokenizers)
        and truncate oversized tool results so the request fits context_limit.

        Trims to an absolute budget shared across tool messages, not a fixed
        1/3 of each message, so even a single huge result (e.g. a 90-day news
        range) is cut down to fit the model's real context window."""
        if context_limit <= 0:
            return
        budget = int(context_limit * 0.85)
        total = sum((len(m.get("content") or "") if isinstance(m.get("content"), str) else 0) // 3
                    for m in messages)
        if total + 1024 <= budget:
            return
        tool_msgs = [m for m in messages
                     if m.get("role") == "tool" and isinstance(m.get("content"), str)
                     and len(m["content"]) > 600]
        if not tool_msgs:
            return
        # Per-message budget: split the context budget across the tool messages.
        per_msg = max(1200, budget // max(1, len(tool_msgs)))
        tool_msgs.sort(key=lambda m: len(m["content"]), reverse=True)
        for m in tool_msgs:
            c = m["content"]
            if len(c) <= per_msg:
                continue
            keep = max(400, per_msg // 2)
            m["content"] = c[:keep] + "\n...[risultato troncato per contesto]...\n" + c[-keep // 2:]
            total -= max(0, (len(c) - len(m["content"])) // 3)
            if total + 1024 <= budget:
                break
        if total + 1024 > budget:
            print(f"[AI] Context guard: still {total} est tokens after truncation "
                  f"(budget {budget})")

    MAX_TURNS = 15
    _seen_paths = set()
    _allowed_root = os.path.join(get_project_root(), "Allowed_root")
    _last_call = None                  # (tool_name, tool_args) of previous turn
    for _ in range(MAX_TURNS):
        called_this_turn = set()
        if not msg.tool_calls:
            break
        # Loop guard: if the model repeats the exact same single tool call that
        # just produced a result, stop instead of spinning (e.g. webfetch the
        # same URL forever after a failed extraction). _last_call tracks the
        # call actually executed last turn, never the one pending now.
        if len(msg.tool_calls) == 1:
            tc0 = msg.tool_calls[0]
            if (tc0.function.name, tc0.function.arguments) == _last_call:
                print(f"[AI] Loop guard: repeated tool call "
                      f"{tc0.function.name}() with identical args — stopping")
                break
        _last_call = None
        if len(msg.tool_calls) == 1:
            _last_call = (msg.tool_calls[0].function.name,
                          msg.tool_calls[0].function.arguments)
        for tc in msg.tool_calls:
            tool_name = tc.function.name
            tool_args = tc.function.arguments
            called_this_turn.add(tool_name)
            print(f"[MCP] Call: {tool_name}({tool_args})")
            if gui:
                gui.show_tool_indicator(tool_name)
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                }]
            })

            out = _gate_online_tool(tool_name, tool_args, gui)
            if out is None:
                try:
                    args = json.loads(tc.function.arguments)
                    # Bound tools to a fraction of the model context so huge
                    # results (e.g. a 90-day news range) never overflow the
                    # window. Dynamic: only tools that declare max_chars in
                    # their schema receive it — no hardcoded tool list.
                    tool_def = next((t for t in tools
                                     if t.get("function", {}).get("name") == tool_name),
                                    None)
                    if tool_def is not None:
                        schema = (tool_def.get("function", {}).get("parameters") or {})
                        props = schema.get("properties", {}) if isinstance(schema, dict) else {}
                        if "max_chars" in props:
                            args.setdefault(
                                "max_chars",
                                max(8000, int((context_limit or 4096) * 2)))
                    result = mcp.call_tool(tc.function.name, args)
                    print(f"[MCP] Result: {tool_name} -> {str(result)[:200]}")
                    if isinstance(result, dict) and isinstance(result.get("content"), list):
                        parts = []
                        for item in result["content"]:
                            if isinstance(item, dict) and item.get("type") == "text":
                                parts.append(item.get("text", ""))
                        out = "\n".join(parts)
                    else:
                        out = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
                    from tool_auth import audit
                    audit(tool_name, tool_args, "ok")
                except Exception as e:
                    out = f"Error: {e}"
                    try:
                        from tool_auth import audit
                        audit(tool_name, tool_args, f"error: {e}")
                    except Exception:
                        pass
            # Trim BEFORE appending so a single oversized tool result never
            # enters the conversation at full size.
            if context_limit > 0 and isinstance(out, str) and len(out) > 20000:
                per_msg = max(1200, int(context_limit * 0.85) // 4)
                if len(out) > per_msg:
                    keep = max(400, per_msg // 2)
                    out = out[:keep] + "\n...[risultato troncato per contesto]...\n" + out[-keep // 2:]
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": out
            })
            if file_links is not None:
                file_links.extend(_collect_file_paths(out, _allowed_root, _seen_paths))

        if "websearch" in called_this_turn and "search_news" not in called_this_turn:
            for tc in msg.tool_calls:
                if tc.function.name == "websearch":
                    try:
                        args = json.loads(tc.function.arguments)
                        news_result = mcp.call_tool("search_news", args)
                        parsed = json.loads(news_result) if isinstance(news_result, str) else news_result
                        if isinstance(parsed, dict) and "results" in parsed:
                            parsed["results"] = parsed["results"][:50]
                        news_content = json.dumps(parsed, ensure_ascii=False)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": f"{tc.id}_news",
                            "content": f"[Archivio notizie locale]\n{news_content}"
                        })
                        print(f"[MCP] Auto news search: {len(parsed.get('results', []))} results")
                    except Exception:
                        pass
                    break

        _trim_for_context()
        _sampling = None
        if temperature is None:
            try:
                import model_params
                _sampling = model_params.sampling_kwargs("tool")
                temperature = _sampling["temperature"]
            except Exception:
                temperature = 0.7
        resp = call_with_retry(lambda: openai_client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            temperature=temperature,
            **({k: _sampling[k] for k in ("top_p", "presence_penalty", "frequency_penalty")}
               if _sampling else {}),
            extra_body={**({"disable_thinking": False}),
                        **(_sampling.get("_extra") if _sampling else {})}
        ), log_prefix=log_prefix)
        if usage is not None:
            usage.add(getattr(resp, "usage", None))
        msg = resp.choices[0].message
        if not msg.tool_calls:
            break

    return msg


def init_mcp(mcp_server_url, timeout=120, log_prefix="[AI]"):
    if not mcp_server_url:
        return None, None
    from mcp_client import McpClient
    try:
        mcp = McpClient(mcp_server_url, timeout=timeout)
        mcp.initialize()
        tools = mcp.get_tools()
        print(f"{log_prefix} MCP initialized: {len(tools)} tools")
        return mcp, tools
    except Exception as e:
        print(f"{log_prefix} MCP init failed: {e}")
        return None, None


_HTML_ENTITIES = re.compile(r'&(?:amp|#38|lt|#60|gt|#62|quot|#34|apos|#39|nbsp|#160);')
_HTML_TAG_RE = re.compile(r'<[^>]+>')
_URL_RE = re.compile(r'https?://[^\s<>\[\]]+')
_REPLY_RE = re.compile(r'^>\s?.*$', re.MULTILINE)
_SIGNATURE_RE = re.compile(r'-- \n.*', re.DOTALL)
_CONTROL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u034f\u200b-\u200f\u2028-\u202f\ufeff]')
_MARKDOWN_RE = re.compile(r'[*_#`]')
_MULTI_PUNCT = re.compile(r'([!?.])\1+')
_MULTI_SPACE = re.compile(r'\s+')


def clean_for_tts(text, max_len=300, truncated_suffix="..."):
    if not text:
        return ""
    entities = {"&amp;": "&", "&#38;": "&", "&lt;": "<", "&#60;": "<",
                "&gt;": ">", "&#62;": ">", "&quot;": "\"", "&#34;": "\"",
                "&apos;": "'", "&#39;": "'", "&nbsp;": " ", "&#160;": " "}
    for entity, replacement in entities.items():
        text = text.replace(entity, replacement)
    text = _HTML_TAG_RE.sub("", text)
    text = _URL_RE.sub("[link]", text)
    text = _REPLY_RE.sub("", text)
    text = _SIGNATURE_RE.sub("", text)
    text = _CONTROL_RE.sub("", text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Cf')
    text = _MARKDOWN_RE.sub("", text)
    text = _MULTI_PUNCT.sub(r'\1', text)
    text = _MULTI_SPACE.sub(" ", text).strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0] + truncated_suffix
    return text


# ── Crypto utilities ──────────────────────────────────────────────────────────

_fernet_cache = None


def _get_fernet():
    global _fernet_cache
    if _fernet_cache is not None:
        return _fernet_cache
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        print("[Crypto] cryptography library not available")
        return None
    key = _get_or_create_key()
    if key:
        _fernet_cache = Fernet(key)
    return _fernet_cache


def _get_or_create_key():
    try:
        import keyring
        key = keyring.get_password("vass", "fernet_key")
        if key:
            return key.encode()
        from cryptography.fernet import Fernet
        new_key = Fernet.generate_key()
        keyring.set_password("vass", "fernet_key", new_key.decode())
        return new_key
    except Exception:
        pass
    import platform, getpass, hashlib, base64
    machine_id = platform.node() + getpass.getuser()
    return base64.urlsafe_b64encode(hashlib.sha256(machine_id.encode()).digest())


def encrypt_fields(entry, keep_plain=None):
    if keep_plain is None:
        keep_plain = {"id"}
    f = _get_fernet()
    if f is None:
        return entry
    out = {}
    for k, v in entry.items():
        if k in keep_plain:
            out[k] = v
        elif isinstance(v, str) and v.startswith("gAAAAA"):
            out[k] = v
        else:
            out[k] = f.encrypt(str(v).encode()).decode()
    return out


def decrypt_fields(entry):
    f = _get_fernet()
    if f is None:
        return entry
    out = {}
    for k, v in entry.items():
        if isinstance(v, str) and v.startswith("gAAAAA"):
            try:
                out[k] = f.decrypt(v.encode()).decode()
            except Exception:
                out[k] = v
        else:
            out[k] = v
    return out


# ── Fuzzy matching utilities ──────────────────────────────────────────────────

def fuzzy_ratio(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def fuzzy_match_word(prompt, keywords, threshold=0.75, min_len=4):
    prompt_words = prompt.split()
    for kw in keywords:
        if len(kw) < min_len or ' ' in kw:
            continue
        for word in prompt_words:
            if len(word) < min_len:
                continue
            if SequenceMatcher(None, kw, word).ratio() >= threshold:
                return True
    return False


def list_audio_devices(resolved_inp=None, resolved_out=None):
    try:
        import sounddevice as sd
        import configparser
        cfg = configparser.ConfigParser()
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "settings.ini")
        cfg.read(path, encoding="utf-8")
        inp = cfg.getint("audio", "input_device", fallback=-1)
        out = cfg.getint("audio", "output_device", fallback=-1)
        hostapis = sd.query_hostapis()
        devs = sd.query_devices()
        def _print_dev(kind, idx):
            for d in devs:
                if d["index"] == idx:
                    ha = hostapis[d["hostapi"]]["name"][:18]
                    print(f"  [{d['index']:2d}] {d['name'][:49]:50s} api={ha:20s} ch={d['max_input_channels'] if kind=='Input' else d['max_output_channels']}")
                    return
            print(f"  [{idx:2d}] (non trovato)")
        actual_inp = resolved_inp if resolved_inp is not None else inp
        actual_out = resolved_out if resolved_out is not None else out
        label_in = f"Input device (settings: {inp}"
        label_in += f", resolved: {actual_inp}" if resolved_inp is not None else ""
        label_in += "):"
        print(label_in)
        _print_dev("Input", actual_inp if actual_inp >= 0 else sd.default.device[0])
        label_out = f"Output device (settings: {out}"
        label_out += f", resolved: {actual_out}" if resolved_out is not None else ""
        label_out += "):"
        print(label_out)
        _print_dev("Output", actual_out if actual_out >= 0 else sd.default.device[1])
    except Exception:
        pass
