import os
import sys
import time
import threading
import subprocess
import numpy as np
from collections import deque

_KOKORO_LANGS = {
    "it": ("i", "if_sara"),
    "en": ("a", "af_heart"),
    "de": ("a", "af_heart"),   # German not supported by Kokoro, fallback to English
    "fr": ("f", "ff_siwis"),
    "es": ("e", "ef_dora"),
    "pt": ("p", "pf_dora"),
    "ja": ("j", "jf_alpha"),
    "ko": ("a", "af_heart"),   # Korean not supported by Kokoro, fallback to English
    "zh": ("z", "zf_xiaobei"),
}


class TtsEngine:
    def __init__(self, gui, state_getter, state_setter, tts_volume, language="en", output_device=-1):
        self.gui = gui
        self._get_state = state_getter
        self._set_state = state_setter
        self.tts_volume = tts_volume
        self.language = language
        self.output_device = None if output_device < 0 else output_device

        self.tts_playing = False
        self.tts_busy = threading.Lock()
        self._kokoro_pipeline = None
        self._kokoro_code = None
        self._kokoro_voice = None
        self._tts_data = None
        self._tts_sr = None
        self._tts_play_start = 0.0
        self._tts_wav_path = ""
        self._tts_done = threading.Event()
        self._state_before_tts = "listening"

        self._speak_queue = deque()
        self._speak_lock = threading.Lock()
        self._speaker_running = True
        self._sd_abort = threading.Event()
        self._wav_to_clean = ""
        threading.Thread(target=self._speak_worker, daemon=True).start()
        self._cleanup_orphan_wavs()

    def speak(self, text, speed=1.0):
        self._speak_kokoro(text, speed)

    def speak_nowait(self, text, speed=1.0):
        self._speak_kokoro(text, speed)

    def enqueue(self, text, speed=1.0, on_done=None):
        with self._speak_lock:
            self._speak_queue.append((text, speed, on_done))
        print(f"[TTS] Enqueued: {text[:60]}")

    def _speak_worker(self):
        while self._speaker_running:
            if self._get_state() in ("waiting", "waiting_resources", "recording", "playing"):
                time.sleep(0.1)
                continue
            with self._speak_lock:
                if not self._speak_queue:
                    item = None
                else:
                    item = self._speak_queue.popleft()
            if item:
                text, speed, on_done = item
                print(f"[TTS] Worker speaking: {text[:60]}")
                self.tts_busy.acquire()
                try:
                    self._tts_done.clear()
                    self._speak_kokoro(text, speed)
                    duration = len(getattr(self, '_tts_data', [])) / max(getattr(self, '_tts_sr', 24000) or 24000, 1)
                    timeout = max(60, duration * 1.5 + 5)
                    if not self._tts_done.wait(timeout=timeout):
                        print(f"[TTS] WARNING: _tts_done timeout after {timeout:.0f}s, forcing")
                        self._tts_done.set()
                    if on_done:
                        try:
                            on_done()
                        except Exception as e:
                            print(f"[TTS] on_done callback error: {e}")
                except Exception as e:
                    print(f"[TTS] Worker error: {e}")
                    self._tts_done.set()
                finally:
                    self.tts_busy.release()
            else:
                time.sleep(0.1)

    def _init_kokoro(self):
        lang_code, voice = _KOKORO_LANGS.get(self.language, ("a", "af_heart"))
        self._kokoro_code = lang_code
        self._kokoro_voice = voice

    def preload(self):
        def _load():
            try:
                self._init_kokoro()
                print(f"[TTS] Preloading Kokoro pipeline (lang={self._kokoro_code}, voice={self._kokoro_voice})...")
                from kokoro import KPipeline
                self._kokoro_pipeline = KPipeline(lang_code=self._kokoro_code)
                print("[TTS] Kokoro pipeline ready")
            except ImportError as e:
                print(f"[TTS] Kokoro preload failed (missing dependency): {e}")
                self._kokoro_code = None  # Force fallback on speak
            except Exception as e:
                print(f"[TTS] Kokoro preload failed: {e}")
        threading.Thread(target=_load, daemon=True).start()

    def _save_state_and_set_playing(self):
        self._state_before_tts = self._get_state()
        self.tts_playing = True
        self._set_state("playing")
        print(f"[TTS] Playback started (prev_state={self._state_before_tts})")

    def _play_wav(self, wav_path, speed=1.0):
        self._tts_done.clear()
        self._sd_abort.clear()
        self._wav_to_clean = wav_path
        import sounddevice as sd
        import soundfile as sf
        data, sr = sf.read(wav_path)
        self._tts_data, self._tts_sr = data, sr
        peak = np.max(np.abs(self._tts_data))
        if peak > 0:
            self._tts_data = self._tts_data * (self.tts_volume / peak)
        self._tts_play_start = time.time()
        self._sd_pos = 0

        def _cb(outdata, frames, _time, _status):
            if self._sd_abort.is_set():
                raise sd.CallbackAbort()
            if self._tts_data is None:
                raise sd.CallbackStop()
            n = min(len(self._tts_data) - self._sd_pos, frames)
            outdata[:n, 0] = self._tts_data[self._sd_pos:self._sd_pos + n]
            self._sd_pos += n
            if n < frames:
                outdata[n:, 0] = 0
                raise sd.CallbackStop()

        try:
            self._sd_stream = sd.OutputStream(
                samplerate=self._tts_sr, device=self.output_device,
                channels=1, callback=_cb, finished_callback=self._on_stream_finished)
            self._sd_stream.start()
        except Exception as e:
            print(f"[TTS] OutputStream error: {e}")
            self._tts_done.set()
            return

        if self.gui:
            self.gui.volume_top_bar.set_volume(self.tts_volume)
        self.gui.start_tts_playback(
            data=self._tts_data,
            samplerate=self._tts_sr,
            total_samples=len(self._tts_data),
            on_complete=self._on_tts_done
        )

    def _on_stream_finished(self):
        self._cleanup_wav()
        if self.gui:
            self.gui.schedule(0, self._on_tts_done)

    def _cleanup_wav(self):
        path = getattr(self, '_wav_to_clean', '')
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
        self._wav_to_clean = ''

    @staticmethod
    def _cleanup_orphan_wavs():
        import glob
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for f in glob.glob(os.path.join(root, "tts_output_*.wav")):
            try:
                os.remove(f)
            except OSError:
                pass

    def _speak_kokoro(self, text, speed=1.0):
        if not text or not text.strip():
            return
        self._save_state_and_set_playing()
        try:
            import torch
            import soundfile as sf
            import uuid
            if self._kokoro_code is None:
                self._init_kokoro()
            if self._kokoro_code is None:
                raise ImportError("Kokoro not available for this language")
            if self._kokoro_pipeline is None or self._kokoro_pipeline.lang_code != self._kokoro_code:
                from kokoro import KPipeline
                print(f"[TTS] Loading Kokoro pipeline (lang={self._kokoro_code}, voice={self._kokoro_voice})...")
                self._kokoro_pipeline = KPipeline(lang_code=self._kokoro_code)
            self._tts_wav_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), f"tts_output_{uuid.uuid4().hex[:8]}.wav")
            wav_path = self._tts_wav_path
            words = text.split()
            since_punct = 0
            for i, w in enumerate(words):
                since_punct += 1
                if any(p in w for p in ('.', '!', '?')):
                    since_punct = 0
                elif since_punct >= 30:
                    words[i] += "\n"
                    since_punct = 0
            text = " ".join(words)
            generator = self._kokoro_pipeline(text, voice=self._kokoro_voice, speed=speed,
                                               split_pattern=r'(?<=[.!?])\s+|\n+')
            all_audio = []
            for gs, ps, audio in generator:
                all_audio.append(audio)
            if all_audio:
                audio = torch.cat(all_audio).numpy()
                sf.write(wav_path, audio, 24000)
                dur = len(audio) / 24000
                print(f"[TTS] Kokoro WAV: {len(all_audio)} chunks, {dur:.1f}s")
            else:
                raise RuntimeError("Kokoro generated no audio")
        except Exception as e:
            print(f"[TTS] Kokoro ({self.language}) failed: {e}")
            # Chain: Kokoro(lang) -> Windows default -> Kokoro(en) -> Windows(en)
            if not self._speak_windows_default(text):
                print(f"[TTS] Windows default TTS failed. Trying Kokoro English...")
                if not self._speak_kokoro_internal(text, speed, "a", "af_heart"):
                    print(f"[TTS] Kokoro English failed. Trying Windows English...")
                    self._speak_windows_tts(text, "en")
            self._on_tts_done()
            return
        self._play_wav(wav_path, speed)

    def _speak_kokoro_internal(self, text, speed, lang_code, voice):
        import torch
        import soundfile as sf
        import uuid
        try:
            from kokoro import KPipeline
            pipeline = KPipeline(lang_code=lang_code)
            wav_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), f"tts_output_{uuid.uuid4().hex[:8]}.wav")
            generator = pipeline(text, voice=voice, speed=speed,
                                  split_pattern=r'(?<=[.!?])\s+|\n+')
            all_audio = []
            for gs, ps, audio in generator:
                all_audio.append(audio)
            if all_audio:
                audio = torch.cat(all_audio).numpy()
                sf.write(wav_path, audio, 24000)
                dur = len(audio) / 24000
                print(f"[TTS] Kokoro ({lang_code}) WAV: {len(all_audio)} chunks, {dur:.1f}s")
                self._play_wav(wav_path, speed)
                return True
        except Exception as e:
            print(f"[TTS] Kokoro ({lang_code}) failed: {e}")
        return False

    def _speak_windows_default(self, text):
        if sys.platform != "win32":
            return False
        import base64
        try:
            encoded = base64.b64encode(text.encode("utf-16-le")).decode("ascii")
            subprocess.run(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-EncodedCommand",
                 f"Add-Type -AssemblyName System.Speech; "
                 f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                 f"$s.Speak([System.Text.Encoding]::Unicode.GetString([System.Convert]::FromBase64String('{encoded}')))"],
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            print(f"[TTS] Windows TTS default spoke")
            return True
        except Exception as e:
            print(f"[TTS] Windows TTS default failed: {e}")
            return False

    def _speak_windows_tts(self, text, lang):
        if sys.platform != "win32":
            return False
        import base64

        _SAPI_LANGS = {
            "it": "it-IT", "en": "en-US", "de": "de-DE", "fr": "fr-FR",
            "es": "es-ES", "pt": "pt-BR", "ja": "ja-JP", "ko": "ko-KR",
            "zh": "zh-CN",
        }
        culture = _SAPI_LANGS.get(lang, "en-US")
        try:
            encoded = base64.b64encode(text.encode("utf-16-le")).decode("ascii")
            subprocess.run(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-EncodedCommand",
                 f"Add-Type -AssemblyName System.Speech; "
                 f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                 f"try {{ $s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::NotSet, [System.Speech.Synthesis.VoiceAge]::NotSet, 0, [System.Globalization.CultureInfo]'{culture}') }} catch {{ }}; "
                 f"$s.Speak([System.Text.Encoding]::Unicode.GetString([System.Convert]::FromBase64String('{encoded}')))"],
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            print(f"[TTS] Windows TTS spoke ({culture})")
            return True
        except Exception as e:
            print(f"[TTS] Windows TTS failed: {e}")
            return False

    def stop(self):
        self._speaker_running = False
        with self._speak_lock:
            self._speak_queue.clear()
        self._sd_abort.set()
        if hasattr(self, '_sd_stream') and getattr(self, '_sd_stream', None):
            try:
                self._sd_stream.abort()
            except Exception:
                pass
        self._cleanup_wav()
        self._on_tts_done()

    def get_position(self):
        if not self._tts_play_start or not self.tts_playing:
            return 0
        elapsed = time.time() - self._tts_play_start
        return max(0, int(elapsed * self._tts_sr))

    def update_settings(self, tts_volume):
        self.tts_volume = tts_volume

    def _on_tts_done(self):
        if not self.tts_playing:
            return
        self.tts_playing = False
        prev = self._state_before_tts
        self._set_state(prev)
        print(f"[TTS] Playback ended, restored state to {prev}")
        self._tts_done.set()
        self.gui.stop_tts_playback()
        self._tts_data = None
        self._tts_sr = None
        self._cleanup_wav()
        if self._tts_wav_path and os.path.exists(self._tts_wav_path):
            try:
                os.remove(self._tts_wav_path)
            except OSError:
                pass
