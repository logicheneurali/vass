"""Detect whether the configured AI model supports image input (multimodal).

Fully automatic layered detection (no manual override, no live probe):
1. Server metadata (authoritative): `GET {base}/v1/models` ->
   `architecture.input_modalities`. If the field is present, it is decisive.
2. Model-name heuristic (fallback for remote endpoints: OpenAI/Groq/...).

The result is cached in Allowed_root/private_model_capabilities.json, keyed by
model@url, and self-invalidates when the model or URL changes.
"""
import json
import os
import re
import urllib.request

_BASE = os.path.dirname(os.path.abspath(__file__))          # src/
_ROOT = os.path.dirname(_BASE)                               # project root
_CACHE_PATH = os.path.join(_ROOT, "Allowed_root",
                           "private_model_capabilities.json")

# Model-name signals for remote endpoints (regex on lowercased name)
_VISION_NAME_PATTERNS = (
    r"-vl", r"_vl", r"\bvl\b", "llava", "minicpm", "gpt-4o", "gpt-4.1",
    "claude-3", "claude-4", "gemini", "internvl", "paligemma", "idefics",
    "fuyu", "cogvlm", "pixtral", "moondream", "glm-4v", "qwen2.5-vl",
    "phi-3.5-vision", "phi4-vision", "gemma-4-v", "gemma3", "smolvlm",
)


def _settings():
    import configparser
    cfg = configparser.ConfigParser()
    cfg.read(os.path.join(_ROOT, "config", "settings.ini"), encoding="utf-8")
    return {
        "url": cfg.get("ai", "url", fallback="http://127.0.0.1:8080/v1").rstrip("/"),
        "model": cfg.get("ai", "model", fallback="").strip(),
    }


def _fetch_json(url, timeout=6):
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "vass/1.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None


# ── 1. Server metadata ─────────────────────────────────────────

def _server_metadata(url, model):
    """Return (image_support_or_None, gguf_path_or_None) from /v1/models."""
    data = _fetch_json(url.rstrip("/") + "/models")
    if not data or not isinstance(data, dict):
        return None, None
    models = data.get("data") or []
    target = (model or "").lower()
    gguf = None
    for m in models:
        args = (m.get("status") or {}).get("args") or []
        path = ""
        if "--model" in args:
            i = args.index("--model")
            if i + 1 < len(args):
                path = args[i + 1]
        if path and path.lower().endswith(".gguf") and not gguf:
            gguf = path
        mid = (m.get("id") or "").lower()
        if mid == target or (target and target in mid):
            arch = m.get("architecture") or {}
            mods = arch.get("input_modalities")
            if isinstance(mods, list):
                return "image" in mods, path
            return None, path
    return None, gguf


# ── 2. GGUF architecture ───────────────────────────────────────



# ── 3. Name heuristic ──────────────────────────────────────────

def _name_is_vision(name):
    low = (name or "").lower()
    return any(re.search(p, low) for p in _VISION_NAME_PATTERNS)


# ── cache ──────────────────────────────────────────────────────

def _load_cache():
    try:
        with open(_CACHE_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_cache(data):
    try:
        os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def _detect(url, model):
    mods, _ = _server_metadata(url, model)
    if mods:
        return True
    # Server did not report image support — fall back to name heuristic.
    return _name_is_vision(model or "")


def detect_image_support(url=None, model=None, use_cache=True):
    s = _settings()
    url = url or s["url"]
    model = model or s["model"]
    if not model:
        return False
    key = f"{model}@{url}"
    cached = _load_cache()
    if use_cache and key in cached:
        return bool(cached[key])
    result = bool(_detect(url, model))
    cached[key] = result
    _save_cache(cached)
    return result


def supports_images():
    return detect_image_support()
