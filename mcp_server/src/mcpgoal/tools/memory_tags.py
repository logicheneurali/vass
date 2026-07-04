import json
import time as _time
from pathlib import Path
from . import to_num

_DEFAULT_WEIGHTS = {
    "personal_data": 10, "health": 10, "finance": 10,
    "family": 10, "pets": 10,
    "contacts": 8,
    "preferences": 7, "personal_interests": 7, "purchases": 7,
    "orders": 6, "bills": 6, "invoices": 6, "work": 6, "education": 6,
    "favorite_music": 5, "food": 5, "home": 5, "personal_means_of_transport": 5,
    "deliveries": 4, "travel": 4, "tech": 4, "events": 4,
    "sales": 3,
    "generic": 1,
}
TAG_WEIGHTS = dict(_DEFAULT_WEIGHTS)
MIN_RELEVANCE = 10


def _refresh_weights(allowed_root):
    global TAG_WEIGHTS, MIN_RELEVANCE
    cfg = Path(allowed_root).resolve() / "tags_config.json" if allowed_root else None
    if cfg and cfg.exists():
        try:
            loaded = json.loads(cfg.read_text(encoding="utf-8"))
            tw = loaded.get("tags", {})
            if tw:
                TAG_WEIGHTS = tw
            MIN_RELEVANCE = loaded.get("min_relevance", 10)
            return
        except Exception:
            pass
    TAG_WEIGHTS = dict(_DEFAULT_WEIGHTS)
    MIN_RELEVANCE = 10


async def save_tags(tags: str, allowed_root: str, entry_id: str = "", source: str = "chat", content: str = "") -> str:
    _refresh_weights(allowed_root)
    tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()]
    if not tag_list:
        return "error: no valid tags provided"

    invalid = [t for t in tag_list if t not in TAG_WEIGHTS]
    if invalid:
        available = ", ".join(sorted(TAG_WEIGHTS.keys()))
        return f"error: invalid tags: {', '.join(invalid)}. Available: {available}"

    relevance = sum(TAG_WEIGHTS[t] for t in tag_list)
    if relevance < MIN_RELEVANCE:
        return f"skipped: relevance {relevance} below minimum {MIN_RELEVANCE}"

    root = Path(allowed_root).resolve()
    tags_path = root / "memory_tags.json"

    try:
        raw = tags_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception:
        data = {"entries": []}

    import datetime
    entry = {
        "id": entry_id if entry_id else str(int(_time.time() * 1000)),
        "tags": tag_list,
        "relevance": relevance,
        "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": source,
        "content": content[:300] if content else "",
    }
    existing_idx = None
    for i, e in enumerate(data["entries"]):
        if e.get("id") == entry["id"]:
            existing_idx = i
            break
    if existing_idx is not None:
        data["entries"][existing_idx] = entry
    else:
        data["entries"].append(entry)

    tags_path.parent.mkdir(parents=True, exist_ok=True)
    tags_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"saved: {len(tag_list)} tags, relevance {relevance}"


async def search_tags(tags: str, allowed_root: str) -> str:
    """Search tagged memory entries by comma-separated tags. Only returns entries from active sources."""
    root = Path(allowed_root).resolve()
    tags_path = root / "memory_tags.json"
    sources_path = root / "memory_sources.json"

    tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()]
    if not tag_list:
        return json.dumps({"results": [], "count": 0, "error": "no tags provided"})

    try:
        data = json.loads(tags_path.read_text(encoding="utf-8"))
    except Exception:
        return json.dumps({"results": [], "count": 0})

    try:
        sources_cfg = json.loads(sources_path.read_text(encoding="utf-8"))
    except Exception:
        sources_cfg = {}

    active_sources = {"chat"}
    for src, enabled in sources_cfg.items():
        if enabled:
            active_sources.add(src)

    matching = []
    for entry in data.get("entries", []):
        entry_tags = entry.get("tags", [])
        if not any(t in entry_tags for t in tag_list):
            continue
        src = entry.get("source", "chat")
        if src not in active_sources:
            continue
        matching.append(entry)

    matching.sort(key=lambda e: e.get("relevance", 0), reverse=True)
    top10 = matching[:10]

    return json.dumps({"results": top10, "count": len(top10)}, ensure_ascii=False)
