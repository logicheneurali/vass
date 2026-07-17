"""Noise Auto-Pause plugin — detects ambient noise and auto-pauses listening."""
import time
import numpy as np

from plugins._base import Plugin


class NoiseAutoPausePlugin(Plugin):
    """Encapsulates all noise detection and auto-pause logic for the main loop."""

    def __init__(self):
        self._app = None
        self._noise_high_since = None
        self._running_noise_floor = None
        self._nf_print_counter = 0

    def on_load(self, app) -> None:
        self._app = app
        print("[Noise] Plugin loaded")

    def on_unload(self) -> None:
        self._noise_high_since = None
        self._running_noise_floor = None
        self._app = None
        print("[Noise] Plugin unloaded")

    def on_settings_change(self, settings: dict) -> None:
        """Reset state when noise settings change."""
        self._noise_high_since = None
        self._running_noise_floor = None

    def get_threads(self) -> list:
        return []

    def get_hook(self, name: str) -> list:
        if name == "reset_state":
            return [self.reset_state]
        if name == "auto_pause_check":
            return [self.check_auto_pause_resume]
        if name == "main_loop_frame":
            return [self.process_listening_frame]
        return []

    def reset_state(self):
        """Reset all internal noise tracking state."""
        self._noise_high_since = None
        self._running_noise_floor = None
        self._nf_print_counter = 0

    # ── Main loop hooks ──────────────────────────────────────────

    def check_auto_pause_resume(self, get_frame_fn, start_stream_fn):
        """Called when app is auto-paused. Returns True if we should continue (resumed)."""
        app = self._app
        elapsed = time.time() - app.state_manager.get_auto_paused_at()
        if elapsed < app.noise_pause_duration:
            return False

        print(f"[Noise] Checking noise floor after {app.noise_pause_duration}s pause...")
        if app.audio_handler.stream is None:
            start_stream_fn()

        nf_samples = []
        deadline = time.time() + 0.5
        while len(nf_samples) < 20 and time.time() < deadline:
            f = get_frame_fn()
            if f is not None:
                nf_samples.append(float(np.sqrt(np.mean(f**2))))
            else:
                time.sleep(0.01)

        if nf_samples:
            current_nf = sum(nf_samples) / len(nf_samples)
            adaptive_threshold = max(app.noise_pause_threshold,
                                     app.voice_recognition.noise_floor * 2.0)
            print(f"[Noise] Current noise floor: {current_nf:.6f} (threshold: {adaptive_threshold:.6f})")
            if current_nf < adaptive_threshold:
                print("[Noise] Auto-resuming: noise floor dropped below threshold")
                self._noise_high_since = None
                self._running_noise_floor = None
                app.voice_recognition.reset_noise_floor()
                app.state_manager.exit_auto_pause()
                return True
            else:
                print(f"[Noise] Still noisy, staying paused for another {app.noise_pause_duration}s")
                app.state_manager.extend_auto_pause()
        else:
            print("[Noise] Check: no audio samples captured, staying paused")
            app.state_manager.extend_auto_pause()
        return False

    def process_listening_frame(self, frame, raw_rms):
        """Called once per frame when state is 'listening'. May trigger auto-pause."""
        app = self._app
        if not app.noise_pause:
            return None

        nf = float(np.sqrt(np.mean(frame**2)))
        adaptive_threshold = max(app.noise_pause_threshold,
                                 app.voice_recognition.noise_floor * 2.0)
        if self._running_noise_floor is None:
            self._running_noise_floor = nf
        else:
            self._running_noise_floor = 0.99 * self._running_noise_floor + 0.01 * nf
        nf = self._running_noise_floor
        self._nf_print_counter += 1

        if nf > adaptive_threshold:
            if self._noise_high_since is None:
                self._noise_high_since = time.time()
            elapsed_noisy = time.time() - self._noise_high_since
            if elapsed_noisy >= app.noise_pause_duration:
                print(f"[Noise] Auto-pausing: noise floor {nf:.4f} > {adaptive_threshold:.4f} for {app.noise_pause_duration}s")
                app.state_manager.set_auto_paused()
                self._noise_high_since = None
                return "auto_paused"
        else:
            self._noise_high_since = None
            if app.noise_filter:
                app.noise_filter.maybe_update_profile(
                    frame, is_silence=True, now=time.time())

        # GUI update
        if self._nf_print_counter % 50 == 0:
            gain = app.voice_recognition.input_volume
            nf_raw = min(1.0, nf * 50)
            app.gui.noise_floor_signal.emit(gain, nf_raw)
        if self._nf_print_counter >= 250:
            self._nf_print_counter = 0
            if nf > adaptive_threshold and app.debug_enabled:
                print(f"[NoiseFloor] {nf:.6f} (adaptive threshold: {adaptive_threshold:.6f})")

        return None
