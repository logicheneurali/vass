import threading
import time


class StateManager:
    """Centralizes VASS application state transitions.

    Guarantees:
    - Pause intent (manual or auto) is preserved while temporary states
      (waiting, running_script, playing, ...) are active.
    - Operations that finish and request "listening" return to "paused" if
      a pause flag is still set.
    - Manual pause has priority over auto-pause.
    - Auto-pause can only happen from the listening state.
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
        """Generic state change. Preserves pause flags across transitions.

        When listening is requested but a pause flag is active, the state
        is redirected to "paused" instead (unless force=True).
        """
        with self._lock:
            if new_state == "listening" and not force:
                if self._manual_pause:
                    new_state = "paused"
                    detail = detail or "manual"
                elif self._auto_paused_at is not None:
                    new_state = "paused"
                    detail = detail or "auto"
            self._state = new_state
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
        """Resume listening.

        Without force, a manual pause prevents resuming (auto-pause is cleared).
        With force, all pause flags are cleared.
        """
        with self._lock:
            if self._manual_pause and not force:
                # Manual pause wins; just clear any stale auto-pause flag.
                self._auto_paused_at = None
                if self._state != "paused":
                    self._state = "paused"
                    self.app._update_gui_state("paused")
                return False
            self._state = "listening"
            self._manual_pause = False
            self._auto_paused_at = None
        self.app.audio_handler.start_stream()
        self.app._update_gui_state("listening")
        self.app._verify_stream_state(expected_listening=True)
        return True

    def exit_auto_pause(self):
        """Leave auto-pause and resume listening.

        Only resumes when the current state is actually paused, so temporary
        states (waiting, running_script, ...) are not interrupted.
        """
        with self._lock:
            if self._manual_pause:
                # Manual pause is in effect; just drop the auto-pause flag.
                self._auto_paused_at = None
                return False
            if self._state != "paused":
                # Operation in progress; keep the flag so we return to paused after.
                return False
            self._auto_paused_at = None
            self._state = "listening"
        self.app.audio_handler.start_stream()
        self.app._update_gui_state("listening")
        self.app._verify_stream_state(expected_listening=True)
        return True

    def is_manual_paused(self):
        with self._lock:
            return self._manual_pause

    def is_auto_paused(self):
        with self._lock:
            return self._auto_paused_at is not None

    def is_paused(self):
        with self._lock:
            return self._manual_pause or self._auto_paused_at is not None

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
