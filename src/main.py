import json
import subprocess
import time
import threading
import re
import datetime
import warnings
warnings.filterwarnings("ignore", message=".*dropout option.*")
warnings.filterwarnings("ignore", message=".*num_layers.*")
warnings.filterwarnings("ignore", message=".*weight_norm.*deprecated.*")
import os
import sys

import configparser
import faulthandler

try:
    import numpy as np
except ImportError:
    msg = "Missing dependencies. Run: pip install -r requirements.txt"
    try:
        if not sys.stdout or not sys.stdout.isatty():
            if sys.platform == "win32":
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, msg, "VASS - Errore", 0x10)
            elif sys.platform == "darwin":
                import subprocess
                subprocess.run(["osascript", "-e", f'display dialog "{msg}" with title "VASS - Errore" buttons {{"OK"}}'], timeout=5)
            else:
                import subprocess
                subprocess.run(["notify-send", "VASS - Errore", msg], timeout=5)
    except Exception:
        log_exc()
    print(msg)
    sys.exit(1)

os.makedirs("log", exist_ok=True)
_faulthandler_file = open("log/faulthandler.log", "w")
faulthandler.enable(_faulthandler_file)

import ssl as _ssl
import threading as _threading
_ssl_lock = _threading.Lock()
_original_create_default_context = _ssl.create_default_context
def _safe_create_default_context(*args, **kwargs):
    with _ssl_lock:
        return _original_create_default_context(*args, **kwargs)
_ssl.create_default_context = _safe_create_default_context

from audio_handler import AudioHandler
from voice_recognition import VoiceRecognition
from command_executor import CommandExecutor
from openai import OpenAI
from utils import get_project_root, call_with_retry, execute_mcp_tool_calls, init_mcp, kill_process, beep, paste_text, parse_blacklist, is_local_url, strip_markdown, cleanup_orphan_files, is_script_command, strip_script_prefix, strip_think_tags, start_llama_server, clean_for_tts, log_exc
from activity_tracker import get_tracker
from gui import VassGUI
from i18n import t
from script_engine import VASScript
from tts_engine import TtsEngine
from event_reminder import EventReminder
from idle_tracker import IdleTracker
from state_manager import StateManager

import builtins as _builtins
_original_print = _builtins.print
_debug_log_file = None

def _ts_print(*args, **kwargs):
    ts = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}]"
    msg = ts + " " + " ".join(str(a) for a in args)
    if _debug_log_file is not None:
        try:
            _debug_log_file.write(msg + "\n")
            _debug_log_file.flush()
        except Exception:
            log_exc()
    try:
        _original_print(msg, **kwargs)
    except Exception:
        log_exc()
_builtins.print = _ts_print


def _rotate_debug_log(path, max_bytes):
    if not os.path.exists(path):
        return
    if os.path.getsize(path) <= max_bytes:
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        target = max_bytes // 2
        while lines and sum(len(l) for l in lines) > target:
            lines.pop(0)
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception:
        log_exc()


def _load_version():
    try:
        with open(os.path.join(get_project_root(), "VERSION")) as f:
            return f.read().strip()
    except Exception:
        return "0.0.0"

from prompts import (MCP_PROMPT, VASSCRIPT_TOOLS_PROMPT,
                     _compress_heuristic, _load_vascript_reference,
                     append_tool_descriptions)

__version__ = _load_version()


class VassApp:
    @staticmethod
    def _resolve_audio_device(saved_id, saved_name, kind="input"):
        """Resolve a possibly stale device ID using the saved device name.

        Device IDs assigned by the OS are not stable across reboots or
        plug/unplug events. The saved name is the stable identifier.
        A saved ID of -1 means "system default" and must be preserved.
        """
        if saved_id < 0:
            return saved_id
        if not saved_name:
            return saved_id
        try:
            import sounddevice as sd
            devs = sd.query_devices()
            ch_key = "max_input_channels" if kind == "input" else "max_output_channels"
            # If the saved ID still points to a device with the saved name, use it.
            for d in devs:
                if d["index"] == saved_id and d.get(ch_key, 0) > 0 and d.get("name", "") == saved_name:
                    return saved_id
            # Otherwise look for a device with the exact saved name.
            for d in devs:
                if d.get(ch_key, 0) > 0 and d.get("name", "") == saved_name:
                    print(f"[Audio] Resolved {kind} device by name: '{saved_name}' -> id={d['index']} (was {saved_id})")
                    return d["index"]
            # Fallback: partial name match.
            for d in devs:
                if d.get(ch_key, 0) > 0 and saved_name in d.get("name", ""):
                    print(f"[Audio] Resolved {kind} device by partial name: '{saved_name}' -> id={d['index']} (was {saved_id})")
                    return d["index"]
        except Exception as e:
            print(f"[Audio] Device resolution failed: {e}")
        return saved_id

    def __init__(self, gui, settings_file="config/settings.ini"):
        self.gui = gui
        self.state_manager = StateManager(self)
        self._ai_lock = threading.Lock()
        self._remote_reply_cb = None
        self.settings_file = settings_file
        self.app_version = __version__
        self.settings = self._load_settings()
        inp = int(self.settings.get("input_device", -1))
        inp_name = self.settings.get("input_device_name", "")
        inp = self._resolve_audio_device(inp, inp_name, kind="input")
        out = int(self.settings.get("output_device", -1))
        out_name = self.settings.get("output_device_name", "")
        out = self._resolve_audio_device(out, out_name, kind="output")
        self.audio_handler = AudioHandler(input_device=inp)
        self.language = self.settings["language"]
        self.wake_word_sensitivity = self.settings["sensitivity"]
        self.wake_word = self.settings.get("wakeword", "vass")
        self.ai_url = self.settings["ai_url"]
        self.ai_api_key = self.settings.get("api_key", "")
        self.ai_model = self.settings["ai_model"]
        self.system_message = self.settings["system_message"]
        self.allow_ai_scripts = self.settings.get("allow_ai_scripts", False)
        self.context_length = self.settings.get("context_length", 0)
        self._tokenizer = None
        self.debug_enabled = self.settings.get("debug_enabled", False)
        self.overflow_strategy = self.settings.get("overflow_strategy", "truncate")
        self.compress_context = self.settings.get("compress_context", "false").lower() == "true"
        self.auto_context_selection = self.settings.get("auto_context_selection", False)
        self.waveform_enabled = False
        self.gui_font_family = self.settings["gui_font_family"]
        self.gui_font_size = self.settings["gui_font_size"]
        self.command_similarity = self.settings["command_similarity"]
        self.word_learning_enabled = self.settings.get("word_learning_enabled", False)
        self.app_volume = self.settings.get("app_volume", 1.0)
        self.tts = TtsEngine(
            gui=gui,
            state_getter=lambda: self.state,
            state_setter=self.set_state,
            app_volume=self.app_volume,
            language=self.language,
            output_device=out,
            kokoro_voice=self.settings.get("kokoro_voice", ""),
        )
        self.tts.preload()
        self.gui.volume_top_bar.set_volume(self.app_volume)
        self.mcp_server_url = self.settings["mcp_server_url"]
        self.mcp_process = None
        self.memory_tokens = self.settings.get("memory_tokens", 5000)
        self.blacklist = parse_blacklist(self.settings.get("blacklist", ""))
        self.llama_server_path = self.settings.get("llama_server_path", "")
        self.llama_server_working_directory = self.settings.get("llama_server_working_directory", "")
        self.llama_server_arguments = self.settings.get("llama_server_arguments", "")
        self.llama_autostart = self.settings.get("llama_autostart", "false").lower() == "true"
        self.llama_process = None


        self._silent_frames = 0
        self._mic_recording = False
        self._memory_cache = None

        # Audio diagnostics for wake-word issues
        self._audio_stats_time = time.time()
        self._audio_stats_frames = 0
        self._audio_stats_wake = 0
        self._audio_stats_energy_sum = 0.0
        self._audio_stats_energy_max = 0.0
        self._audio_stats_energy_min = float('inf')
        self._audio_stats_count = 0

        reminder_advance = self.settings.get("reminder_advance", 3600)
        self.idle_tracker = IdleTracker()
        self.event_reminder = EventReminder(self, advance_seconds=reminder_advance, language=self.language, idle_tracker=self.idle_tracker)

        wr_lang = t("whisper.language", self.language)
        wr_prompt = t("whisper.initial_prompt_wakeword", self.language)
        wr_prompt = f"{self.wake_word}, {wr_prompt}"
        wr_transcribe = t("whisper.initial_prompt_transcription", self.language)
        try:
            wr_variants = list(t("whisper.wake_variants", self.language))
            if not isinstance(wr_variants, list):
                raise ValueError
        except Exception:
            wr_variants = ["{wake}", "hey {wake}", "ciao {wake}"]
        wr_variants = [v.replace("{wake}", self.wake_word) for v in wr_variants]
        print(f"[Startup] Wake word: {self.wake_word!r}, variants: {wr_variants}")
        self.voice_recognition = VoiceRecognition(
            wake_word=self.wake_word,
            sensitivity=self.wake_word_sensitivity,
            whisper_language=wr_lang,
            wake_prompt=wr_prompt,
            transcribe_prompt=wr_transcribe,
            wake_variants=wr_variants
        )
        self.voice_recognition.input_volume = self.settings.get("input_volume", 1.0)
        self.voice_recognition.debug_enabled = self.debug_enabled
        self.command_executor = CommandExecutor(similarity_threshold=self.command_similarity, language=self.language, word_learning_enabled=self.word_learning_enabled, app=self)
        self.openai_client = OpenAI(base_url=self.ai_url, api_key=self.ai_api_key or "not-needed")
        # If llama.cpp is set to auto-start, defer context/model detection until
        # the server is actually ready. Otherwise probe immediately.
        if self.context_length <= 0 and not (self.llama_autostart and self.llama_server_path.strip()):
            threading.Thread(target=self._detect_context_length, daemon=True).start()
        if not self.ai_model.strip() and self.llama_server_path.strip() and not self.llama_autostart:
            threading.Thread(target=self._auto_select_model, daemon=True).start()
        self.running = False
        self._state_vars_lock = threading.Lock()
        from script_runner import ScriptRunner
        self.script_runner = ScriptRunner(self)
        self.script_queue = self.script_runner.queue
        self.state_lock = threading.RLock()
        from timer_manager import TimerManager
        self.timer_manager = TimerManager(self)
        from notification_manager import NotificationManager
        self.notification_manager = NotificationManager()
        from notification_router import NotificationRouter
        self.notification_router = NotificationRouter(self)
        self.context_notes = []
        self.conversation_history = []
        from memory_manager import MemoryManager
        self.memory = MemoryManager(self)
        self.memory.load_sources()
        from audio_filter import NoiseFilter
        self.noise_filter = NoiseFilter()
        self.mode = "chat" if self.settings.get("lastmode", "c") == "c" else "transcription"
        self.gui.set_mode_display(self.mode)
        self.memory_mode = "full"
        self._input_mode = False


    def set_mode(self, mode):
        self.mode = mode
        self.gui.set_mode_display(mode)
        self._save_setting("gui", "lastmode", "c" if mode == "chat" else "t")
        print(f"[Mode] Switched to '{mode}'")

    @staticmethod
    def _save_setting(section, key, value):
        import configparser
        try:
            cfg = configparser.ConfigParser()
            path = os.path.join(get_project_root(), "config", "settings.ini")
            cfg.read(path, encoding="utf-8")
            if not cfg.has_section(section):
                cfg.add_section(section)
            cfg.set(section, key, value)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                cfg.write(f)
        except Exception:
            log_exc()

    def set_memory_mode(self, mode):
        self.memory_mode = mode
        print(f"[MemoryMode] Switched to '{mode}'")

    def _load_settings(self):
        from settings_manager import load_settings
        return load_settings(self.settings_file)

    @property
    def state(self):
        return self.state_manager.state

    def set_state(self, new_state, detail="", silent_gui=False, source=""):
        """Backward-compatible state setter. Delegates to StateManager.

        StateManager handles redirecting 'listening' back to 'paused' when a
        pause flag is still active, so operations that complete while paused
        automatically return to the paused state.
        """
        if self.state in ("paused", "loading") and new_state == "listening":
            self.noise_filter.reset_calibration()
        if self.state in ("waiting", "waiting_resources") and new_state not in ("waiting", "waiting_resources") and hasattr(self, 'tts'):
            self.tts._flush_deferred()
        self.state_manager.set_state(new_state, detail, silent_gui)

    def _update_gui_state(self, new_state, detail="", silent_gui=False):
        """Pure GUI update. Called by StateManager after internal state is set."""
        if not silent_gui:
            try:
                if hasattr(self, '_plugin_server'):
                    self._plugin_server.broadcast("state", {
                        "state": new_state, "prev": self.state, "source": "",
                    })
                self.gui.set_state(new_state, detail)
            except Exception as e:
                with open("log/crash.log", "a") as f:
                    f.write(f"gui.set_state failed: {e}\n")

    def _verify_stream_state(self, expected_listening):
        """Log invariant violations between expected state and actual stream state."""
        try:
            stream_active = self.audio_handler.stream is not None
            if expected_listening and not stream_active:
                print(f"[StateInvariant] Expected listening but stream is stopped (state={self.state})")
            elif not expected_listening and stream_active:
                print(f"[StateInvariant] Expected paused but stream is still active (state={self.state})")
        except Exception:
            log_exc()

    def handle_button_press(self):
        try:
            self._handle_button_press_impl()
        except Exception as e:
            print(f"[ButtonPress] Error: {e}")

    def trigger_mic_recording(self):
        self._mic_recording = True

    def _handle_button_press_impl(self):
        with self.state_lock:
            current = self.state
            if current == "listening":
                self.state_manager.set_manual_paused()
            elif current == "recording":
                self.audio_handler.stop_recording()
                self.audio_handler.recorded_buffer.clear()
                self.state_manager.set_manual_paused()
            elif current == "paused":
                self.voice_recognition.reset_noise_floor()
                self.voice_recognition.reset_model()
                self.state_manager.resume_listening(force=True)
            elif current == "playing":
                self.stop_playback()
                self.state_manager.resume_listening(force=True)
                self.gui.schedule(0, lambda: self.state_manager.resume_listening(force=True))
            elif current == "running_script":
                self.script_runner.cancel_current()
            elif current in ("waiting",):
                if self.gui.player.data is not None:
                    self.stop_playback()
                self.state_manager.resume_listening(force=True)
            elif current == "waiting_resources":
                self.state_manager.resume_listening(force=True)
        if self.gui.player.isVisible():
            self.stop_playback()

    def stop_playback(self):
        try:
            self.tts.stop()
        except Exception as e:
            print(f"[StopPlayback] Error: {e}")

    def _watch_commands_file(self):
        commands_path = self.command_executor.commands_file
        if not os.path.exists(commands_path):
            return
        last_mtime = os.path.getmtime(commands_path)
        while self.running:
            time.sleep(2)
            try:
                if os.path.exists(commands_path):
                    mtime = os.path.getmtime(commands_path)
                    if mtime != last_mtime:
                        last_mtime = mtime
                        self.command_executor.reload_commands()
                        print(f"[Watch] Commands reloaded from {commands_path}")
            except Exception as e:
                print(f"[Watch] Commands watcher error: {e}")

    def _watch_settings_file(self):
        abs_path = os.path.abspath(self.settings_file)
        if not os.path.exists(abs_path):
            return
        last_mtime = os.path.getmtime(abs_path)
        while self.running:
            time.sleep(2)
            try:
                if os.path.exists(abs_path):
                    mtime = os.path.getmtime(abs_path)
                    if mtime != last_mtime:
                        last_mtime = mtime
                        self.settings = self._load_settings()
                        self.command_executor.similarity_threshold = self.settings["command_similarity"]
                        self.command_executor.word_learning_enabled = self.settings.get("word_learning_enabled", False)
                        self.ai_api_key = self.settings.get("api_key", "")
                        self.openai_client.api_key = self.ai_api_key or "not-needed"
                        self.ai_model = self.settings["ai_model"]
                        if not self.ai_model.strip() and self.settings.get("llama_server_path", "").strip():
                            threading.Thread(target=self._auto_select_model, daemon=True).start()
                        elif self.ai_model.strip():
                            threading.Thread(target=self._verify_model_and_autoselect, daemon=True).start()
                        old_url = self.ai_url
                        self.ai_url = self.settings["ai_url"]
                        self.system_message = self.settings.get("system_message", "")
                        self.allow_ai_scripts = self.settings.get("allow_ai_scripts", False)
                        self.context_length = self.settings.get("context_length", 0)
                        if self.context_length <= 0:
                            threading.Thread(target=self._detect_context_length, daemon=True).start()
                        self.overflow_strategy = self.settings.get("overflow_strategy", "truncate")
                        self.compress_context = self.settings.get("compress_context", "false").lower() == "true"
                        self.auto_context_selection = self.settings.get("auto_context_selection", False)
                        self.debug_enabled = self.settings.get("debug_enabled", False)
                        self.voice_recognition.debug_enabled = self.debug_enabled
                        self.gui.debug_border_signal.emit()
                        if self.ai_url != old_url:
                            self.openai_client = OpenAI(base_url=self.ai_url, api_key=self.ai_api_key or "not-needed")
                        self.mcp_server_url = self.settings["mcp_server_url"]
                        self.memory_tokens = self.settings.get("memory_tokens", 5000)
                        self.blacklist = parse_blacklist(self.settings.get("blacklist", ""))
                        self.llama_server_path = self.settings.get("llama_server_path", "")
                        self.llama_autostart = self.settings.get("llama_autostart", "false").lower() == "true"
                        self.app_volume = self.settings.get("app_volume", 1.0)
                        self.tts.update_settings(self.app_volume)
                        self.gui.volume_top_bar.set_volume(self.app_volume)
                        # Ricarica dispositivi audio
                        new_inp = int(self.settings.get("input_device", -1))
                        new_inp_name = self.settings.get("input_device_name", "")
                        new_inp = self._resolve_audio_device(new_inp, new_inp_name, kind="input")
                        old_inp = -1 if self.audio_handler.input_device is None else self.audio_handler.input_device
                        if new_inp != old_inp:
                            was_streaming = (self.audio_handler.stream is not None)
                            self.audio_handler.stop_stream()
                            self.audio_handler.input_device = None if new_inp < 0 else new_inp
                            if was_streaming:
                                self.audio_handler.start_stream()
                            self.voice_recognition.reset_noise_floor()
                            print(f"[Watch] Input device changed to: {new_inp}")
                        new_vol = float(self.settings.get("input_volume", 1.0))
                        if abs(new_vol - self.voice_recognition.input_volume) > 0.001:
                            self.voice_recognition.input_volume = new_vol
                            print(f"[Watch] Input volume changed to: {new_vol}")
                        new_out = int(self.settings.get("output_device", -1))
                        new_out_name = self.settings.get("output_device_name", "")
                        new_out = self._resolve_audio_device(new_out, new_out_name, kind="output")
                        self.tts.update_output_device(new_out)
                        self.gui.schedule(0, self.gui.update_button_tooltip)
                        # Ricarica sensitivity wake word
                        new_sens = float(self.settings.get("sensitivity", 0.010))
                        if new_sens != self.voice_recognition.energy_threshold:
                            self.voice_recognition.energy_threshold = new_sens
                            print(f"[Watch] Wake word sensitivity changed to: {new_sens}")
                        print(f"[Watch] Settings reloaded from {abs_path}")
            except Exception as e:
                print(f"[Watch] Settings watcher error: {e}")

    @staticmethod
    def _load_layout():
        """Read window geometry and limits from config/layout.ini. Creates with defaults if missing."""
        path = os.path.join(get_project_root(), "config", "layout.ini")
        layout = configparser.ConfigParser()
        defaults = {"x": 1541, "y": 52, "width": 240, "height": 32}
        limits = {"min_width": 200, "min_height": 32, "max_width": 600, "max_height": 400}
        if not os.path.exists(path):
            layout["window"] = {k: str(v) for k, v in defaults.items()}
            layout["limits"] = {k: str(v) for k, v in limits.items()}
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                layout.write(f)
            return defaults, limits
        try:
            layout.read(path, encoding="utf-8")
            window = {k: layout.getint("window", k, fallback=defaults[k]) for k in defaults}
            limits_val = {k: layout.getint("limits", k, fallback=limits[k]) for k in limits}
            return window, limits_val
        except Exception:
            return defaults, limits

    def run(self):
        # Cleanup old OCR debug images from previous sessions
        try:
            import glob as _glob
            for f in _glob.glob("log/ocr_debug_*.png"):
                try:
                    os.remove(f)
                except OSError:
                    pass
        except Exception:
            log_exc()

        if self.settings.get("debug_enabled", False):
            os.makedirs("log", exist_ok=True)
            max_bytes = int(self.settings.get("debug_log_max_kb", 1024)) * 1024
            _rotate_debug_log("log/debug.log", max_bytes)
            global _debug_log_file
            _debug_log_file = open("log/debug.log", "a", encoding="utf-8")

        print(f"VASS v{__version__} - Voice assistant software")
        self.gui.set_loading_progress(5, 100, "Voice models...")
        self.voice_recognition.load_models()
        self.gui.set_loading_progress(85, 100, "Audio...")
        self.audio_handler.start_stream()
        from utils import get_project_root, list_audio_devices
        inp = self.audio_handler.input_device
        out = self.tts.output_device
        list_audio_devices(resolved_inp=inp, resolved_out=out)
        self.gui.set_loading_progress(88, 100, "Threads...")
        self.running = True

        self.gui.set_loading_progress(90, 100, "Plugins...")
        from plugin_server import PluginServer
        self._plugin_server = PluginServer(self, port=8765)
        self._plugin_server.start()

        self.gui.set_loading_progress(95, 100, "Ready")
        self.set_state("listening")

        # Threads start only after the app is in listening state (GUI stable)
        threading.Thread(target=self._watch_commands_file, daemon=True).start()
        threading.Thread(target=self._watch_settings_file, daemon=True).start()
        threading.Thread(target=self.script_runner.watch_queue, daemon=True).start()
        if self.mcp_server_url and os.path.exists(os.path.join(get_project_root(), "mcp_server", "run_server.py")):
            threading.Thread(target=self._start_mcp_server, daemon=True).start()
        if self.llama_server_path.strip() and self.llama_autostart:
            threading.Thread(target=self._start_llamacpp, daemon=True).start()
        if self.event_reminder:
            threading.Thread(target=self.event_reminder.run, daemon=True).start()
            # Run startup schedules after a short delay for services to initialize
            threading.Thread(target=lambda: (time.sleep(3), self.event_reminder.run_startup_schedules()), daemon=True).start()
        threading.Thread(target=self._health_check_loop, daemon=True).start()
        threading.Thread(target=self._health_check_once, daemon=True).start()
        threading.Thread(target=self._mcp_health_check_loop, daemon=True).start()
        if self.settings.get("calendar_sync_enabled", "false").lower() == "true":
            threading.Thread(target=self._sync_calendar_loop, daemon=True).start()
        from mail import start as start_mail
        start_mail(self)
        self.memory.start_deferred_loop()
        if self.memory.is_source_enabled("files"):
            from memory_files_scanner import FileScanner
            self._file_scanner = FileScanner(self.memory._files_config, self.memory)
            threading.Thread(target=self._file_scanner.run, daemon=True).start()

        self.gui.set_mode_display(self.mode)
        self.gui.update_memory_bar()

        # Double beep to indicate app is ready
        beep(self.app_volume)
        time.sleep(0.15)
        beep(self.app_volume)
        while self.running:
            try:
                if self._input_mode:
                    time.sleep(0.05)
                    continue
                frame = self.audio_handler.get_frame()
                raw_frame = frame
                raw_rms = float(np.sqrt(np.mean(frame**2))) if frame is not None else 0.0
                if frame is not None and self.noise_filter:
                    frame = self.noise_filter.process(frame, raw_rms=raw_rms)
                is_manual_paused = self.state_manager.is_manual_paused()
                with self._state_vars_lock:
                    if frame is None:
                        self._silent_frames += 1
                        if self._silent_frames > 300 and self.state != "paused" and not is_manual_paused:
                            with self.state_lock:
                                cs = self.state
                            if cs == "listening":
                                print("[Audio] Stream appears dead, restarting...")
                                self.audio_handler.stop_stream()
                                time.sleep(0.1)
                                self.audio_handler.start_stream()
                                self._silent_frames = 0
                    else:
                        self._silent_frames = 0

                if frame is not None:
                    # Accumulate audio diagnostics
                    frame_energy = float(np.sqrt(np.mean(frame**2)))
                    self._audio_stats_frames += 1
                    self._audio_stats_energy_sum += frame_energy
                    self._audio_stats_energy_max = max(self._audio_stats_energy_max, frame_energy)
                    self._audio_stats_energy_min = min(self._audio_stats_energy_min, frame_energy)
                    self._audio_stats_count += 1

                    # ── Plugin broadcast (before should_skip so plugins always receive data) ──
                    if hasattr(self, '_plugin_server') and raw_frame is not None:
                        try:
                            nf = self.voice_recognition.noise_floor
                        except Exception:
                            nf = 0.0
                        self._plugin_server.broadcast("audio", {
                            "rms": raw_rms, "noise_floor": nf,
                            "auto_paused": self.state == "paused",
                            "listening": self.state == "listening",
                        })

                    # Read state fresh under lock and decide whether to process this frame.
                    with self.state_lock:
                        current_state = self.state
                        if current_state == "recording":
                            self.gui.volume_signal.emit(frame_energy)
                        should_skip = current_state in ["paused", "playing", "waiting", "waiting_resources", "running_script"]

                    if should_skip:
                        continue

                    if not self.audio_handler.is_recording:
                        # Defensive: re-check we are still listening before wake-word detection.
                        if current_state != "listening" and not self._mic_recording:
                            continue
                        if self._mic_recording:
                            self._mic_recording = False
                            print("Mic button pressed. Switching to recording mode...")
                            try:
                                beep(self.app_volume)
                            except Exception as ex:
                                with open("log/crash.log", "a") as f:
                                    f.write(f"Beep error: {ex}\n")
                            self.audio_handler.clear_queue()
                            self.stop_playback()
                            self.audio_handler.start_recording()
                            self.voice_recognition.reset_model()
                            self.state_manager.set_state("recording")
                            continue
                        try:
                            wake = self.voice_recognition.detect_wake_word(frame, raw_energy=raw_rms)
                            if wake:
                                self._audio_stats_wake += 1
                        except Exception as ex:
                            with open("log/crash.log", "a") as f:
                                f.write(f"detect_wake_word error: {ex}\n")
                            print(f"[WakeWord] detect_wake_word error: {ex}")
                            wake = False
                        if wake and current_state == "listening":
                            print("Wake word detected! Switching to recording mode...")
                            try:
                                beep(self.app_volume)
                            except Exception as ex:
                                with open("log/crash.log", "a") as f:
                                    f.write(f"Beep error: {ex}\n")
                            self.audio_handler.clear_queue()
                            self.stop_playback()
                            self.audio_handler.start_recording()
                            self.voice_recognition.reset_model()
                            self.state_manager.set_state("recording")
                            continue

                    self.audio_handler.process_recording(frame, vad_frame=raw_frame)

                    if not self.audio_handler.is_recording and len(self.audio_handler.recorded_buffer) > 0:
                        self.state_manager.set_state("listening")
                        self._transcribe_and_process()
                        self.audio_handler.clear_queue()

                # Periodic audio diagnostics log (every 10s)
                try:
                    now = time.time()
                    if now - self._audio_stats_time >= 10:
                        stream_ok = self.audio_handler.stream is not None
                        if self._audio_stats_count > 0:
                            avg_energy = self._audio_stats_energy_sum / self._audio_stats_count
                            print(f"[AudioStats] stream_ok={stream_ok} frames={self._audio_stats_frames} "
                                  f"avg_energy={avg_energy:.6f} min={self._audio_stats_energy_min:.6f} "
                                  f"max={self._audio_stats_energy_max:.6f} input_volume={self.voice_recognition.input_volume:.3f} "
                                  f"noise_floor={self.voice_recognition._noise_floor:.6f} wakes={self._audio_stats_wake}")
                        else:
                            print(f"[AudioStats] stream_ok={stream_ok} frames=0 NO_AUDIO_RECEIVED")
                        self._audio_stats_time = now
                        self._audio_stats_frames = 0
                        self._audio_stats_wake = 0
                        self._audio_stats_energy_sum = 0.0
                        self._audio_stats_energy_max = 0.0
                        self._audio_stats_energy_min = float('inf')
                        self._audio_stats_count = 0
                except Exception as e:
                    print(f"[AudioStats] log error: {e}")

            except KeyboardInterrupt:
                print("\nShutting down Vass...")
                self.running = False
                break
            except Exception as e:
                import traceback
                with open("log/crash.log", "a") as f:
                    f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
                    traceback.print_exc(file=f)
                print(f"\n[CRASH] Loop error. Restarting in 3 seconds. Details in crash.log")
                traceback.print_exc()
                self.audio_handler.stop_stream()
                time.sleep(3)
                self.audio_handler.start_stream()
                self.audio_handler.clear_queue()
                if hasattr(self.voice_recognition, 'reset_model'):
                    self.voice_recognition.reset_model()
                continue
        self.audio_handler.stop_stream()

    def _start_mcp_server(self):
        from mcp_server import McpServerThread
        self._mcp_thread = McpServerThread(
            allow_scripts=self.allow_ai_scripts,
            debug=getattr(self, 'debug_enabled', False),
        )
        self._mcp_thread.start()
        time.sleep(2)

    def _health_check_loop(self):
        import urllib.request
        while self.running:
            time.sleep(60)
            if not self.running:
                break
            health_url = f"{self.ai_url.rstrip('/')}/health"
            try:
                with urllib.request.urlopen(health_url, timeout=5) as r:
                    ok = r.status == 200
                if self.debug_enabled:
                    print(f"[Health] {health_url} -> {r.status}")
            except Exception as e:
                ok = False
                if self.debug_enabled:
                    print(f"[Health] {health_url} unreachable: {e}")
            self.gui.schedule_signal.emit(lambda ok=ok: self.gui.set_health_status(ok))

    def _mcp_health_check_loop(self):
        """Periodically check if the MCP server is reachable."""
        import urllib.request, socket
        time.sleep(10)  # give MCP server time to start
        while self.running:
            time.sleep(60)
            if not self.running:
                break
            ok = False
            try:
                url = self.mcp_server_url.rstrip("/")
                host = url.replace("http://", "").replace("https://", "").split(":")[0]
                port = int(url.split(":")[-1]) if ":" in url.split("//")[-1] else 80
                s = socket.socket()
                s.settimeout(3)
                s.connect((host, port))
                s.close()
                ok = True
            except Exception:
                ok = False
            if self.debug_enabled and not ok:
                print(f"[MCP-Health] MCP server unreachable at {self.mcp_server_url}")
            self.gui.schedule_signal.emit(lambda ok=ok: self.gui.set_mcp_status(ok))

    def _health_check_once(self):
        time.sleep(3)  # brief delay for server startup
        import urllib.request
        health_url = f"{self.ai_url.rstrip('/')}/health"
        try:
            with urllib.request.urlopen(health_url, timeout=5) as r:
                ok = r.status == 200
            if self.debug_enabled:
                print(f"[Health] {health_url} -> {r.status}")
        except Exception as e:
            ok = False
            if self.debug_enabled:
                print(f"[Health] {health_url} unreachable: {e}")
        self.gui.schedule_signal.emit(lambda ok=ok: self.gui.set_health_status(ok))

    def _sync_calendar_loop(self):
        time.sleep(5)
        from google_calendar import GoogleCalendar
        gcal = GoogleCalendar()
        minutes = int(self.settings.get("calendar_sync_minutes", 30))
        days = int(self.settings.get("calendar_sync_days", 7))
        events_path = os.path.join(get_project_root(), "Allowed_root", "events.json")
        try:
            tracker = get_tracker(); tracker.start("Calendar sync", "sync")
            new_or_changed = gcal.sync_to_vass(events_path, days=days) or []
            tracker.end("Calendar sync")
            if new_or_changed and self.memory.is_source_enabled("calendar"):
                for ev in new_or_changed:
                    classify_content = (
                        f"Calendar event: {ev.get('summary', '')}\n"
                        f"When: {ev.get('start', '')} -> {ev.get('end', '')}"
                    )
                    self.memory.enqueue_external(classify_content, ev["id"], "calendar")
        except Exception as e:
            print(f"[GCal] Sync error: {e}")
        while self.running:
            time.sleep(minutes * 60)
            try:
                tracker = get_tracker(); tracker.start("Calendar sync", "sync")
                new_or_changed = gcal.sync_to_vass(events_path, days=days) or []
                tracker.end("Calendar sync")
                if new_or_changed and self.memory.is_source_enabled("calendar"):
                    for ev in new_or_changed:
                        classify_content = (
                            f"Calendar event: {ev.get('summary', '')}\n"
                            f"When: {ev.get('start', '')} -> {ev.get('end', '')}"
                        )
                        self.memory.enqueue_external(classify_content, ev["id"], "calendar")
            except Exception as e:
                print(f"[GCal] Sync error: {e}")

    def _wait_for_llamacpp_ready(self, timeout=60):
        """Poll /v1/models until llama-server responds or timeout expires."""
        import urllib.request
        import json
        url = f"{self.ai_url.rstrip('/')}/models"
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=2) as resp:
                    models = json.loads(resp.read()).get("data", [])
                if models:
                    return True
            except Exception:
                log_exc()
            time.sleep(0.5)
        return False

    def _start_llamacpp(self):
        proc, status = start_llama_server(
            self.llama_server_path,
            self.llama_server_working_directory,
            self.llama_server_arguments,
        )
        if proc:
            self.llama_process = proc
        print(f"[llama.cpp] {status}")
        print("[llama.cpp] Waiting for server readiness...")
        if self._wait_for_llamacpp_ready(timeout=60):
            print("[llama.cpp] Server ready")
            if self.context_length <= 0:
                self._detect_context_length()
            if not self.ai_model.strip():
                self._auto_select_model()
            elif self.llama_server_path.strip():
                self._verify_model_and_autoselect()
        else:
            print("[llama.cpp] Server did not become ready within 60s")

    def stop(self):
        self.running = False
        try:
            _faulthandler_file.close()
        except Exception:
            log_exc()
        global _debug_log_file
        if _debug_log_file is not None:
            _debug_log_file.close()
            _debug_log_file = None
        if self.llama_process:
            kill_process(self.llama_process)
            self.llama_process = None
        if hasattr(self, '_plugin_server') and self._plugin_server:
            try:
                self._plugin_server.stop()
            except Exception:
                log_exc()

    def _get_tokenizer(self):
        if self._tokenizer is not None:
            return self._tokenizer
        try:
            import tiktoken
            self._tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            try:
                self._tokenizer = tiktoken.encoding_for_model(self.ai_model)
            except Exception:
                self._tokenizer = None
        return self._tokenizer

    def _count_tokens(self, text):
        tok = self._get_tokenizer()
        if tok:
            try:
                return len(tok.encode(text))
            except Exception:
                log_exc()
        return len(text) // 2

    def _estimate_system_overhead(self):
        overhead = self._count_tokens(self.system_message or "") + 50
        overhead += self._count_tokens(self.memory.build_content(""))
        if self.allow_ai_scripts:
            overhead += self._count_tokens(MCP_PROMPT)
            overhead += self._count_tokens(_load_vascript_reference())
        return overhead

    def _process_chat_text(self, text):
        if self.state not in ("listening", "paused"):
            print(f"[Chat] Ignored: state={self.state}")
            return
        ctx_len = self.context_length or 4096
        overhead = self._estimate_system_overhead()
        avail_chars = max(ctx_len - overhead, ctx_len // 4)
        if len(text) > avail_chars:
            if self.overflow_strategy == "summarize":
                print(f"[Chat] Text overflow ({len(text)} > {avail_chars} chars, ctx={ctx_len}, ovh={overhead}), summarizing...")
                threading.Thread(target=self._execute_summarize_text, args=(text,), daemon=True).start()
                return
            else:
                text = text[:avail_chars] + "\n\n[testo troncato]"
                print(f"[Chat] Text overflow ({len(text)} > {avail_chars} chars), truncated")
        print(f"[Chat] Text input ({len(text)} chars)")
        threading.Thread(target=self._execute_chat_text, args=(text,), daemon=True).start()

    def chat_remote(self, text, reply_cb=None):
        """Process text through the full pipeline (commands + AI fallback) for
        remote callers (e.g. Telegram bot). When reply_cb is given, state gates
        are relaxed so the request is never dropped while VASS is speaking, and
        reply_cb(response) fires when the AI response is ready."""
        if reply_cb is not None:
            self._remote_reply_cb = reply_cb
        with open("lastcommands.txt", "w", encoding="utf-8") as f:
            f.write(text)
        self._process_command()

    def _consume_remote_reply(self, text=None):
        """Deliver (or discard) the pending remote reply callback. Must be called
        in every outcome of the command pipeline so a stale callback can never
        steal the response of a later, unrelated chat request."""
        cb = self._remote_reply_cb
        if cb:
            self._remote_reply_cb = None
            if text:
                try:
                    cb(text)
                except Exception as e:
                    print(f"[Remote] reply_cb error: {e}")

    def _execute_summarize_text(self, text):
        self.set_state("waiting")
        ctx_len = self.context_length or 4096
        overhead = self._estimate_system_overhead()
        chunk_size = max(ctx_len - overhead, ctx_len // 4)
        if len(text) <= chunk_size:
            summary = self._summarize_chunk(text)
        else:
            chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
            print(f"[Chat] Summarizing in {len(chunks)} chunks of ~{chunk_size} chars...")
            summaries = []
            for i, chunk in enumerate(chunks):
                s = self._summarize_chunk(chunk)
                if s:
                    summaries.append(s)
                print(f"[Chat] Chunk {i + 1}/{len(chunks)} done ({len(chunk)} -> {len(s)} chars)")
            summary = "\n\n".join(summaries)
            if len(summary) > chunk_size:
                summary = self._summarize_chunk(summary)
                print(f"[Chat] Metasummary: {len(text)} -> {len(summary)} chars")

        max_final = int(ctx_len // 2) * 2
        if len(summary) > max_final:
            summary = summary[:max_final] + "\n\n[riassunto troncato]"

        done = threading.Event()
        self.tts.enqueue("Testo riassunto. Eseguo la richiesta.", on_done=done.set)
        done.wait()
        with open("lastcommands.txt", "w", encoding="utf-8") as f:
            f.write(summary)
        print(f"[Chat] Summarized {len(text)} chars -> {len(summary)} chars")
        self._process_command()

    def _summarize_chunk(self, text):
        for attempt in range(2):
            try:
                resp = self.openai_client.chat.completions.create(
                    model=self.ai_model,
                    messages=[{"role": "user", "content": f"Summarize concisely:\n\n{text}"}],
                    temperature=0.3, max_tokens=500,
                    extra_body={"disable_thinking": True}
                )
                return (resp.choices[0].message.content or "").strip()
            except Exception as e:
                err = str(e)
                if "context" in err.lower() or "exceed" in err.lower():
                    text = text[:len(text) * 3 // 4]
                    if attempt == 0:
                        continue
                if attempt == 1:
                    print(f"[Chat] Chunk summarization failed: {e}")
                    return text[:2000] if len(text) > 2000 else text

    def _execute_chat_text(self, text):
        with open("lastcommands.txt", "w", encoding="utf-8") as f:
            f.write(text)
        self._process_command()

    def _transcribe_and_process(self):
        audio_data = self.audio_handler.get_recorded_audio()
        self.audio_handler.recorded_buffer.clear()
        
        if len(audio_data) > 0:
            transcription = self.voice_recognition.transcribe_audio(audio_data)
            with open("lastcommands.txt", "w", encoding="utf-8") as f:
                f.write(transcription)
            print(f"Transcription: {transcription}")
            if hasattr(self, 'idle_tracker') and self.idle_tracker:
                self.idle_tracker.update_voice_activity()
            self._process_command()
        else:
            print("No audio recorded.")

    def _listen_once(self, timeout=15):
        if self.state_manager.is_paused():
            print("[ListenOnce] Ignored: paused")
            return ""
        if self.state != "listening":
            print(f"[ListenOnce] Blocked: state={self.state}")
            return ""
        import sounddevice as sd
        import numpy as np
        from audio_handler import SileroVAD, _resolve_vad_model
        self._input_mode = True
        self.audio_handler.stop_stream()
        self.audio_handler.clear_queue()
        try:
            sample_rate = 16000
            frame_size = 320
            vad = SileroVAD(_resolve_vad_model(), sample_rate=sample_rate, threshold=0.5)
            recorded = []
            speech_detected = False
            silence_start = None
            silence_threshold = 2.0

            def callback(indata, frames, time_info, status):
                recorded.append(indata.copy().flatten())

            with sd.InputStream(
                samplerate=sample_rate, channels=1,
                blocksize=frame_size, latency="high",
                callback=callback,
            ):
                start = time.time()
                while time.time() - start < timeout:
                    if recorded:
                        frame = recorded[-1]
                        try:
                            is_speech = vad.is_speech(frame)
                        except Exception as ex:
                            print(f"[Listen] VAD error: {ex}")
                            is_speech = False
                        if is_speech:
                            if not speech_detected:
                                print("[Listen] Speech detected")
                            speech_detected = True
                            silence_start = None
                        elif speech_detected:
                            if silence_start is None:
                                silence_start = time.time()
                            elif time.time() - silence_start >= silence_threshold:
                                print(f"[Listen] Silence threshold reached ({silence_threshold}s)")
                                break
                    time.sleep(0.01)

            print(f"[Listen] Done: recorded={len(recorded)} frames, speech={speech_detected}")
            if recorded and speech_detected:
                audio = np.concatenate(recorded)
                text = self.voice_recognition.transcribe_audio(audio)
                print(f"[Listen] Transcribed: {text!r}")
                return text
            print("[Listen] No speech detected or no audio")
            return ""
        finally:
            if self.state_manager.is_paused():
                self.state_manager.set_state("paused")
                print("[Listen] Restored paused state")
            else:
                self.state_manager.set_state("listening")
                self.audio_handler.start_stream()
            self.audio_handler.clear_queue()
            self._input_mode = False

    def _process_command(self):
        if self.state in ("recording", "playing") and self._remote_reply_cb is None:
            print(f"[ProcessCommand] Blocked: state={self.state}")
            return
        try:
            with open("lastcommands.txt", "r", encoding="utf-8") as f:
                transcribed_text = f.read().strip()
        except FileNotFoundError:
            print("No transcription file found.")
            return
        if not transcribed_text:
            print("Empty transcription.")
            return
        self.gui._chat_input.add_to_history(transcribed_text)
        if self.mode == "transcription":
            print(f"[Mode] Transcription mode: pasting text")
            paste_text(transcribed_text)
            self.set_state("listening")
            return
        matched_command, matched_vars = self.command_executor.find_matching_command(transcribed_text)
        if matched_command == "__delayed__":
            duration_text = matched_vars.get("duration", "") if matched_vars else ""
            original_key = matched_vars.get("original_key", "") if matched_vars else ""
            self._consume_remote_reply()
            threading.Thread(target=self._execute_delayed_command,
                             args=(duration_text, original_key, transcribed_text), daemon=True).start()
            return
        if matched_command and is_script_command(matched_command):
            print(f"Executing script command: {matched_command}")
            script_name = strip_script_prefix(matched_command)
            self._consume_remote_reply()
            self.script_runner.enqueue(script_name, params=matched_vars, transcribed_text=transcribed_text)
            return
        if matched_command:
            print(f"Executing command: {matched_command}")
            self._consume_remote_reply()
            ok = self.command_executor.execute_command(matched_command)
            self.command_executor.track_command_outcome(transcribed_text, ok)
        else:
            print("No matching command found. Sending to AI Agent.")
            self.command_executor.track_command_outcome(transcribed_text, True)
            threading.Thread(target=self._handle_ai_fallback, args=(transcribed_text,), daemon=True).start()

    def _execute_delayed_command(self, duration_text, original_key, transcribed_text):
        from i18n import t
        lang = getattr(self, "language", "en")
        if self.debug_enabled:
            print(f"[Delayed] _execute_delayed_command: start duration_text='{duration_text}' cmd='{original_key}' state={self.state}")
        seconds = self._parse_delay_duration(duration_text)
        if seconds is None:
            if self.debug_enabled:
                print(f"[Delayed] _execute_delayed_command: parse failed, state={self.state}")
            self.tts.enqueue(t("delayed.parse_error", lang))
            self.set_state("listening")
            return
        duration_str = f"{seconds}s"
        mins = seconds // 60
        if mins >= 1:
            duration_str = f"{mins}m"
        if mins >= 60:
            h = mins // 60
            remaining_m = mins % 60
            duration_str = f"{h}h" + (f"{remaining_m}m" if remaining_m else "")
        self.timer_manager.start(duration_str, command_text=original_key)
        print(f"[Delayed] Scheduled '{original_key}' in {seconds}s")
        self.tts.enqueue(t("delayed.scheduled", lang).replace("{cmd}", original_key))
        if self.debug_enabled:
            print(f"[Delayed] _execute_delayed_command: setting listening, state={self.state}")
        self.set_state("listening")

    def _parse_delay_duration(self, text):
        try:
            from timer_manager import parse_duration
            secs = parse_duration(text)
            if secs > 10:
                return secs
        except Exception:
            log_exc()
        try:
            lang = getattr(self, "language", "en")
            prompt = (
                f"Convert this relative time to seconds: '{text}'. "
                f"Reply ONLY the number, no other text. "
                f"Examples: '10 minuti' -> 600, '1 ora' -> 3600, "
                f"'un ora' -> 3600, '30 secondi' -> 30, '2 ore' -> 7200."
            )
            kwargs = dict(
                model=self.ai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=50,
            )
            msg = call_with_retry(lambda: self.openai_client.chat.completions.create(**kwargs)).choices[0].message
            result = msg.content.strip()
            secs = int(re.search(r'\d+', result).group())
            print(f"[Delayed] AI parsed '{text}' -> {secs}s")
            return secs
        except Exception as e:
            print(f"[Delayed] Duration parse failed: {e}")
            return None

    def _process_delayed_command(self, text):
        if self.debug_enabled:
            print(f"[Delayed] _process_delayed_command: start text='{text}' state={self.state}")
        from utils import is_script_command, strip_script_prefix
        cmd, vars = self.command_executor.find_matching_command(text)
        if self.debug_enabled:
            print(f"[Delayed] _process_delayed_command: matched='{cmd}' is_script={is_script_command(cmd) if cmd else False} state={self.state}")
        if cmd and is_script_command(cmd):
            self.script_runner.enqueue(strip_script_prefix(cmd), params=vars, transcribed_text=text)
        elif cmd:
            self.command_executor.execute_command(cmd)
        if self.debug_enabled:
            print(f"[Delayed] _process_delayed_command: end state={self.state}")

    def _handle_ai_fallback(self, prompt_original):
        self.set_state("waiting")
        if self.blacklist:
            words, phrases = self.blacklist
            lowered = prompt_original.lower()
            clean = lowered

            for phrase in phrases:
                clean = clean.replace(phrase, "")

            for word in words:
                clean = re.sub(r'\b' + re.escape(word) + r'\b', '', clean)

            clean = clean.strip()
            if not clean:
                print(f"[Blacklist] Testo vuoto dopo filtro: '{prompt_original}'")
                self._consume_remote_reply()
                self.tts.enqueue(t("ai.blacklisted", self.language))
                self.set_state("listening")
                return

            if clean != lowered:
                print(f"[Blacklist] Filtrato: '{prompt_original}' -> '{clean}'")
                prompt = clean
            else:
                prompt = prompt_original
        else:
            prompt = prompt_original

        if is_local_url(self.ai_url):
            from resource_monitor import wait_for_resources
            self.set_state("waiting_resources", "Verifica risorse...")
            time.sleep(0.05)
            timeout = self.settings.get("resource_timeout", 300)

            def _res_status(s):
                worst = max(s.items(), key=lambda x: (x[1] / (self.settings.get(f"{x[0]}_max", 80) or 1)))
                self.set_state("waiting_resources", f"{worst[0].upper()} {worst[1]:.0f}%")

            ready = wait_for_resources(self.settings, timeout=timeout,
                                       cancel_check=lambda: self.state != "waiting_resources",
                                       on_status=_res_status)
            if not ready:
                self._consume_remote_reply()
                self.set_state("listening")
                return
            self.set_state("waiting")

        self._ai_lock.acquire()
        tracker = get_tracker(); tracker.start("AI query", "ai")
        try:
            now = time.strftime("%Y-%m-%d (%A) %H:%M:%S")
            base = self.system_message or ""
            date_prefix = t("ai.date_prefix", self.language)
            system_content = f"{base}\n\n{date_prefix}{now}".strip()
            vas_ref = _load_vascript_reference()

            mcp, tools = init_mcp(self.mcp_server_url, timeout=10)

            if not self.allow_ai_scripts and tools:
                tools = [t for t in tools if t["function"]["name"] not in ("interact", "script")]

            import tool_groups
            kw_groups = tool_groups.select_tool_groups(prompt, self.language)
            ai_groups = tool_groups.select_tool_groups_ai(prompt, tools, self.openai_client, self.ai_model)
            groups = ai_groups | kw_groups
            tools = tool_groups.resolve_tool_names(groups, tools,
                                                    getattr(self, 'debug_enabled', False))

            if self.auto_context_selection and not tool_groups.needs_memory(prompt, self.language):
                memory_content = ""
                if self.debug_enabled:
                    print(f"[DEBUG] needs_memory({prompt[:80]}) = False  (skip memory)")
            else:
                memory_content = self.memory.build_content(prompt, mcp, tools)
                if self.debug_enabled:
                    print(f"[DEBUG] needs_memory({prompt[:80]}) = True  (include memory)")

            tools_block = append_tool_descriptions(MCP_PROMPT, tools) if tools else MCP_PROMPT
            if tools:
                mail_tools = {t["function"]["name"] for t in tools}
                if "reply_email" in mail_tools:
                    tools_block += (
                        "\n\nEMAIL TOOLS: When asked to reply/send/forward an email, you MUST use these tools."
                        "\nDO NOT write email text yourself — call the tools immediately."
                        "\n- search_emails(keywords): find the email by sender name, get the msg_id."
                        "\n- reply_email(msg_id, body): reply. Call search_emails() FIRST to get msg_id."
                        "\n- send_email(to, subject, body): compose new email."
                        "\n- forward_email(msg_id, to): forward. Find msg_id with search_emails() first."
                    )
                elif "search_emails" in mail_tools:
                    tools_block += (
                        "\n\nEMAIL: You can search emails with search_emails() but sending/reply is unavailable."
                    )
                browser_tools = {t["function"]["name"] for t in tools}
                if "browser_show" in browser_tools:
                    tools_block += (
                        "\n\nBROWSER AUTH: If a website requires login, use browser_show() to let the user log in manually."
                        "\nNEVER fill credentials yourself — the user handles authentication. Ask the user to log in."
                        "\nAfter login, use browser_check_auth() to verify before proceeding."
                    )
            if self.allow_ai_scripts:
                tools_block += VASSCRIPT_TOOLS_PROMPT + vas_ref
            notes_block = "\n".join(self.context_notes)
            if notes_block:
                notes_block = f"Context notes (low priority, can be ignored if context is full):\n{notes_block}\n\n"
            messages = [
                {"role": "system", "content": notes_block + memory_content + system_content + tools_block},
                {"role": "user", "content": prompt}
            ]
            if self.compress_context:
                lang = self.language or "en"
                messages[0]["content"] = _compress_heuristic(messages[0]["content"], lang)
                messages[1]["content"] = _compress_heuristic(messages[1]["content"], lang)
            kwargs = dict(
                model=self.ai_model,
                messages=messages,
                temperature=0.7,
                max_tokens=max(200, min((self.context_length or 4096) - sum(max(1, self._count_tokens(m["content"])) for m in messages) - (self._count_tokens(json.dumps(tools)) if tools else 0) - 256, max(1024, (self.context_length or 4096) // 2))),
                extra_body={"disable_thinking": True}
            )

            if tools:
                kwargs["tools"] = tools

            ctx_available = (self.context_length or 4096)
            if self.context_length <= 0:
                for _ in range(50):
                    if self.context_length > 0:
                        break
                    time.sleep(0.1)
                if self.context_length <= 0:
                    # Detection may have failed or been skipped; retry once.
                    self._detect_context_length()
                ctx_available = (self.context_length or 4096)
            prompt_tokens_est = sum(max(1, self._count_tokens(m["content"])) for m in messages)
            if tools:
                prompt_tokens_est += self._count_tokens(json.dumps(tools))
            if prompt_tokens_est + kwargs["max_tokens"] > ctx_available:
                if tools and tools_block in messages[0]["content"]:
                    messages[0]["content"] = messages[0]["content"][:messages[0]["content"].rfind(tools_block)].rstrip()
                    kwargs.pop("tools", None)
                    prompt_tokens_est = sum(max(1, self._count_tokens(m["content"])) for m in messages)
                    kwargs["max_tokens"] = max(200, min(ctx_available - prompt_tokens_est - 128, 4096))
                    print(f"[AI] Dropped MCP tools to fit context ({prompt_tokens_est} prompt est, {kwargs['max_tokens']} max_tok)")
                if prompt_tokens_est + kwargs["max_tokens"] > ctx_available:
                    excess = (prompt_tokens_est + kwargs["max_tokens"] - ctx_available) * 2 + 200
                    trim_at = max(500, len(messages[0]["content"]) - excess)
                    messages[0]["content"] = messages[0]["content"][:trim_at]
                    kwargs["max_tokens"] = max(200, ctx_available - self._count_tokens(messages[0]["content"]) - self._count_tokens(messages[1]["content"]) - 128)
                    print(f"[AI] Trimmed system prompt by {excess} chars to fit context")

            print(f"[AI] Payload -> model={self.ai_model}, tools={len(tools) if tools else 0}, system_len={len(messages[0]['content'])}, user_len={len(messages[1]['content'])}, max_tokens={kwargs.get('max_tokens', 'N/A')}")

            if self.debug_enabled:
                sys_txt = messages[0]['content']
                sys_len = len(sys_txt)
                print(f"[Debug] --- AI Request ---")
                print(f"[Debug] System ({sys_len} chars):\n{sys_txt[:1000]}{'...[truncated]' if sys_len > 1000 else ''}")
                print(f"[Debug] User ({len(messages[1]['content'])} chars):\n{messages[1]['content']}")

            # ── Streaming API call ──────────────────────────────────────────
            kwargs["stream"] = True
            kwargs["stream_options"] = {"include_usage": True}
            stream = call_with_retry(lambda: self.openai_client.chat.completions.create(**kwargs))

            content_buffer = ""
            full_content = ""
            tool_calls_acc = {}
            finish_reason = None
            MIN_TTS_WORDS = 8
            CPS = 0.0
            MIN_SECS_LENGTH = 5.0
            _stream_start = time.time()
            # total_enqueued = 0
            
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                finish_reason = chunk.choices[0].finish_reason
            
                if delta.content:
                    content_buffer += delta.content
                    full_content += delta.content
                    buf_words = len(re.sub(r'\s+', ' ', content_buffer.strip()).split())
                    if buf_words >= MIN_TTS_WORDS:
                        n = 0
                        while True:
                            idx = -1
                            for p in ('.', '!', '?'):
                                pos = content_buffer.find(p)
                                if pos != -1 and (idx == -1 or pos < idx):
                                    idx = pos
                            if idx == -1:
                                break
                            sentence = content_buffer[:idx + 1].strip()
                            content_buffer = content_buffer[idx + 1:]
                            if sentence:
                                self.tts.enqueue(sentence)
                                n += 1
                        if n > 0:
                            # if total_enqueued == 0:
                            #     self.tts.pause()    
                            # total_enqueued += n                            
                            # if total_enqueued + n >= 3:
                            #     self.tts.unpause()
                            #     total_enqueued = 0                            
                            if self.debug_enabled:
                                print(f"[Stream] Enqueued {n} sentences , {buf_words} buf words >= {MIN_TTS_WORDS} min)")

                    elapsed = time.time() - _stream_start
                    if elapsed > MIN_SECS_LENGTH:
                        prev_cps = CPS
                        prev_mtw = MIN_TTS_WORDS
                        CPS = ( prev_cps + ( len(full_content) / elapsed ) ) / 2
                        MIN_TTS_WORDS = max(5, min(100, int(CPS * MIN_SECS_LENGTH * 3 )))
                        if self.debug_enabled and (prev_cps != CPS or prev_mtw != MIN_TTS_WORDS):
                            print(f"[Stream] CPS={CPS:.1f} ({prev_cps:.1f}) -> MIN_TTS_WORDS={MIN_TTS_WORDS} ({prev_mtw}), tot_chars={len(full_content)}, elapsed={elapsed:.1f}s")

                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {"id": "", "name": "", "arguments": ""}
                        acc = tool_calls_acc[idx]
                        if tc_delta.id:
                            acc["id"] += tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                acc["name"] += tc_delta.function.name
                            if tc_delta.function.arguments:
                                acc["arguments"] += tc_delta.function.arguments

                if finish_reason:
                    break

            self.tts.unpause()
            remaining = content_buffer.strip()
            if remaining:
                self.tts.enqueue(remaining)
                print(f"[Stream] Remaining enqueued: {len(remaining.split())} words, {len(remaining)} chars")
            elapsed = time.time() - _stream_start
            print(f"[Stream] Done: {len(full_content)} chars in {elapsed:.1f}s (CPS={CPS:.1f}), tool_calls={bool(tool_calls_acc)}, finish={finish_reason}")

            if not finish_reason:
                if not full_content:
                    print(f"[Stream] WARNING: stream ended without finish_reason and empty content — retrying once")
                    try:
                        stream2 = call_with_retry(
                            lambda: self.openai_client.chat.completions.create(**kwargs),
                            log_prefix="[Stream Retry]")
                        for chunk2 in stream2:
                            if not chunk2.choices:
                                continue
                            d2 = chunk2.choices[0].delta
                            if d2.content:
                                full_content += d2.content
                            if d2.tool_calls:
                                for tc_delta in d2.tool_calls:
                                    idx = tc_delta.index
                                    if idx not in tool_calls_acc:
                                        tool_calls_acc[idx] = {"id": "", "name": "", "arguments": ""}
                                    acc = tool_calls_acc[idx]
                                    if tc_delta.id:
                                        acc["id"] += tc_delta.id
                                    if tc_delta.function:
                                        if tc_delta.function.name:
                                            acc["name"] += tc_delta.function.name
                                        if tc_delta.function.arguments:
                                            acc["arguments"] += tc_delta.function.arguments
                            fr2 = chunk2.choices[0].finish_reason
                            if fr2:
                                finish_reason = fr2
                                break
                        if full_content:
                            self.tts.enqueue(full_content)
                            print(f"[Stream] Retry succeeded: {len(full_content)} chars, finish={finish_reason}")
                        else:
                            print(f"[Stream] Retry also returned empty content")
                    except Exception as e:
                        print(f"[Stream] Retry failed: {e}")
                else:
                    print(f"[Stream] WARNING: stream ended without finish_reason but has {len(full_content)} chars — using partial content")

            # ── Handle tool calls ──────────────────────────────────────────
            script_called = False
            ai_response = full_content
            response_from_tool_calls = False
            if tool_calls_acc and finish_reason == "tool_calls":
                tool_calls_list = []
                for idx in sorted(tool_calls_acc.keys()):
                    tc = tool_calls_acc[idx]
                    tc_obj = type("", (), {
                        "id": tc["id"],
                        "function": type("", (), {"name": tc["name"], "arguments": tc["arguments"]})(),
                        "type": "function"
                    })()
                    tool_calls_list.append(tc_obj)
                    print(f"[AI] Tool call: {tc['name']}({tc['arguments'][:200]})")

                script_called = any(
                    tc_obj.function.name == "script" or
                    (tc_obj.function.name == "interact" and
                     any(kw in tc_obj.function.arguments.lower() for kw in ("addevent", "add_event", "listevents", "list_events", "removeevent", "remove_event")))
                    for tc_obj in tool_calls_list
                )

                pseudo_msg = type("", (), {"tool_calls": tool_calls_list, "content": None})()
                msg = execute_mcp_tool_calls(messages, pseudo_msg, mcp, tools, self.openai_client, self.ai_model, gui=self.gui,
                                             context_limit=self.context_length or 32768)
                ai_response = msg.content or ""
                response_from_tool_calls = True

            ai_response = strip_think_tags(ai_response)

            self._consume_remote_reply(strip_markdown(ai_response) or "")

            if ai_response and self.gui:
                self.gui.schedule_signal.emit(
                    lambda t=ai_response: self.gui.show_links(t))

            print(f"AI Agent Response: {ai_response}")

            if self.debug_enabled:
                print(f"[Debug] --- AI Response ({len(ai_response)} chars) ---\n{ai_response}")

            if not script_called:
                self.conversation_history.append({"role": "user", "content": prompt})
                self.conversation_history.append({"role": "assistant", "content": ai_response})

            if ai_response and self.gui:
                self.gui.schedule_signal.emit(
                    lambda: self.gui.show_ai_responses())
            total = sum(len(json.dumps(m, ensure_ascii=False)) for m in self.conversation_history)
            if total > self.memory_tokens * 4:
                self.conversation_history = self.conversation_history[-10:]

            mem_path = os.path.join(get_project_root(), "Allowed_root", "memory.json")
            mem_dir = os.path.join(get_project_root(), "Allowed_root", "memory")
            os.makedirs(mem_dir, exist_ok=True)
            try:
                with self._state_vars_lock:
                    if self._memory_cache is None:
                        try:
                            with open(mem_path, encoding="utf-8") as f:
                                self._memory_cache = json.load(f)
                        except Exception:
                            self._memory_cache = {}
                    existing = self._memory_cache
                saved_ids = []
                for entry in self.conversation_history[-2:]:
                    vid = str(int(time.time() * 1000))
                    hf_path = os.path.join(mem_dir, f"{vid}.json")
                    with open(hf_path, "w", encoding="utf-8") as hf:
                        json.dump({"info": json.dumps(entry, ensure_ascii=False)}, hf, ensure_ascii=False, indent=2)
                    saved_ids.append(vid)
                    time.sleep(0.002)
                old_ids = existing.get("history", [])
                merged_ids = (old_ids + saved_ids)[-20:]
                mem = {"history": merged_ids}
                if "summary_id" in existing:
                    mem["summary_id"] = existing["summary_id"]
                with self._state_vars_lock:
                    self._memory_cache = mem
                with open(mem_path, "w", encoding="utf-8") as f:
                    json.dump(mem, f, ensure_ascii=False, indent=2)
                # Light cleanup: move unreferenced files to archive every N saves
                if len(merged_ids) % 5 == 0:
                    cleanup_orphan_files(mem_dir, merged_ids, existing.get("summary_id", ""))
            except Exception as e:
                print(f"[Memory] Save error: {e}")

            threading.Thread(target=self.memory.classify_message, args=(prompt,), daemon=True).start()
            threading.Thread(target=self.memory.trim_if_needed, daemon=True).start()
            self.gui.update_memory_bar()

            clean_text = strip_markdown(ai_response)
            try:
                path = os.path.join(get_project_root(), "Allowed_root", "last_response.txt")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(clean_text)
            except Exception:
                log_exc()
            done = threading.Event()
            if response_from_tool_calls and clean_text:
                self.tts.enqueue(clean_text)
            self.tts.enqueue("", on_done=done.set)
            done.wait()
            self.set_state("listening")
        except Exception as e:
            body = getattr(e, "body", None)
            if isinstance(body, dict):
                err_body = body.get("error", {})
                if isinstance(err_body, dict):
                    err_msg = err_body.get("message", str(e))
                else:
                    err_msg = str(err_body)
            else:
                err_msg = str(e)
            if "model not found" in err_msg.lower():
                old_model = self.ai_model
                self.ai_model = ""
                self.settings["ai_model"] = ""
                self._auto_select_model()
                if self.ai_model.strip() and self.ai_model != old_model:
                    msg = t("notifications.model_not_found_retry", self.language)
                    msg = msg.replace("{old}", old_model).replace("{new}", self.ai_model)
                    err_msg = self._route_ai_error(msg, priority=8)
                elif not self.ai_model.strip():
                    msg = t("notifications.no_valid_model", self.language)
                    err_msg = self._route_ai_error(msg, priority=9)
            print(f"Error calling AI Agent: {e}")
            self.set_state("listening")
            self._consume_remote_reply(err_msg or "")
            if err_msg:
                self.tts.enqueue(err_msg)
        finally:
            self._ai_lock.release()
            tracker.end("AI query")

    def inject_context(self, text):
        self.context_notes.append(text.strip())
        if len(self.context_notes) > 50:
            self.context_notes = self.context_notes[-50:]

    def inject_memory(self, text):
        import json, time as _time
        root = get_project_root()
        mem_dir = os.path.join(root, "Allowed_root", "memory")
        os.makedirs(mem_dir, exist_ok=True)
        vid = str(int(_time.time() * 1000))
        entry = {"info": json.dumps({"role": "system", "content": text.strip()}, ensure_ascii=False)}
        entry_path = os.path.join(mem_dir, f"{vid}.json")
        with open(entry_path, "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)
        mem_path = os.path.join(root, "Allowed_root", "memory.json")
        existing = {}
        if os.path.exists(mem_path):
            with open(mem_path, encoding="utf-8") as f:
                existing = json.load(f)
        history = existing.get("history", [])
        history.append(vid)
        existing["history"] = history[-20:]
        with open(mem_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        print(f"[Memory] inject_memory: {vid} ({len(text)} chars)")
        return vid

    def _detect_context_length(self):
        ctx = 0
        try:
            import urllib.request
            import json
            url = f"{self.ai_url.rstrip('/')}/models"
            with urllib.request.urlopen(url, timeout=5) as resp:
                models = json.loads(resp.read()).get("data", [])
            if models:
                for m in models:
                    meta = m.get("meta", {})
                    if meta.get("n_ctx", 0) > 0:
                        ctx = meta["n_ctx"]
                        break
                    if m.get("max_seq_len", 0) > 0:
                        ctx = m["max_seq_len"]
                        break
                    status = m.get("status", {})
                    if isinstance(status, dict):
                        args = status.get("args", [])
                        if isinstance(args, list):
                            for i, arg in enumerate(args):
                                if arg in ("-c", "--ctx-size") and i + 1 < len(args):
                                    try:
                                        ctx = int(args[i+1])
                                        break
                                    except ValueError:
                                        pass
                    if ctx > 0:
                        break
                if ctx > 0:
                    self.context_length = ctx
                    print(f"[Settings] Context length detected from model API: {ctx} tokens")
                    return
        except Exception as e:
            print(f"[Settings] Context length auto-detect failed ({e})")

        if self.context_length <= 0:
            try:
                import shlex
                args = shlex.split(self.llama_server_arguments, posix=False)
                for i, arg in enumerate(args):
                    if arg in ("-c", "--ctx-size") and i + 1 < len(args):
                        ctx = int(args[i+1])
                        break
            except Exception:
                log_exc()
            if ctx > 0:
                self.context_length = ctx
                print(f"[Settings] Context length detected from llama arguments: {ctx} tokens")
                return

        if self.context_length <= 0:
            self.context_length = 4096
            print(f"[Settings] Context length fallback: {self.context_length} tokens")

    def _auto_select_model(self):
        ai_model = self.settings.get("ai_model", "").strip()
        llama_path = self.settings.get("llama_server_path", "").strip()
        if ai_model or not llama_path:
            return

        try:
            import urllib.request
            import json
            url = f"{self.ai_url.rstrip('/')}/models"
            with urllib.request.urlopen(url, timeout=5) as resp:
                models = json.loads(resp.read()).get("data", [])

            candidates = []
            for m in models:
                mid = m["id"]
                meta = m.get("meta") or {}
                params = meta.get("n_params", float("inf"))
                if meta.get("size", 0) > 0 and params <= 12_000_000_000:
                    candidates.append((params, mid))

            if not candidates:
                for m in models:
                    mid = m["id"]
                    if "gemma" in mid.lower() or "qwen" in mid.lower():
                        candidates.append((float("inf"), mid))
                        break
                if not candidates and models:
                    candidates = [(float("inf"), models[0]["id"])]

            if not candidates:
                return

            candidates.sort()
            selected = candidates[0][1]
            params = candidates[0][0]
            self.ai_model = selected
            self.settings["ai_model"] = selected
            self._save_setting("ai", "model", selected)
            p_text = f"{params/1e9:.1f}B" if params < float("inf") else "?"
            print(f"[Settings] Auto-selected AI model: {selected} ({p_text} params)")
            from i18n import t
            msg = t("notifications.auto_model_selected", self.language).replace("{model}", selected)
            self._route_ai_ready(msg, priority=6)
        except Exception as e:
            print(f"[Settings] Auto model selection failed: {e}")

    def _route_ai_error(self, msg, priority):
        """Route AI error via router; returns text to speak (or "" if speech handled/skipped)."""
        router = getattr(self, "notification_router", None)
        if router is None:
            if hasattr(self, 'notification_manager'):
                self.notification_manager.add(msg, priority=priority, data={"type": "auth"})
            return msg
        action = router.get_action("ai_error")
        if action in ("notification", "both") and hasattr(self, 'notification_manager'):
            self.notification_manager.add(msg, priority=priority, data={"type": "auth"})
        return msg if action in ("tts", "both") else ""

    def _route_ai_ready(self, msg, priority):
        """Route AI-ready info via router (notification and/or TTS per config)."""
        router = getattr(self, "notification_router", None)
        action = router.get_action("ai_ready") if router else "both"
        if action in ("notification", "both") and hasattr(self, 'notification_manager'):
            self.notification_manager.add(msg, priority=priority, data={"type": "auth"})
        if action in ("tts", "both") and hasattr(self, 'tts') and self.tts and \
                self.state not in ("recording", "playing"):
            self.tts.enqueue(msg)

    def _verify_model_and_autoselect(self):
        """Check if the configured AI model exists on the server; auto-select if not."""
        current = self.ai_model.strip()
        if not current:
            return
        try:
            import urllib.request, json
            url = f"{self.ai_url.rstrip('/')}/models"
            with urllib.request.urlopen(url, timeout=5) as resp:
                models = json.loads(resp.read()).get("data", [])
            model_ids = {m["id"] for m in models}
            if current in model_ids:
                return
            print(f"[Settings] Model '{current}' not found on server, auto-selecting...")
            old = current
            self.ai_model = ""
            self.settings["ai_model"] = ""
            self._auto_select_model()
            if self.ai_model.strip() and self.ai_model != old:
                from i18n import t
                msg = t("notifications.model_not_found_retry", self.language)
                msg = msg.replace("{old}", old).replace("{new}", self.ai_model)
                self._route_ai_ready(msg, priority=8)
        except Exception as e:
            print(f"[Settings] Model verification failed: {e}")

    def get_tts_position(self):
        return self.tts.get_position()

def main():
        import argparse
        parser = argparse.ArgumentParser(description="VASS Voice Assistant")
        parser.add_argument("--compress-memory", action="store_true", help="Comprimi memory.json tramite AI e poi esci")
        parser.add_argument("--version", action="version", version=f"VASS v{__version__}")
        args, _ = parser.parse_known_args()
    
        # Load settings first to get GUI params
        import configparser
        import os
        
        settings_file = "config/settings.ini"
        config = configparser.ConfigParser()
        abs_path = os.path.abspath(settings_file)
        layout_window, layout_limits = VassApp._load_layout()
        gui_x = layout_window["x"]
        gui_y = layout_window["y"]
        gui_width = layout_window["width"]
        gui_height = layout_window["height"]
        if os.path.exists(abs_path):
            config.read(abs_path, encoding="utf-8")
            gui_font_family = config.get("gui", "font_family", fallback="Segoe UI")
            gui_font_size = config.getint("gui", "font_size", fallback=12)
            gui_language = config.get("locale", "language", fallback="en")
            compact_mode = config.getboolean("gui", "compact_mode", fallback=False)
        else:
            gui_font_family, gui_font_size = "Segoe UI", 12
            gui_language = "en"
            compact_mode = False
        
        if args.compress_memory:
            import subprocess
            llama_proc = None
            llama_path = config.get("llamacpp", "llama_server_path", fallback="").strip()
            if llama_path:
                exe = os.path.join(llama_path, "llama-server.exe")
                if os.path.isfile(exe):
                    cwd = config.get("llamacpp", "llama_server_working_directory", fallback="").strip() or llama_path
                    args_str = config.get("llamacpp", "llama_server_arguments", fallback="").strip()
                    cmd = [exe] + (args_str.split() if args_str else [])
                    print(f"[llama.cpp] Avvio: {' '.join(cmd)} (cwd={cwd})")
                    llama_proc = subprocess.Popen(cmd, cwd=cwd, creationflags=subprocess.CREATE_NO_WINDOW)
                    time.sleep(5)
                else:
                    print(f"[llama.cpp] llama-server.exe non trovato in: {llama_path}")
            ai_url = config.get("ai", "url", fallback="http://127.0.0.1:8080/v1")
            ai_model = config.get("ai", "model", fallback="gemma-4-E2B-it-Q8_0")
            client = OpenAI(base_url=ai_url, api_key="not-needed")
            mem_tokens = config.getint("ai", "memory_tokens", fallback=5000)
            app = VassApp.__new__(VassApp)
            app.openai_client = client
            app.ai_model = ai_model
            app.memory_tokens = mem_tokens
            app._ai_lock = threading.Lock()
            app.memory_mode = "full"
            from memory_manager import MemoryManager
            app.memory = MemoryManager(app)
            try:
                app.memory.trim_if_needed(force=True)
            except Exception as e:
                print(f"[Memory] Compression failed: {e}")
            if llama_proc:
                llama_proc.kill()
                llama_proc.wait(timeout=5)
            sys.exit(0)
    
        import ctypes
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QIcon
        from PySide6.QtCore import QTimer
    
        qapp = QApplication(sys.argv)
        ico_path = os.path.join(get_project_root(), "vass.ico")
        if sys.platform == "win32":
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("logicheneurali.vass.app")
                import winreg
                key = winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Classes\AppUserModelId\logicheneurali.vass.app")
                winreg.SetValueEx(key, "IconUri", 0, winreg.REG_EXPAND_SZ, ico_path)
                winreg.CloseKey(key)
            except Exception:
                log_exc()
        if os.path.exists(ico_path):
            qapp.setWindowIcon(QIcon(ico_path))
    
        gui = VassGUI(
            app=None, 
            x=gui_x, y=gui_y, 
            width=gui_width, height=gui_height,
            font_family=gui_font_family, font_size=gui_font_size,
            language=gui_language
        )
        if compact_mode:
            gui.set_compact_mode(True, from_restore=True)
            gui._compact_toggle.setChecked(True)

        # Defer heavy init so the event loop paints the window first
        _state = {"app": None, "thread": None}
    
        def _start_vass():
            _state["app"] = VassApp(gui=gui)
            gui.app = _state["app"]
            gui.update_button_tooltip()
            gui._refresh_debug_border()
            _state["app"].notification_manager.gui = gui
            gui.chat_text_signal.connect(_state["app"]._process_chat_text)
            gui.mic_pressed.connect(_state["app"].trigger_mic_recording)
            gui.set_state("loading")
            def _run_safe():
                try:
                    _state["app"].run()
                except BaseException as e:
                    import traceback
                    with open("log/crash.log", "a") as f:
                        f.write(f"\n=== CRASH in _run_safe ({time.strftime('%Y-%m-%d %H:%M:%S')}) ===\n")
                        traceback.print_exc(file=f)
                    print(f"\n[FATAL] Unrecoverable error: {e}")
                    traceback.print_exc()
            _state["thread"] = threading.Thread(target=_run_safe)
            _state["thread"].start()
    
        def _cleanup():
            a = _state["app"]
            t = _state["thread"]
            if a:
                a.stop()
                a.running = False
            if t:
                t.join(timeout=3)
    
        qapp.aboutToQuit.connect(_cleanup)
        QTimer.singleShot(0, _start_vass)
        sys.exit(qapp.exec())
    

if __name__ == "__main__":
    main()

