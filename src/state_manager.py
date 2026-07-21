import threading


def _sm_log(app, msg):
    if getattr(app, 'debug_enabled', False):
        print(f"[StateManager] {msg}")


class StateManager:
    """Centralizes VASS application state transitions.

    Manual pause (user clicked) has priority over everything.
    Operations that finish and request "listening" return to "paused"
    if manual pause is still active.
    """

    def __init__(self, app):
        self.app = app
        self._lock = threading.RLock()
        self._state = "loading"
        self._manual_pause = False

    @property
    def state(self):
        with self._lock:
            return self._state

    def set_state(self, new_state, detail="", silent_gui=False, force=False, source=""):
        """Generic state change. Preserves manual pause across transitions."""
        with self._lock:
            old_state = self._state
            redirected = False
            if new_state == "listening" and not force and self._manual_pause:
                new_state = "paused"
                detail = detail or "manual"
                redirected = True
            self._state = new_state
        _sm_log(self.app, f"set_state: {old_state} -> {new_state}"
                f"{f' (redirected, detail={detail})' if redirected else ''}"
                f" manual_pause={self._manual_pause}"
                f" silent_gui={silent_gui}")
        self.app._update_gui_state(new_state, detail, silent_gui)
        return True

    def set_manual_paused(self):
        """User pressed the pause button."""
        with self._lock:
            old_state = self._state
            self._manual_pause = True
            self._state = "paused"
        _sm_log(self.app, f"set_manual_paused: {old_state} -> paused")
        self.app.audio_handler.stop_stream()
        self.app._update_gui_state("paused")
        self.app._verify_stream_state(expected_listening=False)
        return True

    def resume_listening(self, force=False):
        """Resume listening. Force clears manual pause."""
        with self._lock:
            old_state = self._state
            if self._manual_pause and not force:
                if self._state != "paused":
                    self._state = "paused"
                    _sm_log(self.app, f"resume_listening: blocked, {old_state} -> paused")
                    self.app._update_gui_state("paused")
                else:
                    _sm_log(self.app, "resume_listening: rejected, manual pause")
                return False
            self._state = "listening"
            self._manual_pause = False
        _sm_log(self.app, f"resume_listening: {old_state} -> listening (force={force})")
        self.app.audio_handler.start_stream()
        self.app._update_gui_state("listening")
        self.app._verify_stream_state(expected_listening=True)
        return True

    def is_manual_paused(self):
        with self._lock:
            return self._manual_pause

    def is_paused(self):
        with self._lock:
            return self._manual_pause
