import sys
import time

_fullscreen_warned = set()


class IdleTracker:
    def __init__(self):
        self._last_voice_ts = time.time()

    def update_voice_activity(self):
        self._last_voice_ts = time.time()

    def get_input_idle_seconds(self):
        if sys.platform == "win32":
            return self._idle_win32()
        elif sys.platform == "darwin":
            return self._idle_darwin()
        else:
            return self._idle_linux()

    def _idle_win32(self):
        try:
            import ctypes
            from ctypes import wintypes
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
            user32 = ctypes.windll.user32
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(lii)
            if user32.GetLastInputInfo(ctypes.byref(lii)):
                tick_diff = int(ctypes.windll.kernel32.GetTickCount()) - lii.dwTime
                return max(tick_diff, 0) / 1000.0
        except Exception:
            pass
        return 0

    def _idle_darwin(self):
        try:
            import subprocess
            r = subprocess.run(
                ["ioreg", "-c", "IOHIDSystem"],
                capture_output=True, text=True, timeout=5
            )
            for line in r.stdout.splitlines():
                if "Idle" in line:
                    import re
                    m = re.search(r"(\d+)", line)
                    if m:
                        return int(m.group(1)) / 1_000_000_000.0
        except Exception:
            pass
        return 0

    def _idle_linux(self):
        try:
            import subprocess
            r = subprocess.run(
                ["xprintidle"],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0 and r.stdout.strip():
                return int(r.stdout.strip()) / 1000.0
        except Exception:
            pass
        return 0

    def get_total_idle_seconds(self):
        if self._is_fullscreen():
            return 0
        input_idle = self.get_input_idle_seconds()
        voice_idle = time.time() - self._last_voice_ts
        return min(input_idle, voice_idle)

    def _is_fullscreen(self):
        if sys.platform == "win32":
            return self._is_fullscreen_win32()
        elif sys.platform == "darwin":
            return self._is_fullscreen_darwin()
        else:
            return self._is_fullscreen_linux()

    @staticmethod
    def _is_fullscreen_win32():
        try:
            import ctypes
            from ctypes import wintypes

            class RECT(ctypes.Structure):
                _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                            ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            rect = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            fw = rect.right - rect.left
            fh = rect.bottom - rect.top
            sw = user32.GetSystemMetrics(0)   # SM_CXSCREEN
            sh = user32.GetSystemMetrics(1)   # SM_CYSCREEN
            return fw >= sw and fh >= sh
        except Exception:
            return False

    @staticmethod
    def _is_fullscreen_darwin():
        try:
            import Quartz
            window_list = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
                Quartz.kCGNullWindowID
            )
            for w in window_list:
                if w.get(Quartz.kCGWindowLayer, 99) == 0:
                    bounds = w.get(Quartz.kCGWindowBounds, {})
                    ww, wh = bounds.get("Width", 0), bounds.get("Height", 0)
                    display = Quartz.CGMainDisplayID()
                    sw = Quartz.CGDisplayPixelsWide(display)
                    sh = Quartz.CGDisplayPixelsHigh(display)
                    return ww >= sw and wh >= sh
            return False
        except ImportError:
            if "darwin" not in _fullscreen_warned:
                _fullscreen_warned.add("darwin")
                print("[IdleTracker] fullscreen detection: Quartz not installed, install pyobjc-framework-Quartz")
            return False
        except Exception:
            return False

    @staticmethod
    def _is_fullscreen_linux():
        try:
            import subprocess, re
            r = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowgeometry", "--shell"],
                capture_output=True, text=True, timeout=3
            )
            if r.returncode != 0:
                return False
            geom = {}
            for line in r.stdout.strip().splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    geom[k] = int(v)
            r2 = subprocess.run(
                ["xrandr", "--current"],
                capture_output=True, text=True, timeout=3
            )
            for line in r2.stdout.splitlines():
                m = re.search(r'(\d+)x(\d+)\+\d+\+\d+', line)
                if m:
                    sw, sh = int(m.group(1)), int(m.group(2))
                    fw = geom.get("WIDTH", 0)
                    fh = geom.get("HEIGHT", 0)
                    return fw >= sw and fh >= sh
        except FileNotFoundError:
            if "linux" not in _fullscreen_warned:
                _fullscreen_warned.add("linux")
                print("[IdleTracker] fullscreen detection: xdotool not found, install with: sudo apt install xdotool")
            return False
        except Exception:
            pass
        return False
