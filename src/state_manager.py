import threading
import time


class StateManager:
    """Centralizes VASS application state transitions.

    Guarantees:
    - Manual pause is never overridden by automatic transitions.
    - Auto-pause can only happen from the listening state.
    - Stream and GUI are updated atomically through VassApp callbacks.
    """

    def __init__(self, app):
        self.app = app
        self._lock = threading.RLock()
        self._state = "loading"
        self._manual_pause = False
        self._auto_paused_at = None

    @property
    def state(self):
        with self._lock:
            return self._state

    def set_state(self, new_state, detail="", silent_gui=False, force=False):
        """Generic state change. Respects manual pause when entering listening."""
        with self._lock:
            if new_state == "listening" and self._manual_pause and not force:
                return False
            self._state = new_state
            if new_state != "paused":
                self._manual_pause = False
                self._auto_paused_at = None
        self.app._update_gui_state(new_state, detail, silent_gui)
        return True

    def set_manual_paused(self):
        """User pressed the pause button. This state is sacred."""
        with self._lock:
            self._manual_pause = True
            self._auto_paused_at = None
            self._state = "paused"
        self.app.audio_handler.stop_stream()
        self.app._update_gui_state("paused")
        self.app._verify_stream_state(expected_listening=False)
        return True

    def set_auto_paused(self):
        """Auto-pause due to noise. Blocked if user manually paused."""
        with self._lock:
            if self._manual_pause:
                return False
            if self._state != "listening":
                return False
            self._state = "paused"
            self._auto_paused_at = time.time()
        self.app.audio_handler.stop_stream()
        self.app._update_gui_state("paused")
        self.app._verify_stream_state(expected_listening=False)
        return True

    def resume_listening(self, force=False):
        """Resume listening, unless manually paused (unless force=True)."""
        with self._lock:
            if self._manual_pause and not force:
                return False
            self._state = "listening"
            self._manual_pause = False
            self._auto_paused_at = None
        self.app.audio_handler.start_stream()
        self.app._update_gui_state("listening")
        self.app._verify_stream_state(expected_listening=True)
        return True

    def exit_auto_pause(self):
        """Leave auto-pause and resume listening."""
        return self.resume_listening(force=False)

    def is_manual_paused(self):
        with self._lock:
            return self._manual_pause

    def is_auto_paused(self):
        with self._lock:
            return self._auto_paused_at is not None

    def get_auto_paused_at(self):
        with self._lock:
            return self._auto_paused_at

    def clear_auto_pause(self):
        with self._lock:
            self._auto_paused_at = None

    def extend_auto_pause(self):
        """Extend the auto-pause timer (noise still high)."""
        with self._lock:
            if self._auto_paused_at is not None:
                self._auto_paused_at = time.time()

    def reset_pause_flags(self):
        with self._lock:
            self._manual_pause = False
            self._auto_paused_at = None
