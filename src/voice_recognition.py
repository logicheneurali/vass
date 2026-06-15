import numpy as np
from faster_whisper import WhisperModel
import threading

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
    def __init__(self, wake_word="vass", transcription_model="medium", sensitivity=0.005,
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
        self.speech_buffer = []
        self.is_speaking = False
        self.silence_timeout = 15
        self.silence_counter = 0
        self.max_speech_chunks = 120

        # Adaptive noise floor
        self._noise_floor = 0.0
        self._noise_buffer = []
        self._noise_frames = 0

        self._lock = threading.Lock()

    def load_models(self):
        self.wakeword_model = WhisperModel("tiny", device="cpu", compute_type="int8")
        transcribe_device = "cuda" if _cuda_available() else "cpu"
        transcribe_type = "float16" if transcribe_device == "cuda" else "int8"
        print(f"[Whisper] Transcription device={transcribe_device} compute_type={transcribe_type}")
        self.whisper_model = WhisperModel(self.transcription_model, device=transcribe_device, compute_type=transcribe_type)

    def detect_wake_word(self, audio_chunk):
        if isinstance(audio_chunk, bytes):
            audio_chunk = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0
            
        energy = np.sqrt(np.mean(audio_chunk**2))
        
        with self._lock:
            threshold = self.energy_threshold
            if self._noise_floor > 0:
                threshold = max(threshold, self._noise_floor * 3.0)
            if energy > threshold:
                self.is_speaking = True
                self.silence_counter = 0
                if len(self.speech_buffer) < self.max_speech_chunks:
                    self.speech_buffer.append(audio_chunk)
            else:
                self.silence_counter += 1
                if not self.is_speaking:
                    self._noise_buffer.append(energy)
                    self._noise_frames += 1
                    if self._noise_frames >= 100:
                        avg = sum(self._noise_buffer) / len(self._noise_buffer)
                        if self._noise_floor == 0.0:
                            self._noise_floor = avg
                            print(f"[NoiseFloor] Initial: {self._noise_floor:.6f}")
                        else:
                            self._noise_floor = 0.9 * self._noise_floor + 0.1 * avg
                        self._noise_buffer = []
                        self._noise_frames = 0
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
        print(f"[WakeWord Debug] samples={len(audio_data)} dur={dur_ms:.0f}ms energy={energy:.6f} peak={peak:.4f}")

        try:
            negative = _NEGATIVE_PROMPT.get(self.whisper_language, _NEGATIVE_PROMPT["en"])
            ignore = _IGNORE_WORD.get(self.whisper_language, "Ignore")
            prompt = f"{self.wake_prompt}. {ignore}: {negative}"
            segments, _ = self.wakeword_model.transcribe(
                audio_data,
                language=self.whisper_language,
                beam_size=1,
                word_timestamps=False,
                initial_prompt=prompt,
                condition_on_previous_text=False,
                no_speech_threshold=0.5,
                compression_ratio_threshold=None,
            )
            text = " ".join([seg.text for seg in segments]).lower().strip()
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

    def transcribe_audio(self, audio_data, sample_rate=16000):
        max_val = np.max(np.abs(audio_data))
        if max_val > 0:
            audio_data = audio_data * (0.5 / max_val)
            audio_data = np.clip(audio_data, -1.0, 1.0)
            
        # Use large model for accurate command transcription
        segments, info = self.whisper_model.transcribe(
            audio_data,
            language=self.whisper_language,
            beam_size=5,
            initial_prompt=self.transcribe_prompt
        )
        transcription = " ".join([segment.text for segment in segments])
        return transcription.strip()
