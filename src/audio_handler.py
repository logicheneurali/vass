import numpy as np
import os
import queue
import time
import sounddevice as sd


class SileroVAD:
    """Silero VAD via onnxruntime. Buffers arbitrary chunk sizes into 512-sample
    frames (32ms at 16kHz) for the ONNX model. Maintains internal context and
    hidden state for streaming frame-by-frame processing."""

    def __init__(self, model_path, sample_rate=16000, threshold=0.5):
        if sample_rate not in (8000, 16000):
            raise ValueError("sample_rate must be 8000 or 16000")
        self.sr = sample_rate
        self.frame_size = 512 if sample_rate == 16000 else 256
        self.context_size = 64 if sample_rate == 16000 else 32
        self.threshold = threshold
        self._buffer = np.zeros(0, dtype=np.float32)
        self._context = np.zeros(self.context_size, dtype=np.float32)
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._last_prob = 0.0

        import onnxruntime
        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self.session = onnxruntime.InferenceSession(
            model_path, providers=["CPUExecutionProvider"], sess_options=opts)

    def reset(self):
        self._buffer = np.zeros(0, dtype=np.float32)
        self._context = np.zeros(self.context_size, dtype=np.float32).ravel()
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._last_prob = 0.0

    def process(self, audio_chunk):
        audio = np.atleast_1d(np.asarray(audio_chunk, dtype=np.float32)).ravel()
        if self._buffer.ndim != 1:
            self._buffer = self._buffer.ravel()
        self._buffer = np.concatenate([self._buffer, audio])
        while len(self._buffer) >= self.frame_size:
            frame = self._buffer[:self.frame_size]
            self._buffer = self._buffer[self.frame_size:]
            x = np.concatenate([self._context, frame]).reshape(1, -1).astype(np.float32)
            ort_inputs = {
                "input": x,
                "state": np.atleast_3d(self._state),
                "sr": np.array(self.sr, dtype=np.int64),
            }
            out, self._state = self.session.run(None, ort_inputs)
            self._context = x[:, -self.context_size:].ravel()
            self._last_prob = float(out.squeeze())
        return self._last_prob

    def is_speech(self, audio_chunk):
        return self.process(audio_chunk) >= self.threshold


def _resolve_vad_model():
    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tts", "silero_vad.onnx"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "silero_vad.onnx"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    import urllib.request
    target = candidates[0]
    os.makedirs(os.path.dirname(target), exist_ok=True)
    url = "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
    urllib.request.urlretrieve(url, target)
    return target


class AudioHandler:
    def __init__(self, sample_rate=16000, channels=1, frame_duration_ms=20, input_device=-1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.input_device = None if input_device < 0 else input_device
        self.frame_size = int(sample_rate * frame_duration_ms / 1000)
        model_path = _resolve_vad_model()
        self.vad = SileroVAD(model_path, sample_rate=sample_rate, threshold=0.5)
        self.audio_queue = queue.Queue(maxsize=500)
        self.is_recording = False
        self.silence_threshold = 3.0
        self.silence_start = None
        self.stream = None
        self.recorded_buffer = []

    def audio_callback(self, indata, frames, time_info, status):
        if status and "overflow" not in str(status):
            print(f"Audio callback status: {status}")
        audio_data = indata.copy().flatten()
        try:
            self.audio_queue.put_nowait(audio_data)
        except queue.Full:
            pass

    def start_stream(self):
        if self.stream is not None:
            return
        print(f"[Audio] Starting stream: device={self.input_device}, sr={self.sample_rate}, ch={self.channels}")
        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                callback=self.audio_callback,
                blocksize=self.frame_size,
                latency="high",
                device=self.input_device,
            )
            self.stream.start()
            print(f"[Audio] Stream started OK")
        except Exception as e:
            print(f"[Audio] Stream start FAILED: {e}")
            self.stream = None

    def stop_stream(self):
        if hasattr(self, "stream") and self.stream:
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
        self.vad.reset()
        self._vad_debug_cnt = 0

    def stop_recording(self):
        self.is_recording = False

    def process_recording(self, audio_data, vad_frame=None):
        if self.is_recording:
            self.recorded_buffer.append(audio_data)
            if self._detect_silence(vad_frame if vad_frame is not None else audio_data):
                if self.silence_start is None:
                    self.silence_start = time.time()
                elif (time.time() - self.silence_start) >= self.silence_threshold:
                    self.stop_recording()
            else:
                self.silence_start = None

    def _detect_silence(self, audio_data):
        try:
            prob = self.vad.process(audio_data)
            speech = prob >= self.vad.threshold
            self._vad_debug_cnt += 1
            if self._vad_debug_cnt <= 10 or self._vad_debug_cnt % 50 == 0:
                buf = len(self.vad._buffer)
                print(f"[VAD] frame={self._vad_debug_cnt} prob={prob:.4f} speech={speech} buf={buf}")
            return not speech
        except Exception as e:
            print(f"[VAD] ERROR frame={getattr(self,'_vad_debug_cnt',0)}: {e}")
            return True

    def get_recorded_audio(self):
        if not self.recorded_buffer:
            return np.array([])
        return np.concatenate(self.recorded_buffer)
