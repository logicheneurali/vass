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
        if os.path.exists(ini_path):
            cfg.read(ini_path, encoding="utf-8")
        return {
            "enabled": cfg.getboolean("poll", "enabled", fallback=True),
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
            raw_guid = entry.get("id") or entry.get("link", "")
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
            })
        return items

    def _notify_new_items(self, items):
        for item in items:
            source = item.get("source", "RSS")
            title = item.get("title", "")
            link = item.get("link", "")
            guid = item.get("guid", "")
            msg = f"{source}: {title}"
            self._send_cmd("notify", {
                "text": msg, "priority": 5,
                "data": {"type": "rss", "link": link, "guid": guid, "title": title, "source": source},
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
