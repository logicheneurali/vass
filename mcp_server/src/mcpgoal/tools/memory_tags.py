import json
import time as _time
from pathlib import Path
from . import to_num

TAG_WEIGHTS = {
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
MIN_RELEVANCE = 10


async def save_tags(tags: str, allowed_root: str, entry_id: str = "") -> str:
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
    }
    data["entries"].append(entry)

    tags_path.parent.mkdir(parents=True, exist_ok=True)
    tags_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"saved: {len(tag_list)} tags, relevance {relevance}"
