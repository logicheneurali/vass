"""User Profile plugin — builds structured profile from permanent memory."""
import threading
import time

from plugins._base import Plugin
from .user_profile import UserProfile


class UserProfilePlugin(Plugin):
    def __init__(self):
        self._app = None
        self._profile = None

    def on_load(self, app) -> None:
        self._app = app
        self._profile = UserProfile(app)
        app._profile = self._profile
        print("[Profile] Plugin loaded")

    def on_unload(self) -> None:
        self._profile = None
        if hasattr(self._app, '_profile'):
            self._app._profile = None
        print("[Profile] Plugin unloaded")

    def get_threads(self) -> list:
        return [
            (self._profile_loop, (), {}),
        ]

    def _profile_loop(self):
        time.sleep(300)
        while self._app.running:
            try:
                agent = getattr(self._app, '_agent', None)
                if self._profile.is_idle():
                    if self._profile.should_update():
                        print("[Profile] Starting build/update...")
                        self._profile.build_or_update()
                    if agent:
                        agent.check_and_act()
            except Exception as e:
                print(f"[Profile] Error: {e}")
            time.sleep(1800)
