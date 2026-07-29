"""Thread-safe activity tracker for background operations."""
import threading
import time


CATEGORY_COLORS = {
    "ai": "#3498db",
    "tts": "#2ecc71",
    "stt": "#e67e22",
    "memory": "#9b59b6",
    "plugin": "#1abc9c",
    "sync": "#f39c12",
    "script": "#e74c3c",
    "default": "#7f8c8d",
}


class ActivityTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self._active = {}
        self._history = []

    def start(self, name, category="default"):
        with self._lock:
            self._active[name] = {"category": category, "start": time.time()}

    def end(self, name):
        with self._lock:
            if name not in self._active:
                return
            entry = self._active.pop(name)
            duration = time.time() - entry["start"]
            self._history.append({
                "name": name,
                "category": entry["category"],
                "start": entry["start"],
                "duration": duration,
            })
            if len(self._history) > 50:
                self._history = self._history[-50:]

    def get_active(self):
        with self._lock:
            return dict(self._active)

    def is_active(self):
        with self._lock:
            return len(self._active) > 0

    def get_recent(self, count=10):
        with self._lock:
            return list(reversed(self._history[-count:]))


_tracker = None
_lock = threading.Lock()


def get_tracker():
    global _tracker
    with _lock:
        if _tracker is None:
            _tracker = ActivityTracker()
        return _tracker
