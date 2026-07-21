"""Settings loader for VASS — reads settings.ini and returns a flat dict."""
import os
import configparser

_KOKORO_DEFAULT_VOICE = {
    "it": "if_sara",
    "en": "af_heart",
    "de": "af_heart",
    "fr": "ff_siwis",
    "es": "ef_dora",
    "pt": "pf_dora",
    "ja": "jf_alpha",
    "ko": "af_heart",
    "zh": "zf_xiaobei",
}


def load_settings(settings_file):
    config = configparser.ConfigParser()
    abs_path = os.path.abspath(settings_file)
    print(f"[Settings] Looking for: {abs_path}")

    result = {}

    if os.path.exists(abs_path):
        config.read(abs_path, encoding="utf-8")
        result["language"] = config.get("locale", "language", fallback="en")
        result["lastmode"] = config.get("gui", "lastmode", fallback="c")
        result["sensitivity"] = config.getfloat("wakeword", "sensitivity", fallback=0.010)
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
        result["auto_context_selection"] = config.get("ai", "auto_context_selection", fallback="false").lower() == "true"
        result["context_length"] = config.getint("ai", "context_length", fallback=0)
        result["overflow_strategy"] = config.get("ai", "overflow_strategy", fallback="truncate")
        result["compress_context"] = config.get("ai", "compress_context", fallback="false")

        result["gui_x"] = config.getint("gui", "x", fallback=1541)
        result["gui_y"] = config.getint("gui", "y", fallback=52)
        result["gui_width"] = config.getint("gui", "width", fallback=220)
        result["gui_height"] = config.getint("gui", "height", fallback=32)
        result["gui_font_family"] = config.get("gui", "font_family", fallback="Segoe UI")
        result["gui_font_size"] = config.getint("gui", "font_size", fallback=12)
        result["paused_opacity"] = config.getfloat("gui", "paused_opacity", fallback=0.5)
        result["command_similarity"] = config.getfloat("commands", "similarity", fallback=0.6)
        result["word_learning_enabled"] = config.get("commands", "word_learning_enabled", fallback="false").lower() == "true"
        lang = result.get("language", "en")
        result["kokoro_voice"] = config.get("tts", "kokoro_voice", fallback=_KOKORO_DEFAULT_VOICE.get(lang, "af_heart"))

        app_volume = config.getfloat("audio", "app_volume", fallback=None)
        if app_volume is None:
            old_vol = config.getfloat("tts", "volume", fallback=0.95)
            old_out = config.getfloat("audio", "output_volume", fallback=1.0)
            app_volume = old_vol * old_out
            config.set("audio", "app_volume", f"{app_volume:.2f}")
            for section, key in [("tts", "volume"), ("audio", "output_volume")]:
                if config.has_option(section, key):
                    config.remove_option(section, key)
            with open(abs_path, "w", encoding="utf-8") as f:
                config.write(f)
        result["app_volume"] = max(0.0, min(1.0, app_volume))
        result["mcp_server_url"] = config.get("ai", "mcp_server_url", fallback="http://localhost:9988")
        result["memory_tokens"] = config.getint("ai", "memory_tokens", fallback=5000)
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
        result["input_device"] = config.getint("audio", "input_device", fallback=-1)
        result["output_device"] = config.getint("audio", "output_device", fallback=-1)
        result["input_device_name"] = config.get("audio", "input_device_name", fallback="")
        result["output_device_name"] = config.get("audio", "output_device_name", fallback="")
        result["input_volume"] = config.getfloat("audio", "input_volume", fallback=1.0)
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
        result["sensitivity"] = 0.010
        result["wakeword"] = "vass"
        result["ai_url"] = "http://127.0.0.1:8080/v1"
        result["api_key"] = ""
        result["ai_model"] = ""
        result["system_message"] = "You are a helpful and concise voice assistant."
        result["allow_ai_scripts"] = False
        result["auto_context_selection"] = False
        result["context_length"] = 0
        result["overflow_strategy"] = "truncate"
        result["gui_x"] = 1541
        result["gui_y"] = 52
        result["gui_width"] = 220
        result["gui_height"] = 32
        result["gui_font_family"] = "Segoe UI"
        result["gui_font_size"] = 12
        result["paused_opacity"] = 0.5
        result["command_similarity"] = 0.6
        result["word_learning_enabled"] = False
        result["app_volume"] = 1.0
        result["kokoro_voice"] = _KOKORO_DEFAULT_VOICE.get(lang, "af_heart")
        result["mcp_server_url"] = "http://localhost:9988"
        result["memory_tokens"] = 5000
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
        result["input_device"] = -1
        result["output_device"] = -1
        result["input_device_name"] = ""
        result["output_device_name"] = ""
        result["input_volume"] = 1.0
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
            "font_family": "Segoe UI", "font_size": "12", "lastmode": "c",
            "paused_opacity": "0.5"
        }
        config["wakeword"] = {"sensitivity": "0.010", "wakeword": "vass"}
        config["commands"] = {"similarity": "0.6", "word_learning_enabled": "false"}
        config["tts"] = {"tts_engine": "kokoro", "kokoro_voice": _KOKORO_DEFAULT_VOICE.get(lang, "af_heart")}
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
            "memory_tokens": "5000",
            "allow_ai_scripts": "false",
            "auto_context_selection": "false",
            "context_length": "0",
            "compress_context": "false",
            "overflow_strategy": "truncate"
        }
        config["resources"] = {"cpu_max": "75", "ram_max": "99", "gpu_max": "75", "vram_max": "99", "resource_timeout": "10"}
        config["events"] = {"reminder_advance": "3600"}
        config["audio"] = {"input_device": "-1", "output_device": "-1", "input_device_name": "", "output_device_name": "", "input_volume": "1.0", "app_volume": "1.0"}
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
