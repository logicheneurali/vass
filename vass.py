import json
import subprocess
import time
import threading
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
    print("Missing dependencies. Run: pip install -r requirements.txt")
    sys.exit(1)

faulthandler.enable(open("faulthandler.log", "w"))

from audio_handler import AudioHandler
from voice_recognition import VoiceRecognition
from command_executor import CommandExecutor
from openai import OpenAI
from utils import call_with_retry, execute_mcp_tool_calls, init_mcp, is_process_running, kill_port, kill_process, beep, paste_text, parse_blacklist, is_local_url, strip_markdown, cleanup_orphan_files, is_script_command, strip_script_prefix, strip_think_tags, start_llama_server
from gui import VassGUI
from i18n import t
from script_engine import VASScript
from tts_engine import TtsEngine
from event_reminder import EventReminder
from idle_tracker import IdleTracker


def _load_version():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")) as f:
            return f.read().strip()
    except Exception:
        return "0.0.0"

__version__ = _load_version()


MEMORY_SUMMARIZATION_PROMPT = (
    "Summarize these conversations concisely."
    "Keep important info (user informations, preferences, user events (user's requests to AI are not considered as 'user events'),family members informations, pets informations,family members events, pets events)."
    "Output only a short JSON summary with key 'summary'."
)

MCP_PROMPT = (
    "\n\nYou have access to MCP tools to interact with VASS. "
    "Use the interact tool to execute VASScript code directly. "
    "For example: interact(\"say('hello')\") will speak hello."
)


def _load_vascript_reference():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Allowed_root", "VASCRIPT_REFERENCE.md")
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        return f"\n\n--- VASScript Reference ---\n{content}\n--- End Reference ---\n"
    except Exception:
        return ""


class VassApp:
    def __init__(self, gui, settings_file="settings.ini"):
        self.gui = gui
        self.audio_handler = AudioHandler()
        self.settings_file = settings_file
        self.settings = self._load_settings()
        self.language = self.settings["language"]
        self.wake_word_sensitivity = self.settings["sensitivity"]
        self.wake_word = self.settings.get("wakeword", "vass")
        self.ai_url = self.settings["ai_url"]
        self.ai_api_key = self.settings.get("api_key", "")
        self.ai_model = self.settings["ai_model"]
        self.system_message = self.settings["system_message"]
        self.gui_x = self.settings["gui_x"]
        self.gui_y = self.settings["gui_y"]
        self.gui_width = self.settings["gui_width"]
        self.gui_height = self.settings["gui_height"]
        self.gui_font_family = self.settings["gui_font_family"]
        self.gui_font_size = self.settings["gui_font_size"]
        self.command_similarity = self.settings["command_similarity"]
        tts_volume = self.settings.get("volume", 0.95)
        self.tts = TtsEngine(
            gui=gui,
            state_getter=lambda: self.state,
            state_setter=self.set_state,
            tts_volume=tts_volume,
            language=self.language,
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

        reminder_advance = self.settings.get("reminder_advance", 3600)
        self.idle_tracker = IdleTracker()
        self.event_reminder = EventReminder(self, advance_seconds=reminder_advance, language=self.language, idle_tracker=self.idle_tracker)

        wr_lang = t("whisper.language", self.language)
        wr_prompt = t("whisper.initial_prompt_wakeword", self.language)
        wr_transcribe = t("whisper.initial_prompt_transcription", self.language)
        self.voice_recognition = VoiceRecognition(
            wake_word=self.wake_word,
            sensitivity=self.wake_word_sensitivity,
            whisper_language=wr_lang,
            wake_prompt=wr_prompt,
            transcribe_prompt=wr_transcribe,
            wake_variants=[self.wake_word, f"hey {self.wake_word}", f"ciao {self.wake_word}"]
        )
        self.command_executor = CommandExecutor(similarity_threshold=self.command_similarity)
        self.openai_client = OpenAI(base_url=self.ai_url, api_key=self.ai_api_key or "not-needed")
        self.running = False
        self._trim_lock = threading.Lock()
        self._script_engine_lock = threading.Lock()
        self._active_script_engine = None
        self.state = "loading"
        self.state_lock = threading.RLock()
        self.conversation_history = []
        self.mode = "chat" if self.settings.get("lastmode", "c") == "c" else "trascrizione"
        self.memory_mode = "full"
        self._input_mode = False
        self._ensure_memory_file()

    @staticmethod
    def _ensure_memory_file():
        dir_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Allowed_root")
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
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.ini")
            cfg.read(path)
            if not cfg.has_section(section):
                cfg.add_section(section)
            cfg.set(section, key, value)
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
            config.read(abs_path)
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
            result["ai_model"] = config.get("ai", "model", fallback="gemma-4-E2B-it-Q8_0")
            result["system_message"] = config.get("ai", "system_message", fallback="")
            
            result["gui_x"] = config.getint("gui", "x", fallback=100)
            result["gui_y"] = config.getint("gui", "y", fallback=100)
            result["gui_width"] = config.getint("gui", "width", fallback=220)
            result["gui_height"] = config.getint("gui", "height", fallback=60)
            result["gui_font_family"] = config.get("gui", "font_family", fallback="Segoe UI")
            result["gui_font_size"] = config.getint("gui", "font_size", fallback=14)
            result["command_similarity"] = config.getfloat("commands", "similarity", fallback=0.6)
            result["volume"] = config.getfloat("tts", "volume", fallback=0.95)
            result["mcp_server_url"] = config.get("ai", "mcp_server_url", fallback="")
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
            result["ai_model"] = "gemma-4-E2B-it-Q8_0"
            result["system_message"] = "Sei un assistente vocale utile e conciso."
            result["gui_x"] = 100
            result["gui_y"] = 100
            result["gui_width"] = 220
            result["gui_height"] = 60
            result["gui_font_family"] = "Segoe UI"
            result["gui_font_size"] = 14
            result["command_similarity"] = 0.6
            result["volume"] = 0.95
            result["mcp_server_url"] = ""
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

            config["locale"] = {"language": lang}
            config["wakeword"] = {"sensitivity": "0.005", "wakeword": "vass"}
            config["ai"] = {
                "url": "http://127.0.0.1:8080/v1",
                "api_key": "",
                "model": "gemma-4-E2B-it-Q8_0",
                "system_message": "Sei un assistente vocale utile e conciso."
            }
            config["gui"] = {
                "x": "100", "y": "100", "width": "220", "height": "60",
                "font_family": "Segoe UI", "font_size": "14"
            }
            config["commands"] = {"similarity": "0.6"}
            config["tts"] = {"tts_engine": "kokoro", "volume": "0.95"}
            config["resources"] = {"cpu_max": "75", "ram_max": "99", "gpu_max": "75", "vram_max": "99", "resource_timeout": "10"}
            config["ai"]["mcp_server_url"] = ""
            config["ai"]["blacklist"] = ""
            with open(abs_path, "w") as f:
                config.write(f)
            return result

    def set_state(self, new_state, detail=""):
        with self.state_lock:
            self.state = new_state
            from log_utils import rotate_if_needed
            rotate_if_needed("debug.log", 500_000, 2)
            with open("debug.log", "a") as f:
                f.write(f"set_state: {new_state}\n")
            try:
                self.gui.set_state(new_state, detail)
            except Exception as e:
                with open("crash.log", "a") as f:
                    f.write(f"gui.set_state failed: {e}\n")

    def handle_button_press(self):
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
                self.audio_handler.start_stream()
                self.set_state("listening")
            elif current == "playing":
                self.stop_playback()
                self.set_state("listening")
            elif current == "running_script":
                with self._script_engine_lock:
                    engine = self._active_script_engine
                    if engine:
                        engine.stop()
                        self._active_script_engine = None
                self.set_state("listening")
            elif current in ("waiting",):
                pass
            elif current == "waiting_resources":
                self.set_state("listening")

    def stop_playback(self):
        self.tts.stop()

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
            except Exception:
                pass

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
                        self.ai_api_key = self.settings.get("api_key", "")
                        self.openai_client.api_key = self.ai_api_key or "not-needed"
                        self.mcp_server_url = self.settings["mcp_server_url"]
                        self.memory_tokens = self.settings.get("memory_tokens", 2000)
                        self.blacklist = parse_blacklist(self.settings.get("blacklist", ""))
                        self.llama_server_path = self.settings.get("llama_server_path", "")
                        self.llama_autostart = self.settings.get("llama_autostart", "false").lower() == "true"
                        tv = self.settings.get("volume", 0.95)
                        self.tts.update_settings(tv)
                        self.gui.volume_top_bar.set_volume(tv)
                        self.gui_x = self.settings["gui_x"]
                        self.gui_y = self.settings["gui_y"]
                        self.gui_width = self.settings["gui_width"]
                        self.gui_height = self.settings["gui_height"]
                        self.gui.schedule(0, lambda: self.gui.setGeometry(
                            self.gui_x, self.gui_y, self.gui_width, self.gui_height))
                        self.gui.schedule(0, self.gui._clamp_to_screen)
                        print(f"[Watch] Settings reloaded from {abs_path}")
            except Exception:
                pass

    def _watch_script_queue(self):
        queue_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "exec_queue.json")
        result_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "exec_result.json")
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
                print(f"[ScriptQueue] Executing: {label}")

                def _write_result(r):
                    result = {"id": request_id, "result": r}
                    with open(result_path, "w", encoding="utf-8") as f:
                        json.dump(result, f)
                    print(f"[ScriptQueue] Completed: {label} -> {r.get('status')}")

                if code:
                    self._run_script(None, result_callback=_write_result, code=code)
                else:
                    self._run_script(script_name, result_callback=_write_result)
            except Exception:
                pass

    def save_gui_position(self, x, y):
        config = configparser.ConfigParser()
        abs_path = os.path.abspath(self.settings_file)
        try:
            if os.path.exists(abs_path):
                config.read(abs_path)
            if "gui" not in config:
                config["gui"] = {}
            config["gui"]["x"] = str(x)
            config["gui"]["y"] = str(y)
            with open(abs_path, "w") as f:
                config.write(f)
        except Exception as e:
            print(f"[Settings] Could not save position: {e}")

    def run(self):
        print(f"VASS v{__version__} - Voice Activated Command System")
        self.voice_recognition.load_models()
        self.set_state("listening")
        self.running = True
        self.audio_handler.start_stream()
        threading.Thread(target=self._watch_commands_file, daemon=True).start()
        threading.Thread(target=self._watch_settings_file, daemon=True).start()
        threading.Thread(target=self._watch_script_queue, daemon=True).start()
        if self.mcp_server_url and os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server", "run_server.py")):
            threading.Thread(target=self._start_mcp_server, daemon=True).start()
        if self.llama_server_path.strip() and self.llama_autostart:
            threading.Thread(target=self._start_llamacpp, daemon=True).start()
        if self.event_reminder:
            threading.Thread(target=self.event_reminder.run, daemon=True).start()
        threading.Thread(target=self._health_check_loop, daemon=True).start()
        threading.Thread(target=self._health_check_once, daemon=True).start()
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
                        if wake:
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
        mcp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server")
        script = os.path.join(mcp_dir, "run_server.py")
        kill_port(9988)
        time.sleep(1)
        print(f"[MCP] Starting MCPGoal server from {script}")
        self.mcp_process = subprocess.Popen(
            [sys.executable, script],
            cwd=mcp_dir
        )
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
                print(f"[Health] {health_url} -> {r.status_code}")
            except Exception as e:
                ok = False
                print(f"[Health] {health_url} unreachable: {e}")
            self.gui.schedule_signal.emit(lambda ok=ok: self.gui.set_health_status(ok))

    def _health_check_once(self):
        time.sleep(3)  # brief delay for server startup
        import httpx
        health_url = f"{self.ai_url.rstrip('/')}/health"
        try:
            r = httpx.get(health_url, timeout=5)
            ok = r.status_code == 200
            print(f"[Health] {health_url} -> {r.status_code}")
        except Exception as e:
            ok = False
            print(f"[Health] {health_url} unreachable: {e}")
        self.gui.schedule_signal.emit(lambda ok=ok: self.gui.set_health_status(ok))

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
        import subprocess as _sp
        if self.mcp_process:
            kill_process(self.mcp_process)
            self.mcp_process = None
        if self.llama_process:
            kill_process(self.llama_process)
            self.llama_process = None

    def _transcribe_and_process(self):
        audio_data = self.audio_handler.get_recorded_audio()
        self.audio_handler.recorded_buffer.clear()
        
        if len(audio_data) > 0:
            transcription = self.voice_recognition.transcribe_audio(audio_data)
            with open("lastcommands.txt", "w") as f:
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
            with open("lastcommands.txt", "r") as f:
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
        if matched_command and is_script_command(matched_command):
            print(f"Executing script command: {matched_command}")
            script_name = strip_script_prefix(matched_command)
            threading.Thread(target=self._run_script, args=(script_name,), kwargs={"params": matched_vars}, daemon=True).start()
            return
        if matched_command:
            print(f"Executing command: {matched_command}")
            threading.Thread(target=self._execute_and_speak, args=(matched_command,), daemon=True).start()
        else:
            print("No matching command found. Sending to AI Agent.")
            threading.Thread(target=self._handle_ai_fallback, args=(transcribed_text,), daemon=True).start()

    def _execute_and_speak(self, command):
        if is_script_command(command):
            self._run_script(strip_script_prefix(command))
            return
        self.command_executor.execute_command(command)

    def _run_script(self, name_or_code=None, result_callback=None, code=None, params=None):
        import json as _json
        script_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")
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
            self.set_state("running_script")
            script_error = None
            engine = None
            try:
                engine = VASScript(
                    self, script_name=script_name, auth_callback=_auth_callback,
                    line_callback=lambda c, t: [
                        self.gui.set_state("running_script", f"{c}/{t}"),
                        self.gui.memory_bar.set_value(c, 1, t)
                    ]
                )
                with self._script_engine_lock:
                    self._active_script_engine = engine
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
                else:
                    self.tts._state_before_tts = "listening"
                    threading.Thread(target=self.tts.speak, args=(f"Errore script: {script_error}",), daemon=True).start()
            finally:
                self._active_script_engine = None
                self.set_state("listening")

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
            self.set_state("waiting_resources")
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

        try:
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            base = self.system_message or ""
            date_prefix = t("ai.date_prefix", self.language)
            system_content = f"{base}\n\n{date_prefix}{now}".strip()
            vas_ref = _load_vascript_reference()

            mcp, tools = init_mcp(self.mcp_server_url, timeout=10)

            memory_content = ""
            if tools and mcp and self.memory_mode != "none":
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
                                    sf_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Allowed_root", "memory", f"{summary_id}.json")
                                    if os.path.exists(sf_path):
                                        with open(sf_path, encoding="utf-8") as sf:
                                            summary_text = json.load(sf).get("info", "")
                                parts.append(f"summary : {summary_text}")
                            for vid in mem_data.get("history", []):
                                hf_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Allowed_root", "memory", f"{vid}.json")
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
                                memory_content = "\n\nPrevious conversations:\n" + "\n".join(parts)
                        except Exception:
                            pass
                        break

            messages = [
                {"role": "system", "content": memory_content + system_content + MCP_PROMPT + vas_ref },
                {"role": "user", "content": prompt}
            ]

            kwargs = dict(
                model=self.ai_model,
                messages=messages,
                temperature=0.7,
                extra_body={"disable_thinking": True}
            )

            if tools:
                kwargs["tools"] = tools

            msg = call_with_retry(lambda: self.openai_client.chat.completions.create(**kwargs)).choices[0].message
            script_called = any(tc.function.name == "script" or
                (tc.function.name == "interact" and
                 any(kw in tc.function.arguments.lower() for kw in ("addevent", "listevents", "removeevent")))
                for tc in (msg.tool_calls or []))
            msg = execute_mcp_tool_calls(messages, msg, mcp, tools, self.openai_client, self.ai_model)

            ai_response = msg.content or ""
            ai_response = strip_think_tags(ai_response)
            print(f"AI Agent Response: {ai_response}")

            if not script_called:
                self.conversation_history.append({"role": "user", "content": prompt})
                self.conversation_history.append({"role": "assistant", "content": ai_response})
            total = sum(len(json.dumps(m, ensure_ascii=False)) for m in self.conversation_history)
            if total > self.memory_tokens * 4:
                self.conversation_history = self.conversation_history[-10:]

            mem_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Allowed_root", "memory.json")
            mem_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Allowed_root", "memory")
            os.makedirs(mem_dir, exist_ok=True)
            try:
                existing = {}
                try:
                    with open(mem_path, encoding="utf-8") as f:
                        existing = json.load(f)
                except Exception:
                    pass
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
                with open(mem_path, "w", encoding="utf-8") as f:
                    json.dump(mem, f, ensure_ascii=False, indent=2)
                # Light cleanup: move unreferenced files to archive every N saves
                if len(merged_ids) % 5 == 0:
                    cleanup_orphan_files(mem_dir, merged_ids, existing.get("summary_id", ""))
            except Exception as e:
                print(f"[Memory] Save error: {e}")

            threading.Thread(target=self._trim_memory_if_needed, daemon=True).start()

            self.gui.update_memory_bar()

            clean_text = strip_markdown(ai_response)
            self.tts.speak(clean_text)
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
            threading.Thread(target=self.tts.speak, args=(err_msg,), daemon=True).start()
            self.set_state("listening")

    def _trim_memory_if_needed(self):
        if not self._trim_lock.acquire(blocking=False):
            print("[Memory] Trim already in progress, skip")
            return
        try:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Allowed_root", "memory.json")
            mem_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Allowed_root", "memory")
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

            # Load history content from individual files
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

            prompt = MEMORY_SUMMARIZATION_PROMPT
            if old_summary:
                prompt += "\n\nExisting summary to build upon:\n" + old_summary
            prompt += "\n\nNew conversations:\n" + json.dumps(history_content, ensure_ascii=False)
            prompt += "\n\nAfter summarizing, save your result using the writeinfo() function. Example: writeinfo('{\"summary\": \"...\"}'). The function returns an ID — include it in your response to confirm success."

            resp = call_with_retry(lambda: self.openai_client.chat.completions.create(
                model=self.ai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                extra_body={"disable_thinking": True}
            ))
            summary_text = (resp.choices[0].message.content or "").strip()
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

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="VASS Voice Assistant")
    parser.add_argument("--compress-memory", action="store_true", help="Comprimi memory.json tramite AI e poi esci")
    parser.add_argument("--version", action="version", version=f"VASS v{__version__}")
    args = parser.parse_args()

    # Load settings first to get GUI params
    import configparser
    import os
    
    settings_file = "settings.ini"
    config = configparser.ConfigParser()
    abs_path = os.path.abspath(settings_file)
    
    if os.path.exists(abs_path):
        config.read(abs_path)
        gui_x = config.getint("gui", "x", fallback=100)
        gui_y = config.getint("gui", "y", fallback=100)
        gui_width = config.getint("gui", "width", fallback=220)
        gui_height = config.getint("gui", "height", fallback=60)
        gui_font_family = config.get("gui", "font_family", fallback="Segoe UI")
        gui_font_size = config.getint("gui", "font_size", fallback=14)
        gui_language = config.get("locale", "language", fallback="en")
    else:
        gui_x, gui_y, gui_width, gui_height = 100, 100, 220, 60
        gui_font_family, gui_font_size = "Segoe UI", 14
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
        mem_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Allowed_root", "memory.json")
        mem_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Allowed_root", "memory")
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
    ico_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vass.ico")
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
