"""Real-time DSP noise cancellation for the VASS audio pipeline.
Targets constant ambient noise (fans, AC, hum) with <0.01% CPU impact.
"""
import numpy as np


class NoiseFilter:
    def __init__(self, sample_rate=16000, frame_size=320):
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.noise_profile = None       # float64[n_fft//2+1] magnitude spectrum
        self._enabled = True
        self._calibrating = True
        self._calib_accum = []          # list of float64[frame_size]
        self._calib_target = 100        # ~2 seconds at 50fps
        self._last_update = 0

        # Biquad IIR high-pass filter, Butterworth 2nd order, 80Hz @ 16000Hz
        # Coefficients computed via scipy.signal.butter(2, 80/8000, 'high')
        self._hp_b = np.array([0.96508099, -1.93016197, 0.96508099])
        self._hp_a = np.array([1.0, -1.92935037, 0.93148062])
        self._hp_z = np.zeros((2,))  # filter state [z1, z2]

    @property
    def calibrated(self):
        return self.noise_profile is not None

    def reset_calibration(self):
        """Restart noise profile calibration (on device change, resume from pause)."""
        self._calibrating = True
        self._calib_accum = []
        self.noise_profile = None
        self._last_update = 0

    def process(self, frame, raw_rms=0.0):
        """Main entry: returns filtered frame. Pass-through if not a numpy array.
        raw_rms: pre-filter RMS energy for calibration gating (0 = unknown/force)."""
        if not self._enabled or not isinstance(frame, np.ndarray):
            return frame

        # Ensure float64 for processing
        frame = frame.astype(np.float64, copy=False)
        # Store original dtype for output
        out_dtype = frame.dtype

        # Stage 1: High-pass filter
        frame, self._hp_z = _biquad(frame, self._hp_b, self._hp_a, self._hp_z)

        # Calibration — only accumulate during likely silence (RMS < 10% of max)
        if self._calibrating:
            if raw_rms <= 0.0 or raw_rms < 0.03:  # silence gate: skip frames with speech
                self._calib_accum.append(frame.copy())
            if len(self._calib_accum) >= self._calib_target:
                self._finish_calibration()
                self._calibrating = False
            return frame.astype(out_dtype)

        # Stage 2: Spectral subtraction
        if self.noise_profile is not None:
            frame = _spectral_subtract(frame, self.noise_profile)

        # Stage 3: Soft clip
        frame = np.clip(frame, -0.95, 0.95)

        return frame.astype(out_dtype)

    def _finish_calibration(self):
        """Compute average noise spectrum from accumulated frames."""
        n_fft = 512
        profile = np.zeros(n_fft // 2 + 1)
        for f in self._calib_accum:
            spec = np.abs(np.fft.rfft(f, n=n_fft))
            profile += spec
        profile /= len(self._calib_accum)
        self.noise_profile = profile
        self._calib_accum = []
        print(f"[NoiseFilter] Calibrated: noise profile rms_mag={np.sqrt(np.mean(profile**2)):.6f}")

    def maybe_update_profile(self, frame, is_silence=False, now=0):
        """Update noise profile via EMA if in silence state.
        Args:
            frame: current audio frame
            is_silence: True if current frame is below speech threshold
            now: current time.time() value
        """
        if not self.calibrated:
            return
        if not is_silence:
            self._last_update = now
            return
        if now - self._last_update < 2.0:  # need 2s of silence first
            return
        # Exponential moving average update every ~30s
        if now - self._last_update >= 30.0:
            spec = np.abs(np.fft.rfft(frame.astype(np.float64), n=512))
            self.noise_profile = 0.9 * self.noise_profile + 0.1 * spec
            self._last_update = now


def _biquad(signal, b, a, z):
    """Apply biquad IIR filter with direct form II transposed.
    b: numerator coefficients (len 3)
    a: denominator coefficients (len 3, a[0]=1)
    z: filter state (len 2)
    Returns: filtered signal, updated state
    """
    y = np.zeros_like(signal)
    b0, b1, b2 = b[0], b[1], b[2]
    a1, a2 = a[1], a[2]
    z1, z2 = z[0], z[1]
    for i in range(len(signal)):
        x = signal[i]
        y[i] = b0 * x + z1
        z1 = b1 * x - a1 * y[i] + z2
        z2 = b2 * x - a2 * y[i]
    return y, np.array([z1, z2])


def _spectral_subtract(frame, noise_profile, oversubtract=1.2):
    """Subtract noise spectrum from frame using magnitude spectral subtraction."""
    n_fft = 512
    # FFT
    spec = np.fft.rfft(frame, n=n_fft)
    phase = np.angle(spec)
    mag = np.abs(spec)
    # Subtract
    clean_mag = np.maximum(0.0, mag - noise_profile * oversubtract)
    # Reconstruct
    clean_spec = clean_mag * np.exp(1j * phase)
    clean = np.fft.irfft(clean_spec, n=n_fft)
    # Trim to original frame size
    return clean[:len(frame)]
