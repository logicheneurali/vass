import os
import sys
import time
import threading
import subprocess
import numpy as np
from collections import deque
from utils import get_project_root, strip_markdown

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
    def __init__(self, gui, state_getter, state_setter, app_volume, language="en", output_device=-1, kokoro_voice=""):
        self.gui = gui
        self._get_state = state_getter
        self._set_state = state_setter
        self._app = getattr(state_setter, "__self__", None)
        self.app_volume = app_volume
        self.language = language
        self.output_device = None if output_device < 0 else output_device
        self._kokoro_voice_override = kokoro_voice

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
        self._stream_gen = 0

        self._speak_queue = deque()
        self._speak_lock = threading.Lock()
        self._deferred_queue = []   # TTS deferred while AI is busy
        self._deferred_lock = threading.Lock()
        self._speaker_running = True
        self._sd_abort = threading.Event()
        self._wav_to_clean = ""
        self._tts_paused = False
        self._tts_pause_pos = 0
        self._gen_seq = 0

        self._audio_queue = deque()
        self._audio_lock = threading.Lock()
        self._audio_ready = threading.Event()

        threading.Thread(target=self._gen_worker, daemon=True).start()
        threading.Thread(target=self._play_worker, daemon=True).start()
        self._cleanup_orphan_wavs()

    def _debug_enabled(self):
        return getattr(self._app, 'debug_enabled', False)

    def _log(self, msg):
        if self._debug_enabled():
            print(f"[TTS-DEBUG] {threading.current_thread().name} | {msg}")

    def speak(self, text, speed=0.9):
        self._speak_kokoro(text, speed)

    def speak_nowait(self, text, speed=0.9):
        self._speak_kokoro(text, speed)

    def enqueue(self, text, speed=0.9, on_done=None, defer_if_busy=False):
        text = strip_markdown(str(text))
        if defer_if_busy and self._get_state() == "waiting":
            with self._deferred_lock:
                self._deferred_queue.append((text, speed, on_done))
            self._log(f"enqueue: DEFERRED (AI busy) text='{text[:60]}' deferred={len(self._deferred_queue)}")
            return
        with self._speak_lock:
            self._speak_queue.append((text, speed, on_done))
            speak_len = len(self._speak_queue)
        self._log(f"enqueue: text='{text[:60]}' speak_queue={speak_len} on_done={on_done is not None}")
        if text:
            print(f"[TTS] Enqueued: {text[:60]}")

    def _flush_deferred(self):
        """Move deferred TTS messages to speak queue when AI is no longer busy."""
        with self._deferred_lock:
            if not self._deferred_queue:
                return
            count = len(self._deferred_queue)
            with self._speak_lock:
                for item in self._deferred_queue:
                    self._speak_queue.append(item)
                speak_len = len(self._speak_queue)
            self._deferred_queue.clear()
        self._log(f"_flush_deferred: moved {count} deferred messages, speak_queue={speak_len}")

    def _gen_worker(self):
        while self._speaker_running:
            with self._speak_lock:
                if self._speak_queue:
                    text, speed, on_done = self._speak_queue.popleft()
                else:
                    text = None
            if text is None:
                time.sleep(0.1)
                continue
            gen = self._gen_seq
            print(f"[TTS] Generating audio: {text[:60]}")
            result = self._generate_kokoro_audio(text, speed)
            if gen != self._gen_seq:
                print(f"[TTS] Discarded stale generation (gen {gen} != {self._gen_seq})")
                if on_done:
                    try:
                        on_done()
                    except Exception as e:
                        print(f"[TTS] stale gen on_done error: {e}")
                continue
            if result is None:
                if on_done:
                    with self._audio_lock:
                        self._audio_queue.append((None, None, on_done))
                    self._audio_ready.set()
                continue
            audio_data, sr = result
            with self._audio_lock:
                self._audio_queue.append((audio_data, sr, on_done))
            self._audio_ready.set()

    def _play_worker(self):
        last_wait_state = None
        while self._speaker_running:
            if self._tts_paused:
                with self._audio_lock:
                    if self._audio_queue:
                        self._tts_paused = False
                    else:
                        time.sleep(0.1)
                        continue
            current_state = self._get_state()
            if current_state in ("recording", "playing"):
                if last_wait_state != current_state:
                    self._log(f"_play_worker: waiting, state={current_state}")
                    last_wait_state = current_state
                time.sleep(0.1)
                continue
            last_wait_state = None
            with self._audio_lock:
                if self._audio_queue:
                    audio_data, sr, on_done = self._audio_queue.popleft()
                    audio_len = len(self._audio_queue)
                else:
                    audio_data = None
                    on_done = None
                    audio_len = 0
            if audio_data is None:
                if on_done:
                    try:
                        on_done()
                    except Exception as e:
                        print(f"[TTS] on_done callback error: {e}")
                else:
                    self._audio_ready.wait(timeout=0.5)
                    self._audio_ready.clear()
                continue
            self._log(f"_play_worker: popped audio, audio_queue_remaining={audio_len} state={current_state}")
            print(f"[TTS] Playing audio")
            duration = len(audio_data) / max(sr or 24000, 1)
            timeout = max(60, duration * 1.5 + 5)
            self._save_state_and_set_playing()
            self._play_audio_data(audio_data, sr)
            if not self._tts_done.wait(timeout=timeout):
                print(f"[TTS] WARNING: Player timeout after {timeout:.0f}s, forcing")
                self._tts_done.set()
            if on_done:
                try:
                    on_done()
                except Exception as e:
                    print(f"[TTS] on_done callback error: {e}")

    def _init_kokoro(self):
        lang_code, voice = _KOKORO_LANGS.get(self.language, ("a", "af_heart"))
        self._kokoro_code = lang_code
        self._kokoro_voice = self._kokoro_voice_override or voice

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
        with self._speak_lock:
            speak_len = len(self._speak_queue)
        with self._audio_lock:
            audio_len = len(self._audio_queue)
        self._log(f"_save_state_and_set_playing: prev_state={self._state_before_tts} "
                  f"tts_playing=True speak_queue={speak_len} audio_queue={audio_len}")
        self._set_state("playing")
        print(f"[TTS] Playback started (prev_state={self._state_before_tts})")

    def _play_wav(self, wav_path, speed=1.0):
        self._log(f"_play_wav: starting path={wav_path} speed={speed}")
        self._tts_done.clear()
        self._sd_abort.clear()
        if hasattr(self, '_sd_stream') and self._sd_stream is not None:
            try:
                self._sd_stream.stop()
            except Exception:
                pass
        self._wav_to_clean = wav_path
        import sounddevice as sd
        import soundfile as sf
        data, sr = sf.read(wav_path)
        self._tts_sr = sr
        peak = np.max(np.abs(data))
        if peak > 0:
            self._tts_data = data / peak
        else:
            self._tts_data = data
        self._tts_play_start = time.time()
        self._sd_pos = 0
        self._stream_gen += 1
        gen = self._stream_gen

        def _cb(outdata, frames, _time, _status):
            if self._sd_abort.is_set():
                raise sd.CallbackAbort()
            if self._tts_data is None:
                raise sd.CallbackStop()
            n = min(len(self._tts_data) - self._sd_pos, frames)
            outdata[:n, 0] = self._tts_data[self._sd_pos:self._sd_pos + n] * self.app_volume
            self._sd_pos += n
            if n < frames:
                outdata[n:, 0] = 0
                raise sd.CallbackStop()

        def _on_finished():
            self._cleanup_wav()
            if gen == self._stream_gen:
                self._on_tts_done()

        try:
            self._sd_stream = sd.OutputStream(
                samplerate=self._tts_sr, device=self.output_device,
                channels=1, callback=_cb, finished_callback=_on_finished)
            self._sd_stream.start()
        except Exception as e:
            print(f"[TTS] OutputStream error: {e}")
            self._tts_done.set()
            return

        if self.gui:
            self.gui.volume_top_bar.set_volume(self.app_volume)
        self.gui.start_tts_playback(
            data=self._tts_data,
            samplerate=self._tts_sr,
            total_samples=len(self._tts_data),
            on_complete=None
        )

    def _play_audio_data(self, audio_data, sample_rate):
        self._log(f"_play_audio_data: starting sample_rate={sample_rate} samples={len(audio_data)}")
        self._tts_done.clear()
        self._sd_abort.clear()
        if hasattr(self, '_sd_stream') and self._sd_stream is not None:
            try:
                self._sd_stream.stop()
            except Exception:
                pass
        self._tts_sr = sample_rate
        peak = np.max(np.abs(audio_data))
        if peak > 0:
            self._tts_data = audio_data / peak
        else:
            self._tts_data = audio_data
        self._tts_play_start = time.time()
        self._sd_pos = 0
        self._stream_gen += 1
        gen = self._stream_gen

        import sounddevice as sd

        def _cb(outdata, frames, _time, _status):
            if self._sd_abort.is_set():
                raise sd.CallbackAbort()
            if self._tts_data is None:
                raise sd.CallbackStop()
            n = min(len(self._tts_data) - self._sd_pos, frames)
            outdata[:n, 0] = self._tts_data[self._sd_pos:self._sd_pos + n] * self.app_volume
            self._sd_pos += n
            if n < frames:
                outdata[n:, 0] = 0
                raise sd.CallbackStop()

        def _on_finished():
            if gen == self._stream_gen:
                self._on_tts_done()

        try:
            self._sd_stream = sd.OutputStream(
                samplerate=sample_rate, device=self.output_device,
                channels=1, callback=_cb, finished_callback=_on_finished)
            self._sd_stream.start()
        except Exception as e:
            print(f"[TTS] OutputStream error: {e}")
            self._tts_done.set()
            return

        if self.gui:
            self.gui.volume_top_bar.set_volume(self.app_volume)
        self.gui.start_tts_playback(
            data=self._tts_data,
            samplerate=sample_rate,
            total_samples=len(self._tts_data),
            on_complete=None
        )

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
        root = get_project_root()
        for f in glob.glob(os.path.join(root, "tts_output_*.wav")):
            try:
                os.remove(f)
            except OSError:
                pass

    def _generate_kokoro_audio(self, text, speed=1.0):
        if not text or not text.strip():
            return None
        try:
            import torch
            if self._kokoro_code is None:
                self._init_kokoro()
            if self._kokoro_code is None:
                return None
            if self._kokoro_pipeline is None or self._kokoro_pipeline.lang_code != self._kokoro_code:
                from kokoro import KPipeline
                print(f"[TTS] Loading Kokoro pipeline (lang={self._kokoro_code}, voice={self._kokoro_voice})...")
                self._kokoro_pipeline = KPipeline(lang_code=self._kokoro_code)
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
                dur = len(audio) / 24000
                print(f"[TTS] Kokoro generated: {len(all_audio)} chunks, {dur:.1f}s")
                return audio, 24000
            print(f"[TTS] Kokoro generated no audio")
            return None
        except Exception as e:
            print(f"[TTS] Kokoro generation failed: {e}")
            return None

    def _speak_kokoro(self, text, speed=1.0):
        self._save_state_and_set_playing()
        result = self._generate_kokoro_audio(text, speed)
        if result is not None:
            audio_data, sr = result
            import uuid
            wav_path = os.path.join(get_project_root(), f"tts_output_{uuid.uuid4().hex[:8]}.wav")
            import soundfile as sf
            sf.write(wav_path, audio_data, sr)
            self._tts_wav_path = wav_path
            self._play_wav(wav_path, speed)
        else:
            print(f"[TTS] Kokoro ({self.language}) failed, trying fallbacks...")
            if not self._speak_windows_default(text):
                print(f"[TTS] Windows default TTS failed. Trying Kokoro English...")
                if not self._speak_kokoro_internal(text, speed, "a", "af_heart"):
                    print(f"[TTS] Kokoro English failed. Trying Windows English...")
                    self._speak_windows_tts(text, "en")
            self._on_tts_done()

    def _speak_kokoro_internal(self, text, speed, lang_code, voice):
        import torch
        import soundfile as sf
        import uuid
        try:
            from kokoro import KPipeline
            pipeline = KPipeline(lang_code=lang_code)
            wav_path = os.path.join(get_project_root(), f"tts_output_{uuid.uuid4().hex[:8]}.wav")
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
        self._tts_paused = True
        self._gen_seq += 1
        self._stream_gen += 1
        with self._speak_lock:
            self._speak_queue.clear()
        with self._audio_lock:
            while self._audio_queue:
                _, _, on_done = self._audio_queue.popleft()
                if on_done:
                    try:
                        on_done()
                    except Exception as e:
                        print(f"[TTS] stop() callback error: {e}")
        self._audio_ready.set()
        self._sd_abort.set()
        if hasattr(self, '_sd_stream') and getattr(self, '_sd_stream', None):
            try:
                self._sd_stream.abort()
            except Exception:
                pass
        self._cleanup_wav()
        self._on_tts_done()

    def pause(self):
        if self._tts_paused:
            return
        self._tts_pause_pos = getattr(self, '_sd_pos', 0)
        if hasattr(self, '_sd_stream') and self._sd_stream is not None:
            try:
                self._sd_stream.stop()
            except Exception:
                pass
        self._tts_paused = True
        print(f"[TTS] Paused at sample {self._tts_pause_pos}")

    def unpause(self):
        if not self._tts_paused:
            return
        self._tts_paused = False
        if hasattr(self, '_sd_stream') and self._sd_stream is not None:
            try:
                self._sd_stream.start()
            except Exception:
                pass
        print("[TTS] Unpaused")

    def get_position(self):
        if not self._tts_play_start or not self.tts_playing:
            return 0
        if self._tts_paused:
            return self._tts_pause_pos
        elapsed = time.time() - self._tts_play_start
        return max(0, int(elapsed * self._tts_sr))

    def update_settings(self, app_volume):
        self.app_volume = app_volume

    def update_output_device(self, device_id):
        self.output_device = None if device_id < 0 else device_id

    def _on_tts_done(self):
        if not self.tts_playing:
            self._log("_on_tts_done: ignored, tts_playing already False")
            return
        self.tts_playing = False
        current = self._get_state()
        prev = self._state_before_tts
        with self._speak_lock:
            speak_len = len(self._speak_queue)
        with self._audio_lock:
            audio_len = len(self._audio_queue)
        self._log(f"_on_tts_done: current={current} prev={prev} tts_playing=False "
                  f"speak_queue={speak_len} audio_queue={audio_len}")
        if current == "playing":
            self._set_state(prev)
            print(f"[TTS] Playback ended, restored state to {prev}")
        else:
            print(f"[TTS] Playback ended, state changed to {current} (was {prev}), not overwriting")
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
