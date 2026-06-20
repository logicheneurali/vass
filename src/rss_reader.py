import json
import os
import threading
import time
import feedparser

from datetime import datetime, timezone, timedelta


class RssReader:
    def __init__(self, feeds_path, cache_path, on_new_items=None):
        self._feeds_path = feeds_path
        self._cache_path = cache_path
        self._on_new_items = on_new_items
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._feeds = []
        self._cache = {}
        self._load_feeds()
        self._load_cache()

    def _load_feeds(self):
        try:
            with open(self._feeds_path, encoding="utf-8") as f:
                self._feeds = json.load(f).get("feeds", [])
        except Exception:
            self._feeds = []
            try:
                os.makedirs(os.path.dirname(self._feeds_path), exist_ok=True)
                with open(self._feeds_path, "w", encoding="utf-8") as f:
                    json.dump({"feeds": []}, f, ensure_ascii=False, indent=2)
                    f.write("\n")
            except Exception:
                pass

    def _load_cache(self):
        try:
            with open(self._cache_path, encoding="utf-8") as f:
                self._cache = json.load(f).get("feeds", {})
        except Exception:
            self._cache = {}

    def _save_cache(self):
        with self._lock:
            with open(self._cache_path, "w", encoding="utf-8") as f:
                json.dump({"feeds": self._cache}, f, ensure_ascii=False, indent=2)
                f.write("\n")

    def reload_feeds(self):
        self._load_feeds()

    def get_feeds(self):
        return [f for f in self._feeds if f.get("active", True)]

    def fetch_feed(self, feed):
        url = feed.get("url", "")
        feed_id = feed.get("id", "")
        name = feed.get("name", "")
        try:
            parsed = feedparser.parse(url)
        except Exception as e:
            print(f"[RSS] Failed to parse {name}: {e}")
            return []
        if parsed.bozo and not parsed.entries:
            return []
        items = []
        for entry in parsed.entries:
            pub_date = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    import calendar
                    ts = calendar.timegm(entry.published_parsed)
                    pub_date = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                except Exception:
                    pass
            if not pub_date and hasattr(entry, "updated_parsed") and entry.updated_parsed:
                try:
                    import calendar
                    ts = calendar.timegm(entry.updated_parsed)
                    pub_date = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                except Exception:
                    pass
            raw_guid = entry.get("id") or entry.get("link", "")
            if "#" in raw_guid and raw_guid.startswith("http"):
                raw_guid = raw_guid.split("#")[0]
            if raw_guid.startswith("http"):
                from urllib.parse import urlparse, urlunparse
                parsed = urlparse(raw_guid)
                guid = urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
            else:
                guid = raw_guid
            items.append({
                "guid": guid,
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "summary": entry.get("summary", entry.get("description", "")),
                "pubDate": pub_date,
                "source": name,
                "seen": False,
            })
        return items

    def fetch_now(self, feed_id=None):
        active = self.get_feeds()
        if feed_id:
            active = [f for f in active if f.get("id") == feed_id]
        all_items = []
        for feed in active:
            items = self.fetch_feed(feed)
            fid = feed.get("id", "")
            now = datetime.now(timezone.utc).isoformat()
            with self._lock:
                cache_entry = self._cache.get(fid, {"items": [], "last_poll": None})
                existing_guids = {it.get("guid") for it in cache_entry.get("items", [])}
                old_last_poll = cache_entry.get("last_poll")
                cutoff = None
                if old_last_poll:
                    try:
                        cutoff = datetime.fromisoformat(old_last_poll) - timedelta(hours=24)
                    except Exception:
                        pass
                for item in items:
                    pub = item.get("pubDate")
                    if not pub:
                        continue
                    if cutoff:
                        try:
                            item_date = datetime.fromisoformat(pub)
                            if item_date < cutoff:
                                continue
                        except Exception:
                            pass
                    if item.get("guid") not in existing_guids:
                        cache_entry.setdefault("items", []).append(item)
                        existing_guids.add(item.get("guid"))
                if len(cache_entry.get("items", [])) > 20:
                    cache_entry["items"] = cache_entry["items"][-20:]
                cache_entry["last_poll"] = now
                self._cache[fid] = cache_entry
            all_items.extend(items)
        self._save_cache()
        return all_items

    def get_new_items(self):
        result = []
        with self._lock:
            for fid, entry in self._cache.items():
                for item in entry.get("items", []):
                    if not item.get("seen", False):
                        result.append(item)
        return result

    def get_cached(self, feed_id=None, limit=20):
        with self._lock:
            if feed_id:
                entry = self._cache.get(feed_id, {})
                return entry.get("items", [])[-limit:]
            all_items = []
            for fid, entry in self._cache.items():
                all_items.extend(entry.get("items", []))
            return all_items[-limit:]

    def mark_seen(self, guid):
        with self._lock:
            for fid, entry in self._cache.items():
                for item in entry.get("items", []):
                    if item.get("guid") == guid:
                        item["seen"] = True
        self._save_cache()

    def mark_guids_seen(self, guids):
        guids_set = set(guids)
        with self._lock:
            for fid, entry in self._cache.items():
                for item in entry.get("items", []):
                    if item.get("guid") in guids_set:
                        item["seen"] = True
        self._save_cache()

    def start_polling(self):
        self._stop_event.clear()
        t = threading.Thread(target=self._poll_loop, daemon=True)
        t.start()

    def stop_polling(self):
        self._stop_event.set()

    def _poll_loop(self):
        while not self._stop_event.is_set():
            self._load_feeds()
            active = self.get_feeds()
            now = datetime.now(timezone.utc)
            min_sleep = 60
            for feed in active:
                fid = feed.get("id", "")
                interval_str = str(feed.get("interval", "60"))
                try:
                    interval_val = int(interval_str)
                except (ValueError, TypeError):
                    interval_val = 60
                unit = feed.get("interval_unit", "min")
                if unit == "hours":
                    interval_sec = interval_val * 3600
                elif unit == "days":
                    interval_sec = interval_val * 86400
                else:
                    interval_sec = interval_val * 60
                if interval_sec < min_sleep:
                    min_sleep = interval_sec
                last_poll_str = (self._cache.get(fid) or {}).get("last_poll")
                if last_poll_str:
                    try:
                        last_poll = datetime.fromisoformat(last_poll_str).replace(tzinfo=timezone.utc)
                    except Exception:
                        last_poll = None
                else:
                    last_poll = None
                elapsed = (now - last_poll).total_seconds() if last_poll else interval_sec + 1
                if elapsed >= interval_sec:
                    print(f"[RSS] Polling {feed.get('name', '?')}")
                    new_items = []
                    items = self.fetch_feed(feed)
                    fid2 = feed.get("id", "")
                    now_iso = now.isoformat()
                    with self._lock:
                        cache_entry = self._cache.get(fid2, {"items": [], "last_poll": None})
                        existing_guids = {it.get("guid") for it in cache_entry.get("items", [])}
                        cutoff = None
                        if last_poll:
                            cutoff = last_poll - timedelta(hours=24)
                        for item in items:
                            pub = item.get("pubDate")
                            if not pub:
                                continue
                            if cutoff:
                                try:
                                    import calendar
                                    item_date = datetime.fromisoformat(pub)
                                    if item_date < cutoff:
                                        continue
                                except Exception:
                                    pass
                            if item.get("guid") not in existing_guids:
                                cache_entry.setdefault("items", []).append(item)
                                new_items.append(item)
                                existing_guids.add(item.get("guid"))
                        if len(cache_entry.get("items", [])) > 20:
                            cache_entry["items"] = cache_entry["items"][-20:]
                        cache_entry["last_poll"] = now_iso
                        self._cache[fid2] = cache_entry
                    self._save_cache()
                    if new_items and self._on_new_items and last_poll is not None:
                        try:
                            self._on_new_items(new_items)
                        except Exception as e:
                            print(f"[RSS] on_new_items callback error: {e}")
            if min_sleep < 30:
                min_sleep = 30
            if self._stop_event.wait(min_sleep):
                break
