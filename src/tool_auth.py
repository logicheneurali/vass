"""Security layer for AI-driven online tool operations.

Three mechanisms:
  - audit(): append-only log with rotation cap (1 MB, keeps last half)
  - check_rate()/mark_call(): rate limit (max N online calls per minute,
    minimum interval between calls) — sliding window in memory
  - tool_authorized()/grant_tool(): persistent per-tool permissions in the
    system keyring (service "vass-auth", accounts "tool:<name>" / "tool:__all__"),
    separate from script permissions.

Used by execute_mcp_tool_calls (utils.py) as a gate before calling any
online MCP tool on behalf of the AI.
"""
import os
import threading
import time
from collections import deque

_AUDIT_MAX = 1_000_000
_AUDIT_PATH = None

_lock = threading.Lock()
_window = deque()

_RATE_PER_MIN = 10
_MIN_INTERVAL = 1.0

SENSITIVE_TOOLS = {
    "browser_click", "browser_fill", "browser_submit", "browser_download",
    "send_email", "reply_email", "forward_email",
}

ONLINE_TOOLS = {
    "websearch", "webfetch", "browse",
    "browser_open", "browser_read", "browser_click", "browser_fill",
    "browser_submit", "browser_download", "browser_back", "browser_show",
    "browser_check_auth",
}


def _audit_path():
    global _AUDIT_PATH
    if _AUDIT_PATH is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _AUDIT_PATH = os.path.join(root, "Allowed_root", "private_ai_audit.log")
    return _AUDIT_PATH


def configure(rate_per_min=10, min_interval=1.0):
    global _RATE_PER_MIN, _MIN_INTERVAL
    _RATE_PER_MIN = max(1, int(rate_per_min))
    _MIN_INTERVAL = max(0.0, float(min_interval))


def audit(tool, args_preview, outcome="ok"):
    """Append one audit line; keep the log under _AUDIT_MAX bytes."""
    try:
        path = _audit_path()
        line = (f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {tool} | "
                f"{(args_preview or '')[:200]} | {outcome}\n")
        with _lock:
            if os.path.isfile(path) and os.path.getsize(path) > _AUDIT_MAX:
                with open(path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                with open(path, "w", encoding="utf-8") as f:
                    f.writelines(lines[len(lines) // 2:])
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass


def check_rate():
    """Return (allowed, wait_seconds). If the per-minute budget is exhausted
    -> (False, 0). Otherwise, if the minimum interval is not met, the caller
    should wait wait_seconds before calling mark_call()."""
    now = time.time()
    with _lock:
        while _window and now - _window[0] > 60:
            _window.popleft()
        if len(_window) >= _RATE_PER_MIN:
            return False, 0.0
        if _window and now - _window[-1] < _MIN_INTERVAL:
            return True, _MIN_INTERVAL - (now - _window[-1])
        return True, 0.0


def mark_call():
    with _lock:
        _window.append(time.time())
        while _window and time.time() - _window[0] > 60:
            _window.popleft()


# ── Permissions (keyring, separated from script permissions) ─────

def _keyring():
    try:
        import keyring
        return keyring
    except Exception:
        return None


def tool_authorized(tool):
    """True if permanently granted (per-tool or __all__); None if no grant."""
    kr = _keyring()
    if kr is None:
        return None
    try:
        if kr.get_password("vass-auth", f"tool:{tool}") == "1":
            return True
        if kr.get_password("vass-auth", "tool:__all__") == "1":
            return True
    except Exception:
        pass
    return None


def grant_tool(tool, allow_all=False):
    kr = _keyring()
    if kr is None:
        return
    try:
        if allow_all:
            kr.set_password("vass-auth", "tool:__all__", "1")
        else:
            kr.set_password("vass-auth", f"tool:{tool}", "1")
    except Exception:
        pass


def list_tool_permissions():
    """Return [(tool_name, scope)] for every granted tool permission.
    scope is 'all' (tool:__all__) or 'tool' (single tool). Localization
    of the scope label happens in the UI layer.
    Mirrors the script permission listing (keyring has no enumeration API)."""
    names = sorted(ONLINE_TOOLS | SENSITIVE_TOOLS)
    kr = _keyring()
    if kr is None:
        return []
    entries = []
    try:
        if kr.get_password("vass-auth", "tool:__all__") == "1":
            entries.append(("__all__", "all"))
    except Exception:
        pass
    for name in names:
        try:
            if kr.get_password("vass-auth", f"tool:{name}") == "1":
                entries.append((name, "tool"))
        except Exception:
            pass
    return entries


def revoke_tool(tool):
    kr = _keyring()
    if kr is None:
        return
    try:
        kr.delete_password("vass-auth", f"tool:{tool}")
    except Exception:
        pass
