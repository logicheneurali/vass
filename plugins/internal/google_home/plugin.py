"""Google Home plugin — enables Google Assistant SDK integration for voice commands."""
from plugins._base import Plugin


class GoogleHomePlugin(Plugin):
    def __init__(self):
        self._app = None

    def on_load(self, app) -> None:
        self._app = app
        print("[GoogleHome] Plugin loaded")

    def on_unload(self) -> None:
        self._app = None
        print("[GoogleHome] Plugin unloaded")

    def get_threads(self) -> list:
        return []
