"""Memory Files Scanner plugin — walks configured folders and enqueues new files."""
from plugins._base import Plugin


class MemoryFilesScannerPlugin(Plugin):
    def __init__(self):
        self._scanner = None

    def on_load(self, app) -> None:
        if not app.memory.is_source_enabled("files"):
            print("[FileScanner] Source disabled, skipping")
            return
        from .memory_files_scanner import FileScanner
        self._scanner = FileScanner(app.memory._files_config, app.memory)
        print("[FileScanner] Plugin loaded")

    def on_unload(self) -> None:
        if self._scanner:
            self._scanner.stop()
            self._scanner = None
        print("[FileScanner] Plugin unloaded")

    def get_threads(self) -> list:
        if not self._scanner:
            return []
        return [
            (self._scanner.run, (), {}),
        ]
