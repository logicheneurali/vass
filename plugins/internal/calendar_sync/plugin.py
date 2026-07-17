"""Google Calendar Sync plugin — imports events and enqueues for memory tagging."""
import os
import time

from plugins._base import Plugin
from utils import get_project_root


class CalendarSyncPlugin(Plugin):
    def __init__(self):
        self._app = None

    def on_load(self, app) -> None:
        self._app = app
        print("[GCal] Plugin loaded")

    def on_unload(self) -> None:
        self._app = None
        print("[GCal] Plugin unloaded")

    def get_threads(self) -> list:
        enabled = self._app.settings.get("calendar_sync_enabled", "false").lower() == "true"
        if not enabled:
            print("[GCal] Disabled in settings, skipping")
            return []
        return [
            (self._calendar_loop, (), {}),
        ]

    def _calendar_loop(self):
        app = self._app
        time.sleep(5)
        from google_calendar import GoogleCalendar
        gcal = GoogleCalendar()
        minutes = int(app.settings.get("calendar_sync_minutes", 30))
        days = int(app.settings.get("calendar_sync_days", 7))
        events_path = os.path.join(get_project_root(), "Allowed_root", "events.json")
        try:
            self._sync(gcal, events_path, days, app)
        except Exception as e:
            print(f"[GCal] Sync error: {e}")
        while app.running:
            time.sleep(minutes * 60)
            try:
                self._sync(gcal, events_path, days, app)
            except Exception as e:
                print(f"[GCal] Sync error: {e}")

    @staticmethod
    def _sync(gcal, events_path, days, app):
        new_or_changed = gcal.sync_to_vass(events_path, days=days) or []
        if new_or_changed and app.memory.is_source_enabled("calendar"):
            for ev in new_or_changed:
                classify_content = (
                    f"Calendar event: {ev.get('summary', '')}\n"
                    f"When: {ev.get('start', '')} -> {ev.get('end', '')}"
                )
                app.memory.enqueue_external(classify_content, ev["id"], "calendar")
