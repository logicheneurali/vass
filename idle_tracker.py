import sys
import time


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
        input_idle = self.get_input_idle_seconds()
        voice_idle = time.time() - self._last_voice_ts
        return min(input_idle, voice_idle)
