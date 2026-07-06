import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from difflib import SequenceMatcher
from openai import APIConnectionError
from urllib.parse import urlparse

SCRIPT_PREFIXES = ("vasscript:", "script:")


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
    import pyautogui
    try:
        pyautogui.write(text, interval=0.01)
    except Exception as e:
        print(f"[Paste] Error: {e}")


# ── String / text utilities ──────────────────────────────────────────────────

def parse_blacklist(raw):
    return set(w.strip().lower() for w in raw.split(",") if w.strip())


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
    proc = subprocess.Popen(cmd, cwd=cwd, creationflags=creationflags,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
    for attempt in range(retries):
        try:
            return fn()
        except APIConnectionError:
            if attempt == retries - 1:
                raise
            delay = delays[attempt]
            print(f"{log_prefix} Connessione fallita, riprovo tra {delay}s ({attempt+2}/{retries})")
            time.sleep(delay)


def execute_mcp_tool_calls(messages, msg, mcp, tools, openai_client, model, temperature=0.7, log_prefix="[AI]", gui=None):
    if not (msg.tool_calls and mcp and tools):
        return msg

    MAX_TURNS = 10
    for _ in range(MAX_TURNS):
        for tc in msg.tool_calls:
            tool_name = tc.function.name
            tool_args = tc.function.arguments
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
            try:
                args = json.loads(tc.function.arguments)
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
            except Exception as e:
                out = f"Errore: {e}"
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": out
            })

        resp = call_with_retry(lambda: openai_client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            temperature=temperature,
            extra_body={"disable_thinking": False}
        ), log_prefix=log_prefix)
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


def list_audio_devices():
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
        print(f"Input device (settings: {inp}):")
        _print_dev("Input", inp if inp >= 0 else sd.default.device[0])
        print(f"Output device (settings: {out}):")
        _print_dev("Output", out if out >= 0 else sd.default.device[1])
    except Exception:
        pass
