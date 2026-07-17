"""Proactive Agent plugin — exposes agent for background action execution."""
from plugins._base import Plugin
from .proactive_agent import ProactiveAgent


class ProactiveAgentPlugin(Plugin):
    def __init__(self):
        self._agent = None
        self._app = None

    def on_load(self, app) -> None:
        self._app = app
        self._agent = ProactiveAgent(app)
        app._agent = self._agent
        print("[Agent] Plugin loaded")

    def on_unload(self) -> None:
        self._agent = None
        if hasattr(self._app, '_agent'):
            self._app._agent = None
        print("[Agent] Plugin unloaded")

    def get_threads(self) -> list:
        return []
