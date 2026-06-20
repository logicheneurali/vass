# RSS Feed Integration — Design Doc

**Date**: 2026-06-20
**Status**: approved

---

## Overview

Integrate RSS feed reading into VASS with background polling for notifications and voice commands for on-demand reading. New articles appear in the notification bell popup with clickable links that open a reusable HTML viewer.

---

## Architecture

```
rss_feeds.json ──> RssReader (singleton)
                     │
                     ├── polling thread (intervallo per feed)
                     │     └── nuovi item → NotificationManager
                     │
                     ├── rss_cache.json (cap 20 item/feed, last_poll)
                     │
                     ├── get_new_items(feed?) → NotificationManager
                     ├── get_cached(feed?)     → GUI
                     ├── mark_seen(guid)       → deduplica notifiche
                     └── fetch_now(feed?)      → VASScript rss_fetch()
```

### Files

| File | Status | Purpose |
|------|--------|---------|
| `Allowed_root/rss_feeds.json` | done | Feed definitions (name, url, active, interval, interval_unit, lang) |
| `Allowed_root/rss_cache.json` | new | Cached items per feed + last_poll timestamps |
| `src/rss_reader.py` | new | Backend: fetch, cache, polling |
| `src/main.py` | modified | Start/stop polling, `_on_rss_items()` callback, `rss_fetch` integration |
| `src/script_engine.py` | modified | New VASScript function `rss_fetch(name?)` |
| `src/gui.py` | modified | Popup notifiche QDialog + QTextBrowser, HTMLViewer modale |
| `scripts/rss_read.vass` | new | Voice command script |
| `config/commands_*.ini` | modified | "leggi feed RSS" → script:rss_read |
| `locales/*.json` | modified | Section `rss` with localized labels |
| `requirements.txt` | modified | Add `feedparser` |

---

## Data Model

### `rss_cache.json`
```json
{
  "feeds": {
    "<feed_id>": {
      "last_poll": "2026-06-20T10:30:00",
      "items": [
        {
          "guid": "https://...",
          "title": "Trump announces new policy",
          "link": "https://...",
          "summary": "In a press conference today...",
          "pubDate": "2026-06-20T09:15:00",
          "source": "BBC News",
          "seen": false
        }
      ]
    }
  }
}
```

- `seen`: boolean, set to `true` when user opens the notification popup (not when notification is created). `get_new_items()` returns items with `seen==False`.
- Cap: 20 items per feed, FIFO removal of oldest
- `pubDate` may be `null` if feed doesn't provide it → item always considered new on first fetch, deduplicated by `link`

---

## Backend: `src/rss_reader.py`

Singleton class. Dependencies: `feedparser`, `threading`.

### Public API

| Method | Description |
|--------|-------------|
| `__init__(feeds_path, cache_path, on_new_items=None)` | Loads feeds and cache |
| `reload_feeds()` | Re-reads `rss_feeds.json` |
| `get_feeds()` → list[dict] | Returns active feeds |
| `fetch_feed(feed)` → list[dict] | `feedparser.parse(url)`, normalizes entries |
| `fetch_now(feed_id=None)` → list[dict] | Fetch one or all active feeds, update cache |
| `get_new_items()` → list[dict] | Items with `seen==False` |
| `get_cached(feed_id=None, limit=20)` → list[dict] | Read-only cache access |
| `mark_seen(guid)` | Sets `seen=True` on matching item |
| `start_polling()` | Starts daemon thread |
| `stop_polling()` | Signals stop, joins thread |

### Polling Logic

1. Read all active feeds and their intervals
2. Sleep = min interval across all feeds
3. On wake: for each feed where `now - last_poll >= interval`, call `fetch_feed()`
4. New items (by `link` not in cache) → added with `seen=False`
5. Call `on_new_items(new_items)` if callback set

### Item Normalization (from feedparser entry → dict)

- `guid`: `entry.get('id')` or `entry.get('link')`
- `title`: `entry.get('title', '')`
- `link`: `entry.get('link', '')`
- `summary`: `entry.get('summary')` or `entry.get('description', '')`
- `pubDate`: parsed ISO datetime string, or `None`
- `source`: feed name from config
- `seen`: `False`

---

## GUI

### Notification Popup

Replaces current `QMenu` popup with a `QDialog` containing `QTextBrowser`.

- Layout: title bar "Notifiche (N)" + scrollable content
- Each notification: type icon + text. RSS items include an HTML anchor link
- `QTextBrowser.anchorClicked` signal → opens `HTMLViewer` for RSS links
- Size: 400×400px
- Content refreshed from `NotificationManager` unread list

### HTMLViewer (reusable modal)

- `QMainWindow` (modal), 800×600
- `QWebEngineView` for content display
- `QWebEngineUrlRequestInterceptor`: only allows same-origin + main frame requests, blocks 3rd-party images/fonts/scripts/trackers
- Post-load CSS injection via `runJavaScript`: dark theme, max-width 700px centered, hide cookie banners/sidebars
- Top bar: Back, Forward, title label, "Open in browser" button, close button
- Reusable for any URL — future: history links, AI-provided links, "approfondisci"

---

## Voice Command

### Command registration (`config/commands_it.ini` etc.)
```ini
leggi feed RSS = script:rss_read
leggi feed {param1} = script:rss_read
```

### `scripts/rss_read.vass`
```
$param1 = "{$param1}"
$items = ""
ifempty($param1,
    $items = rss_fetch(),
    $items = rss_fetch($param1)
)
$summary = ai("Ecco alcuni articoli RSS. Riassumi i più importanti in italiano in 3-4 frasi: " + $items)
say($summary)
```

---

## VASScript: `rss_fetch(name?)`

Added to `script_engine.py:_call_function`. Added to `_SIDE_EFFECT_FUNCTIONS` (makes network requests).

Returns JSON array of items (title, summary, link, pubDate, source).

---

## NotificationManager Integration

- `notification_manager.add(title=source, message=title, priority=5, data={"type": "rss", "link": link, "guid": guid})`
- Bell counter increments via existing `gui.bell_signal`
- Click on bell → QDialog popup renders all notification types, RSS items show clickable link

---

## i18n (`locales/*.json`)

New section `rss`:
- `notifications_title`: "Notifiche"
- `read_article`: "Leggi articolo completo"
- `viewer_title`: "HTML Viewer"
- `open_in_browser`: "Apri nel browser"
- `new_articles_count`: "{count} nuovi articoli"

---

## Excluded from this spec

- TTS notification for new RSS items
- Polling retry/backoff logic
- MCP tool `rss_fetch`
- Feed auto-discovery from website URLs
