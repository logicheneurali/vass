import json
import subprocess
import time
import threading
from collections import deque
import re
import warnings
warnings.filterwarnings("ignore", message=".*dropout option.*")
warnings.filterwarnings("ignore", message=".*num_layers.*")
warnings.filterwarnings("ignore", message=".*weight_norm.*deprecated.*")
try:
    import winsound
except ImportError:
    pass
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
        pass
    print(msg)
    sys.exit(1)

os.makedirs("log", exist_ok=True)
_faulthandler_file = open("log/faulthandler.log", "w")
faulthandler.enable(_faulthandler_file)

from audio_handler import AudioHandler
from voice_recognition import VoiceRecognition
from command_executor import CommandExecutor
from openai import OpenAI
from utils import call_with_retry, execute_mcp_tool_calls, init_mcp, is_process_running, kill_port, kill_process, beep, paste_text, parse_blacklist, is_local_url, strip_markdown, cleanup_orphan_files, is_script_command, strip_script_prefix, strip_think_tags, start_llama_server, clean_for_tts
from gui import VassGUI
from i18n import t
from script_engine import VASScript
from tts_engine import TtsEngine
from event_reminder import EventReminder
from idle_tracker import IdleTracker

import builtins as _builtins
_original_print = _builtins.print
def _ts_print(*args, **kwargs):
    _original_print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}]", *args, **kwargs)
_builtins.print = _ts_print


class _TeeOutput:
    def __init__(self, *files):
        self._files = files
    def write(self, text):
        for f in self._files:
            f.write(text)
            f.flush()
    def flush(self):
        for f in self._files:
            f.flush()
    def isatty(self):
        return False


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
        pass


def _load_version():
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "VERSION")) as f:
            return f.read().strip()
    except Exception:
        return "0.0.0"

__version__ = _load_version()


MEMORY_SUMMARIZATION_PROMPT = (
    "Summarize these conversations concisely. "
    "All entries contain personal user data — extract and merge the key facts. "
    "Output only a short JSON summary with key 'summary'."
)

MCP_PROMPT = (
    "\n\nYou have access to MCP tools:"
    "\n- browse(url): read text content from any web page (httpx, fast)"
    "\n- webfetch(url): read from JavaScript pages using a full browser (Playwright, slower)"
    "\n- websearch(query): search DuckDuckGo for results in JSON format"
    "\n- interact(code): run VASScript code (e.g. interact(\"say('hello')\") speaks via TTS)"
    "\n- read_file(path): read files from user storage"
    "\n- write_file(path, content): write files to user storage"
    "\n- current_time(): get current date and time"
)


SAVETAGS_PROMPT = (
    "IMPORTANT: After every response, you MUST call savetags() to classify "
    "the user's message with tags from this list ONLY: "
    "personal_data, health, finance, family, pets, contacts, "
    "preferences, personal_interests, purchases, orders, bills, invoices, "
    "work, education, favorite_music, food, home, "
    "personal_means_of_transport, deliveries, travel, tech, events, sales, generic. "
    "Pass them as comma-separated string: savetags('food,health')\n\n"
)


def _load_vascript_reference():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Allowed_root", "VASCRIPT_REFERENCE.md")
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        return f"\n\n--- VASScript Reference ---\n{content}\n--- End Reference ---\n"
    except Exception:
        return ""


class ScriptQueue:
    """FIFO serial script execution queue.  One script runs at a time;
    additional requests are queued and processed in order."""

    def __init__(self, app):
        self.app = app
        self._queue = deque()
        self._lock = threading.Lock()
        self._active_engine = None
        self._running = False
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()

    def enqueue(self, name_or_code=None, code=None, params=None, result_callback=None, source="", transcribed_text=None, silent=False):
        item = (name_or_code, code, params, result_callback, source, transcribed_text, silent)
        with self._lock:
            self._queue.append(item)
            qlen = len(self._queue)
        if qlen == 1:
            self.app.set_state("running_script", silent_gui=silent)
        elif qlen > 1:
            print(f"[ScriptQueue] Queued {source or 'script'} (position {qlen})")

    def cancel_current(self):
        with self._lock:
            engine = self._active_engine
        if engine:
            engine.stop()

    def cancel_all(self):
        with self._lock:
            self._queue.clear()
            engine = self._active_engine
        if engine:
            engine.stop()

    def _worker(self):
        while True:
            if self.app.state in ("waiting", "waiting_resources"):
                time.sleep(0.1)
                continue
            with self._lock:
                if not self._queue:
                    item = None
                else:
                    item = self._queue.popleft()
            if item is None:
                time.sleep(0.1)
                continue
            name_or_code, code, params, result_callback, source, transcribed_text, silent = item
            self._execute_script(name_or_code, code, params, result_callback, transcribed_text, silent)
            time.sleep(0.1)

    def _execute_script(self, name_or_code, code, params, result_callback, transcribed_text=None, silent=False):
        self.app._execute_script_impl(name_or_code, code, params, result_callback, self, transcribed_text, silent)


class VassApp:
    def __init__(self, gui, settings_file="config/settings.ini"):
        self.gui = gui
        self.state = "loading"
        self._ai_lock = threading.Lock()
        self.settings_file = settings_file
        self.settings = self._load_settings()
        inp = int(self.settings.get("input_device", -1))
        out = int(self.settings.get("output_device", -1))
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
        self._summary_cache = {}
        self.debug_enabled = self.settings.get("debug_enabled", False)
        self.overflow_strategy = self.settings.get("overflow_strategy", "truncate")
        self.gui_x = self.settings["gui_x"]
        self.gui_y = self.settings["gui_y"]
        self.gui_width = self.settings["gui_width"]
        self.gui_height = self.settings["gui_height"]
        self.gui_font_family = self.settings["gui_font_family"]
        self.gui_font_size = self.settings["gui_font_size"]
        self.command_similarity = self.settings["command_similarity"]
        self.word_learning_enabled = self.settings.get("word_learning_enabled", False)
        tts_volume = self.settings.get("volume", 0.95) * self.settings.get("output_volume", 1.0)
        self.tts = TtsEngine(
            gui=gui,
            state_getter=lambda: self.state,
            state_setter=self.set_state,
            tts_volume=tts_volume,
            language=self.language,
            output_device=out,
        )
        self.tts.preload()
        self.gui.volume_top_bar.set_volume(tts_volume)
        self.mcp_server_url = self.settings["mcp_server_url"]
        self.mcp_process = None
        self.memory_tokens = self.settings.get("memory_tokens", 2000)
        self.blacklist = parse_blacklist(self.settings.get("blacklist", ""))
        self.llama_server_path = self.settings.get("llama_server_path", "")
        self.llama_server_working_directory = self.settings.get("llama_server_working_directory", "")
        self.llama_server_arguments = self.settings.get("llama_server_arguments", "")
        self.llama_autostart = self.settings.get("llama_autostart", "false").lower() == "true"
        self.llama_process = None

        self.noise_pause = self.settings.get("noise_pause", False)
        self.noise_pause_threshold = self.settings.get("noise_pause_threshold", 0.002)
        self.noise_pause_duration = self.settings.get("noise_pause_duration", 30)
        self._noise_high_frames = 0
        self._nf_print_counter = 0
        self._silent_frames = 0
        self._auto_paused_at = None
        self._running_noise_floor = None
        self._memory_cache = None

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
        if self.context_length <= 0:
            threading.Thread(target=self._detect_context_length, daemon=True).start()
        if not self.ai_model.strip() and self.llama_server_path.strip():
            threading.Thread(target=self._auto_select_model, daemon=True).start()
        self.running = False
        self._trim_lock = threading.Lock()
        self.script_queue = ScriptQueue(self)
        self.state_lock = threading.RLock()
        from timer_manager import TimerManager
        self.timer_manager = TimerManager(self)
        from notification_manager import NotificationManager
        self.notification_manager = NotificationManager()
        self.context_notes = []
        self.conversation_history = []
        self.mode = "chat" if self.settings.get("lastmode", "c") == "c" else "trascrizione"
        self.memory_mode = "full"
        self._input_mode = False
        self._ensure_memory_file()

    @staticmethod
    def _ensure_memory_file():
        dir_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Allowed_root")
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
            print(f"[Memory] Created directory {dir_path}")
        mem_dir = os.path.join(dir_path, "memory")
        if not os.path.exists(mem_dir):
            os.makedirs(mem_dir)
        path = os.path.join(dir_path, "memory.json")
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"history": []}, f, indent=2)
            print(f"[Memory] Created empty {path}")

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
            path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "settings.ini")
            cfg.read(path, encoding="utf-8")
            if not cfg.has_section(section):
                cfg.add_section(section)
            cfg.set(section, key, value)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                cfg.write(f)
        except Exception:
            pass

    def set_memory_mode(self, mode):
        self.memory_mode = mode
        print(f"[MemoryMode] Switched to '{mode}'")

    def _load_settings(self):
        config = configparser.ConfigParser()
        abs_path = os.path.abspath(self.settings_file)
        print(f"[Settings] Looking for: {abs_path}")
        
        result = {}
        
        if os.path.exists(abs_path):
            config.read(abs_path, encoding="utf-8")
            result["language"] = config.get("locale", "language", fallback="en")
            result["lastmode"] = config.get("gui", "lastmode", fallback="c")
            result["sensitivity"] = config.getfloat("wakeword", "sensitivity", fallback=0.005)
            result["wakeword"] = config.get("wakeword", "wakeword", fallback="vass")
            result["ai_url"] = config.get("ai", "url", fallback="http://127.0.0.1:8080/v1")
            try:
                import keyring
                cm_key = keyring.get_password("vass", "api_key")
                result["api_key"] = cm_key if cm_key else config.get("ai", "api_key", fallback="")
            except Exception:
                result["api_key"] = config.get("ai", "api_key", fallback="")
            result["ai_model"] = config.get("ai", "model", fallback="")
            result["system_message"] = config.get("ai", "system_message", fallback="")
            result["allow_ai_scripts"] = config.get("ai", "allow_ai_scripts", fallback="false").lower() == "true"
            result["context_length"] = config.getint("ai", "context_length", fallback=0)
            result["overflow_strategy"] = config.get("ai", "overflow_strategy", fallback="truncate")
            
            result["gui_x"] = config.getint("gui", "x", fallback=1541)
            result["gui_y"] = config.getint("gui", "y", fallback=52)
            result["gui_width"] = config.getint("gui", "width", fallback=220)
            result["gui_height"] = config.getint("gui", "height", fallback=32)
            result["gui_font_family"] = config.get("gui", "font_family", fallback="Segoe UI")
            result["gui_font_size"] = config.getint("gui", "font_size", fallback=12)
            result["command_similarity"] = config.getfloat("commands", "similarity", fallback=0.6)
            result["word_learning_enabled"] = config.get("commands", "word_learning_enabled", fallback="false").lower() == "true"
            result["volume"] = config.getfloat("tts", "volume", fallback=0.95)
            result["mcp_server_url"] = config.get("ai", "mcp_server_url", fallback="http://localhost:9988")
            result["memory_tokens"] = config.getint("ai", "memory_tokens", fallback=2000)
            result["blacklist"] = config.get("ai", "blacklist", fallback="")
            result["llama_server_path"] = config.get("llamacpp", "llama_server_path", fallback="")
            result["llama_server_working_directory"] = config.get("llamacpp", "llama_server_working_directory", fallback="")
            result["llama_server_arguments"] = config.get("llamacpp", "llama_server_arguments", fallback="")
            result["llama_autostart"] = config.get("llamacpp", "llama_autostart", fallback="false")
            result["cpu_max"] = config.getfloat("resources", "cpu_max", fallback=75.0)
            result["ram_max"] = config.getfloat("resources", "ram_max", fallback=99.0)
            result["gpu_max"] = config.getfloat("resources", "gpu_max", fallback=75.0)
            result["vram_max"] = config.getfloat("resources", "vram_max", fallback=99.0)
            result["resource_timeout"] = config.getint("resources", "resource_timeout", fallback=10)
            result["reminder_advance"] = config.getint("events", "reminder_advance", fallback=3600)
            result["noise_pause"] = config.get("noise", "noise_pause", fallback="false").lower() == "true"
            result["noise_pause_threshold"] = config.getfloat("noise", "noise_pause_threshold", fallback=0.002)
            result["noise_pause_duration"] = config.getint("noise", "noise_pause_duration", fallback=30)
            result["input_device"] = config.getint("audio", "input_device", fallback=-1)
            result["output_device"] = config.getint("audio", "output_device", fallback=-1)
            result["input_volume"] = config.getfloat("audio", "input_volume", fallback=1.0)
            result["output_volume"] = config.getfloat("audio", "output_volume", fallback=1.0)
            result["calendar_enabled"] = config.get("google", "calendar_enabled", fallback="false")
            result["calendar_sync_enabled"] = config.get("google", "calendar_sync_enabled", fallback="false")
            result["calendar_sync_minutes"] = config.getint("google", "calendar_sync_minutes", fallback=30)
            result["calendar_sync_days"] = config.getint("google", "calendar_sync_days", fallback=7)
            result["gmail_enabled"] = config.get("google", "gmail_enabled", fallback="false")
            result["gmail_sync_minutes"] = config.getint("google", "gmail_sync_minutes", fallback=5)
            result["gmail_max_results"] = config.getint("google", "gmail_max_results", fallback=10)
            result["google_home_enabled"] = config.get("google", "google_home_enabled", fallback="false")
            result["google_home_model_id"] = config.get("google", "google_home_model_id", fallback="")
            result["google_home_device_id"] = config.get("google", "google_home_device_id", fallback="")

            result["debug_enabled"] = config.get("debug", "debug_enabled", fallback="false").lower() == "true"
            result["debug_log_max_kb"] = config.getint("debug", "debug_log_max_kb", fallback=1024)

            from setup_google import is_google_configured
            if not is_google_configured():
                result["calendar_enabled"] = "false"
                result["calendar_sync_enabled"] = "false"
                result["gmail_enabled"] = "false"
                result["google_home_enabled"] = "false"
                print("[Settings] Google OAuth2 not configured — all Google services disabled")

            print(f"[Settings] Loaded -> Model: {result['ai_model']} | Lang: {result['language']}")
            return result
        else:
            print(f"[Settings] File not found. Creating default at {abs_path}")
            lang = "en"
            result["language"] = lang
            result["lastmode"] = "c"
            result["sensitivity"] = 0.005
            result["wakeword"] = "vass"
            result["ai_url"] = "http://127.0.0.1:8080/v1"
            result["api_key"] = ""
            result["ai_model"] = ""
            result["system_message"] = "You are a helpful and concise voice assistant."
            result["allow_ai_scripts"] = False
            result["context_length"] = 0
            result["overflow_strategy"] = "truncate"
            result["gui_x"] = 1541
            result["gui_y"] = 52
            result["gui_width"] = 220
            result["gui_height"] = 32
            result["gui_font_family"] = "Segoe UI"
            result["gui_font_size"] = 12
            result["command_similarity"] = 0.6
            result["word_learning_enabled"] = False
            result["volume"] = 0.95
            result["mcp_server_url"] = "http://localhost:9988"
            result["memory_tokens"] = 2000
            result["blacklist"] = ""
            result["llama_server_path"] = ""
            result["llama_server_working_directory"] = ""
            result["llama_server_arguments"] = ""
            result["llama_autostart"] = "false"
            result["cpu_max"] = 75.0
            result["ram_max"] = 99.0
            result["gpu_max"] = 75.0
            result["vram_max"] = 99.0
            result["resource_timeout"] = 10
            result["reminder_advance"] = 3600
            result["noise_pause"] = False
            result["noise_pause_threshold"] = 0.002
            result["noise_pause_duration"] = 30
            result["input_device"] = -1
            result["output_device"] = -1
            result["input_volume"] = 1.0
            result["output_volume"] = 1.0
            result["calendar_enabled"] = "false"
            result["calendar_sync_enabled"] = "false"
            result["calendar_sync_minutes"] = 30
            result["calendar_sync_days"] = 7
            result["gmail_enabled"] = "false"
            result["gmail_sync_minutes"] = 5
            result["gmail_max_results"] = 10
            result["google_home_enabled"] = "false"
            result["google_home_model_id"] = ""
            result["google_home_device_id"] = ""
            result["debug_enabled"] = False
            result["debug_log_max_kb"] = 1024

            config["locale"] = {"language": lang}
            config["gui"] = {
                "x": "1541", "y": "52", "width": "220", "height": "32",
                "font_family": "Segoe UI", "font_size": "12", "lastmode": "c"
            }
            config["wakeword"] = {"sensitivity": "0.005", "wakeword": "vass"}
            config["commands"] = {"similarity": "0.6", "word_learning_enabled": "false"}
            config["tts"] = {"tts_engine": "kokoro", "volume": "0.95"}
            config["llamacpp"] = {
                "llama_server_path": "",
                "llama_server_working_directory": "",
                "llama_server_arguments": "",
                "llama_autostart": "false"
            }
            config["ai"] = {
                "url": "http://127.0.0.1:8080/v1",
                "api_key": "",
                "model": "gemma-4-E2B-it-Q8_0",
                "system_message": "You are a helpful and concise voice assistant.",
                "mcp_server_url": "http://localhost:9988",
                "blacklist": "",
                "memory_tokens": "2000",
                "allow_ai_scripts": "false",
                "context_length": "0",
                "overflow_strategy": "truncate"
            }
            config["resources"] = {"cpu_max": "75", "ram_max": "99", "gpu_max": "75", "vram_max": "99", "resource_timeout": "10"}
            config["events"] = {"reminder_advance": "3600"}
            config["noise"] = {
                "noise_pause": "false",
                "noise_pause_threshold": "0.002",
                "noise_pause_duration": "30"
            }
            config["audio"] = {"input_device": "-1", "output_device": "-1", "input_volume": "1.0", "output_volume": "1.0"}
            config["google"] = {
                "calendar_enabled": "false",
                "calendar_sync_enabled": "false",
                "calendar_sync_minutes": "30",
                "calendar_sync_days": "7",
                "gmail_enabled": "false",
                "gmail_sync_minutes": "5",
                "gmail_max_results": "10",
                "google_home_enabled": "false",
                "google_home_model_id": "",
                "google_home_device_id": "",
                "calendar_setup": "start"
            }
            config["debug"] = {
                "debug_enabled": "false",
                "debug_log_max_kb": "1024"
            }
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                config.write(f)
            return result

    def set_state(self, new_state, detail="", silent_gui=False):
        with self.state_lock:
            self.state = new_state
            if not silent_gui:
                try:
                    self.gui.set_state(new_state, detail)
                except Exception as e:
                    with open("log/crash.log", "a") as f:
                        f.write(f"gui.set_state failed: {e}\n")

    def handle_button_press(self):
        try:
            self._handle_button_press_impl()
        except Exception as e:
            print(f"[ButtonPress] Error: {e}")

    def _handle_button_press_impl(self):
        with self.state_lock:
            current = self.state
            if current == "listening":
                self.set_state("paused")
                self.audio_handler.stop_stream()
            elif current == "recording":
                self.audio_handler.stop_recording()
                self.audio_handler.recorded_buffer.clear()
                self.set_state("paused")
                self.audio_handler.stop_stream()
            elif current == "paused":
                self._noise_high_frames = 0
                self._auto_paused_at = None
                self._running_noise_floor = None
                self.audio_handler.start_stream()
                self.set_state("listening")
            elif current == "playing":
                self.stop_playback()
                self.set_state("listening")
            elif current == "running_script":
                self.script_queue.cancel_current()
            elif current in ("waiting",):
                pass
            elif current == "waiting_resources":
                self.set_state("listening")

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
                        old_url = self.ai_url
                        self.ai_url = self.settings["ai_url"]
                        self.system_message = self.settings.get("system_message", "")
                        self.allow_ai_scripts = self.settings.get("allow_ai_scripts", False)
                        self.context_length = self.settings.get("context_length", 0)
                        self.overflow_strategy = self.settings.get("overflow_strategy", "truncate")
                        self.debug_enabled = self.settings.get("debug_enabled", False)
                        self.voice_recognition.debug_enabled = self.debug_enabled
                        if self.ai_url != old_url:
                            self.openai_client = OpenAI(base_url=self.ai_url, api_key=self.ai_api_key or "not-needed")
                        self.mcp_server_url = self.settings["mcp_server_url"]
                        self.memory_tokens = self.settings.get("memory_tokens", 2000)
                        self.blacklist = parse_blacklist(self.settings.get("blacklist", ""))
                        self.llama_server_path = self.settings.get("llama_server_path", "")
                        self.llama_autostart = self.settings.get("llama_autostart", "false").lower() == "true"
                        tv = self.settings.get("volume", 0.95)
                        ov = self.settings.get("output_volume", 1.0)
                        effective = tv * ov
                        self.tts.update_settings(effective)
                        self.gui.volume_top_bar.set_volume(effective)
                        self.voice_recognition.input_volume = self.settings.get("input_volume", 1.0)
                        self.noise_pause = self.settings.get("noise_pause", False)
                        self.noise_pause_threshold = self.settings.get("noise_pause_threshold", 0.002)
                        self.noise_pause_duration = self.settings.get("noise_pause_duration", 30)
                        if not self.noise_pause and self._auto_paused_at is not None:
                            self.audio_handler.start_stream()
                            self._noise_high_frames = 0
                            self._auto_paused_at = None
                            self._running_noise_floor = None
                            self.set_state("listening")
                            print("[Noise] Auto-pause disabled via settings, resuming")
                        self.gui_x = self.settings["gui_x"]
                        self.gui_y = self.settings["gui_y"]
                        self.gui_width = self.settings["gui_width"]
                        self.gui_height = self.settings["gui_height"]
                        self.gui.schedule(0, lambda: self.gui.setGeometry(
                            self.gui_x, self.gui_y, self.gui_width, self.gui_height))
                        self.gui.schedule(0, self.gui._clamp_to_screen)
                        print(f"[Watch] Settings reloaded from {abs_path}")
            except Exception as e:
                print(f"[Watch] Settings watcher error: {e}")

    def _watch_script_queue(self):
        queue_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "exec_queue.json")
        result_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "exec_result.json")
        while self.running:
            time.sleep(1)
            try:
                if not os.path.exists(queue_path):
                    continue
                with open(queue_path, "r", encoding="utf-8") as f:
                    request = json.load(f)
                request_id = request.get("id")
                script_name = request.get("script", "")
                code = request.get("code", "")
                if not request_id or (not script_name and not code):
                    continue
                os.remove(queue_path)

                label = script_name or "inline"
                print(f"[ScriptQueue] Enqueued: {label}")

                def _write_result(r):
                    result = {"id": request_id, "result": r}
                    with open(result_path, "w", encoding="utf-8") as f:
                        json.dump(result, f)
                    print(f"[ScriptQueue] Completed: {label} -> {r.get('status')}")

                self._run_script(name_or_code=script_name if script_name else None, result_callback=_write_result, code=code or None)
            except Exception as e:
                print(f"[Watch] Script queue watcher error: {e}")

    def save_gui_position(self, x, y):
        config = configparser.ConfigParser()
        abs_path = os.path.abspath(self.settings_file)
        try:
            if os.path.exists(abs_path):
                config.read(abs_path, encoding="utf-8")
            if "gui" not in config:
                config["gui"] = {}
            config["gui"]["x"] = str(x)
            config["gui"]["y"] = str(y)
            with open(abs_path, "w") as f:
                config.write(f)
        except Exception as e:
            print(f"[Settings] Could not save position: {e}")

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
            pass

        if self.settings.get("debug_enabled", False):
            os.makedirs("log", exist_ok=True)
            max_bytes = int(self.settings.get("debug_log_max_kb", 1024)) * 1024
            _rotate_debug_log("log/debug.log", max_bytes)
            self._debug_file = open("log/debug.log", "a", encoding="utf-8")
            self._debug_original_stdout = sys.stdout
            files = [self._debug_file]
            if sys.stdout and sys.stdout.isatty():
                files.insert(0, sys.__stdout__)
            sys.stdout = _TeeOutput(*files)

        print(f"VASS v{__version__} - Voice assistant software")
        self.voice_recognition.load_models()
        self.set_state("listening")
        self.running = True
        self.audio_handler.start_stream()
        threading.Thread(target=self._watch_commands_file, daemon=True).start()
        threading.Thread(target=self._watch_settings_file, daemon=True).start()
        threading.Thread(target=self._watch_script_queue, daemon=True).start()
        if self.mcp_server_url and os.path.exists(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mcp_server", "run_server.py")):
            threading.Thread(target=self._start_mcp_server, daemon=True).start()
        if self.llama_server_path.strip() and self.llama_autostart:
            threading.Thread(target=self._start_llamacpp, daemon=True).start()
        if self.event_reminder:
            threading.Thread(target=self.event_reminder.run, daemon=True).start()
        threading.Thread(target=self._health_check_loop, daemon=True).start()
        threading.Thread(target=self._health_check_once, daemon=True).start()
        if self.settings.get("calendar_sync_enabled", "false").lower() == "true":
            threading.Thread(target=self._sync_calendar_loop, daemon=True).start()
        if self.settings.get("gmail_enabled", "false").lower() == "true":
            threading.Thread(target=self._sync_gmail_loop, daemon=True).start()
        self.gui.set_mode_display(self.mode)
        self.gui.update_memory_bar()

        # Double beep to indicate app is ready
        vol = self.settings.get("volume", 0.95)
        beep(vol)
        time.sleep(0.15)
        beep(vol)
        while self.running:
            try:
                if self._input_mode:
                    time.sleep(0.05)
                    continue
                frame = self.audio_handler.get_frame()
                if frame is None:
                    self._silent_frames += 1
                    if self._silent_frames > 300 and not self._auto_paused_at and self.state == "listening":
                        print("[Audio] Stream appears dead, restarting...")
                        self.audio_handler.stop_stream()
                        time.sleep(0.1)
                        self.audio_handler.start_stream()
                        self._silent_frames = 0
                else:
                    self._silent_frames = 0
                if self._auto_paused_at is not None:
                    elapsed = time.time() - self._auto_paused_at
                    if elapsed >= self.noise_pause_duration:
                        print(f"[Noise] Checking noise floor after {self.noise_pause_duration}s pause...")
                        self.audio_handler.start_stream()
                        time.sleep(0.3)
                        nf_samples = []
                        for _ in range(100):
                            f = self.audio_handler.get_frame()
                            if f is not None:
                                nf_samples.append(float(np.sqrt(np.mean(f**2))))
                            else:
                                time.sleep(0.01)
                        if nf_samples:
                            current_nf = sum(nf_samples) / len(nf_samples)
                            print(f"[Noise] Current noise floor: {current_nf:.6f} (threshold: {self.noise_pause_threshold})")
                            if current_nf < self.noise_pause_threshold:
                                print(f"[Noise] Auto-resuming: noise floor dropped below threshold")
                                self._noise_high_frames = 0
                                self._auto_paused_at = None
                                self._running_noise_floor = None
                                self.set_state("listening")
                                continue
                            else:
                                print(f"[Noise] Still noisy, staying paused for another {self.noise_pause_duration}s")
                                self.audio_handler.stop_stream()
                                self._auto_paused_at = time.time()
                        else:
                            print(f"[Noise] Check: no audio samples captured, staying paused")
                            self.audio_handler.stop_stream()
                            self._auto_paused_at = time.time()
                if frame is not None:
                    with self.state_lock:
                        if self.state == "recording":
                            rms = float(np.sqrt(np.mean(frame**2)))
                            self.gui.volume_signal.emit(rms)
                        if self.state in ["paused", "playing", "waiting", "waiting_resources", "running_script"]:
                            continue
                        
                    if not self.audio_handler.is_recording:
                        try:
                            wake = self.voice_recognition.detect_wake_word(frame)
                        except Exception as ex:
                            with open("crash.log", "a") as f:
                                f.write(f"detect_wake_word error: {ex}\n")
                            wake = False
                        if wake and self.state == "listening":
                            self._noise_high_frames = 0
                            self._nf_print_counter = 0
                            self._running_noise_floor = None
                            print("Wake word detected! Switching to recording mode...")
                            try:
                                beep(self.settings.get("volume", 0.95))
                            except Exception as ex:
                                with open("crash.log", "a") as f:
                                    f.write(f"Beep error: {ex}\n")
                            self.audio_handler.clear_queue()
                            self.audio_handler.start_recording()
                            self.voice_recognition.reset_model()
                            self.set_state("recording")
                            continue

                        if not wake and self.state == "listening":
                            nf = float(np.sqrt(np.mean(frame**2)))
                            if self._running_noise_floor is None:
                                self._running_noise_floor = nf
                            else:
                                self._running_noise_floor = 0.99 * self._running_noise_floor + 0.01 * nf
                            nf = self._running_noise_floor
                            self._nf_print_counter += 1
                            if self.noise_pause and nf > self.noise_pause_threshold:
                                self._noise_high_frames += 1
                                frames_per_sec = 50
                                max_frames = self.noise_pause_duration * frames_per_sec
                                if self._noise_high_frames >= max_frames:
                                    print(f"[Noise] Auto-pausing: noise floor {nf:.4f} > {self.noise_pause_threshold} for {self.noise_pause_duration}s")
                                    self.audio_handler.stop_stream()
                                    self._auto_paused_at = time.time()
                                    self._noise_high_frames = 0
                                    self.set_state("paused")
                            else:
                                self._noise_high_frames = max(0, self._noise_high_frames - 1)
                            if self._nf_print_counter >= 250:
                                self._nf_print_counter = 0
                                if nf > self.noise_pause_threshold and self.debug_enabled:
                                    print(f"[NoiseFloor] {nf:.6f} (threshold: {self.noise_pause_threshold})")

                    self.audio_handler.process_recording(frame)
                    
                    if not self.audio_handler.is_recording and len(self.audio_handler.recorded_buffer) > 0:
                        self.set_state("listening")
                        self._transcribe_and_process()
                        self.audio_handler.clear_queue()
                        
            except KeyboardInterrupt:
                print("\nShutting down Vass...")
                self.running = False
                break
            except Exception as e:
                import traceback
                with open("crash.log", "a") as f:
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
        self._mcp_thread = McpServerThread()
        self._mcp_thread.start()
        time.sleep(2)

    def _health_check_loop(self):
        import httpx
        while self.running:
            time.sleep(60)
            if not self.running:
                break
            health_url = f"{self.ai_url.rstrip('/')}/health"
            try:
                r = httpx.get(health_url, timeout=5)
                ok = r.status_code == 200
                if self.debug_enabled:
                    print(f"[Health] {health_url} -> {r.status_code}")
            except Exception as e:
                ok = False
                if self.debug_enabled:
                    print(f"[Health] {health_url} unreachable: {e}")
            self.gui.schedule_signal.emit(lambda ok=ok: self.gui.set_health_status(ok))

    def _health_check_once(self):
        time.sleep(3)  # brief delay for server startup
        import httpx
        health_url = f"{self.ai_url.rstrip('/')}/health"
        try:
            r = httpx.get(health_url, timeout=5)
            ok = r.status_code == 200
            if self.debug_enabled:
                print(f"[Health] {health_url} -> {r.status_code}")
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
        events_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Allowed_root", "events.json")
        try:
            gcal.sync_to_vass(events_path, days=days)
        except Exception as e:
            print(f"[GCal] Sync error: {e}")
        while self.running:
            time.sleep(minutes * 60)
            try:
                gcal.sync_to_vass(events_path, days=days)
            except Exception as e:
                print(f"[GCal] Sync error: {e}")

    def _sync_gmail_loop(self):
        time.sleep(5)
        from gmail_handler import GmailHandler
        gmail = GmailHandler()
        minutes = int(self.settings.get("gmail_sync_minutes", 5))
        max_results = int(self.settings.get("gmail_max_results", 10))
        seen_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Allowed_root", "gmail_seen.json")
        print(f"[Gmail] Sync started (every {minutes}m, max {max_results} msgs)")
        try:
            new = gmail.check_new(seen_path, max_results=max_results)
            self._announce_emails(new)
        except Exception as e:
            print(f"[Gmail] Sync error: {e}")
        while self.running:
            time.sleep(minutes * 60)
            try:
                new = gmail.check_new(seen_path, max_results=max_results)
                self._announce_emails(new)
            except Exception as e:
                print(f"[Gmail] Sync error: {e}")

    def _announce_emails(self, emails):
        if not emails:
            return
        for em in emails:
            from_parts = clean_for_tts(em['from'], 80)
            subj = clean_for_tts(em['subject'], 120)
            snip = clean_for_tts(em['snippet'], 200, " " + t("notifications.email_truncated", self.language))
            text = f"Nuova email da {from_parts}. Oggetto: {subj}. {snip}"
            self.tts.enqueue(text)
            notif = t("notifications.new_email", self.language).replace("{from}", from_parts).replace("{subject}", subj)
            priority = 7 if em.get("important") else 5
            self.notification_manager.add(notif, priority=priority)

    def _start_llamacpp(self):
        proc, status = start_llama_server(
            self.llama_server_path,
            self.llama_server_working_directory,
            self.llama_server_arguments,
        )
        if proc:
            self.llama_process = proc
        else:
            print(f"[llama.cpp] {status}")

    def stop(self):
        self.running = False
        try:
            _faulthandler_file.close()
        except Exception:
            pass
        if hasattr(self, '_debug_file') and self._debug_file:
            sys.stdout = getattr(self, '_debug_original_stdout', sys.__stdout__)
            self._debug_file.close()
        import subprocess as _sp
        if self.llama_process:
            kill_process(self.llama_process)
            self.llama_process = None

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
                pass
        return len(text) // 2

    def _estimate_tokens(self, text):
        return self._count_tokens(text)

    def _estimate_system_overhead(self):
        overhead = self._count_tokens(self.system_message or "") + 50
        overhead += self._count_tokens(self._build_memory_content())
        if self.allow_ai_scripts:
            overhead += self._count_tokens(MCP_PROMPT)
            overhead += self._count_tokens(_load_vascript_reference())
        return overhead

    def _process_chat_text(self, text):
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

        self.tts.speak("Testo riassunto. Eseguo la richiesta.")
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
        import sounddevice as sd
        import numpy as np
        import webrtcvad
        self._input_mode = True
        self.audio_handler.stop_stream()
        self.audio_handler.clear_queue()
        try:
            sample_rate = 16000
            frame_size = 320
            vad = webrtcvad.Vad(2)
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
                        audio_int16 = (frame * 32767).astype(np.int16).tobytes()
                        try:
                            is_speech = vad.is_speech(audio_int16[:frame_size * 2], sample_rate)
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
            self.audio_handler.start_stream()
            self.audio_handler.clear_queue()
            self._input_mode = False

    def _process_command(self):
        try:
            with open("lastcommands.txt", "r", encoding="utf-8") as f:
                transcribed_text = f.read().strip()
        except FileNotFoundError:
            print("No transcription file found.")
            return
        if not transcribed_text:
            print("Empty transcription.")
            return
        if self.mode == "trascrizione":
            print(f"[Mode] Transcription mode: pasting text")
            paste_text(transcribed_text)
            self.set_state("listening")
            return
        matched_command, matched_vars = self.command_executor.find_matching_command(transcribed_text)
        if matched_command == "__delayed__":
            duration_text = matched_vars.get("duration", "") if matched_vars else ""
            original_key = matched_vars.get("original_key", "") if matched_vars else ""
            threading.Thread(target=self._execute_delayed_command,
                             args=(duration_text, original_key, transcribed_text), daemon=True).start()
            return
        if matched_command and is_script_command(matched_command):
            print(f"Executing script command: {matched_command}")
            script_name = strip_script_prefix(matched_command)
            self._run_script(script_name, params=matched_vars, transcribed_text=transcribed_text)
            return
        if matched_command:
            print(f"Executing command: {matched_command}")
            ok = self.command_executor.execute_command(matched_command)
            self.command_executor.track_command_outcome(transcribed_text, ok)
        else:
            print("No matching command found. Sending to AI Agent.")
            self.command_executor.track_command_outcome(transcribed_text, True)
            threading.Thread(target=self._handle_ai_fallback, args=(transcribed_text,), daemon=True).start()

    def _execute_delayed_command(self, duration_text, original_key, transcribed_text):
        from i18n import t
        lang = getattr(self, "language", "en")
        seconds = self._parse_delay_duration(duration_text)
        if seconds is None:
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
        self.set_state("listening")

    def _parse_delay_duration(self, text):
        try:
            from timer_manager import parse_duration
            secs = parse_duration(text)
            if secs > 10:
                return secs
        except Exception:
            pass
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
        from utils import is_script_command, strip_script_prefix
        cmd, vars = self.command_executor.find_matching_command(text)
        if cmd and is_script_command(cmd):
            self._run_script(strip_script_prefix(cmd), params=vars, transcribed_text=text)
        elif cmd:
            self.command_executor.execute_command(cmd)

    def _run_script(self, name_or_code=None, result_callback=None, code=None, params=None, transcribed_text=None, silent=False):
        self.script_queue.enqueue(name_or_code, code, params, result_callback, "direct", transcribed_text, silent=silent)

    def _execute_script_impl(self, name_or_code, code, params, result_callback, queue, transcribed_text=None, silent=False):
        import json as _json
        script_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
        if code is not None:
            script_name = "inline"
            is_file = False
        elif name_or_code:
            script_path = os.path.join(script_dir, f"{name_or_code}.vass")
            is_file = os.path.exists(script_path)
            script_name = name_or_code if is_file else "inline"
        else:
            err_msg = t("scripts.not_found", self.language).replace("{name}", "inline")
            if result_callback:
                result_callback({"status": "error", "detail": err_msg})
            return

        def _auth_get(script):
            try:
                import keyring
                raw = keyring.get_password("vass-auth", script)
                return _json.loads(raw) if raw else {}
            except Exception:
                return {}

        def _auth_set(script, data):
            import keyring
            if is_file and script_path:
                try:
                    import hashlib
                    with open(script_path, "rb") as f:
                        data["_hash"] = hashlib.sha256(f.read()).hexdigest()
                except Exception:
                    pass
            keyring.set_password("vass-auth", script, _json.dumps(data))

        def _migrate_auth_ini():
            ini_path = os.path.join(script_dir, "auth.ini")
            if not os.path.exists(ini_path):
                return
            cfg = configparser.ConfigParser()
            cfg.read(ini_path)
            migrated = False
            for sec in cfg.sections():
                existing = _auth_get(sec)
                for opt in cfg.options(sec):
                    if cfg.getboolean(sec, opt):
                        existing[opt] = True
                _auth_set(sec, existing)
                migrated = True
            if migrated:
                os.remove(ini_path)
                print(f"[Auth] Migrato auth.ini in Credential Manager")

        _migrate_auth_ini()

        def _load_auth(func_name=None):
            data = _auth_get(script_name)
            if is_file and script_path and "_hash" in data:
                try:
                    import hashlib
                    with open(script_path, "rb") as f:
                        current_hash = hashlib.sha256(f.read()).hexdigest()
                    if current_hash != data["_hash"]:
                        import keyring
                        keyring.delete_password("vass-auth", script_name)
                        return None
                except Exception:
                    pass
            if data.get("_all_"):
                return "all"
            if func_name and data.get(func_name):
                return "function"
            return None

        def _save_auth(func_name, allow_all=False):
            data = _auth_get(script_name)
            if allow_all:
                data["_all_"] = True
            else:
                data[func_name] = True
            _auth_set(script_name, data)

        def _auth_callback(name, func):
            cached = _load_auth(func)
            if cached in ("all", "function"):
                return cached
            result = self.gui.request_auth(name, func)
            if result == "function":
                _save_auth(func)
            elif result == "all":
                _save_auth(func, allow_all=True)
            elif result == "once":
                result = "function"
            return result

        code_text = None
        if code is not None:
            code_text = code.replace('\u2018', "'").replace('\u2019', "'").replace('\u201c', '"').replace('\u201d', '"')
            print(f"[VASScript] Esecuzione inline ({len(code_text)} chars):")
            for line in code_text.strip().split("\n"):
                print(f"  {line}")
        elif is_file:
            with open(script_path, encoding="utf-8") as f:
                code_text = f.read()
            print(f"[VASScript] Esecuzione file: {script_path}")
        else:
            err_msg = t("scripts.not_found", self.language).replace("{name}", name_or_code or "inline")
            print(f"[VASScript] {err_msg}")
            if result_callback:
                result_callback({"status": "not_found", "script": name_or_code, "detail": err_msg, "message": err_msg})
            else:
                threading.Thread(target=self.tts.speak, args=(err_msg,), daemon=True).start()
            return

        if code_text:
            self.set_state("running_script", silent_gui=silent)
            script_error = None
            engine = None
            try:
                engine = VASScript(
                    self, script_name=script_name, auth_callback=_auth_callback,
                    line_callback=lambda c, t: [
                        self.set_state("running_script", f"{c}/{t}", silent_gui=silent),
                        (None if silent else self.gui.memory_bar.set_value(c, 1, t))
                    ]
                )
                queue._active_engine = engine
                if params:
                    engine.vars.update(params)
                engine.execute(code_text)
                output_vars = {k: v for k, v in engine.vars.items() if not k.startswith("_")}
                if result_callback:
                    result_callback({"status": "ok", "script": script_name, "vars": output_vars, "message": "Script executed successfully."})
            except Exception as e:
                script_error = str(e)
                print(f"[VASScript] Error: {script_error}")
                if result_callback:
                    result_callback({"status": "error", "script": script_name, "detail": script_error, "message": "Script failed: " + script_error})
            finally:
                queue._active_engine = None
                if len(self.script_queue._queue) == 0:
                    self.set_state("listening", silent_gui=silent)

            if script_error and not result_callback:
                threading.Thread(target=self.tts.speak, args=(f"Errore script: {script_error}",), daemon=True).start()

    def _handle_ai_fallback(self, prompt):
        self.set_state("waiting")
        if self.blacklist:
            lowered = prompt.lower()
            found = [w for w in self.blacklist if w in lowered]
            if found:
                print(f"[Blacklist] Bloccato: parole {found} in '{prompt}'")
                threading.Thread(target=self.tts.speak, args=(t("ai.blacklisted", self.language),), daemon=True).start()
                self.set_state("listening")
                return

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
                self.set_state("listening")
                return
            self.set_state("waiting")

        self._ai_lock.acquire()
        try:
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            base = self.system_message or ""
            date_prefix = t("ai.date_prefix", self.language)
            system_content = f"{base}\n\n{date_prefix}{now}".strip()
            vas_ref = _load_vascript_reference()

            mcp, tools = init_mcp(self.mcp_server_url, timeout=10)

            if not self.allow_ai_scripts and tools:
                tools = [t for t in tools if t["function"]["name"] not in ("interact", "script")]

            memory_content = self._build_memory_content(mcp, tools)

            tools_block = MCP_PROMPT + vas_ref if self.allow_ai_scripts else ""
            notes_block = "\n".join(self.context_notes)
            if notes_block:
                notes_block = f"Context notes (low priority, can be ignored if context is full):\n{notes_block}\n\n"
            messages = [
                {"role": "system", "content": notes_block + memory_content + system_content + tools_block},
                {"role": "user", "content": prompt}
            ]
            kwargs = dict(
                model=self.ai_model,
                messages=messages,
                temperature=0.7,
                max_tokens=max(200, min((self.context_length or 4096) - sum(max(1, self._count_tokens(m["content"])) for m in messages) - (2500 if tools else 0) - 256, 4096)),
                extra_body={"disable_thinking": True}
            )

            if tools:
                kwargs["tools"] = tools

            ctx_available = (self.context_length or 4096)
            prompt_tokens_est = sum(max(1, self._count_tokens(m["content"])) for m in messages)
            if tools:
                prompt_tokens_est += 2500
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

            overflow_retries = 3
            msg = None
            while overflow_retries > 0:
                try:
                    msg = call_with_retry(lambda: self.openai_client.chat.completions.create(**kwargs)).choices[0].message
                    break
                except Exception as e:
                    err_str = str(e)
                    if "exceed_context" in err_str.lower() or "10240" in err_str or "10266" in err_str:
                        overflow_retries -= 1
                        if "tools" in kwargs and tools:
                            kwargs.pop("tools", None)
                            messages[0]["content"] = messages[0]["content"][:messages[0]["content"].rfind(tools_block)].rstrip() if tools_block in messages[0]["content"] else messages[0]["content"]
                            kwargs["messages"] = messages
                            kwargs["max_tokens"] = max(200, (self.context_length or 4096) - sum(max(1, self._count_tokens(m["content"])) for m in messages) - 128)
                            print(f"[AI] Context overflow - retrying without tools (attempt {4 - overflow_retries}/3)")
                        else:
                            excess = len(messages[0]["content"]) // 4
                            messages[0]["content"] = messages[0]["content"][:-excess] if excess > 0 else messages[0]["content"][:2000]
                            kwargs["messages"] = messages
                            kwargs["max_tokens"] = max(200, (self.context_length or 4096) - sum(max(1, self._count_tokens(m["content"])) for m in messages) - 128)
                            print(f"[AI] Context overflow - trimming system content (attempt {4 - overflow_retries}/3)")
                    else:
                        raise e
            if not msg:
                raise RuntimeError("Failed to get AI response after retrying context overflow")
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    print(f"[AI] Tool call: {tc.function.name}({tc.function.arguments[:200]})")
            script_called = any(tc.function.name == "script" or
                (tc.function.name == "interact" and
                 any(kw in tc.function.arguments.lower() for kw in ("addevent", "listevents", "removeevent")))
                for tc in (msg.tool_calls or []))
            msg = execute_mcp_tool_calls(messages, msg, mcp, tools, self.openai_client, self.ai_model)

            ai_response = msg.content or ""
            ai_response = strip_think_tags(ai_response)

            print(f"AI Agent Response: {ai_response}")

            if self.debug_enabled:
                print(f"[Debug] --- AI Response ({len(ai_response)} chars) ---\n{ai_response}")

            if not script_called:
                self.conversation_history.append({"role": "user", "content": prompt})
                self.conversation_history.append({"role": "assistant", "content": ai_response})
            total = sum(len(json.dumps(m, ensure_ascii=False)) for m in self.conversation_history)
            if total > self.memory_tokens * 4:
                self.conversation_history = self.conversation_history[-10:]

            mem_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Allowed_root", "memory.json")
            mem_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Allowed_root", "memory")
            os.makedirs(mem_dir, exist_ok=True)
            try:
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
                self._memory_cache = mem
                with open(mem_path, "w", encoding="utf-8") as f:
                    json.dump(mem, f, ensure_ascii=False, indent=2)
                # Light cleanup: move unreferenced files to archive every N saves
                if len(merged_ids) % 5 == 0:
                    cleanup_orphan_files(mem_dir, merged_ids, existing.get("summary_id", ""))
            except Exception as e:
                print(f"[Memory] Save error: {e}")

            threading.Thread(target=self._classify_message, args=(prompt,), daemon=True).start()

            threading.Thread(target=self._trim_memory_if_needed, daemon=True).start()

            self.gui.update_memory_bar()

            clean_text = strip_markdown(ai_response)
            try:
                path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Allowed_root", "last_response.txt")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(clean_text)
            except Exception:
                pass
            self.tts.speak_nowait(clean_text)
            self.tts._tts_done.wait()
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
            print(f"Error calling AI Agent: {e}")
            self.set_state("listening")
            threading.Thread(target=self.tts.speak, args=(err_msg,), daemon=True).start()
        finally:
            self._ai_lock.release()

    def inject_context(self, text):
        self.context_notes.append(text.strip())
        if len(self.context_notes) > 50:
            self.context_notes = self.context_notes[-50:]

    def inject_memory(self, text):
        import json, time as _time
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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

    def _build_memory_content(self, mcp=None, tools=None):
        if self.memory_mode == "none":
            return ""
        if mcp is None or tools is None:
            from utils import init_mcp
            mcp, tools = init_mcp(self.mcp_server_url, timeout=10)
        if not mcp or not tools:
            return ""
        for t_def in tools:
            if t_def["function"]["name"] == "read_file":
                try:
                    result = mcp.call_tool("read_file", {"path": "memory.json"})
                    text = result.get("content", [{}])[0].get("text", "")
                    mem_data = json.loads(text) if text else {}
                    parts = []
                    if self.memory_mode == "full":
                        summary_text = "No Info"
                        summary_id = mem_data.get("summary_id", "")
                        if summary_id:
                            sf_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Allowed_root", "memory", f"{summary_id}.json")
                            if os.path.exists(sf_path):
                                with open(sf_path, encoding="utf-8") as sf:
                                    summary_text = json.load(sf).get("info", "")
                            if summary_text and summary_text != "No Info":
                                cached = self._summary_cache.get(summary_id)
                                if cached:
                                    summary_text = cached
                                elif self._count_tokens(summary_text) > 500:
                                    summary_text = self._compress_summary(summary_text, summary_id, mem_data)
                                    if summary_text:
                                        self._summary_cache[summary_id] = summary_text
                        parts.append(f"summary : {summary_text}")
                    for vid in mem_data.get("history", []):
                        hf_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Allowed_root", "memory", f"{vid}.json")
                        if os.path.exists(hf_path):
                            try:
                                with open(hf_path, encoding="utf-8") as hf:
                                    entry = json.load(hf).get("info", "")
                                entry_data = json.loads(entry)
                                role = "user" if entry_data.get("role") == "user" else "assistant"
                                parts.append(f"{role}: {entry_data['content']}")
                            except Exception:
                                pass
                    if parts:
                        return "\n\nPrevious conversations:\n" + "\n".join(parts)
                except Exception:
                    pass
                break
        return ""

    def _compress_summary(self, summary_text, summary_id, mem_data):
        import json as _json
        try:
            prompt = (
                "Condense this summary to under 500 tokens. "
                "Keep ALL key facts, names, dates, preferences. "
                "Output ONLY the condensed text, no JSON, no commentary.\n\n"
                f"{summary_text}"
            )
            resp = call_with_retry(lambda: self.openai_client.chat.completions.create(
                model=self.ai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=500,
                extra_body={"disable_thinking": True}
            ), log_prefix="[Summary]")
            compressed = (resp.choices[0].message.content or "").strip()
            if compressed:
                print(f"[Summary] Compressed {len(summary_text)} -> {len(compressed)} chars")
                mem_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Allowed_root", "memory")
                sf_path = os.path.join(mem_dir, f"{summary_id}.json")
                with open(sf_path, "w", encoding="utf-8") as sf:
                    _json.dump({"info": compressed}, sf, ensure_ascii=False, indent=2)
                return compressed
        except Exception as e:
            print(f"[Summary] Compression failed: {e}")
        return summary_text

    def _detect_context_length(self):
        try:
            import httpx
            url = f"{self.ai_url.rstrip('/')}/models"
            with httpx.Client(timeout=5) as client:
                resp = client.get(url)
            models = resp.json().get("data", [])
            if models:
                ctx = 0
                for m in models:
                    meta = m.get("meta", {})
                    if meta.get("n_ctx", 0) > 0:
                        ctx = meta["n_ctx"]
                        break
                    if m.get("max_seq_len", 0) > 0:
                        ctx = m["max_seq_len"]
                        break
                if ctx > 0:
                    self.context_length = ctx
                    print(f"[Settings] Context length detected from model: {ctx} tokens")
                    return
        except Exception as e:
            print(f"[Settings] Context length auto-detect failed ({e})")
        if self.context_length <= 0:
            self.context_length = 4096
            print(f"[Settings] Context length fallback: {self.context_length} tokens")

    def _auto_select_model(self):
        ai_model = self.settings.get("ai_model", "").strip()
        llama_path = self.settings.get("llama_server_path", "").strip()
        if ai_model or not llama_path:
            return

        try:
            import httpx
            url = f"{self.ai_url.rstrip('/')}/models"
            with httpx.Client(timeout=5) as client:
                resp = client.get(url)
            models = resp.json().get("data", [])

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
            if hasattr(self, 'notification_manager'):
                self.notification_manager.add(msg, priority=6)
            if hasattr(self, 'tts') and self.tts:
                self.tts.enqueue(msg)
        except Exception as e:
            print(f"[Settings] Auto model selection failed: {e}")

    def _classify_message(self, user_message):
        print(f"[Classify] Starting classification for: {user_message[:80]}...")
        try:
            import sys as _sys
            _mcp_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mcp_server", "src")
            if _mcp_src not in _sys.path:
                _sys.path.insert(0, _mcp_src)
            from mcpgoal.tools.memory_tags import TAG_WEIGHTS
            from utils import init_mcp
            mcp, _ = init_mcp(self.mcp_server_url, timeout=30)
            if not mcp:
                print("[Classify] MCP not available")
                return
        except Exception as e:
            print(f"[Classify] Init error: {e}")
            return

        entry_id = ""
        assistant_text = ""
        history = []
        mem_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Allowed_root", "memory.json")
        mem_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Allowed_root", "memory")
        try:
            with open(mem_path, encoding="utf-8") as f:
                mem_data = json.load(f)
            history = mem_data.get("history", [])
            if len(history) >= 2:
                entry_id = history[-1]
                user_id = history[-2]
                for vid, role_label in [(user_id, "user"), (entry_id, "assistant")]:
                    hf = os.path.join(mem_dir, f"{vid}.json")
                    if os.path.exists(hf):
                        try:
                            with open(hf, encoding="utf-8") as hfp:
                                info = json.loads(json.load(hfp).get("info", "{}"))
                            if info.get("role") == "assistant":
                                assistant_text = info.get("content", "")
                        except Exception:
                            pass
            elif history:
                entry_id = history[-1]
        except Exception:
            pass

        tag_list = ", ".join(sorted(TAG_WEIGHTS.keys()))
        if assistant_text:
            classify_prompt = (
                f"Classify this conversation with 1-3 comma-separated tags ONLY from: {tag_list}\n\n"
                f"User: \"{user_message[:400]}\"\n"
                f"Assistant: \"{assistant_text[:400]}\"\n\n"
                f"Rules:\n"
                f"- Return ONLY 1-3 most relevant tags, nothing else.\n"
                f"- If the conversation is generic/chatty, return ONLY 'generic'.\n"
                f"- Example travel chat: travel,personal_interests\n"
                f"- Example health question: health\n"
                f"- Example small talk: generic"
            )
        else:
            classify_prompt = (
                f"Classify this user message with 1-3 comma-separated tags ONLY from: {tag_list}\n\n"
                f"Message: \"{user_message[:500]}\"\n\n"
                f"Rules:\n"
                f"- Return ONLY 1-3 most relevant tags, nothing else.\n"
                f"- If the message is generic/chatty, return ONLY 'generic'.\n"
                f"- Example travel chat: travel,personal_interests\n"
                f"- Example health question: health\n"
                f"- Example small talk: generic"
            )
        try:
            resp = self.openai_client.chat.completions.create(
                model=self.ai_model,
                messages=[{"role": "user", "content": classify_prompt}],
                temperature=0.1,
                max_tokens=50,
                extra_body={"disable_thinking": True}
            )
            raw = (resp.choices[0].message.content or "").strip().lower()
            tags = [t.strip() for t in raw.split(",") if t.strip() and t.strip() in TAG_WEIGHTS][:3]
            if tags:
                tags_str = ",".join(tags)
                result = mcp.call_tool("savetags", {"tags": tags_str, "entry_id": entry_id})
                content = result.get("content", [{}])[0].get("text", str(result))
                print(f"[Classify] Tags: {tags} -> {content} (AI response)")
                if len(history) >= 2:
                    user_entry_id = history[-2]
                    mcp.call_tool("savetags", {"tags": tags_str, "entry_id": user_entry_id})
                    print(f"[Classify] Also tagged user entry {user_entry_id}")
            else:
                print(f"[Classify] AI returned unusable tags: '{raw}'")
        except Exception as e:
            print(f"[Classify] Error: {e}")

    def _trim_memory_if_needed(self):
        if not self._trim_lock.acquire(blocking=False):
            print("[Memory] Trim already in progress, skip")
            return
        try:
            path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Allowed_root", "memory.json")
            mem_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Allowed_root", "memory")
            if not os.path.exists(path):
                return

            try:
                with open(path, encoding="utf-8") as f:
                    old = json.load(f)
            except Exception:
                return

            history_ids = old.get("history", [])
            summary_id = old.get("summary_id", "")
            if not history_ids:
                return

            total_size = os.path.getsize(path)
            for vid in history_ids:
                hf_path = os.path.join(mem_dir, f"{vid}.json")
                if os.path.exists(hf_path):
                    total_size += os.path.getsize(hf_path)
            if summary_id:
                sf_path = os.path.join(mem_dir, f"{summary_id}.json")
                if os.path.exists(sf_path):
                    total_size += os.path.getsize(sf_path)

            threshold = self.memory_tokens * 2
            if total_size < threshold:
                return
            print(f"[Memory] Total size {total_size} > threshold {threshold}, compressing...")
            mtime_before = os.path.getmtime(path)

            allowed_root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Allowed_root")
            tags_path = os.path.join(allowed_root, "memory_tags.json")
            tagged_ids = set()
            if os.path.exists(tags_path):
                try:
                    with open(tags_path, encoding="utf-8") as f:
                        tags_data = json.load(f)
                    tagged_ids = {e["id"] for e in tags_data.get("entries", []) if e.get("relevance", 0) >= 10}
                except Exception:
                    pass

            def _find_entry(vid):
                hf_path = os.path.join(mem_dir, f"{vid}.json")
                if os.path.exists(hf_path):
                    return hf_path
                archive_root = os.path.join(mem_dir, "archive")
                if os.path.isdir(archive_root):
                    for month_dir in os.listdir(archive_root):
                        candidate = os.path.join(archive_root, month_dir, f"{vid}.json")
                        if os.path.exists(candidate):
                            return candidate
                return None

            tagged_ids_list = sorted(tagged_ids)
            if not tagged_ids_list:
                return

            history_content = []
            for vid in tagged_ids_list[:100]:
                entry_path = _find_entry(vid)
                if entry_path:
                    try:
                        with open(entry_path, encoding="utf-8") as hf:
                            entry = json.load(hf).get("info", "")
                        history_content.append(json.loads(entry))
                    except Exception:
                        pass

            if not history_content:
                return

            # Load existing summary
            old_summary = ""
            summary_id = old.get("summary_id", "")
            if summary_id:
                sf_path = os.path.join(mem_dir, f"{summary_id}.json")
                if os.path.exists(sf_path):
                    try:
                        with open(sf_path, encoding="utf-8") as sf:
                            old_summary = json.load(sf).get("info", "")
                    except Exception:
                        pass

            prompt = MEMORY_SUMMARIZATION_PROMPT
            if old_summary:
                prompt += "\n\nExisting summary to build upon:\n" + old_summary
            prompt += f"\n\nTagged conversations ({len(history_content)} entries):\n" + json.dumps(history_content, ensure_ascii=False)
            prompt += "\n\nAfter summarizing, save your result using the writeinfo() function. Example: writeinfo('{\"summary\": \"...\"}'). The function returns an ID — include it in your response to confirm success."

            print(f"[Memory] Summarization request -> prompt_len={len(prompt)}, entries={len(history_content)}")
            resp = call_with_retry(lambda: self.openai_client.chat.completions.create(
                model=self.ai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                extra_body={"disable_thinking": True}
            ))
            summary_text = (resp.choices[0].message.content or "").strip()
            print(f"[Memory] Summarization response -> {summary_text[:200]}")
            if not summary_text:
                print("[Memory] Trim: AI returned empty summary, skipping")
                return
            try:
                parsed = json.loads(summary_text)
                if isinstance(parsed, dict) and "summary" in parsed:
                    summary_text = json.dumps(parsed["summary"], ensure_ascii=False)
            except (json.JSONDecodeError, ValueError):
                pass

            if os.path.getmtime(path) != mtime_before:
                print("[Memory] Trim: file modified during compression, skipping write")
                return

            # Save summary as a new info file
            new_sid = str(int(time.time() * 1000))
            sf_path = os.path.join(mem_dir, f"{new_sid}.json")
            with open(sf_path, "w", encoding="utf-8") as sf:
                json.dump({"info": summary_text}, sf, ensure_ascii=False, indent=2)

            # Update memory.json: keep last 6 history IDs, set summary_id
            new_history_ids = history_ids[-6:]
            new_data = {"history": new_history_ids, "summary_id": new_sid}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(new_data, f, ensure_ascii=False, indent=2)

            # Move unreferenced files to archive
            referenced = set(new_history_ids) | {new_sid} | tagged_ids
            if summary_id:
                referenced.add(summary_id)
            now_ts = time.time()
            archive_date = time.strftime("%Y-%m", time.localtime(now_ts))
            archive_dir = os.path.join(mem_dir, "archive", archive_date)
            os.makedirs(archive_dir, exist_ok=True)
            for fname in os.listdir(mem_dir):
                if fname.endswith(".json"):
                    fid = fname[:-5]
                    if fid not in referenced:
                        try:
                            src = os.path.join(mem_dir, fname)
                            dst = os.path.join(archive_dir, fname)
                            import shutil
                            shutil.move(src, dst)
                        except OSError:
                            pass

            # Cleanup archives older than 6 months
            archive_root = os.path.join(mem_dir, "archive")
            if os.path.isdir(archive_root):
                cutoff_ts = now_ts - (180 * 86400)
                for entry in os.listdir(archive_root):
                    entry_path = os.path.join(archive_root, entry)
                    if os.path.isdir(entry_path):
                        try:
                            entry_date = time.mktime(time.strptime(entry, "%Y-%m"))
                            if entry_date < cutoff_ts:
                                shutil.rmtree(entry_path)
                                print(f"[Memory] Cleaned old archive: {entry}")
                        except (ValueError, OSError):
                            pass

            print(f"[Memory] Trimmed to {os.path.getsize(path)} bytes, {len(new_history_ids)} history entries kept")
        except Exception as e:
            print(f"[Memory] Trim failed: {e}")
        finally:
            self._trim_lock.release()

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
        
        if os.path.exists(abs_path):
            config.read(abs_path, encoding="utf-8")
            gui_x = config.getint("gui", "x", fallback=1541)
            gui_y = config.getint("gui", "y", fallback=52)
            gui_width = config.getint("gui", "width", fallback=220)
            gui_height = config.getint("gui", "height", fallback=32)
            gui_font_family = config.get("gui", "font_family", fallback="Segoe UI")
            gui_font_size = config.getint("gui", "font_size", fallback=12)
            gui_language = config.get("locale", "language", fallback="en")
        else:
            gui_x, gui_y, gui_width, gui_height = 1541, 52, 220, 32
            gui_font_family, gui_font_size = "Segoe UI", 12
            gui_language = "en"
        
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
            mem_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Allowed_root", "memory.json")
            mem_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Allowed_root", "memory")
            if os.path.exists(mem_path):
                with open(mem_path, encoding="utf-8") as f:
                    old = json.load(f)
                history_ids = old.get("history", [])
                # Load history from individual files
                history_content = []
                for vid in history_ids:
                    hf_path = os.path.join(mem_dir, f"{vid}.json")
                    if os.path.exists(hf_path):
                        try:
                            with open(hf_path, encoding="utf-8") as hf:
                                entry = json.load(hf).get("info", "")
                            history_content.append(json.loads(entry))
                        except Exception:
                            pass
                # Load existing summary
                old_summary = ""
                summary_id = old.get("summary_id", "")
                if summary_id:
                    sf_path = os.path.join(mem_dir, f"{summary_id}.json")
                    if os.path.exists(sf_path):
                        try:
                            with open(sf_path, encoding="utf-8") as sf:
                                old_summary = json.load(sf).get("info", "")
                        except Exception:
                            pass
                if history_content:
                    prompt = MEMORY_SUMMARIZATION_PROMPT
                    if old_summary:
                        prompt += "\n\nExisting summary to build upon:\n" + old_summary
                    prompt += "\n\nNew conversations:\n" + json.dumps(history_content, ensure_ascii=False)
                    prompt += "\n\nAfter summarizing, save your result using the writeinfo() function. Example: writeinfo('{\"summary\": \"...\"}')"
                    try:
                        resp = call_with_retry(lambda: client.chat.completions.create(
                            model=ai_model,
                            messages=[{"role": "user", "content": prompt}],
                            temperature=0.3,
                            extra_body={"disable_thinking": True}
                        ))
                        summary_text = (resp.choices[0].message.content or "").strip()
                        if not summary_text:
                            print("[Memory] Compression: AI returned empty summary, skipping")
                        else:
                            try:
                                parsed = json.loads(summary_text)
                                if isinstance(parsed, dict) and "summary" in parsed:
                                    summary_text = json.dumps(parsed["summary"], ensure_ascii=False)
                            except (json.JSONDecodeError, ValueError):
                                pass
                            new_sid = str(int(time.time() * 1000))
                            sf_path = os.path.join(mem_dir, f"{new_sid}.json")
                            with open(sf_path, "w", encoding="utf-8") as sf:
                                json.dump({"info": summary_text}, sf, ensure_ascii=False, indent=2)
                            new_history_ids = history_ids[-6:]
                            new_data = {"history": new_history_ids, "summary_id": new_sid}
                            with open(mem_path, "w", encoding="utf-8") as f:
                                json.dump(new_data, f, ensure_ascii=False, indent=2)
                            # Archive unreferenced files
                            import shutil
                            referenced = set(new_history_ids) | {new_sid}
                            if summary_id:
                                referenced.add(summary_id)
                            now_ts = time.time()
                            archive_date = time.strftime("%Y-%m", time.localtime(now_ts))
                            archive_dir = os.path.join(mem_dir, "archive", archive_date)
                            os.makedirs(archive_dir, exist_ok=True)
                            for fname in os.listdir(mem_dir):
                                if fname.endswith(".json"):
                                    fid = fname[:-5]
                                    if fid not in referenced:
                                        try:
                                            shutil.move(os.path.join(mem_dir, fname), os.path.join(archive_dir, fname))
                                        except OSError:
                                            pass
                            # Cleanup archives older than 6 months
                            archive_root = os.path.join(mem_dir, "archive")
                            if os.path.isdir(archive_root):
                                cutoff_ts = now_ts - (180 * 86400)
                                for entry in os.listdir(archive_root):
                                    entry_path = os.path.join(archive_root, entry)
                                    if os.path.isdir(entry_path):
                                        try:
                                            entry_date = time.mktime(time.strptime(entry, "%Y-%m"))
                                            if entry_date < cutoff_ts:
                                                shutil.rmtree(entry_path)
                                                print(f"[Memory] Cleaned old archive: {entry}")
                                        except (ValueError, OSError):
                                            pass
                            print(f"[Memory] Compressed: {len(history_content)} exchanges -> summary + last 6")
                    except Exception as e:
                        print(f"[Memory] Compression failed: {e}")
                else:
                    print("[Memory] No history to compress.")
            else:
                print("[Memory] memory.json not found.")
            if llama_proc:
                llama_proc.kill()
                llama_proc.wait(timeout=5)
            sys.exit(0)
    
        import ctypes
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QIcon
        from PySide6.QtCore import QTimer
    
        qapp = QApplication(sys.argv)
        if sys.platform == "win32":
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("vass.app")
            except Exception:
                pass
        ico_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vass.ico")
        if os.path.exists(ico_path):
            qapp.setWindowIcon(QIcon(ico_path))
    
        gui = VassGUI(
            app=None, 
            x=gui_x, y=gui_y, 
            width=gui_width, height=gui_height,
            font_family=gui_font_family, font_size=gui_font_size,
            language=gui_language
        )
    
        # Defer heavy init so the event loop paints the window first
        _state = {"app": None, "thread": None}
    
        def _start_vass():
            _state["app"] = VassApp(gui=gui)
            gui.app = _state["app"]
            _state["app"].notification_manager.gui = gui
            gui.chat_text_signal.connect(_state["app"]._process_chat_text)
            gui.set_state("loading")
            def _run_safe():
                try:
                    _state["app"].run()
                except BaseException as e:
                    import traceback
                    with open("crash.log", "a") as f:
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
