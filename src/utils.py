import json
import os
import re
import subprocess
import sys
import time
from openai import APIConnectionError
from urllib.parse import urlparse

SCRIPT_PREFIXES = ("vasscript:", "script:")


# ── System / process utilities ───────────────────────────────────────────────

def is_process_running(name):
    try:
        if sys.platform == "win32":
            r = subprocess.run(["tasklist"], capture_output=True, text=True)
            return name.lower() in r.stdout.lower()
        else:
            r = subprocess.run(["pgrep", "-f", name], capture_output=True)
            return r.returncode == 0
    except Exception:
        return False


def kill_port(port):
    try:
        if sys.platform == "win32":
            r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
            for line in r.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    pid = line.strip().split()[-1]
                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
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
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=5)
        else:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
    except Exception:
        pass


# ── Audio utility ────────────────────────────────────────────────────────────

def beep(volume=0.6):
    import os
    import soundfile as sf
    import sounddevice as sd
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sounds", "beep.wav")
    try:
        data, sr = sf.read(path)
        sd.play(data * volume, sr)
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


def execute_mcp_tool_calls(messages, msg, mcp, tools, openai_client, model, temperature=0.7, log_prefix="[AI]"):
    if not (msg.tool_calls and mcp and tools):
        return msg

    for tc in msg.tool_calls:
        tool_name = tc.function.name
        tool_args = tc.function.arguments
        print(f"[MCP] Call: {tool_name}({tool_args})")
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
            if isinstance(result, dict) and "content" in result:
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
        temperature=temperature,
        extra_body={"disable_thinking": True}
    ), log_prefix=log_prefix)
    return resp.choices[0].message


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
