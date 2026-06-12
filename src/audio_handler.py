import numpy as np
import sounddevice as sd
import webrtcvad
import queue
import time

class AudioHandler:
    def __init__(self, sample_rate=16000, channels=1, frame_duration_ms=20):
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_size = int(sample_rate * frame_duration_ms / 1000)
        self.vad = webrtcvad.Vad(2)
        self.audio_queue = queue.Queue(maxsize=500)  # Increased from 100
        self.is_recording = False
        self.silence_threshold = 3.0
        self.silence_start = None
        self.stream = None
        self.recorded_buffer = []

    def audio_callback(self, indata, frames, time_info, status):
        if status and 'overflow' not in str(status):
            print(f"Audio callback status: {status}")
        audio_data = indata.copy().flatten()
        try:
            self.audio_queue.put_nowait(audio_data)
        except queue.Full:
            pass

    def start_stream(self):
        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            callback=self.audio_callback,
            blocksize=self.frame_size,
            latency='high'  # Use high latency to prevent overflow
        )
        self.stream.start()

    def stop_stream(self):
        if hasattr(self, 'stream') and self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
            
    def get_frame(self):
        try:
            return self.audio_queue.get(timeout=0.1)
        except queue.Empty:
            return None

    def clear_queue(self):
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

    def start_recording(self):
        self.recorded_buffer.clear()
        self.is_recording = True
        self.silence_start = None

    def stop_recording(self):
        self.is_recording = False

    def process_recording(self, audio_data):
        if self.is_recording:
            self.recorded_buffer.append(audio_data)
            if self._detect_silence(audio_data):
                if self.silence_start is None:
                    self.silence_start = time.time()
                elif (time.time() - self.silence_start) >= self.silence_threshold:
                    self.stop_recording()
            else:
                self.silence_start = None

    def _detect_silence(self, audio_data):
        audio_int16 = (audio_data * 32767).astype(np.int16).tobytes()
        frame_bytes = audio_int16[:self.frame_size * 2]
        if len(frame_bytes) < self.frame_size * 2:
            return False
        try:
            is_speech = self.vad.is_speech(frame_bytes, self.sample_rate)
            return not is_speech
        except Exception:
            return False

    def get_recorded_audio(self):
        if not self.recorded_buffer:
            return np.array([])
        return np.concatenate(self.recorded_buffer)