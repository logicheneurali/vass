"""Real-time noise cancellation for VASS.
MCRA noise estimation + Decision-Directed Wiener filter.
Handles non-stationary ambient noise (outdoor, traffic, wind).
Pure numpy, no external dependencies.
"""
import numpy as np


class NoiseFilter:
    def __init__(self, sample_rate=16000, frame_size=320):
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self._enabled = True

        # Biquad high-pass 80Hz @ 16000Hz (Butterworth 2nd order)
        self._hp_b = np.array([0.96508099, -1.93016197, 0.96508099])
        self._hp_a = np.array([1.0, -1.92935037, 0.93148062])
        self._hp_z = np.zeros((2,))

        # MCRA noise estimation state
        self._noise = None
        self._smooth = None
        self._min_buf = None
        self._min_pos = 0
        self._frame_count = 0

        # Wiener filter state (Decision-Directed approach)
        self._prev_gamma = None
        self._prev_gain = None

        # Parameters
        self._alpha_s = 0.7          # periodogram smoothing
        self._alpha_d = 0.95         # noise update slow factor
        self._delta = 2.0            # VAD threshold
        self._beta = 0.01            # min speech presence probability
        self._alpha_snr = 0.98       # a priori SNR smoothing
        self._n_fft = 512
        self._min_window = 100       # ~2 seconds minima tracking

        # Per-band suppression floor (replaces spectral floor + oversubtract)
        freqs = np.fft.rfftfreq(self._n_fft, 1.0 / sample_rate)
        self._floor = np.where(
            freqs < 300, 0.04,
            np.where(freqs > 4000, 0.06, 0.10)
        )

    @property
    def calibrated(self):
        return self._min_buf is not None and self._frame_count >= self._min_window

    def reset_calibration(self):
        self._noise = None
        self._smooth = None
        self._min_buf = None
        self._min_pos = 0
        self._frame_count = 0
        self._prev_gamma = None
        self._prev_gain = None
        self._hp_z = np.zeros((2,))

    def process(self, frame, raw_rms=0.0):
        if not self._enabled or not isinstance(frame, np.ndarray):
            return frame

        frame = np.asarray(frame, dtype=np.float64)

        # Stage 1: High-pass filter
        frame, self._hp_z = _biquad(frame, self._hp_b, self._hp_a, self._hp_z)

        # Stage 2: MCRA + Wiener filter
        clean = self._filter_frame(frame)
        return clean if clean is not None else frame.astype(np.float32)

    def _filter_frame(self, frame):
        n = self._n_fft
        spec = np.fft.rfft(frame, n=n)
        mag = np.abs(spec)
        phase = np.angle(spec)
        mag2 = mag * mag
        eps = 1e-12

        # Initialize on first frame
        if self._smooth is None:
            self._smooth = mag.copy()
            self._noise = mag.copy()
            self._min_buf = np.tile(mag.copy(), (self._min_window, 1))
            self._min_pos = 1
            self._prev_gamma = np.ones_like(mag)
            self._prev_gain = np.ones_like(mag)
            return None

        self._frame_count += 1

        # MCRA: smoothed periodogram
        self._smooth = self._alpha_s * self._smooth + (1 - self._alpha_s) * mag

        # MCRA: minima tracking via circular buffer
        self._min_buf[self._min_pos] = self._smooth.copy()
        self._min_pos = (self._min_pos + 1) % self._min_window
        min_smooth = np.min(self._min_buf, axis=0)

        # MCRA: speech presence probability
        ratio = self._smooth / (min_smooth + eps)
        p = np.where(ratio > self._delta, self._beta, 1.0)

        # MCRA: adaptive noise estimate
        alpha_d = self._alpha_d * p + (1.0 - p)
        self._noise = alpha_d * self._noise + (1.0 - alpha_d) * mag

        # Decision-Directed Wiener filter
        noise2 = self._noise * self._noise + eps
        gamma = mag2 / noise2

        xi = self._alpha_snr * (self._prev_gamma * self._prev_gain ** 2) \
             + (1 - self._alpha_snr) * np.maximum(0.0, gamma - 1.0)

        gain = xi / (1.0 + xi)
        gain = np.maximum(gain, self._floor)

        self._prev_gamma = gamma
        self._prev_gain = gain

        # Apply gain and reconstruct
        clean_mag = gain * mag
        clean_spec = clean_mag * np.exp(1j * phase)
        clean = np.fft.irfft(clean_spec, n=n)
        clean = clean[:self.frame_size]
        clean = np.clip(clean, -0.95, 0.95)
        return clean.astype(np.float32)

    def maybe_update_profile(self, frame, is_silence=False, now=0):
        pass


def _biquad(signal, b, a, z):
    """Biquad IIR filter, direct form II transposed."""
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
