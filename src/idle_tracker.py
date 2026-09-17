import glob
import os
import select
import sys
import time
import threading

try:
    import evdev
except ImportError:
    evdev = None

_fullscreen_warned = set()


class _LinuxIdleDetector:
    """Tracks Linux idle state using evdev input events.

    On Linux, opens the keyboard and mouse input devices directly from the
    kernel input layer and polls them with select(). Any key press or mouse
    movement resets the last-activity timestamp. This works regardless of the
    display server (X11, Xwayland, or Wayland) because it reads raw input
    events from /dev/input, bypassing the window system entirely.
    Falls back to CPU/GPU load polling if evdev is not available.
    """

    def __init__(self):
        self._last_input_ts = time.time()
        self._lock = threading.Lock()
        self._devs = self._find_input_devices()
        if self._devs:
            self._start_evdev_loop()
        else:
            self._start_cpu_gpu_loop()

    def _find_input_devices(self):
        """Return list of (InputDevice, fd) for keyboard and mouse devices.
        
        Also includes game controllers / joysticks / gamepads, so any real
        input device the user can hold or operate counts as activity. The fd
        is opened once and reused for select(). Returns an empty list if evdev
        is not installed or no usable input devices are found.
        """
        if evdev is None:
            return []

        devs = []
        try:
            paths = evdev.list_devices()
        except Exception:
            return []

        for path in paths:
            try:
                dev = evdev.InputDevice(path)
            except Exception:
                continue
            name = dev.name.lower()
            # Keep any device that reflects genuine user activity: keyboard,
            # mouse, joystick, gamepad or game controller. Exclude only the
            # multimedia/system nodes (Consumer Control, System Control, etc.)
            # which do not correspond to a device the user actually holds.
            if not ('keyboard' in name or 'mouse' in name
                    or 'joystick' in name or 'gamepad' in name
                    or 'controller' in name or 'game' in name
                    or 'wheel' in name or 'arcade' in name):
                continue
            if 'system' in name or 'consumer' in name:
                continue
            try:
                fd = dev.fileno()
            except Exception:
                continue
            devs.append((dev, fd))

        return devs

    def _start_evdev_loop(self):
        """Start background thread that polls input devices for activity."""
        t = threading.Thread(target=self._evdev_poll_loop, daemon=True)
        t.start()

    def _evdev_poll_loop(self):
        """Poll input devices with select() and reset the timestamp on activity.
        
        Blocks up to 1 second per iteration using select(). When any device is
        ready, drain its queued events with read(); if any key/mouse event is
        found, update the last-activity timestamp. select() is used rather than
        blocking reads so the loop can wake periodically to stay responsive.
        """
        while True:
            try:
                ready_fds = [(dev, fd) for dev, fd in self._devs]
                fds = [fd for _, fd in ready_fds]
                if not fds:
                    time.sleep(1.0)
                    continue
                try:
                    readable, _, _ = select.select(fds, [], [], 1.0)
                except (ValueError, OSError):
                    # A device fd was closed or became invalid; re-scan.
                    self._devs = self._find_input_devices()
                    time.sleep(1.0)
                    continue
                if not readable:
                    continue
                for dev, fd in ready_fds:
                    if fd not in readable:
                        continue
                    try:
                        for ev in dev.read():
                            if ev.type in (evdev.ecodes.EV_KEY, evdev.ecodes.EV_REL, evdev.ecodes.EV_ABS):
                                with self._lock:
                                    self._last_input_ts = time.time()
                                break
                    except (BlockingIOError, OSError, ValueError):
                        continue
                    except Exception:
                        continue
            except Exception:
                pass

    def _get_cpu_load(self):
        """Fallback CPU load percentage using psutil if available."""
        try:
            import psutil
        except ImportError:
            return 0.0
        try:
            return psutil.cpu_percent(interval=0.0)
        except Exception:
            return 0.0

    def _start_cpu_gpu_loop(self):
        """Fallback: start background thread to poll CPU/GPU load."""
        t = threading.Thread(target=self._cpu_gpu_poll_loop, daemon=True)
        t.start()

    def _cpu_gpu_poll_loop(self):
        """Fallback CPU/GPU load polling for when evdev is unavailable.
        
        A sustained CPU load above the threshold suggests the user is active
        (typing, running apps). This is a coarse fallback; evdev is preferred.
        """
        cpu_threshold = 25.0
        while True:
            try:
                if self._get_cpu_load() > cpu_threshold:
                    with self._lock:
                        self._last_input_ts = time.time()
            except Exception:
                pass
            time.sleep(1.0)

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def get_idle_seconds(self):
        """Return idle seconds based on input device activity (or CPU/GPU fallback)."""
        try:
            with self._lock:
                last = self._last_input_ts
            return max(time.time() - last, 0.0)
        except Exception:
            return 0.0

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
