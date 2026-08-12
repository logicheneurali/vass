"""RSS Reader Plugin — polls RSS feeds and sends notifications.
Connects to VASS PluginServer for notify commands.
"""
import configparser
import json
import os
import socket
import threading
import time
from datetime import datetime, timezone, timedelta


_UI_SCHEMA = {
    "id": "rss_reader",
    "title_it": "Fonti RSS",
    "title": "RSS Feeds",
    "sections": [{
        "title_it": "Fonti",
        "title": "Feeds",
        "rows": [
            {"kind": "list", "key": "feeds",
             "label_it": "Feed RSS", "label": "RSS feeds",
             "columns": [{"key": "name", "label_it": "Nome", "label": "Name"},
                         {"key": "url", "label_it": "URL", "label": "URL"},
                         {"key": "active", "label_it": "Attivo", "label": "Active"}],
             "items": []},
            {"kind": "text", "key": "feed_name", "label_it": "Nome", "label": "Name"},
            {"kind": "text", "key": "feed_url", "label_it": "URL", "label": "URL"},
            {"kind": "toggle", "key": "feed_active", "label_it": "Attivo",
             "label": "Active", "value": True},
            {"kind": "slider", "key": "feed_interval", "label_it": "Intervallo",
             "label": "Interval", "min": 5, "max": 1440, "value": 60},
            {"kind": "combo", "key": "feed_unit", "label_it": "Unità",
             "label": "Unit", "options": ["min", "hours", "days"], "value": "min"},
            {"kind": "combo", "key": "feed_lang", "label_it": "Lingua",
             "label": "Language",
             "options": ["it", "en", "de", "fr", "es", "pt", "ja", "ko", "zh"],
             "value": "it"},
            {"kind": "button", "key": "add", "label_it": "Aggiungi", "label": "Add"},
            {"kind": "button", "key": "save", "label_it": "Salva", "label": "Save"},
            {"kind": "button", "key": "delete", "label_it": "Elimina", "label": "Delete"},
        ]
    }]
}


class RssReaderPlugin:
    def __init__(self):
        self._host = "localhost"
        self._port = 8765
        self._sock = None
        self._config = self._load_config()
        self._running = True
        self._lock = threading.Lock()
        self._feeds_path = os.path.join(self._resolve_root(), "Allowed_root", "rss_feeds.json")
        self._cache_path = os.path.join(self._resolve_root(), "Allowed_root", "rss_cache.json")
        self._feeds = []
        self._cache = {}
        self._load_feeds()
        self._load_cache()

    def _load_config(self) -> dict:
        cfg = configparser.ConfigParser()
        ini_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "settings.ini")
        if not os.path.exists(ini_path):
            example = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "settings.example.ini")
            if os.path.exists(example):
                import shutil
                shutil.copy(example, ini_path)
        if os.path.exists(ini_path):
            cfg.read(ini_path, encoding="utf-8")
        return {
            "enabled": cfg.getboolean("poll", "enabled", fallback=True),
            "category_blacklist": cfg.get("poll", "category_blacklist", fallback=""),
            "notify_enabled": cfg.getboolean("poll", "notify_enabled", fallback=True),
        }

    def _load_manifest(self) -> dict:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "plugin_manifest.json"), encoding="utf-8") as f:
            return json.load(f)

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
            try:
                os.makedirs(os.path.dirname(self._cache_path), exist_ok=True)
                with open(self._cache_path, "w", encoding="utf-8") as f:
                    json.dump({"feeds": self._cache}, f, ensure_ascii=False, indent=2)
                    f.write("\n")
            except Exception:
                pass

    # ── Declarative UI (feeds management) ────────────────────────

    def _send_ui_state(self, values):
        self._send_cmd("ui_state", {"values": values})

    def _feeds_state(self):
        return {"feeds": [
            {"id": f.get("id", ""), "name": f.get("name", ""),
             "url": f.get("url", ""), "active": bool(f.get("active", True))}
            for f in self._feeds
        ]}

    def _save_feeds_file(self):
        try:
            os.makedirs(os.path.dirname(self._feeds_path), exist_ok=True)
            with open(self._feeds_path, "w", encoding="utf-8") as f:
                json.dump({"feeds": self._feeds}, f, ensure_ascii=False, indent=2)
                f.write("\n")
        except Exception as e:
            print(f"[RSS] Save feeds failed: {e}")

    def _handle_ui_action(self, action):
        key = action.get("key", "")
        event = action.get("event", "")
        values = action.get("values") or {}
        selected = values.get("feeds_selected", "") or ""
        if event == "select":
            selected = action.get("selected", "")
        if key == "feeds" and event == "select":
            self._load_feeds()
            feed = next((f for f in self._feeds if f.get("id") == selected), None)
            if feed:
                self._send_ui_state({
                    "feed_name": feed.get("name", ""),
                    "feed_url": feed.get("url", ""),
                    "feed_active": bool(feed.get("active", True)),
                    "feed_interval": feed.get("interval", 60),
                    "feed_unit": feed.get("interval_unit", "min"),
                    "feed_lang": feed.get("lang", "it"),
                })
        elif key == "add":
            self._send_ui_state({
                "feed_name": "", "feed_url": "", "feed_active": True,
                "feed_interval": 60, "feed_unit": "min", "feed_lang": "it",
            })
        elif key == "save":
            name = str(values.get("feed_name", "")).strip()
            url = str(values.get("feed_url", "")).strip()
            if not name or not url:
                return
            try:
                interval = int(values.get("feed_interval", 60))
            except (ValueError, TypeError):
                interval = 60
            unit = str(values.get("feed_unit", "min"))
            lang = str(values.get("feed_lang", "it"))
            active = bool(values.get("feed_active", True))
            self._load_feeds()
            if selected:
                for f in self._feeds:
                    if f.get("id") == selected:
                        f.update({"name": name, "url": url, "active": active,
                                  "interval": interval, "interval_unit": unit,
                                  "lang": lang})
                        break
            else:
                import uuid
                self._feeds.append({
                    "id": uuid.uuid4().hex[:8], "name": name, "url": url,
                    "active": active, "interval": interval,
                    "interval_unit": unit, "lang": lang,
                })
            self._save_feeds_file()
            self._send_ui_state(self._feeds_state())
        elif key == "delete":
            if selected:
                self._load_feeds()
                self._feeds = [f for f in self._feeds if f.get("id") != selected]
                self._save_feeds_file()
                self._send_ui_state(self._feeds_state())

    def run(self):
        manifest = self._load_manifest()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self._sock.connect((self._host, self._port))
        except ConnectionRefusedError:
            print("[RSS] VASS not running. Exiting.")
            return

        hello = json.dumps({
            "type": "hello",
            "name": manifest["name"],
            "version": manifest["version"],
            "min_app": manifest["min_app"],
            "subscribe": manifest["subscriptions"],
        }) + "\n"
        self._sock.sendall(hello.encode("utf-8"))
        print(f"[RSS] Connected to VASS on {self._host}:{self._port}")

        self._send_cmd("ui_register", {"schema": _UI_SCHEMA})
        self._load_feeds()
        self._send_ui_state(self._feeds_state())

        threading.Thread(target=self._poll_loop, daemon=True).start()

        buf = b""
        while self._running:
            try:
                self._sock.settimeout(1.0)
                data = self._sock.recv(4096)
            except socket.timeout:
                continue
            except (ConnectionResetError, OSError):
                print("[RSS] Disconnected. Exiting.")
                break
            if not data:
                print("[RSS] Server closed connection. Exiting.")
                break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    msg = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                if msg.get("type") == "error":
                    print(f"[RSS] Server error: {msg.get('msg', 'unknown')}")
                elif msg.get("type") == "cmd" and msg.get("cmd") == "ui_action":
                    self._handle_ui_action(msg.get("action") or {})

        self._running = False
        self._sock.close()

    def _poll_loop(self):
        while self._running:
            try:
                if self._config["enabled"]:
                    self._do_poll()
            except Exception as e:
                print(f"[RSS] Poll error: {e}")
            for _ in range(30):
                if not self._running:
                    break
                time.sleep(1)

    def _do_poll(self):
        self._load_feeds()
        active = [f for f in self._feeds if f.get("active", True)]
        if not active:
            return
        now = datetime.now(timezone.utc)
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

            last_poll_str = (self._cache.get(fid) or {}).get("last_poll")
            if last_poll_str:
                try:
                    last_poll = datetime.fromisoformat(last_poll_str).replace(tzinfo=timezone.utc)
                except Exception:
                    last_poll = None
            else:
                last_poll = None
            elapsed = (now - last_poll).total_seconds() if last_poll else interval_sec + 1
            if elapsed < interval_sec:
                continue

            print(f"[RSS] Polling {feed.get('name', '?')}")
            items = self._fetch_feed(feed)
            new_items = []
            with self._lock:
                cache_entry = self._cache.get(fid, {"items": [], "last_poll": None})
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
                            item_date = datetime.fromisoformat(pub)
                            if item_date < cutoff:
                                continue
                        except Exception:
                            pass
                    if item.get("guid") not in existing_guids:
                        cache_entry.setdefault("items", []).append(item)
                        new_items.append(item)
                        existing_guids.add(item.get("guid"))
                if len(cache_entry.get("items", [])) > 1000:
                    cache_entry["items"] = cache_entry["items"][-1000:]
                cache_entry["last_poll"] = now.isoformat()
                self._cache[fid] = cache_entry
            self._save_cache()
            if new_items and last_poll is not None:
                self._notify_new_items(new_items)

    def _fetch_feed(self, feed):
        try:
            import feedparser
        except ImportError:
            print("[RSS] feedparser not installed")
            return []
        url = feed.get("url", "")
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
            # Use the article link as guid source: some feeds (e.g. Al Jazeera,
            # TechCrunch, Punto Informatico) expose a homepage-with-query as `id`
            # which collapses every entry to the same guid. `link` is the real article URL.
            raw_guid = entry.get("link") or entry.get("id", "")
            if "#" in raw_guid and raw_guid.startswith("http"):
                raw_guid = raw_guid.split("#")[0]
            if raw_guid.startswith("http"):
                from urllib.parse import urlparse, urlunparse
                parsed_url = urlparse(raw_guid)
                guid = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, '', '', ''))
            else:
                guid = raw_guid
            items.append({
                "guid": guid,
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "summary": entry.get("summary", entry.get("description", "")),
                "pubDate": pub_date,
                "source": name,
                "tags": [t.get("term", "") for t in entry.get("tags", []) if t.get("term")],
            })
        return items

    def _notify_new_items(self, items):
        if not self._config.get("notify_enabled", True):
            return
        blacklist_raw = self._config.get("category_blacklist", "")
        blacklist = {b.strip().lower() for b in blacklist_raw.split(",") if b.strip()} if blacklist_raw else set()
        for item in items:
            tags = [t.lower() for t in item.get("tags", [])]
            source = item.get("source", "RSS")
            title = item.get("title", "")
            summary = item.get("summary", "")
            link = item.get("link", "")
            guid = item.get("guid", "")
            full_text = f"{source}: {title} {summary}"
            if blacklist:
                matches_tags = any(bl in t for t in tags for bl in blacklist)
                matches_text = any(bl in full_text.lower() for bl in blacklist)
                if matches_tags or matches_text:
                    continue
            msg = f"{source}: {title}"
            self._send_cmd("notify", {
                "text": msg, "priority": 5,
                "data": {"type": "rss", "link": link, "guid": guid, "title": title, "source": source, "tags": tags},
            })

    def _send_cmd(self, cmd, params=None):
        msg = json.dumps({
            "type": "cmd", "cmd": cmd, **(params or {})
        }) + "\n"
        try:
            self._sock.sendall(msg.encode("utf-8"))
        except Exception as e:
            print(f"[RSS] Send failed: {e}")

    @staticmethod
    def _resolve_root():
        return os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


if __name__ == "__main__":
    plugin = RssReaderPlugin()
    plugin.run()
