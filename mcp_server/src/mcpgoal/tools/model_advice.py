"""Model advice tool — scans HuggingFace for GGUF models, evaluates them
against the current PC hardware and the currently configured model, and
returns a spoken recommendation (TTS by the main app).

Score is composite and family-agnostic:
  score = params_B * family_factor(if known, else 1.0) * (1 + log10(downloads+1)/20)
  - parameters dominate (bigger = smarter, same architecture)
  - downloads/likes = community consensus ("reliable" by usage)
  - family factor is only a small correction for known families; unknown
    families get a neutral 1.0, never zero.
VRAM estimate = GGUF file size + small overhead (KV cache included).
Budget = TOTAL VRAM (the current model is ignored: it is swapped out anyway).
No GPU -> budget = free RAM * 0.7 (CPU inference).
"""
import configparser
import json
import os
import re
import time
import urllib.request

_CACHE_TTL = 24 * 3600

_FAMILIES = ("qwen", "llama", "gemma", "mistral", "deepseek", "phi")

_FAMILY_FACTOR = {
    "deepseek": 1.05,
    "qwen": 1.00,
    "llama": 1.00,
    "gemma": 0.95,
    "mistral": 0.95,
    "phi": 0.90,
}

# Red flags: merged/frankenstein/fiction models are unreliable for general use
_SPAM_WORDS = (
    "uncensored", "abliterated", "heretic", "merge", "fused", "rp", "erotic",
    "nsfw", "story", "fiction", "fable", "dau", "neo", "goddess", "pride",
)

# File suffixes that are NOT the main LLM (projection heads, encoders, tokenizers...)
_NON_MODEL_PARTS = (
    "mmproj", "mtp", "vit", "vision", "encoder", "embedding", "embeddings",
    "tokenizer", "clip", "siglip", "roberta", "merges", "template",
)

# Specialized (non-chat) model repos: ASR/TTS/vision/etc. — excluded from ranking
_SPECIALIZED_WORDS = (
    "asr", "stt", "tts", "streaming", "speech", "audio", "whisper", "parakeet",
    "voice", "ocr", "detect", "segmentation", "embedding-model", "rerank",
)

_QUANT_GB_PER_B = {
    "Q8_0": 1.07, "Q6_K": 0.82, "Q5_K_M": 0.68, "Q5_0": 0.64,
    "Q4_K_M": 0.58, "Q4_K_S": 0.56, "Q4_0": 0.55, "Q3_K_M": 0.46,
}

_OVERHEAD_GB = 0.6

_CACHE_PATH = None
_VASS_ROOT = None
_UA = "vass-model-advisor/0.8.5 (github.com/logicheneurali/vass)"


def _get_vass_root():
    global _VASS_ROOT
    if _VASS_ROOT is None:
        _VASS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    return _VASS_ROOT


def _cache_path():
    global _CACHE_PATH
    if _CACHE_PATH is None:
        _CACHE_PATH = os.path.join(_get_vass_root(), "Allowed_root", "model_advice_cache.json")
    return _CACHE_PATH


# ── Local facts ───────────────────────────────────────────────────

def _get_current_model():
    """Return (family, params_b, active_b, quant) from [ai] model in settings.ini."""
    try:
        cfg = configparser.ConfigParser()
        cfg.read(os.path.join(_get_vass_root(), "config", "settings.ini"), encoding="utf-8")
        name = (cfg.get("ai", "model", fallback="") or "").strip()
    except Exception:
        name = ""
    family, params_b, active_b, quant = "", 0.0, 0.0, ""
    m = re.search(r"(\d+(?:\.\d+)?)[bB](?:-(?:A(\d+(?:\.\d+)?)[bB]))?", name)
    if m:
        params_b = float(m.group(1))
        if m.group(2):
            active_b = float(m.group(2))
        family = _guess_family(name)
    qm = re.search(r"(Q\d(?:_[A-Z0-9]+)*|IQ\d+_[A-Z0-9]+)", name)
    if qm:
        quant = qm.group(1)
    return {"name": name, "family": family, "params": params_b, "active": active_b,
            "quant": quant}


def _size_of_current_model(cur):
    """Estimate the on-disk size of the current model (informational only)."""
    if not cur["params"]:
        return 0.0
    gb_per_b = _QUANT_GB_PER_B.get(cur["quant"], 0.58)
    return cur["params"] * gb_per_b


def _get_hardware():
    hw = {"gpu_name": "", "vram_total_gb": 0.0, "vram_free_gb": 0.0, "ram_free_gb": 0.0}
    try:
        import psutil
        hw["ram_free_gb"] = psutil.virtual_memory().available / 1024**3
    except Exception:
        pass
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        if gpus:
            g = gpus[0]
            hw["gpu_name"] = g.name
            hw["vram_total_gb"] = g.memoryTotal / 1024
            hw["vram_free_gb"] = g.memoryFree / 1024
    except Exception:
        pass
    return hw


# ── HuggingFace scan ──────────────────────────────────────────────

def _hf_get(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _is_spam(name):
    low = name.lower()
    return any(w in low for w in _SPAM_WORDS)


def _is_specialized(name):
    low = name.lower()
    return any(w in low for w in _SPECIALIZED_WORDS)


def _guess_family(name):
    low = name.lower()
    for fam in _FAMILIES:
        if fam in low:
            return fam
    return ""


def _parse_gguf(filename):
    params = 0.0
    active = 0.0
    m = re.search(r"(\d+(?:\.\d+)?)[bB](?:-(?:A(\d+(?:\.\d+)?)[bB]))?", filename)
    if m:
        params = float(m.group(1))
        if m.group(2):
            active = float(m.group(2))
    quant = ""
    qm = re.search(r"(Q\d(?:_[A-Z0-9]+)*|IQ\d+_[A-Z0-9]+)", filename)
    if qm:
        quant = qm.group(1)
    return params, active, quant


def _scan_hf():
    """Collect GGUF models: top downloads overall + per family, dedup by repo."""
    repos = {}
    try:
        for fam in _FAMILIES:
            data = _hf_get(
                f"https://huggingface.co/api/models?search={fam}&filter=gguf"
                f"&sort=downloads&direction=-1&limit=4", timeout=10)
            for m in data:
                rid = m.get("id", "")
                if rid and rid not in repos:
                    repos[rid] = {
                        "id": rid,
                        "downloads": m.get("downloads", 0),
                        "likes": m.get("likes", 0),
                    }
    except Exception as e:
        print(f"[ModelAdvice] family scan failed: {e}")
    # Size-targeted searches: catch small/medium models that top-download
    # ranking hides (large models dominate it) — also finds non-listed families
    try:
        for tag in ("7b", "8b", "9b", "14b"):
            data = _hf_get(
                f"https://huggingface.co/api/models?search={tag}&filter=gguf"
                f"&sort=downloads&direction=-1&limit=4", timeout=10)
            for m in data:
                rid = m.get("id", "")
                if rid and rid not in repos:
                    repos[rid] = {
                        "id": rid,
                        "downloads": m.get("downloads", 0),
                        "likes": m.get("likes", 0),
                    }
    except Exception as e:
        print(f"[ModelAdvice] size scan failed: {e}")
    try:
        data = _hf_get(
            "https://huggingface.co/api/models?filter=gguf&sort=downloads"
            "&direction=-1&limit=25", timeout=10)
        for m in data:
            rid = m.get("id", "")
            if rid and rid not in repos:
                repos[rid] = {
                    "id": rid,
                    "downloads": m.get("downloads", 0),
                    "likes": m.get("likes", 0),
                }
    except Exception as e:
        print(f"[ModelAdvice] top scan failed: {e}")

    ranked = sorted(repos.values(), key=lambda r: r["downloads"], reverse=True)

    candidates = []
    seen_files = set()
    for repo in ranked[:12]:
        rid = repo["id"]
        if _is_spam(rid):
            continue
        try:
            tree = _hf_get(
                f"https://huggingface.co/api/models/{rid}/tree/main?recursive=true", timeout=12)
        except Exception:
            continue
        for entry in tree:
            path = entry.get("path", "")
            if not path.endswith(".gguf"):
                continue
            if path in seen_files:
                continue
            path_low = path.lower()
            if any(part in path_low for part in _NON_MODEL_PARTS):
                continue
            size_b = entry.get("size", -1)
            if size_b is None or size_b <= 0:
                lfs = entry.get("lfs") or {}
                size_b = lfs.get("size", -1)
            if size_b <= 0:
                continue
            params, active, quant = _parse_gguf(path)
            if not params or not quant:
                continue
            if quant not in _QUANT_GB_PER_B and not quant.startswith("IQ"):
                continue
            if _is_specialized(path_low):
                continue
            seen_files.add(path)
            candidates.append({
                "name": path.split("/")[-1].replace(".gguf", ""),
                "repo": rid,
                "family": _guess_family(path),
                "params": params,
                "active": active,
                "quant": quant,
                "size_gb": size_b / 1024**3,
                "downloads": repo["downloads"],
                "likes": repo["likes"],
                "url": f"https://huggingface.co/{rid}/blob/main/{path}",
            })
    return candidates


# ── Evaluation ────────────────────────────────────────────────────

def _score(cand):
    factor = _FAMILY_FACTOR.get(cand["family"], 1.0)
    return cand["params"] * factor * (1 + (cand["downloads"] + 1) ** 0.2 / 40)


def _fits(cand, budget_gb):
    return cand["size_gb"] + _OVERHEAD_GB <= budget_gb


# ── Text (localized) ──────────────────────────────────────────────

def _lang():
    try:
        cfg = configparser.ConfigParser()
        cfg.read(os.path.join(_get_vass_root(), "config", "settings.ini"), encoding="utf-8")
        return cfg.get("locale", "language", fallback="it")
    except Exception:
        return "it"


def _gb(v):
    return f"{v:.1f} GB"


def _fmt_params(c):
    if c["active"]:
        return f"{c['params']:.0f}B ({c['active']:.0f}B attivi)" if _lang() == "it" \
            else f"{c['params']:.0f}B ({c['active']:.0f}B active)"
    return f"{c['params']:.0f}B"


def _build_text(hw, cur, candidates, budget):
    it = _lang() == "it"

    def t(it_s, en_s):
        return it_s if it else en_s

    if cur["name"]:
        cur_line = t(f"Modello attuale: {cur['name']}",
                     f"Current model: {cur['name']}")
    else:
        cur_line = t("Nessun modello configurato in settings.ini.",
                     "No model configured in settings.ini.")
    hw_line = t(
        f"GPU: {hw['gpu_name'] or 'non rilevata'} - VRAM {_gb(hw['vram_total_gb'])} "
        f"(libera {_gb(hw['vram_free_gb'])}), RAM libera {_gb(hw['ram_free_gb'])}.",
        f"GPU: {hw['gpu_name'] or 'not detected'} - VRAM {_gb(hw['vram_total_gb'])} "
        f"(free {_gb(hw['vram_free_gb'])}), free RAM {_gb(hw['ram_free_gb'])}.")

    good = [c for c in candidates if _fits(c, budget)]
    if not good:
        lines = [
            t("Nessun modello compatibile trovato nelle dimensioni di questo PC.",
              "No compatible model found within this PC's size budget."),
            cur_line, hw_line,
            t("Suggerimento: libera VRAM o RAM, oppure resta con il modello attuale.",
              "Tip: free VRAM or RAM, or keep the current model."),
        ]
        return "\n".join(lines)

    good.sort(key=_score, reverse=True)
    best = good[0]
    cur_score = cur["params"] * _FAMILY_FACTOR.get(cur["family"], 1.0)

    lines = [cur_line, hw_line]
    if best["params"] > cur["params"] or (best["params"] == cur["params"] and best["quant"] != cur["quant"]):
        if best["params"] > cur["params"]:
            reason_it = f"piu' intelligente del modello attuale ({best['params']:.0f}B contro {cur['params']:.0f}B)"
            reason_en = f"smarter than the current model ({best['params']:.0f}B vs {cur['params']:.0f}B)"
        else:
            reason_it = f"stessa dimensione ({best['params']:.0f}B) ma quantizzazione migliore ({best['quant']} invece di {cur['quant'] or '?'})"
            reason_en = f"same size ({best['params']:.0f}B) but better quantization ({best['quant']} instead of {cur['quant'] or '?'})"
        lines.append(t(
            f"Consiglio: {best['name']}. {_fmt_params(best)}, file {_gb(best['size_gb'])}, "
            f"~{best['downloads'] / 1e6:.1f} milioni di download. E' {reason_it} e rientra nella "
            f"VRAM totale ({_gb(best['size_gb'] + _OVERHEAD_GB)} stimati, {_gb(budget)} disponibili). "
            f"Cerca '{best['repo']}' su Hugging Face.",
            f"Recommendation: {best['name']}. {_fmt_params(best)}, file {_gb(best['size_gb'])}, "
            f"~{best['downloads'] / 1e6:.1f}M downloads. It is {reason_en} and fits the total "
            f"VRAM (~{_gb(best['size_gb'] + _OVERHEAD_GB)} estimated, {_gb(budget)} available). "
            f"Search '{best['repo']}' on Hugging Face."))
        top3 = "\n".join(
            f"- {c['name']} ({_gb(c['size_gb'])} file, {c['downloads'] / 1e6:.1f}M download)"
            for c in good[:3])
        lines.append(t("Alternative:", "Alternatives:"))
        lines.append(top3)
    else:
        lines.append(t(
            f"Il modello attuale e' gia' il migliore per questo PC: nessun candidato ha "
            f"un punteggio superiore. Il migliore trovato e' {good[0]['name']} con "
            f"{_fmt_params(good[0])} ma non supera il tuo.",
            f"The current model is already the best for this PC: no candidate scores higher. "
            f"The best found is {good[0]['name']} with {_fmt_params(good[0])} but it does not "
            f"beat yours."))
    return "\n".join(lines)


# ── Main entry ────────────────────────────────────────────────────

def get_model_advice() -> str:
    hw = _get_hardware()
    cur = _get_current_model()

    if hw["vram_total_gb"] > 0:
        budget = hw["vram_total_gb"]
    else:
        budget = hw["ram_free_gb"] * 0.7

    candidates = None
    try:
        if os.path.exists(_cache_path()):
            with open(_cache_path(), encoding="utf-8") as f:
                cache = json.load(f)
            if time.time() - cache.get("ts", 0) < _CACHE_TTL:
                candidates = cache.get("candidates")
    except Exception:
        pass

    if candidates is None:
        candidates = _scan_hf()
        try:
            os.makedirs(os.path.dirname(_cache_path()), exist_ok=True)
            with open(_cache_path(), "w", encoding="utf-8") as f:
                json.dump({"ts": time.time(), "candidates": candidates},
                          f, ensure_ascii=False)
        except Exception:
            pass
        print(f"[ModelAdvice] scan complete: {len(candidates)} candidates")

    return _build_text(hw, cur, candidates, budget)
