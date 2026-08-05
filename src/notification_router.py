"""NotificationRouter — routes events to TTS and/or InfoPanel notifications.

Reads action per event type from config/notifications.ini.
Actions: tts, notification, both, none. Missing event -> [default] -> "both".
"""
import configparser
import os


class NotificationRouter:
    ACTIONS = ("tts", "notification", "both", "none")

    def __init__(self, app, config_path=None):
        self._app = app
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "config", "notifications.ini")
        self._config_path = config_path
        self._config = self._load(config_path)

    def _load(self, path):
        cfg = configparser.ConfigParser()
        mapping = {}
        try:
            if not os.path.exists(path):
                example = path.replace(".ini", ".example.ini")
                if os.path.exists(example):
                    import shutil
                    shutil.copy(example, path)
                    print(f"[NotificationRouter] Created {path} from example")
            if os.path.exists(path):
                cfg.read(path, encoding="utf-8")
            for section in cfg.sections():
                action = cfg.get(section, "action", fallback="both").strip().lower()
                if action not in self.ACTIONS:
                    action = "both"
                mapping[section.lower()] = action
        except Exception as e:
            print(f"[NotificationRouter] Config error: {e}")
        return mapping

    def get_action(self, event_type):
        action = self._config.get(event_type.lower())
        if action is None:
            action = self._config.get("default", "both")
        return action

    def reload(self):
        """Reload config from disk (e.g. after GUI edits)."""
        self._config = self._load(self._config_path)
        print(f"[NotificationRouter] Config reloaded: {self._config}")

    def emit(self, event_type, text, priority=5, data=None, tts_kwargs=None):
        """Route an event: speak, notify, both, or none per config."""
        action = self.get_action(event_type)
        if action in ("tts", "both"):
            try:
                kwargs = {"defer_if_busy": True}
                if tts_kwargs:
                    kwargs.update(tts_kwargs)
                self._app.tts.enqueue(text, **kwargs)
            except Exception as e:
                print(f"[NotificationRouter] TTS error: {e}")
        if action in ("notification", "both"):
            try:
                self._app.notification_manager.add(text, priority=priority, data=data)
            except Exception as e:
                print(f"[NotificationRouter] Notification error: {e}")
