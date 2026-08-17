"""Detect whether the configured AI model supports image input (multimodal).

Fully automatic layered detection (no manual override, no live probe):
1. Server metadata (authoritative): `GET {base}/v1/models` ->
   `architecture.input_modalities`. If the field is present, it is decisive.
2. GGUF architecture from the local model file (llama.cpp):
   `general.architecture` (minimal manual GGUF reader, no new dependency).
3. Model-name heuristic (fallback for remote endpoints: OpenAI/Groq/...).

The result is cached in Allowed_root/private_model_capabilities.json, keyed by
model@url, and self-invalidates when the model or URL changes.
"""
import json
import os
import re
import struct
import urllib.request

_BASE = os.path.dirname(os.path.abspath(__file__))          # src/
_ROOT = os.path.dirname(_BASE)                               # project root
_CACHE_PATH = os.path.join(_ROOT, "Allowed_root",
                           "private_model_capabilities.json")

# GGUF architectures that accept image input (underscores/hyphens normalized away)
_VISION_ARCHS = ("qwen2vl", "qwen2_5_vl", "qwen3vl", "qwen3_vl", "qwen_vl",
                 "llava", "mllama", "minicpmv", "paligemma", "idefics",
                 "fuyu", "cogvlm", "pixtral", "gemma3")

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
        "llama_path": cfg.get("llamacpp", "llama_server_path", fallback="").strip(),
        "llama_args": cfg.get("llamacpp", "llama_server_arguments", fallback=""),
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

def _read_gguf_architecture(path):
    """Extract 'general.architecture' from a GGUF file header."""
    try:
        with open(path, "rb") as f:
            if f.read(4) != b"GGUF":
                return None
            f.read(4)              # version
            f.read(8)              # tensor_count
            n_kv = struct.unpack("<Q", f.read(8))[0]
            for _ in range(n_kv):
                klen = struct.unpack("<Q", f.read(8))[0]
                key = f.read(klen).decode("utf-8", "replace")
                vtype = struct.unpack("<I", f.read(4))[0]
                if key == "general.architecture":
                    if vtype == 8:      # string
                        slen = struct.unpack("<Q", f.read(8))[0]
                        return f.read(slen).decode("utf-8", "replace")
                    return None
                _skip_gguf_value(f, vtype)
        return None
    except Exception:
        return None


def _skip_gguf_value(f, vtype):
    if vtype == 8:               # string
        slen = struct.unpack("<Q", f.read(8))[0]
        f.seek(slen, 1)
    elif vtype == 9:             # array
        atype = struct.unpack("<I", f.read(4))[0]
        count = struct.unpack("<Q", f.read(8))[0]
        for _ in range(count):
            _skip_gguf_value(f, atype)
    elif vtype in (0, 1, 7):     # uint8 / int8 / bool
        f.seek(1, 1)
    elif vtype in (2, 3, 4, 5):  # uint16 / int16 / uint32 / int32
        f.seek(4, 1)
    elif vtype == 6:             # float32
        f.seek(4, 1)
    elif vtype in (10, 11):      # uint64 / int64
        f.seek(8, 1)
    elif vtype == 12:            # float64
        f.seek(8, 1)
    else:
        f.seek(16, 1)


def _llama_models_dir(s):
    m = re.search(r"--models-dir\s+(\S+)", s.get("llama_args", ""))
    if m:
        d = m.group(1).strip('"').strip("'")
        if not os.path.isabs(d) and s.get("llama_path"):
            return os.path.join(s["llama_path"], d)
        return d
    if s.get("llama_path"):
        cand = os.path.join(s["llama_path"], "models")
        if os.path.isdir(cand):
            return cand
    return None


def _find_gguf_by_name(models_dir, model):
    if not models_dir or not model:
        return None
    # strip a .gguf extension explicitly (splitext would split on the first dot
    # of names like "Qwen3.5-9B-Q4_0")
    stem = os.path.basename(model).lower()
    if stem.endswith(".gguf"):
        stem = stem[:-5]
    for root, _, files in os.walk(models_dir):
        for fn in files:
            if fn.lower().endswith(".gguf"):
                base = fn[:-5].lower()
                if base == stem or stem.startswith(base):
                    return os.path.join(root, fn)
    return None


def _arch_is_vision(arch):
    a = (arch or "").lower().replace("_", "").replace("-", "")
    return any(v.replace("_", "").replace("-", "") in a for v in _VISION_ARCHS)


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
    mods, gguf = _server_metadata(url, model)
    if mods:
        return True
    # Server reported text-only (or unknown): cross-check with the GGUF
    # architecture and the name heuristic before concluding text-only —
    # llama.cpp can report input_modalities=["text"] for vision models that
    # are not loaded yet or whose metadata lacks the image modality.
    path = gguf or _find_gguf_by_name(_llama_models_dir(_settings()), model)
    if path:
        arch = _read_gguf_architecture(path)
        if arch:
            return _arch_is_vision(arch)
    return _name_is_vision(model)


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
