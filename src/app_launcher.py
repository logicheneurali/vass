"""Cross-platform application launcher with fuzzy name matching.

Enumerates installed user apps and launches them by name:
- Windows: shortcuts (.lnk) from Start Menu Programs folders + UWP/AppX
- macOS:   bundles (.app) from /Applications and system locations
- Linux:   .desktop files from XDG application directories

Fuzzy matching (difflib SequenceMatcher, threshold 0.70) lets users
launch apps by approximate spoken names ("firefox", "calc", "notepad").
"""
import json
import os
import re
import shlex
import subprocess
import sys
import time
from difflib import SequenceMatcher

_APPS_CACHE = None
_APPS_CACHE_TS = 0.0
_CACHE_TTL = 300.0  # 5 minutes

_DENYLIST_ARGS = [
    "rm ", "del ", "format", "shutdown", "remove-item", "rm -rf",
]


def _fuzzy(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


# ── Enumeration ──────────────────────────────────────────────────

def _enumerate_windows():
    apps = []
    bases = [
        os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
        os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "Microsoft", "Windows", "Start Menu", "Programs"),
    ]
    seen = set()
    for base in bases:
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for f in files:
                if f.lower().endswith(".lnk"):
                    name = f[:-4]
                    full = os.path.join(root, f)
                    key = name.lower()
                    if key not in seen:
                        seen.add(key)
                        apps.append({"name": name, "path": full})
    # Supplement with UWP/AppX apps via Get-StartApps
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-StartApps | Select-Object @{N='n';E={$_.Name}},@{N='a';E={$_.AppID}} | ConvertTo-Json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW, timeout=10,
        )
        if result.stdout.strip():
            uwp = json.loads(result.stdout)
            if isinstance(uwp, dict):
                uwp = [uwp]
            for u in uwp:
                key = (u.get("n") or "").strip().lower()
                aid = (u.get("a") or "").strip()
                if key and aid and key not in seen:
                    seen.add(key)
                    apps.append({"name": u["n"], "path": f"shell:AppsFolder\\{aid}"})
    except Exception:
        pass
    return apps


def _enumerate_macos():
    apps = []
    bases = [
        "/Applications", "/System/Applications",
        "/Applications/Utilities", "/System/Applications/Utilities",
        os.path.expanduser("~/Applications"),
    ]
    seen = set()
    for base in bases:
        if not os.path.isdir(base):
            continue
        for f in os.listdir(base):
            if f.endswith(".app"):
                name = f[:-4]
                full = os.path.join(base, f)
                key = name.lower()
                if key not in seen:
                    seen.add(key)
                    apps.append({"name": name, "path": full})
    return apps


def _enumerate_linux():
    apps = []
    bases = [
        "/usr/share/applications",
        "/usr/local/share/applications",
        os.path.expanduser("~/.local/share/applications"),
        "/var/lib/snapd/desktop/applications",
        "/var/lib/flatpak/exports/share/applications",
        os.path.expanduser("~/.local/share/flatpak/exports/share/applications"),
    ]
    xdg = os.environ.get("XDG_DATA_DIRS", "")
    if xdg:
        for d in xdg.split(":"):
            p = os.path.join(d, "applications")
            if p not in bases:
                bases.append(p)
    seen = set()
    for base in bases:
        if not os.path.isdir(base):
            continue
        for f in os.listdir(base):
            if not f.endswith(".desktop"):
                continue
            full = os.path.join(base, f)
            name = None
            exec_cmd = None
            no_display = False
            app_type = None
            try:
                with open(full, encoding="utf-8") as fh:
                    for line in fh:
                        if line.startswith("Name="):
                            name = line[5:].strip()
                        elif line.startswith("Exec="):
                            exec_cmd = line[5:].strip()
                        elif line.startswith("NoDisplay="):
                            no_display = line[10:].strip().lower() == "true"
                        elif line.startswith("Type="):
                            app_type = line[5:].strip()
            except Exception:
                continue
            if no_display:
                continue
            if app_type and app_type != "Application":
                continue
            if not name:
                name = f[:-8]
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            apps.append({"name": name, "path": full, "exec": exec_cmd})
    return apps


def list_apps():
    """Return cached list of installed apps (refreshed every _CACHE_TTL seconds)."""
    global _APPS_CACHE, _APPS_CACHE_TS
    now = time.time()
    if _APPS_CACHE is not None and now - _APPS_CACHE_TS < _CACHE_TTL:
        return _APPS_CACHE
    if sys.platform == "win32":
        apps = _enumerate_windows()
    elif sys.platform == "darwin":
        apps = _enumerate_macos()
    else:
        apps = _enumerate_linux()
    _APPS_CACHE = apps
    _APPS_CACHE_TS = now
    return apps


# ── Matching ────────────────────────────────────────────────────

def _find_best(query):
    q = query.lower().strip()
    best = None
    best_ratio = 0.0
    best_len_diff = float("inf")
    for app in list_apps():
        nl = app["name"].lower()
        if q in nl:
            ratio = 1.0
            if nl == q:
                ratio = 1.1  # exact match trumps everything
        else:
            ratio = _fuzzy(q, nl)
        # tiebreak: prefer exact match, then shortest name (closest to query)
        if ratio > best_ratio or (ratio == best_ratio and len(nl) < best_len_diff):
            best_ratio = ratio
            best_len_diff = len(nl)
            best = app
    if best and best_ratio >= 0.70:
        return best
    return None


# ── Launch ──────────────────────────────────────────────────────

def launch(query, args=""):
    if not query.strip():
        return "error: no app name specified"
    args_lower = (args or "").lower()
    for bad in _DENYLIST_ARGS:
        if bad in args_lower:
            return f"error: args blocked by security policy (contains '{bad}')"
    app = _find_best(query)
    if app is None:
        return f"error: no app found matching: {query}"
    path = app["path"]
    try:
        if sys.platform == "win32":
            return _launch_windows(path, app["name"], args)
        elif sys.platform == "darwin":
            return _launch_macos(path, app["name"], args)
        else:
            return _launch_linux(app, args)
    except Exception as e:
        return f"error: {e}"


def _resolve_lnk_target(lnk_path):
    try:
        ps = (
            '$s = (New-Object -ComObject WScript.Shell).CreateShortcut("'
            + lnk_path.replace('"', '\\"')
            + '"); Write-Output $s.TargetPath'
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW, timeout=5,
        )
        target = (result.stdout or "").strip()
        return target if target else None
    except Exception:
        return None


def _launch_windows(path, name, args):
    is_uwp = path.startswith("shell:AppsFolder\\")
    if not args:
        if is_uwp:
            subprocess.Popen(
                ["explorer.exe", path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            os.startfile(path)  # noqa: S606
        return f"ok: launched {name}"
    if is_uwp:
        subprocess.Popen(
            ["explorer.exe", path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return f"ok: launched {name} (args ignored for UWP apps)"
    target = _resolve_lnk_target(path)
    if target and os.path.exists(target):
        arg_parts = shlex.split(args, posix=False)
        subprocess.Popen(
            [target] + arg_parts,
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    else:
        os.startfile(path)  # noqa: S606
    return f"ok: launched {name}"


def _launch_macos(path, name, args):
    cmd = ["open", path]
    if args:
        cmd += ["--args"] + shlex.split(args)
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return f"ok: launched {name}"


def _launch_linux(app, args):
    exec_line = app.get("exec") or ""
    if exec_line:
        exec_line = re.sub(r"%[fFuUick]", "", exec_line).strip()
        parts = shlex.split(exec_line)
    else:
        parts = [app["path"]]
    if args:
        parts += shlex.split(args)
    subprocess.Popen(parts, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return f"ok: launched {app['name']}"


# ── Close ────────────────────────────────────────────────────────

def close_app(name: str, timeout: float = 5) -> str:
    """Close application(s) by window title or process name.
    Tries graceful close first, force-kills after timeout.
    Returns 'true' if anything was closed, 'false' otherwise."""
    if not name.strip():
        return "false"

    if sys.platform == "win32":
        return _close_win32(name.strip(), timeout)
    elif sys.platform == "darwin":
        return _close_macos(name.strip(), timeout)
    else:
        return _close_linux(name.strip(), timeout)


def _close_win32(name: str, timeout: float) -> str:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi

    name_lower = name.lower()
    windows: list[tuple] = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def enum_proc(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        title_buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title_buf, 256)
        title_str = title_buf.value
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        proc_name = ""
        try:
            h_process = kernel32.OpenProcess(0x0400 | 0x0010, False, pid)
            if h_process:
                exe_buf = ctypes.create_unicode_buffer(260)
                psapi.GetModuleBaseNameW(h_process, None, exe_buf, 260)
                proc_name = exe_buf.value
                kernel32.CloseHandle(h_process)
        except Exception:
            pass
        windows.append((hwnd, title_str or "", (proc_name or "").rstrip(".exe"), pid.value))
        return True

    callback = WNDENUMPROC(enum_proc)
    user32.EnumWindows(callback, 0)

    # Match by window title first
    matched_pids: set[int] = set()
    for hwnd, title, proc, pid in windows:
        if title and name_lower in title.lower():
            matched_pids.add(pid)

    # Fallback: match by process name
    if not matched_pids:
        for hwnd, title, proc, pid in windows:
            if proc and name_lower in proc.lower():
                matched_pids.add(pid)

    if not matched_pids:
        # Try exact process match via tasklist (for background processes without visible windows)
        try:
            r = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {name}.exe", "/NH"],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW, timeout=5
            )
            if name_lower in r.stdout.lower():
                subprocess.run(
                    ["taskkill", "/IM", f"{name}.exe", "/F"],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW, timeout=5
                )
                return "true"
        except Exception:
            pass
        return "false"

    WM_CLOSE = 0x0010

    def _get_all_windows_for_pid(target_pid):
        result = []
        for hwnd, title, proc, pid in windows:
            if pid == target_pid:
                result.append(hwnd)
        return result

    # Send WM_CLOSE to all windows of matched PIDs
    for pid in matched_pids:
        for hwnd in _get_all_windows_for_pid(pid):
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)

    # Poll for process exit
    deadline = time.time() + timeout
    while time.time() < deadline:
        alive = []
        for pid in matched_pids:
            try:
                r = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                    capture_output=True, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW, timeout=5
                )
                if str(pid) in r.stdout:
                    alive.append(pid)
            except Exception:
                pass
        if not alive:
            return "true"
        time.sleep(0.2)

    # Force kill survivors
    killed = False
    for pid in matched_pids:
        try:
            r = subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW, timeout=5
            )
            if r.returncode == 0:
                killed = True
        except Exception:
            pass

    return "true" if killed else "false"


def _close_macos(name: str, timeout: float) -> str:
    safe = name.replace('"', '\\"')
    # Try graceful quit via osascript
    script = (
        'tell application "System Events"\n'
        '  set found to false\n'
        f'  set target to "{safe}"\n'
        '  repeat with proc in (every process whose visible is true)\n'
        '    set pname to name of proc as text\n'
        '    if pname contains target then\n'
        '      try\n'
        '        tell proc to quit\n'
        '        set found to true\n'
        '      end try\n'
        '    end if\n'
        '  end repeat\n'
        '  return found\n'
        'end tell'
    )
    try:
        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout + 2
        )
        if "true" in r.stdout.lower():
            return "true"
    except Exception:
        pass

    # Fallback: pkill with timeout
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = subprocess.run(
                ["pgrep", "-f", name], capture_output=True, text=True, timeout=5
            )
            if not r.stdout.strip():
                return "true"
        except Exception:
            pass
        time.sleep(0.2)

    try:
        subprocess.run(
            ["pkill", "-f", name], capture_output=True, timeout=5
        )
        return "true"
    except Exception:
        return "false"


def _close_linux(name: str, timeout: float) -> str:
    # Try wmctrl graceful close
    try:
        r = subprocess.run(
            ["wmctrl", "-l"], capture_output=True, text=True, timeout=5
        )
        for line in r.stdout.splitlines():
            if name.lower() in line.lower():
                wid = line.split(None, 1)[0]
                subprocess.run(
                    ["wmctrl", "-i", "-c", wid], capture_output=True, timeout=5
                )
    except Exception:
        pass

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = subprocess.run(
                ["pgrep", "-f", name], capture_output=True, text=True, timeout=5
            )
            if not r.stdout.strip():
                return "true"
        except Exception:
            pass
        time.sleep(0.2)

    try:
        subprocess.run(
            ["pkill", "-9", "-f", name], capture_output=True, timeout=5
        )
        return "true"
    except Exception:
        return "false"