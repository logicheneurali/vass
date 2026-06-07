import os
import sys
import time
import threading
import subprocess
import numpy as np

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
    def __init__(self, gui, state_getter, state_setter, tts_volume, language="en"):
        self.gui = gui
        self._get_state = state_getter
        self._set_state = state_setter
        self.tts_volume = tts_volume
        self.language = language

        self.tts_playing = False
        self._kokoro_pipeline = None
        self._kokoro_code = None
        self._kokoro_voice = None
        self._tts_data = None
        self._tts_sr = None
        self._tts_play_start = 0.0
        self._tts_wav_path = ""
        self._tts_done = threading.Event()
        self._state_before_tts = "listening"

    def speak(self, text, speed=1.0):
        self._speak_kokoro(text, speed)

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
            self._tts_wav_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"tts_output_{uuid.uuid4().hex[:8]}.wav")
            wav_path = self._tts_wav_path
            generator = self._kokoro_pipeline(text, voice=self._kokoro_voice, speed=speed)
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
            print(f"[TTS] Kokoro ({self.language}) failed: {e}")
            self.tts_playing = False
            self._set_state("listening")
            # Chain: Kokoro(lang) -> Windows default -> Kokoro(en) -> Windows(en)
            if not self._speak_windows_default(text):
                print(f"[TTS] Windows default TTS failed. Trying Kokoro English...")
                if not self._speak_kokoro_internal(text, speed, "a", "af_heart"):
                    print(f"[TTS] Kokoro English failed. Trying Windows English...")
                    self._speak_windows_tts(text, "en")
            self._tts_done.set()
            return
        self._play_wav(wav_path, speed)

    def _speak_kokoro_internal(self, text, speed, lang_code, voice):
        import torch
        import soundfile as sf
        import uuid
        try:
            from kokoro import KPipeline
            pipeline = KPipeline(lang_code=lang_code)
            wav_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"tts_output_{uuid.uuid4().hex[:8]}.wav")
            generator = pipeline(text, voice=voice, speed=speed)
            all_audio = []
            for gs, ps, audio in generator:
                all_audio.append(audio)
            if all_audio:
                audio = torch.cat(all_audio).numpy()
                sf.write(wav_path, audio, 24000)
                print(f"[TTS] Kokoro ({lang_code}) WAV saved")
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
