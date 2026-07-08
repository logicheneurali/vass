"""Periodic file scanner for permanent memory tagging.
Walks configured folders, extracts text content, and enqueues
new/modified files for AI classification via the deferred queue.
"""
import os
import json
import time
import hashlib
import threading

_TEXT_EXTENSIONS = {
    ".txt", ".md", ".py", ".json", ".csv", ".html", ".xml",
    ".log", ".ini", ".yaml", ".cfg", ".vass", ".css", ".js",
    ".ts", ".rst", ".toml", ".bat", ".sh", ".ps1"
}


class FileScanner:
    def __init__(self, files_config, memory_manager):
        self._config = files_config
        self._memory = memory_manager
        self._running = False

    def run(self):
        """Main scan loop. Reads config from disk each cycle for hot-reload."""
        self._running = True
        time.sleep(10)  # initial delay
        while self._running:
            try:
                self._scan()
            except Exception:
                pass
            interval = self._config.get("interval_minutes", 60) * 60
            time.sleep(max(interval, 60))

    def _scan(self):
        folders = self._config.get("folders", [])
        if not folders:
            return
        max_size = self._config.get("max_file_size_kb", 500) * 1024
        tracker = self._load_tracker()
        updated = False

        for folder in folders:
            if not os.path.isdir(folder):
                continue
            for root, dirs, files in os.walk(folder, followlinks=False):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    try:
                        stat = os.stat(fpath)
                    except OSError:
                        continue
                    fsize = stat.st_size
                    if fsize > max_size:
                        continue
                    key = os.path.normpath(fpath).lower()
                    old = tracker.get(key)
                    if old and old.get("mtime") == stat.st_mtime and old.get("size") == fsize:
                        continue

                    content = self._extract_content(fpath, fname, fsize)
                    eid = hashlib.md5(key.encode()).hexdigest()[:12]
                    self._memory.enqueue_external(content, eid, "files")
                    tracker[key] = {"mtime": stat.st_mtime, "size": fsize}
                    updated = True
                    print(f"[FileScanner] Queued: {fpath} ({fsize} bytes)")

        # Remove deleted files from tracker
        to_delete = []
        for key in tracker:
            if not os.path.exists(key):
                to_delete.append(key)
        for key in to_delete:
            del tracker[key]
            updated = True

        if updated:
            self._save_tracker(tracker)

    def _extract_content(self, fpath, fname, fsize):
        """Build text content for classification: path + optional text snippet."""
        parts = [f"File: {fpath}\nName: {fname}\nSize: {fsize} bytes"]
        ext = os.path.splitext(fname)[1].lower()
        if ext in _TEXT_EXTENSIONS:
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    snippet = f.read(2048)
                parts.append(f"Content preview:\n{snippet}")
            except Exception:
                pass
        return "\n".join(parts)

    def _load_tracker(self):
        try:
            with open(self._tracker_path(), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_tracker(self, data):
        try:
            os.makedirs(os.path.dirname(self._tracker_path()), exist_ok=True)
            with open(self._tracker_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    @staticmethod
    def _tracker_path():
        from utils import get_path
        return get_path("Allowed_root", "memory_files_tracker.json")

    def stop(self):
        self._running = False
