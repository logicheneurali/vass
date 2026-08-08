import numpy as np
from faster_whisper import WhisperModel
import threading
from activity_tracker import get_tracker

_NEGATIVE_PROMPT = {
    "it": "musica, televisione, radio, rumore, traffico, vento, pioggia",
    "en": "music, television, radio, noise, traffic, wind, rain",
    "de": "Musik, Fernsehen, Radio, Larm, Verkehr, Wind, Regen",
    "fr": "musique, television, radio, bruit, circulation, vent, pluie",
    "es": "musica, television, radio, ruido, trafico, viento, lluvia",
    "pt": "musica, televisao, radio, barulho, transito, vento, chuva",
    "ja": "音楽、テレビ、ラジオ、騒音、交通、風、雨",
    "ko": "음악, TV, 라디오, 소음, 교통, 바람, 비",
    "zh": "音乐, 电视, 广播, 噪音, 交通, 风, 雨",
}

_IGNORE_WORD = {
    "it": "Ignora", "en": "Ignore", "de": "Ignorieren",
    "fr": "Ignorer", "es": "Ignorar", "pt": "Ignorar",
    "ja": "無視", "ko": "무시", "zh": "忽略",
}


def _cuda_available():
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


class VoiceRecognition:
    def __init__(self, wake_word="vass", transcription_model="medium", sensitivity=0.010,
                 whisper_language="it", wake_prompt="vass", transcribe_prompt=None,
                 wake_variants=None):
        self.wake_word = wake_word.lower()
        self.transcription_model = transcription_model
        self.whisper_language = whisper_language
        self.wake_prompt = wake_prompt
        self.transcribe_prompt = transcribe_prompt
        self.wake_variants = wake_variants or [self.wake_word]
        self.wakeword_model = None
        self.whisper_model = None

        # VAD (Voice Activity Detection) state
        self.energy_threshold = sensitivity
        self._input_volume = 1.0
        self._auto_gain_enabled = True
        self.debug_enabled = False
        self.speech_buffer = []
        self.is_speaking = False
        self.silence_timeout = 15
        self.silence_counter = 0
        self.max_speech_chunks = 120

        # Adaptive noise floor and microphone adaptation
        self._noise_floor = 0.0
        self._noise_buffer = []
        self._noise_frames = 0
        self._auto_calibrated = False

        self._energy_history = []          # RMS energies
        self._peak_history = []            # peak absolute sample values
        self._history_maxlen = 500         # 10 seconds at 50 fps
        self._clip_history = []            # boolean clipping flags
        self._clip_history_maxlen = 500
        self._clip_cooldown = 0            # frames before another clipping reduction

        self._gain_min = 0.15
        self._gain_max = 1.0
        self._target_noise_rms = 0.015

        self._lock = threading.Lock()

    @property
    def noise_floor(self):
        return self._noise_floor

    @property
    def input_volume(self):
        return self._input_volume

    @input_volume.setter
    def input_volume(self, value):
        self._input_volume = float(value)
        # Max volume (1.0) enables continuous automatic gain regulation;
        # any lower value is treated as a fixed manual gain override.
        self._auto_gain_enabled = self._input_volume >= 0.999

    @property
    def _effective_threshold(self):
        multiplier = min(3.0, max(1.5, 1.0 + self._noise_floor * 200))
        return self._noise_floor * multiplier + max(0.001, self.energy_threshold)

    def load_models(self):
        self.wakeword_model = WhisperModel("tiny", device="cpu", compute_type="int8")
        transcribe_device = "cpu"
        #transcribe_device = "cuda" if _cuda_available() else "cpu"
        transcribe_type = "float16" if transcribe_device == "cuda" else "int8"
        print(f"[Whisper] Transcription device={transcribe_device} compute_type={transcribe_type}")
        self.whisper_model = WhisperModel(self.transcription_model, device=transcribe_device, compute_type=transcribe_type)

    def _update_statistics(self, energy, audio_chunk):
        self._energy_history.append(float(energy))
        if len(self._energy_history) > self._history_maxlen:
            self._energy_history.pop(0)

        peak = float(np.max(np.abs(audio_chunk))) if len(audio_chunk) else 0.0
        self._peak_history.append(peak)
        if len(self._peak_history) > self._history_maxlen:
            self._peak_history.pop(0)

        clipped = peak >= 0.95
        self._clip_history.append(clipped)
        if len(self._clip_history) > self._clip_history_maxlen:
            self._clip_history.pop(0)

        self._handle_clipping()
        self._adapt_input_volume()

    def _update_noise_floor(self):
        if len(self._energy_history) < 50:
            return
        # 30th percentile tracks ambient noise without being biased by loud speech bursts
        self._noise_floor = float(np.percentile(self._energy_history[-self._history_maxlen:], 30))

    def _adapt_input_volume(self):
        if not self._auto_gain_enabled or len(self._energy_history) < 100:
            return
        # Use a low percentile so speech bursts do not dominate the ambient estimate
        ambient = float(np.percentile(self._energy_history[-self._history_maxlen:], 30))
        if ambient <= 1e-6:
            return
        # Dynamic target: track the measured ambient with smoothing so the
        # gain converges instead of spiralling down to the absolute floor.
        target = self._target_noise_rms
        smoothed = target * 0.99 + ambient * 0.01
        self._target_noise_rms = max(0.008, min(0.05, smoothed))
        ratio = self._target_noise_rms / ambient
        # Smooth adaptation: move only 5% toward target per call (~every second)
        new_volume = self._input_volume * (1.0 + 0.05 * (ratio - 1.0))
        new_volume = max(self._gain_min, min(self._gain_max, new_volume))
        if abs(new_volume - self._input_volume) > 0.001:
            self._input_volume = new_volume

    def _handle_clipping(self):
        if not self._auto_gain_enabled:
            return
        if self._clip_cooldown > 0:
            self._clip_cooldown -= 1
            return
        if len(self._clip_history) < 100:
            return
        clip_ratio = sum(self._clip_history[-100:]) / 100.0
        if clip_ratio > 0.05:  # more than 5% clipped frames in last 2 seconds
            # Stronger reduction for severe clipping, converges faster
            reduction = max(0.5, min(0.8, 1.0 - clip_ratio))
            new_volume = self._input_volume * reduction
            new_volume = max(self._gain_min, new_volume)
            if new_volume < self._input_volume:
                self._input_volume = new_volume
                self._clip_cooldown = 10  # wait ~0.2s before next reduction
                if self.debug_enabled:
                    print(f"[Audio] Clipping detected ({clip_ratio:.1%}), reducing gain to {self._input_volume:.3f}")

    def detect_wake_word(self, audio_chunk, raw_energy=None):
        if isinstance(audio_chunk, bytes):
            audio_chunk = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0
        if self._input_volume != 1.0:
            audio_chunk = audio_chunk * self._input_volume

        if raw_energy is None:
            raw_energy = np.sqrt(np.mean(audio_chunk**2))
        else:
            # raw_energy is measured PRE-volume (from the raw audio loop);
            # scale it so the adaptive gain sees post-volume energy.
            raw_energy = raw_energy * self._input_volume
        energy = raw_energy

        with self._lock:
            self._update_statistics(raw_energy, audio_chunk)
            self._update_noise_floor()

            if self._noise_floor == 0.0:
                return False

            if raw_energy > self._noise_floor * 1.3:
                energy = raw_energy
            else:
                energy = max(0.0, raw_energy - self._noise_floor)

            if energy > self._effective_threshold:
                self.is_speaking = True
                self.silence_counter = 0
                if len(self.speech_buffer) < self.max_speech_chunks:
                    self.speech_buffer.append(audio_chunk)
            else:
                self.silence_counter += 1
                if self.is_speaking and self.silence_counter > self.silence_timeout:
                    result = self._process_speech_segment()
                    self.speech_buffer = []
                    self.is_speaking = False
                    self.silence_counter = 0
                    return result
                elif self.is_speaking:
                    if len(self.speech_buffer) < self.max_speech_chunks:
                        self.speech_buffer.append(audio_chunk)

        return False

    def _process_speech_segment(self):
        if len(self.speech_buffer) == 0:
            return False

        audio_data = np.concatenate(self.speech_buffer)

        dur_ms = len(audio_data) / 16.0
        energy = float(np.sqrt(np.mean(audio_data ** 2)))
        peak = float(np.max(np.abs(audio_data)))
        if self.debug_enabled:
            print(f"[WakeWord Debug] samples={len(audio_data)} dur={dur_ms:.0f}ms energy={energy:.6f} peak={peak:.4f}")

        try:
            segments, _ = self.wakeword_model.transcribe(
                audio_data,
                language=self.whisper_language,
                beam_size=1,
                temperature=0.0,
                best_of=1,
                initial_prompt=self.wake_prompt,
                condition_on_previous_text=False,
                vad_filter=True,
                no_speech_threshold=0.6,
                log_prob_threshold=-1.0,
                compression_ratio_threshold=2.4,
            )
            text = " ".join([seg.text for seg in segments]).lower().strip()
            if self.debug_enabled:
                print(f"[WakeWord Check] Transcribed: '{text[:40]}'")
            return any(v in text for v in self.wake_variants)
        except Exception as e:
            print(f"[WakeWord Error] {e}")
            return False

    def reset_model(self):
        with self._lock:
            self.speech_buffer = []
            self.is_speaking = False
            self.silence_counter = 0

    def reset_noise_floor(self):
        with self._lock:
            self._noise_floor = 0.0
            self._noise_buffer = []
            self._noise_frames = 0
            self._auto_calibrated = False
            self._energy_history.clear()
            self._peak_history.clear()
            self._clip_history.clear()
            self._clip_cooldown = 0

    def transcribe_audio(self, audio_data, sample_rate=16000):
        if self._input_volume != 1.0:
            audio_data = audio_data * self._input_volume
        max_val = np.max(np.abs(audio_data))
        if max_val > 0:
            audio_data = audio_data * (0.5 / max_val)
            audio_data = np.clip(audio_data, -1.0, 1.0)

        tracker = get_tracker(); tracker.start("Transcription", "stt")
        segments, info = self.whisper_model.transcribe(
            audio_data,
            language=self.whisper_language,
            beam_size=5,
            initial_prompt=self.transcribe_prompt,
            no_speech_threshold=0.6,
            log_prob_threshold=-1.0,
            compression_ratio_threshold=2.4,
        )
        tracker.end("Transcription")
        transcription = " ".join([segment.text for segment in segments])
        return transcription.strip()
