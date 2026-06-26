import sys
import subprocess


def set_active_window(name: str) -> bool:
    """Activate window by process name or title substring (case-insensitive).
    First tries to match process name, then window title.
    Returns True if a matching window was found and activated."""
    name_lower = name.lower()

    if sys.platform == "win32":
        return _set_active_window_win32(name_lower)
    elif sys.platform == "linux":
        return _set_active_window_linux(name_lower)
    elif sys.platform == "darwin":
        return _set_active_window_mac(name_lower)
    return False


# ---------- Windows ----------

def _set_active_window_win32(name_lower: str) -> bool:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi

    windows = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def enum_proc(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title, 256)
        title_str = title.value
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
        windows.append((hwnd, title_str, proc_name, pid.value))
        return True

    callback = WNDENUMPROC(enum_proc)
    user32.EnumWindows(callback, 0)

    # Priority 1: process name contains name_lower (e.g., "firefox" in "firefox.exe")
    for hwnd, title, proc, pid in windows:
        if proc and name_lower in proc.lower():
            return _activate_win32(hwnd, proc)

    # Priority 2: window title contains name_lower
    for hwnd, title, proc, pid in windows:
        if title and name_lower in title.lower():
            return _activate_win32(hwnd, title or proc)

    return False


def _activate_win32(hwnd, label: str) -> bool:
    import ctypes
    user32 = ctypes.windll.user32

    # If already the foreground window, do nothing
    if hwnd == user32.GetForegroundWindow():
        print(f"[Window] Already active: {label}")
        return True

    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    else:
        user32.ShowWindow(hwnd, 5)  # SW_SHOW

    # Attach foreground thread to allow SetForegroundWindow
    fg_hwnd = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    if fg_thread != target_thread:
        user32.AttachThreadInput(target_thread, fg_thread, True)
    result = user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)
    if fg_thread != target_thread:
        user32.AttachThreadInput(target_thread, fg_thread, False)

    print(f"[Window] Activated: {label}")
    return True


# ---------- Linux ----------

def _set_active_window_linux(name_lower: str) -> bool:
    try:
        result = subprocess.run(
            ["wmctrl", "-l"], capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            parts = line.split(None, 3)
            if len(parts) >= 4 and name_lower in parts[3].lower():
                wid = parts[0]
                subprocess.run(["wmctrl", "-i", "-a", wid], timeout=5)
                print(f"[Window] Activated via wmctrl: {parts[3]}")
                return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    try:
        result = subprocess.run(
            ["xdotool", "search", "--name", name_lower],
            capture_output=True, text=True, timeout=5
        )
        wids = [w for w in result.stdout.splitlines() if w.strip()]
        if wids:
            subprocess.run(["xdotool", "windowactivate", wids[0]], timeout=5)
            print(f"[Window] Activated via xdotool")
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return False


# ---------- macOS ----------

def _set_active_window_mac(name_lower: str) -> bool:
    safe_name = name_lower.replace('\\', '\\\\').replace('"', '\\"')
    script = f'''
    tell application "System Events"
        set found to false
        repeat with proc in (every process whose visible is true)
            set procName to name of proc as text
            if procName contains "{safe_name}" then
                set frontmost of proc to true
                set found to true
                exit repeat
            end if
            try
                set winList to every window of proc
                repeat with w in winList
                    set winTitle to title of w as text
                    if winTitle contains "{safe_name}" then
                        set frontmost of proc to true
                        set found to true
                        exit repeat
                    end if
                end repeat
            end try
            if found then exit repeat
        end repeat
    end tell
    return found
    '''
    try:
        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10
        )
        ok = "true" in r.stdout.lower()
        if ok:
            print(f"[Window] Activated via osascript")
        return ok
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
