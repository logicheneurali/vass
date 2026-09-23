"""World news tools — read daily events digest from private_world_events.json."""
import json
import os
from datetime import datetime, timezone


_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
_WORLD_EVENTS_PATH = os.path.join(_ROOT, "Allowed_root", "private_world_events.json")
_RSS_CACHE_PATH = os.path.join(_ROOT, "Allowed_root", "rss_cache.json")


def _load_events():
    try:
        with open(_WORLD_EVENTS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"events": {}}


def _load_rss_cache():
    try:
        with open(_RSS_CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"feeds": {}}


def _rss_items_for_date(date_str):
    """RSS items whose pubDate falls on the requested calendar date (UTC).
    Returns (items_list, is_fresh) where is_fresh is True only if at least
    one feed was polled today (UTC)."""
    rss = _load_rss_cache()
    feeds = rss.get("feeds", {})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    is_fresh = False
    items = []
    for feed_id, feed_data in feeds.items():
        last_poll = feed_data.get("last_poll", "")
        if last_poll:
            poll_date = last_poll[:10] if len(last_poll) >= 10 else ""
            if poll_date == today:
                is_fresh = True
        for item in feed_data.get("items", []):
            pub = (item.get("pubDate") or "").strip()
            if not pub:
                continue
            # Try to extract YYYY-MM-DD from various formats
            pub_day = pub[:10] if len(pub) >= 10 else ""
            if pub_day == date_str:
                items.append(item)
    return items, is_fresh


async def _fallback_search(keywords):
    """Search RSS cache (freshness-gated) and fall back to live web search.
    Returns a list of normalized article dicts with provenance tags."""
    from mcpgoal.tools.playwright import search_web as _search_web
    terms = [k.lower() for k in keywords.split()]
    matches = []

    # Try RSS cache first (freshness-gated)
    items, is_fresh = _rss_items_for_date(datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    if is_fresh and items:
        for item in items:
            tags = item.get("tags", "")
            if isinstance(tags, list):
                tags = " ".join(str(t) for t in tags)
            text = (
                (item.get("title", "") + " " +
                 item.get("summary", "") + " " + str(tags)).lower()
            )
            if any(t in text for t in terms):
                matches.append({
                    "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "title": item.get("title", ""),
                    "source": "rss cache",
                    "category": "",
                    "location": "",
                    "significance": "",
                    "summary": item.get("summary", ""),
                    "link": item.get("link", ""),
                })
        if matches:
            return matches

    # Fall back to live web search
    try:
        raw = await _search_web(keywords)
        results = json.loads(raw)
        if isinstance(results, list):
            for r in results:
                matches.append({
                    "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "title": r.get("title", ""),
                    "source": "web",
                    "category": "",
                    "location": "",
                    "significance": "",
                    "summary": r.get("snippet", ""),
                    "link": r.get("url", ""),
                })
    except Exception:
        pass
    return matches


async def read_news(date: str, max_chars: int = 20000) -> str:
    """Read world events for a specific date. Use for questions about 'what happened today/yesterday'.
    Args:
        date: date in YYYY-MM-DD format (e.g. '2026-07-28')
        max_chars: optional cap on the returned JSON size.
    Returns JSON with summary, articles, categories, and top_headlines for that date.
    """
    data = _load_events()
    events = data.get("events", {})

    if date in events:
        view = _day_view(events[date], summary_only=False, day_date=date)
        return _to_json({"results": {date: view}}, max_chars)

    # Fallback 1: RSS cache for this date
    rss_items, is_fresh = _rss_items_for_date(date)
    if is_fresh and rss_items:
        today_str = date
        summary_parts = []
        articles = []
        cats = set()
        for item in rss_items[:50]:
            summary_parts.append(item.get("summary", item.get("title", "")))
            title = item.get("title", "")
            link = item.get("link", "")
            source = "rss cache"
            tags = item.get("tags", "")
            if isinstance(tags, list):
                tags = " ".join(str(t) for t in tags)
            art = {
                "title": title,
                "link": link,
                "source": source,
                "summary": (item.get("summary") or "")[:300],
            }
            if tags:
                art["tags"] = tags
                cats.update(t.strip() for t in tags.split(",") if t.strip())
            articles.append(art)
        view = {
            "summary": " | ".join(summary_parts[:3]) if summary_parts else "",
            "categories": sorted(cats)[:10],
            "articles": articles[:8],
        }
        return _to_json({"results": {today_str: view}}, max_chars)

    # Fallback 2: websearch
    fallback = await _fallback_search(f"world news on {date}")
    if fallback:
        return _to_json({"results": fallback}, max_chars)

    return json.dumps({"results": [], "message": f"No events found for {date}"}, ensure_ascii=False)


async def read_news_range(from_date: str, to_date: str, max_chars: int = 20000) -> str:
    """Read world events for a date range.
    Args:
        from_date: start date in YYYY-MM-DD format
        to_date: end date in YYYY-MM-DD format (inclusive)
        max_chars: optional cap on the returned JSON size.
    Returns JSON with the daily summary per date in the range. For ranges
    spanning more than a few days the per-day summary is included instead of
    the full article lists, so the result stays small enough to fit in the
    model's context window.
    """
    data = _load_events()
    events = data.get("events", {})

    days = sorted(d for d in events if from_date <= d <= to_date)
    if days:
        summary_only = len(days) > 3
        result = {d: _day_view(events[d], summary_only=summary_only, day_date=d)
                  for d in days}
        return _to_json({"results": result}, max_chars)

    # No archive data: try RSS cache across the range
    result = {}
    from_dt = datetime.strptime(from_date, "%Y-%m-%d")
    to_dt = datetime.strptime(to_date, "%Y-%m-%d")
    day = from_dt
    while day <= to_dt:
        date_str = day.strftime("%Y-%m-%d")
        rss_items, is_fresh = _rss_items_for_date(date_str)
        if is_fresh and rss_items:
            summary_parts = []
            articles = []
            cats = set()
            for item in rss_items[:30]:
                summary_parts.append(item.get("summary", item.get("title", "")))
                title = item.get("title", "")
                link = item.get("link", "")
                tags = item.get("tags", "")
                art = {
                    "title": title,
                    "link": link,
                    "source": "rss cache",
                    "summary": (item.get("summary") or "")[:300],
                }
                if tags:
                    if isinstance(tags, list):
                        tags = " ".join(str(t) for t in tags)
                    art["tags"] = tags
                    cats.update(t.strip() for t in tags.split(",") if t.strip())
                articles.append(art)
            result[date_str] = {
                "summary": " | ".join(summary_parts[:3]) if summary_parts else "",
                "categories": sorted(cats)[:10],
                "articles": articles[:8],
            }
        day = day.replace(day=day.day + 1)

    if result:
        return _to_json({"results": result}, max_chars)

    # Fallback to websearch
    fallback = await _fallback_search(f"world news from {from_date} to {to_date}")
    if fallback:
        return _to_json({"results": fallback}, max_chars)

    return json.dumps(
        {"results": {}, "message": f"No events found between {from_date} and {to_date}"},
        ensure_ascii=False)


async def search_news(keywords: str, max_chars: int = 20000) -> str:
    """Search world events by keywords across all dates.
    Use for questions like 'find news about climate', 'cerca noticias su elections', 'what happened with X'.
    Args:
        keywords: space-separated keywords to search in titles, summaries, categories, and per-category summaries
        max_chars: optional cap on the returned JSON size.
    Returns JSON with matching articles sorted by date (newest first).
    """
    data = _load_events()
    events = data.get("events", {})
    terms = [k.lower() for k in keywords.split()]

    matches = []
    for d in sorted(events, reverse=True):
        day = events[d]
        for art in day.get("articles", []):
            text = (
                (art.get("title", "") + " " +
                 art.get("summary", "") + " " +
                 art.get("category", "") + " " +
                 art.get("location", "") + " " +
                 art.get("source", "")).lower()
            )
            if any(t in text for t in terms):
                # Compact form when the article has structured fields.
                if art.get("actor") or art.get("action"):
                    matches.append({
                        "date": d,
                        "title": f"{art.get('actor', '')} — {art.get('action', '')}".strip(" —"),
                        "source": art.get("source", ""),
                        "category": art.get("category", ""),
                        "location": art.get("location", ""),
                        "significance": art.get("significance", ""),
                        "summary": art.get("title", "") or art.get("outcome", ""),
                        "link": "",
                    })
                else:
                    matches.append({
                        "date": d,
                        "title": art.get("title", ""),
                        "source": art.get("source", ""),
                        "category": art.get("category", ""),
                        "location": art.get("location", ""),
                        "significance": art.get("significance", ""),
                        "summary": art.get("summary", ""),
                        "link": art.get("link", ""),
                    })
        # Days whose articles were cleaned up still carry per-category summaries
        for cs in day.get("category_summaries", []):
            text = (
                (cs.get("summary", "") + " " +
                 cs.get("category", "")).lower()
            )
            if any(t in text for t in terms):
                links = cs.get("links") or []
                matches.append({
                    "date": d,
                    "title": f"{cs.get('category', 'other').capitalize()} — day summary",
                    "source": "world events archive",
                    "category": cs.get("category", "other"),
                    "location": "",
                    "significance": "archive",
                    "summary": cs.get("summary", ""),
                    "link": links[0] if links else "",
                })
        # Compact structured events from cleaned-up days (actor/action/location).
        for ef in day.get("events_fixed", []):
            text = (
                (ef.get("actor", "") + " " +
                 ef.get("action", "") + " " +
                 ef.get("location", "") + " " +
                 ef.get("title", "") + " " +
                 ef.get("outcome", "")).lower()
            )
            if any(t in text for t in terms):
                cats = day.get("categories", [])
                matches.append({
                    "date": d,
                    "title": f"{ef.get('actor', '')} — {ef.get('action', '')}".strip(" —"),
                    "source": "world events archive",
                    "category": cats[0] if cats else "other",
                    "location": ef.get("location", ""),
                    "significance": ef.get("significance", "archive"),
                    "summary": ef.get("title", "") or ef.get("outcome", ""),
                    "link": "",
                })

    if matches:
        return _to_json({"results": matches}, max_chars)

    # Fallback: RSS + websearch
    fallback = await _fallback_search(keywords)
    if fallback:
        return _to_json({"results": fallback}, max_chars)

    return json.dumps(
        {"results": [], "message": f"No articles matching '{keywords}' found"},
        ensure_ascii=False)


def _compact_events(day, day_date):
    """Compact structured events for a day: use stored events_fixed when the
    day was cleaned up, otherwise derive them on the fly from articles that
    have actor/action (deduplicated by actor+action+location). Falls back to
    the raw articles when no structured fields are available yet."""
    if day.get("events_fixed"):
        return day["events_fixed"]
    seen = set()
    out = []
    for a in day.get("articles", []):
        actor = (a.get("actor") or "").strip()
        action = (a.get("action") or "").strip()
        if not actor and not action:
            continue
        key = (actor.lower(), action.lower(), (a.get("location") or "").lower())
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "date": day_date,
            "location": a.get("location", ""),
            "actor": actor,
            "action": action,
            "title": (a.get("title") or "")[:90],
            "outcome": (a.get("outcome") or a.get("reactions") or "")[:120],
            "significance": a.get("significance", ""),
        })
    return out


def _day_view(day, summary_only, day_date=""):
    """A lightweight view of one day: full day summary + categories, and the
    compact structured events (stored events_fixed or derived on the fly from
    articles with actor/action). Days without structured fields fall back to
    the article list (or topics for long ranges)."""
    view = {
        "summary": day.get("summary", ""),
        "categories": day.get("categories", []),
    }
    events = _compact_events(day, day_date)
    if events:
        view["events"] = events
    else:
        articles = day.get("articles", [])
        if not summary_only:
            view["articles"] = articles[:8]
        else:
            # Keep just the first line of each article title so the range still
            # gives a sense of what happened without shipping every article.
            view["topics"] = [a.get("title", "")[:120]
                              for a in articles[:20]]
    return view


def _to_json(obj, max_chars):
    """Serialize to JSON, then — if it exceeds max_chars — rebuild with the
    per-day contents truncated so the result is always valid JSON and bounded."""
    out = json.dumps(obj, ensure_ascii=False)
    if not max_chars or max_chars <= 0 or len(out) <= max_chars:
        return out
    # Truncate the largest text fields until the JSON fits.
    if isinstance(obj, dict) and "results" in obj:
        res = obj["results"]
        if isinstance(res, list):
            # search_news: cap the list of matches by estimated size.
            half = max(1, len(res) // 2)
            while len(res) > 1 and len(json.dumps(obj, ensure_ascii=False)) > max_chars:
                res = res[:half]
                obj["results"] = res
                half = max(1, half // 2)
            out = json.dumps(obj, ensure_ascii=False)
            return out
        # Iterative truncation of summaries/lists per day.
        changed = True
        while len(out) > max_chars and changed:
            changed = False
            for d in sorted(res):
                day = res[d]
                if not isinstance(day, dict):
                    continue
                s = day.get("summary", "")
                if isinstance(s, str) and len(s) > 200:
                    day["summary"] = s[:len(s) * 3 // 4]
                    changed = True
                if not changed:
                    for key in ("articles", "topics"):
                        if isinstance(day.get(key), list) and len(day[key]) > 1:
                            day[key] = day[key][:max(1, len(day[key]) // 2)]
                            changed = True
                            break
                if changed:
                    break
            if changed:
                out = json.dumps(obj, ensure_ascii=False)
    return out
