import os
import time
import threading
import subprocess
import numpy as np


class TtsEngine:
    def __init__(self, gui, state_getter, state_setter, tts_volume):
        self.gui = gui
        self._get_state = state_getter
        self._set_state = state_setter
        self.tts_volume = tts_volume

        self.tts_playing = False
        self._kokoro_pipeline = None
        self._tts_data = None
        self._tts_sr = None
        self._tts_play_start = 0.0
        self._tts_wav_path = ""
        self._tts_done = threading.Event()
        self._state_before_tts = "listening"

    def speak(self, text, speed=1.0):
        self._speak_kokoro(text, speed)

    def preload(self):
        def _load():
            try:
                print("[TTS] Preloading Kokoro pipeline in background...")
                from kokoro import KPipeline
                self._kokoro_pipeline = KPipeline(lang_code='i')
                print("[TTS] Kokoro pipeline ready")
            except Exception as e:
                print(f"[TTS] Kokoro preload failed: {e}")
        threading.Thread(target=_load, daemon=True).start()

    def _save_state_and_set_playing(self):
        self._state_before_tts = self._get_state()
        self.tts_playing = True
        self._set_state("playing")

    def _play_wav(self, wav_path, speed=1.0):
        self._tts_done.clear()
        import sounddevice as sd
        import soundfile as sf
        self._tts_data, self._tts_sr = sf.read(wav_path)
        peak = np.max(np.abs(self._tts_data))
        if peak > 0:
            self._tts_data = self._tts_data * (self.tts_volume / peak)
        self._tts_play_start = time.time()
        sd.play(self._tts_data, self._tts_sr)
        threading.Thread(target=self._tts_playback_monitor, daemon=True).start()
        if self.gui:
            self.gui.volume_top_bar.set_volume(self.tts_volume)
        self.gui.start_tts_playback(
            data=self._tts_data,
            samplerate=self._tts_sr,
            total_samples=len(self._tts_data),
            on_complete=self._on_tts_done
        )

    def _speak_kokoro(self, text, speed=1.0):
        self._save_state_and_set_playing()
        import uuid
        self._tts_wav_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"tts_output_{uuid.uuid4().hex[:8]}.wav")
        wav_path = self._tts_wav_path
        try:
            import torch
            import soundfile as sf
            if self._kokoro_pipeline is None:
                from kokoro import KPipeline
                print("[TTS] Loading Kokoro pipeline (lang_code='i')...")
                self._kokoro_pipeline = KPipeline(lang_code='i')
            generator = self._kokoro_pipeline(text, voice='if_sara', speed=speed)
            all_audio = []
            for gs, ps, audio in generator:
                all_audio.append(audio)
            if all_audio:
                audio = torch.cat(all_audio).numpy()
                sf.write(wav_path, audio, 24000)
                print(f"[TTS] Kokoro WAV saved")
            else:
                raise RuntimeError("Kokoro generated no audio")
        except Exception as e:
            print(f"Kokoro TTS failed: {e}. Falling back to Windows TTS.")
            self.tts_playing = False
            self._set_state("listening")
            import base64
            encoded = base64.b64encode(text.encode("utf-16-le")).decode("ascii")
            subprocess.run(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-EncodedCommand",
                 f"Add-Type -AssemblyName System.Speech; "
                 f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                 f"$s.Speak([System.Text.Encoding]::Unicode.GetString([System.Convert]::FromBase64String('{encoded}')))"],
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return
        self._play_wav(wav_path, speed)

    def stop(self):
        import sounddevice as sd
        sd.stop()
        self._on_tts_done()

    def get_position(self):
        if not self._tts_play_start or not self.tts_playing:
            return 0
        elapsed = time.time() - self._tts_play_start
        return max(0, int(elapsed * self._tts_sr))

    def update_settings(self, tts_volume):
        self.tts_volume = tts_volume

    def _tts_playback_monitor(self):
        import sounddevice as sd
        try:
            sd.wait()
        except sd.CallbackAbort:
            pass
        except Exception:
            pass
        if self.gui:
            self.gui.schedule(0, self._on_tts_done)

    def _on_tts_done(self):
        if not self.tts_playing:
            return
        self.tts_playing = False
        self._tts_done.set()
        prev = self._state_before_tts
        if prev == "waiting":
            prev = "listening"
        self._set_state(prev)
        self.gui.stop_tts_playback()
        if self._tts_wav_path and os.path.exists(self._tts_wav_path):
            try:
                os.remove(self._tts_wav_path)
            except OSError:
                pass
