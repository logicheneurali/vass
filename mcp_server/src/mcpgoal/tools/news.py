"""World news tools — read daily events digest from private_world_events.json."""
import json
import os


_WORLD_EVENTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))),
    "Allowed_root", "private_world_events.json",
)


def _load_events():
    try:
        with open(_WORLD_EVENTS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"events": {}}


async def read_news(date: str) -> str:
    """Read world events for a specific date. Use for questions about 'what happened today/yesterday'.
    Args:
        date: date in YYYY-MM-DD format (e.g. '2026-07-28')
    Returns JSON with summary, articles, categories, and top_headlines for that date.
    """
    data = _load_events()
    events = data.get("events", {})

    if date not in events:
        return json.dumps({"results": [], "message": f"No events found for {date}"}, ensure_ascii=False)

    result = {date: events[date]}
    return json.dumps({"results": result}, ensure_ascii=False)


async def read_news_range(from_date: str, to_date: str) -> str:
    """Read world events for a date range.
    Args:
        from_date: start date in YYYY-MM-DD format
        to_date: end date in YYYY-MM-DD format (inclusive)
    Returns JSON with summary, articles, categories, and top_headlines for each date in the range.
    """
    data = _load_events()
    events = data.get("events", {})

    result = {}
    for d in sorted(events):
        if from_date <= d <= to_date:
            result[d] = events[d]

    if not result:
        return json.dumps(
            {"results": {}, "message": f"No events found between {from_date} and {to_date}"},
            ensure_ascii=False)

    return json.dumps({"results": result}, ensure_ascii=False)
