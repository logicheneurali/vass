"""Automatic sampling-parameter profiles derived from the active AI model.

Deterministic, knowledge-based profiles per model family (from the GGUF
architecture or model-name patterns), adjusted by parameter count and
quantization, with a conservative generic fallback for unknown families.
Recomputed whenever the model changes; cached in
Allowed_root/private_model_params.json (keyed by model).

The profile is applied ONLY to the main chat request and the MCP tool loop.
"""
import json
import os
import re
import threading

_BASE = os.path.dirname(os.path.abspath(__file__))          # src/
_ROOT = os.path.dirname(_BASE)                               # project root
_CACHE_PATH = os.path.join(_ROOT, "Allowed_root",
                           "private_model_params.json")

_lock = threading.Lock()
_cache = None          # profile dict for the current model
_extra_support = None  # None=unknown, True/False: llama.cpp accepts top_k/min_p/repeat_penalty

# Base profiles per family (from official model-card recommendations).
# temperature: general chat; temperature_tool: MCP tool-calling loop.
_FAMILY_PROFILES = {
    "qwen":    {"temperature": 0.6, "temperature_tool": 0.3,
                "top_p": 0.8, "top_k": 20, "min_p": 0.05, "repeat_penalty": 1.0},
    "llama":   {"temperature": 0.6, "temperature_tool": 0.3,
                "top_p": 0.9, "top_k": 40, "min_p": 0.05, "repeat_penalty": 1.0},
    "gemma":   {"temperature": 0.7, "temperature_tool": 0.3,
                "top_p": 0.95, "top_k": 40, "min_p": 0.05, "repeat_penalty": 1.0},
    "mistral": {"temperature": 0.7, "temperature_tool": 0.3,
                "top_p": 0.9, "top_k": 40, "min_p": 0.05, "repeat_penalty": 1.0},
    "minicpm": {"temperature": 0.6, "temperature_tool": 0.3,
                "top_p": 0.8, "top_k": 20, "min_p": 0.05, "repeat_penalty": 1.0},
    "gemini":  {"temperature": 0.7, "temperature_tool": 0.3,
                "top_p": 0.95, "top_k": 40, "min_p": 0.05, "repeat_penalty": 1.0},
    "vision":  {"temperature": 0.4, "temperature_tool": 0.2,
                "top_p": 0.8, "top_k": 20, "min_p": 0.05, "repeat_penalty": 1.0},
}

# Conservative fallback for unknown families.
_GENERIC = {"temperature": 0.5, "temperature_tool": 0.3,
            "top_p": 0.9, "top_k": 40, "min_p": 0.05, "repeat_penalty": 1.0}

_FAMILY_KEYS = [
    ("qwen", ["qwen"]),
    ("llama", ["llama"]),
    ("gemma", ["gemma"]),
    ("mistral", ["mistral"]),
    ("minicpm", ["minicpm"]),
    ("gemini", ["gemini"]),
]


def _current_model():
    try:
        import configparser
        cfg = configparser.ConfigParser()
        cfg.read(os.path.join(_ROOT, "config", "settings.ini"), encoding="utf-8")
        return cfg.get("ai", "model", fallback="").strip()
    except Exception:
        return ""


def _current_settings():
    try:
        import configparser
        cfg = configparser.ConfigParser()
        cfg.read(os.path.join(_ROOT, "config", "settings.ini"), encoding="utf-8")
        return {
            "url": cfg.get("ai", "url", fallback="http://127.0.0.1:8080/v1").rstrip("/"),
            "model": cfg.get("ai", "model", fallback="").strip(),
        }
    except Exception:
        return {"url": "http://127.0.0.1:8080/v1", "model": ""}


def _gguf_matches(path, model):
    stem = os.path.basename(model).lower()
    if stem.endswith(".gguf"):
        stem = stem[:-5]
    base = os.path.basename(path).lower()
    if base.endswith(".gguf"):
        base = base[:-5]
    return bool(base) and (base == stem or stem.startswith(base))


def _arch_of(model_name):
    """Best-effort GGUF architecture for a model name (None if unavailable)."""
    try:
        import model_capabilities as mc
        s = mc._settings()
        path = mc._find_gguf_by_name(mc._llama_models_dir(s), model_name)
        if path:
            return mc._read_gguf_architecture(path)
        _, gguf = mc._server_metadata(s["url"], model_name)
        if gguf and _gguf_matches(gguf, model_name):
            return mc._read_gguf_architecture(gguf)
    except Exception:
        pass
    return None


def _family_of(arch, name):
    low = f"{arch or ''} {name or ''}".lower()
    for fam, keys in _FAMILY_KEYS:
        if any(k in low for k in keys):
            return fam
    return None


def _is_vision(arch, name):
    try:
        import model_capabilities as mc
        if arch and mc._arch_is_vision(arch):
            return True
        if mc._name_is_vision(name):
            return True
    except Exception:
        pass
    return False


def _parse_size_quant(model):
    size_b = 0.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*[bB](?!\w)", model)
    if m:
        size_b = float(m.group(1))
    quant = ""
    m = re.search(r"(Q\d(?:_[A-Z0-9]+)*|IQ\d+_[A-Z0-9]+|FP\d+|BF16|F16)", model)
    if m:
        quant = m.group(1).upper()
    return size_b, quant


def _adjust(profile, size_b, quant):
    p = dict(profile)
    if quant.startswith("Q3") or quant.startswith("Q4"):
        p["temperature"] = max(0.1, p["temperature"] - 0.1)
        p["temperature_tool"] = max(0.1, p["temperature_tool"] - 0.05)
    if 0 < size_b < 4:
        p["temperature"] = max(0.1, p["temperature"] - 0.1)
        if p["repeat_penalty"] <= 1.0:
            p["repeat_penalty"] = 1.05
    return p


def _clamp(p):
    p["temperature"] = round(min(2.0, max(0.0, p["temperature"])), 2)
    p["temperature_tool"] = round(min(2.0, max(0.0, p["temperature_tool"])), 2)
    p["top_p"] = round(min(1.0, max(0.0, p["top_p"])), 3)
    p["top_k"] = int(max(1, min(200, p["top_k"])))
    p["min_p"] = round(min(1.0, max(0.0, p["min_p"])), 3)
    p["repeat_penalty"] = round(min(2.0, max(0.8, p["repeat_penalty"])), 3)
    return p


def build_profile(model_name=None):
    name = (model_name or _current_model() or "").strip()
    if not name:
        return dict(_GENERIC)
    arch = _arch_of(name)
    vision = _is_vision(arch, name)
    if vision:
        profile = dict(_FAMILY_PROFILES["vision"])
        family = "vision"
    else:
        family = _family_of(arch, name)
        profile = dict(_FAMILY_PROFILES.get(family, _GENERIC))
    size_b, quant = _parse_size_quant(name)
    profile = _clamp(_adjust(profile, size_b, quant))
    profile.update({"presence_penalty": 0.0, "frequency_penalty": 0.0,
                    "family": family or "generic", "arch": arch or ""})
    return profile


def _persist(model_name, profile):
    try:
        os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
        data = {}
        try:
            with open(_CACHE_PATH, encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception:
            data = {}
        data[model_name] = profile
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def refresh(model_name=None):
    """Recompute the profile for the (given or current) model and cache it."""
    global _cache, _extra_support
    name = (model_name or _current_model() or "").strip()
    profile = build_profile(name)
    with _lock:
        _cache = profile
        _extra_support = None  # probe again after a model change
    if name:
        _persist(name, profile)
    return profile


def get_profile():
    global _cache
    with _lock:
        if _cache is None:
            _cache = build_profile()
        return dict(_cache)


def _probe_extras():
    """Probe whether the server accepts top_k/min_p/repeat_penalty (llama.cpp extras)."""
    global _extra_support
    if _extra_support is not None:
        return _extra_support
    s = _current_settings()
    if not s["model"]:
        return False
    try:
        from openai import OpenAI, APIStatusError
        client = OpenAI(base_url=s["url"], api_key="not-needed", timeout=30)
        client.chat.completions.create(
            model=s["model"], messages=[{"role": "user", "content": "ping"}],
            max_tokens=1, temperature=0.5, top_p=0.8,
            extra_body={"top_k": 20, "min_p": 0.05, "repeat_penalty": 1.0})
        _extra_support = True
    except APIStatusError as e:
        if e.status_code in (400, 422):
            _extra_support = False
    except Exception:
        pass  # transient error -> retry on next call
    return _extra_support


def sampling_kwargs(purpose="chat"):
    """Request-body sampling params for a purpose.

    Returns OpenAI-standard keys plus a private "_extra" dict (top_k/min_p/
    repeat_penalty) that must be merged into `extra_body` and is only present
    when the server supports them.
    """
    prof = get_profile()
    purpose = purpose or "chat"
    if purpose == "tool":
        prof = dict(prof)
        prof["temperature"] = prof.get("temperature_tool", prof["temperature"])
    elif purpose == "low":
        prof = dict(prof)
        prof["temperature"] = 0.1
    out = {
        "temperature": prof["temperature"],
        "top_p": prof["top_p"],
        "presence_penalty": prof["presence_penalty"],
        "frequency_penalty": prof["frequency_penalty"],
    }
    if _probe_extras():
        out["_extra"] = {
            "top_k": prof["top_k"],
            "min_p": prof["min_p"],
            "repeat_penalty": prof["repeat_penalty"],
        }
    return out
