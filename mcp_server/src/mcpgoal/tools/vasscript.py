import json
import os
import sys
import time
import uuid
from pathlib import Path
from . import to_num


_VASS_ROOT = None


def _get_vass_root():
    global _VASS_ROOT
    if _VASS_ROOT is None:
        _VASS_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
    return _VASS_ROOT


def _get_available_scripts():
    scripts_dir = _get_vass_root() / "scripts"
    return [f.stem for f in sorted(scripts_dir.glob("*.vass"))]


def _poll_result(queue_path, result_path, request_id, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(str(result_path)):
            try:
                with open(str(result_path), "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("id") == request_id:
                    try:
                        os.remove(str(result_path))
                    except OSError:
                        pass
                    return json.dumps(
                        data.get("result", {"status": "error", "detail": "no result"}),
                        ensure_ascii=False
                    )
            except (json.JSONDecodeError, OSError):
                pass
        time.sleep(0.3)

    try:
        if os.path.exists(str(queue_path)):
            os.remove(str(queue_path))
    except OSError:
        pass
    return json.dumps({
        "status": "timeout",
        "message": f"Timeout dopo {timeout}s."
    }, ensure_ascii=False)


def execute_vasscript_sync(script_name: str, timeout: float = 60) -> str:
    timeout = to_num(timeout, 60)
    vass_root = _get_vass_root()
    scripts_dir = vass_root / "scripts"
    queue_path = vass_root / "scripts" / "exec_queue.json"
    result_path = vass_root / "scripts" / "exec_result.json"

    if script_name == "?":
        return json.dumps({"available_scripts": _get_available_scripts()}, ensure_ascii=False)

    script_path = scripts_dir / f"{script_name}.vass"
    if not script_path.exists():
        available = _get_available_scripts()
        return json.dumps({
            "status": "not_found",
            "requested": script_name,
            "available_scripts": available,
            "message": "Script non trovato. Disponibili: " + ", ".join(available)
        }, ensure_ascii=False)

    request_id = uuid.uuid4().hex[:12]
    request = {"id": request_id, "script": script_name, "timeout": timeout}

    for rp in [queue_path, result_path]:
        if os.path.exists(str(rp)):
            try:
                os.remove(str(rp))
            except OSError:
                pass

    with open(str(queue_path), "w", encoding="utf-8") as f:
        json.dump(request, f)

    return _poll_result(queue_path, result_path, request_id, timeout)


def _validate_vasscript(code):
    errors = []
    for lineno, line in enumerate(code.split("\n"), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        cleaned = stripped
        in_quote = None
        i = 0
        while i < len(cleaned):
            ch = cleaned[i]
            if in_quote:
                if ch == in_quote:
                    cleaned = cleaned[:i] + cleaned[i+1:]  # remove closing quote
                    in_quote = None
                    continue  # don't advance i, char was removed
            elif ch in ('"', "'"):
                in_quote = ch
                cleaned = cleaned[:i] + cleaned[i+1:]  # remove opening quote
                continue  # don't advance i, char was removed
            i += 1
        cleaned = cleaned.replace("(", "").replace(")", "")
        # Now cleaned contains only unquoted parentheses
        opened = stripped.count("(") - cleaned.count("(")
        closed = stripped.count(")") - cleaned.count(")")
        if opened != closed:
            errors.append(f"line {lineno}: unbalanced parentheses — {opened} opening vs {closed} closing")
    if errors:
        return "SYNTAX ERROR:\n" + "\n".join(errors)
    return None


def exec_sync(code: str, timeout: float = 60) -> str:
    timeout = to_num(timeout, 60)
    
    syntax_err = _validate_vasscript(code)
    if syntax_err:
        return json.dumps({"status": "error", "detail": syntax_err, "message": syntax_err})
    
    vass_root = _get_vass_root()
    queue_path = vass_root / "scripts" / "exec_queue.json"
    result_path = vass_root / "scripts" / "exec_result.json"

    if code == "?":
        return json.dumps({"help": "Available functions: ai(prompt), say(text), run(cmd), screen_search(query), screen_click(x?,y?), screen_highlight(x,y,w?,h?,dur?), listen(prompt?), wait(sec), ifcontains(var,search,iftrue,iffalse?), ifempty(var,ifempty,ifnot?), trim(text), len(text), contains(text,substr), equals(a,b), exit(). Variables: $var = value or $var = fn(). Example: $r = ai(\"what is 2+2\")\nsay($r)"}, ensure_ascii=False)

    request_id = uuid.uuid4().hex[:12]
    request = {"id": request_id, "code": code, "timeout": timeout}

    for rp in [queue_path, result_path]:
        if os.path.exists(str(rp)):
            try:
                os.remove(str(rp))
            except OSError:
                pass

    with open(str(queue_path), "w", encoding="utf-8") as f:
        json.dump(request, f)

    return _poll_result(queue_path, result_path, request_id, timeout)


async def execute_vasscript(script_name: str, timeout: float = 60) -> str:
    return await _run_sync(execute_vasscript_sync, script_name, timeout)


def timer_start_sync(duration: str, timeout: float = 60) -> str:
    """Start a timer via VASScript timer_start()."""
    code = f'timer_start("{duration}")'
    return exec_sync(code, timeout)


def timer_list_sync(timeout: float = 60) -> str:
    """List active timers via VASScript timer_list()."""
    return exec_sync("timer_list()", timeout)


async def timer_start(duration: str, timeout: float = 60) -> str:
    return await _run_sync(timer_start_sync, duration, timeout)


async def timer_list(timeout: float = 60) -> str:
    return await _run_sync(timer_list_sync, timeout)


async def execute_code(code: str, timeout: float = 60) -> str:
    return await _run_sync(exec_sync, code, timeout)


def info_write_sync(text: str) -> str:
    vass_root = _get_vass_root()
    memory_dir = vass_root / "Allowed_root" / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    vid = str(int(time.time() * 1000))
    file_path = memory_dir / f"{vid}.json"
    with open(str(file_path), "w", encoding="utf-8") as f:
        json.dump({"info": text}, f, ensure_ascii=False, indent=2)
    return vid


def info_read_sync(vid: str) -> str:
    vass_root = _get_vass_root()
    import re
    safe_vid = re.sub(r'[^a-zA-Z0-9_-]', '_', vid)
    memory_dir = (vass_root / "Allowed_root" / "memory").resolve()
    file_path = (memory_dir / f"{safe_vid}.json").resolve()
    if not str(file_path).startswith(str(memory_dir) + os.sep) and file_path != memory_dir / f"{safe_vid}.json":
        return json.dumps({"error": "access denied", "id": vid}, ensure_ascii=False)
    if not file_path.exists():
        return json.dumps({"error": "not found", "id": vid}, ensure_ascii=False)
    with open(str(file_path), encoding="utf-8") as f:
        data = json.load(f)
    return data.get("info", "")


async def info_write(text: str) -> str:
    return await _run_sync(info_write_sync, text)


async def info_read(vid: str) -> str:
    return await _run_sync(info_read_sync, vid)


def clipboard_get_sync() -> str:
    import pyperclip
    try:
        return pyperclip.paste()
    except Exception:
        return ""


def clipboard_set_sync(text: str) -> str:
    import pyperclip
    try:
        pyperclip.copy(text)
        return "ok"
    except Exception:
        return "error"


async def clipboard_get() -> str:
    return await _run_sync(clipboard_get_sync)


async def clipboard_set(text: str) -> str:
    return await _run_sync(clipboard_set_sync, text)


async def _run_sync(fn, *args):
    import asyncio
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn, *args)
