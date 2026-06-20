import time as _time
from uuid import uuid4

PRIORITY_COLORS = {
    (8, 10): "#e74c3c",
    (4, 7): "#f1c40f",
    (1, 3): "#3498db",
}


class NotificationManager:
    def __init__(self, gui=None):
        self.gui = gui
        self._notifications = []

    def add(self, text, priority=1, data=None):
        n = {
            "id": uuid4().hex[:6],
            "text": text,
            "priority": max(1, min(10, int(priority or 1))),
            "ts": _time.strftime("%H:%M:%S"),
            "read": False,
            "data": data if isinstance(data, dict) else {},
        }
        self._notifications.append(n)
        if self.gui and hasattr(self.gui, '_update_bell'):
            self.gui.schedule(0, self.gui._update_bell)
        return n["id"]

    def unread_count(self):
        return sum(1 for n in self._notifications if not n["read"])

    def mark_all_read(self):
        for n in self._notifications:
            n["read"] = True
        if self.gui and hasattr(self.gui, '_update_bell'):
            self.gui.schedule(0, self.gui._update_bell)

    def list_all(self):
        return list(reversed(self._notifications))

    @staticmethod
    def color_for(priority):
        for (lo, hi), c in PRIORITY_COLORS.items():
            if lo <= priority <= hi:
                return c
        return "#888888"
