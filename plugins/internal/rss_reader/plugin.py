"""RSS Reader plugin — background polling and notification delivery."""
import os
import threading

from plugins._base import Plugin
from utils import get_project_root


class RssReaderPlugin(Plugin):
    def __init__(self):
        self._reader = None
        self._stop_event = None

    def on_load(self, app) -> None:
        feeds_path = os.path.join(get_project_root(), "Allowed_root", "rss_feeds.json")
        cache_path = os.path.join(get_project_root(), "Allowed_root", "rss_cache.json")
        from .rss_reader import RssReader
        self._reader = RssReader(feeds_path, cache_path,
                                 notification_manager=app.notification_manager)
        print("[RSS] Plugin loaded")

    def on_unload(self) -> None:
        if self._reader:
            self._reader.stop_polling()
            self._reader = None
        print("[RSS] Plugin unloaded")

    def get_threads(self) -> list:
        return [
            (self._polling_loop, (), {}),
        ]

    def _polling_loop(self):
        """Poll RSS feeds every 60 minutes."""
        import time
        if not self._reader:
            return
        self._reader.start_polling()
        print("[RSS] Polling started")

    def get_config_widgets(self, section: str) -> list:
        """Return RSS configuration widget for sources_editor."""
        if section != "online_sources":
            return []
        try:
            from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
            w = QWidget()
            l = QVBoxLayout(w)
            l.addWidget(QLabel("RSS Feed Reader"))
            l.addWidget(QLabel("Configure feeds in Allowed_root/rss_feeds.json"))
            return [("RSS", w)]
        except ImportError:
            return []
