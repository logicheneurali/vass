import glob
import os
import sys
import time
import threading

_fullscreen_warned = set()


class _LinuxIdleDetector:
    """Tracks Linux idle state using CPU and GPU load polling.

    On Linux, monitors CPU and GPU utilization to detect user activity.
    High CPU or GPU usage indicates the user is likely active.
    Falls back to 0 if neither CPU nor GPU metrics are available.
    """

    def __init__(self):
        self._last_input_ts = time.time()
        self._lock = threading.Lock()
        self._psutil_available = False
        try:
            import psutil
            self._psutil = psutil
            self._psutil_available = True
        except ImportError:
            self._psutil = None

        self._gpu_available = False
        self._gpu = None
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            if gpus:
                self._gpu_available = True
                self._gpu = gpus[0]
        except Exception:
            pass

        # Rolling average for CPU load to smooth out瞬时 spikes
        self._cpu_samples = []
        self._cpu_avg_window = 3  # last 3 samples

        # Start background monitoring thread
        self._start_cpu_gpu_loop()

    def _get_cpu_load(self):
        """Calculate CPU load percentage using psutil if available.
        
        Maintains a rolling average of the last N samples to smooth
        out instantaneous spikes. Returns the current rolling average.
        Falls back to 0.0 if psutil is not installed.
        """
        if not self._psutil_available:
            return 0.0
        try:
            current = self._psutil.cpu_percent(interval=0.0)
            self._cpu_samples.append(current)
            if len(self._cpu_samples) > self._cpu_avg_window:
                self._cpu_samples.pop(0)
            return sum(self._cpu_samples) / len(self._cpu_samples)
        except Exception:
            return 0.0

    def _get_gpu_load(self):
        """Get GPU utilization percentage (compute load, not memory)."""
        try:
            if self._has_gpu:
                return self._gpu.load * 100.0
        except Exception:
            pass
        return 0.0

    def _start_cpu_gpu_loop(self):
        """Start background thread to poll CPU/GPU and update last input timestamp."""
        t = threading.Thread(target=self._cpu_gpu_poll_loop, daemon=True)
        t.start()

    def _cpu_gpu_poll_loop(self):
        """Poll CPU and GPU load periodically to detect user activity.
        
        Only this thread calls _get_cpu_load() to ensure consistent delta calculation.
        CPU threshold set to 25% (with 3-sample rolling average) to catch
        sustained heavy loads while ignoring short background noise.
        GPU threshold set to 50% for compute activity detection.
        """
        cpu_threshold = 25.0  # 25% CPU sustained = user actively running something
        gpu_threshold = 50.0  # 50% GPU = active compute

        while True:
            try:
                cpu_load = self._get_cpu_load()
                gpu_load = self._get_gpu_load() if self._gpu_available else 0.0

                if cpu_load > cpu_threshold or gpu_load > gpu_threshold:
                    with self._lock:
                        self._last_input_ts = time.time()
            except Exception:
                pass
            time.sleep(1.0)

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def get_idle_seconds(self):
        """Return idle seconds based on CPU/GPU load."""
        try:
            with self._lock:
                last = self._last_input_ts
            return max(time.time() - last, 0.0)
        except Exception:
            return time.time() - self._last_input_ts if hasattr(self, '_last_input_ts') else 0.0

class IdleTracker:
    def __init__(self):
        self._last_voice_ts = time.time()
        if sys.platform == "linux":
            self._linux_detector = _LinuxIdleDetector()
        else:
            self._linux_detector = None

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
        # Use the new CPU/GPU-based detector.
        if hasattr(self, '_linux_detector') and self._linux_detector:
            return self._linux_detector.get_idle_seconds()
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
