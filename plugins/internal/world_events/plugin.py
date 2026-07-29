"""World Events Plugin — builds structured daily digest of world events.
Sources: RSS feeds (via rss_items command) + Wikipedia Current Events.
Connects to VASS PluginServer for ai_query, notify, idle and resource checks.
"""
import configparser
import hashlib
import json
import os
import socket
import threading
import time
import uuid
from datetime import datetime, date, timedelta

_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log.txt")


def _log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [WorldEvents] {msg}"
    print(line)
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


class WorldEventsPlugin:
    def __init__(self):
        self._host = "localhost"
        self._port = 8765
        self._sock = None
        self._sock_lock = threading.Lock()
        self._config = self._load_config()
        self._running = True
        self._pending = []
        self._today_str = ""

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
            "max_age_days": cfg.getint("storage", "max_age_days", fallback=30),
            "max_events_per_day": cfg.getint("storage", "max_events_per_day", fallback=100),
            "interval_min": cfg.getint("schedule", "interval_min", fallback=60),
            "idle_seconds": cfg.getint("schedule", "idle_seconds", fallback=300),
            "cpu_max": cfg.getint("schedule", "cpu_max", fallback=50),
            "ram_max": cfg.getint("schedule", "ram_max", fallback=80),
            "gpu_max": cfg.getint("schedule", "gpu_max", fallback=50),
            "vram_max": cfg.getint("schedule", "vram_max", fallback=90),
            "rss_limit": cfg.getint("rss", "rss_limit", fallback=50),
            "wikipedia_lang": cfg.get("wikipedia", "wikipedia_lang", fallback="en"),
            "notify_significance": cfg.get("notify", "notify_significance", fallback="high"),
        }

    def _load_manifest(self) -> dict:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "plugin_manifest.json"), encoding="utf-8") as f:
            return json.load(f)

    def run(self):
        manifest = self._load_manifest()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self._sock.connect((self._host, self._port))
        except ConnectionRefusedError:
            _log(" VASS not running. Exiting.")
            return

        hello = json.dumps({
            "type": "hello",
            "name": manifest["name"],
            "version": manifest["version"],
            "min_app": manifest["min_app"],
            "subscribe": manifest["subscriptions"],
        }) + "\n"
        self._sock.sendall(hello.encode("utf-8"))
        _log(f" Connected to VASS on {self._host}:{self._port}")

        threading.Thread(target=self._events_loop, daemon=True).start()

        buf = b""
        while self._running:
            with self._sock_lock:
                pass
            time.sleep(0.05)
            with self._sock_lock:
                try:
                    self._sock.settimeout(0.5)
                    data = self._sock.recv(4096)
                except socket.timeout:
                    continue
                except (ConnectionResetError, OSError):
                    _log(" Disconnected. Exiting.")
                    break
                if not data:
                    _log(" Server closed connection. Exiting.")
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue
                    self._on_message(msg)

        self._running = False
        self._sock.close()

    def _on_message(self, msg):
        msg_type = msg.get("type", "?")
        if msg_type != "audio":
            _log(f" <= received: type={msg_type} rid={msg.get('request_id','-')[:8]}")
        if msg_type == "error":
            _log(f" Server error: {msg.get('msg', 'unknown')}")
        else:
            self._pending.append(msg)
            if len(self._pending) > 100:
                self._pending = self._pending[-50:]

    def _events_loop(self):
        last_skip = ""
        while self._running:
            try:
                reason = self._maybe_build_events()
                if reason and reason != last_skip:
                    _log(f" {reason}")
                    last_skip = reason
                elif reason is None:
                    last_skip = ""
            except Exception as e:
                import traceback
                _log(f" Events loop error: {e}\n{traceback.format_exc()}")
            interval = self._config["interval_min"] * 60
            for _ in range(int(interval)):
                if not self._running:
                    break
                time.sleep(1)

    def _maybe_build_events(self):
        idle_reason = self._is_idle()
        if idle_reason:
            return idle_reason

        today = date.today().isoformat()
        self._today_str = today

        data = self._load_data()

        rss_items = self._fetch_rss_items()
        if rss_items:
            new_items = self._filter_new_items(rss_items, data)
            if not new_items:
                _log(" No new RSS items today")
            else:
                _log(f" Processing {len(new_items)} new RSS items")
        else:
            new_items = []

        wiki_text = self._fetch_wikipedia_events()
        if wiki_text:
            wiki_len = len(wiki_text)
            _log(f" Wikipedia data: {wiki_len} chars")
            # Deduplicate Wikipedia by hashing each section
            wiki_items = self._parse_wikipedia_events(wiki_text)
            wiki_new = self._filter_wiki_items(wiki_items, data)
            _log(f" Wikipedia new items: {len(wiki_new)}")
        else:
            wiki_len = 0
            wiki_new = []

        if not new_items and not wiki_new:
            return "Skip: no new items to process"

        # Build AI prompt
        prompt = self._build_prompt(new_items, wiki_new)
        if not prompt:
            return "Skip: no data for AI prompt"

        _log(f" Data collected: {len(prompt)} chars, calling AI...")
        new_events = self._call_ai(prompt)
        if not new_events:
            return "Skip: AI returned no events (timeout/error/invalid JSON)"

        if isinstance(new_events, dict) and "error" in new_events:
            _log(f" Skip: AI returned error: {new_events.get('error')}")
            return None

        # Merge into data
        data = self._merge_events(data, new_events, today)

        # Clean old events
        data = self._clean_old_events(data)
        data["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")

        self._save_data(data)

        # Notify high significance events
        self._notify_significant(data, today)
        _log(" Events updated and saved")

        return None

    def _is_idle(self):
        idle = self._send_idle_check()
        if idle is None:
            return "Skip: idle check failed (server unreachable)"
        idle_s = idle["input_idle_seconds"]
        if idle_s < self._config["idle_seconds"]:
            return f"Skip: not idle ({idle_s}s < {self._config['idle_seconds']}s)"
        res = self._send_resource_check()
        if res is None:
            return "Skip: resource check failed"
        cpu = res.get("cpu", -1); ram = res.get("ram", -1)
        gpu = res.get("gpu", -1); vram = res.get("vram", -1)
        if cpu > self._config["cpu_max"]:
            return f"Skip: CPU too high ({cpu:.0f}% > {self._config['cpu_max']}%)"
        if ram > self._config["ram_max"]:
            return f"Skip: RAM too high ({ram:.0f}% > {self._config['ram_max']}%)"
        if gpu >= 0 and gpu > self._config["gpu_max"]:
            return f"Skip: GPU too high ({gpu:.0f}% > {self._config['gpu_max']}%)"
        if vram >= 0 and vram > self._config["vram_max"]:
            return f"Skip: VRAM too high ({vram:.0f}% > {self._config['vram_max']}%)"
        return None

    def _send_cmd(self, cmd, params=None):
        msg = json.dumps({
            "type": "cmd", "cmd": cmd, **(params or {})
        }, ensure_ascii=False) + "\n"
        with self._sock_lock:
            try:
                self._sock.sendall(msg.encode("utf-8"))
            except Exception as e:
                _log(f" Send '{cmd}' failed: {e}")

    def _send_idle_check(self):
        rid = str(uuid.uuid4())
        msg = json.dumps({"type": "cmd", "cmd": "idle_check", "request_id": rid}) + "\n"
        return self._send_and_wait(rid, msg, "idle_response")

    def _send_resource_check(self):
        rid = str(uuid.uuid4())
        msg = json.dumps({"type": "cmd", "cmd": "resource_check", "request_id": rid}) + "\n"
        return self._send_and_wait(rid, msg, "resource_response")

    def _send_and_wait(self, rid, msg_str, expected_type, timeout=15):
        with self._sock_lock:
            try:
                self._sock.sendall(msg_str.encode("utf-8"))
            except Exception as e:
                _log(f" Send failed: {e}")
                return None
        deadline = time.time() + timeout
        while time.time() < deadline:
            for i, resp in enumerate(self._pending):
                if resp.get("type") == expected_type and resp.get("request_id") == rid:
                    return self._pending.pop(i)
            time.sleep(0.1)
        pending_types = [r.get("type") for r in self._pending[-5:]]
        _log(f" {expected_type} timed out (pending: {pending_types})")
        return None

    def _fetch_rss_items(self):
        rid = str(uuid.uuid4())
        limit = self._config["rss_limit"]
        msg = json.dumps({
            "type": "cmd", "cmd": "rss_items", "request_id": rid, "limit": limit,
        }) + "\n"
        resp = self._send_and_wait(rid, msg, "rss_response", timeout=30)
        if resp is None:
            return None
        return resp.get("items", [])

    def _load_data(self):
        path = os.path.join(self._resolve_root(), "Allowed_root", "private_world_events.json")
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_data(self, data):
        path = os.path.join(self._resolve_root(), "Allowed_root", "private_world_events.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _get_seen_links(self, data):
        """Get all links already present in saved articles."""
        links = set()
        for day_data in data.get("events", {}).values():
            for art in day_data.get("articles", []):
                if art.get("link"):
                    links.add(art["link"])
        return links

    def _filter_new_items(self, rss_items, data):
        today = self._today_str
        seen = self._get_seen_links(data)
        new_items = []
        for item in rss_items:
            link = item.get("link", "")
            if link and link in seen:
                continue
            guid = item.get("guid", "")
            if not guid:
                continue
            pub = item.get("pubDate", "")
            if pub:
                try:
                    pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                    pub_date = pub_dt.strftime("%Y-%m-%d")
                    if pub_date != today:
                        continue
                except Exception:
                    pass
            new_items.append(item)
        return new_items, seen

    def _fetch_wikipedia_events(self):
        lang = self._config["wikipedia_lang"]
        url = f"https://{lang}.wikipedia.org/w/api.php"
        params = {
            "action": "parse",
            "page": "Portal:Current_events",
            "prop": "text",
            "format": "json",
            "redirects": 1,
        }
        try:
            import urllib.request
            import urllib.parse
            qs = urllib.parse.urlencode(params)
            full_url = f"{url}?{qs}"
            req = urllib.request.Request(full_url, headers={
                "User-Agent": "VASS/1.0 (wiki reader; github.com/logicheneurali/vass)",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            text = data.get("parse", {}).get("text", {}).get("*", "")
            if not text:
                return ""
            # Strip HTML tags for basic text extraction
            import re
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', '\n', text)
            text = re.sub(r'\n{3,}', '\n\n', text)
            text = re.sub(r'&amp;', '&', text)
            text = re.sub(r'&lt;', '<', text)
            text = re.sub(r'&gt;', '>', text)
            text = re.sub(r'&quot;', '"', text)
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            # Keep only lines that look like event entries (contain dates or locations)
            return "\n".join(lines[:500])
        except Exception as e:
            _log(f" Wikipedia fetch failed: {e}")
            return ""

    def _parse_wikipedia_events(self, text):
        items = []
        today = self._today_str
        lines = text.split("\n")
        current_title = ""
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Heuristic: lines starting with date-like patterns are event titles
            if len(line) > 20 and (line[0].isdigit() or "–" in line or "—" in line):
                current_title = line[:300]
                # Generate a Wikipedia ID from the title + date
                wiki_id = hashlib.md5(f"{today}_{current_title}".encode()).hexdigest()[:12]
                items.append({
                    "guid": f"wiki:{wiki_id}",
                    "title": current_title,
                    "source": "Wikipedia",
                    "link": "",
                    "summary": "",
                })
            elif current_title and len(line) > 10:
                # Subsequent lines are summary/continuation
                if items:
                    items[-1]["summary"] += " " + line[:200]
        return items

    def _filter_wiki_items(self, wiki_items, data):
        seen_titles = set()
        for day_data in data.get("events", {}).values():
            for art in day_data.get("articles", []):
                if art.get("title"):
                    seen_titles.add(art["title"].lower())
        return [item for item in wiki_items
                if item.get("title", "").lower() not in seen_titles]

    def _build_prompt(self, rss_items, wiki_items):
        parts = []
        if rss_items:
            lines = []
            for item in rss_items[:10]:
                source = item.get("source", "?")
                title = item.get("title", "")
                summary = item.get("summary", "")[:300]
                link = item.get("link", "")
                lines.append(f"[{source}] {title}\n  Summary: {summary}\n  Link: {link}")
            parts.append("=== RSS Articles (today) ===\n" + "\n\n".join(lines))

        if wiki_items:
            lines = []
            for item in wiki_items[:10]:
                lines.append(f"{item['title']}\n  {item['summary'][:300]}")
            parts.append("=== Wikipedia Current Events (today) ===\n" + "\n\n".join(lines))

        if not parts:
            return ""

        data = "\n\n".join(parts)
        prompt = (
            "You are building a daily world events digest. Based on today's news sources below, "
            "extract and structure the key events of the day. Be concise (max 200 chars per item). "
            "Return ONLY valid JSON, nothing else.\n\n"
            "Structure:\n"
            "{\n"
            '  "events": {\n'
            '    "YYYY-MM-DD": {\n'
            '      "summary": "overall day summary in 2-3 sentences",\n'
            '      "articles": [\n'
            '        {\n'
            '          "title": "...",\n'
            '          "source": "...",\n'
            '          "link": "...",\n'
            '          "category": "politics|science|technology|sports|environment|health|economy|other",\n'
            '          "significance": "high|medium|low",\n'
            '          "location": "global" or country/region name,\n'
            '          "summary": "concise summary"\n'
            "        }\n"
            "      ],\n"
            '      "categories": ["politics", "science", ...],\n'
            '      "top_headlines": [\n'
            '        {"title": "...", "source": "...", "link": "..."}\n'
            "      ]\n"
            "    }\n"
            "  }\n"
            "}\n\n"
            "Rules:\n"
            "- Only include events from TODAY's date.\n"
            "- Merge duplicate events from different sources into a single article entry.\n"
            "- Categorize each article accurately.\n"
            "- location: use 'global' if event affects multiple nations or the entire planet.\n"
            "  Otherwise use the specific country or region (e.g. 'Spain', 'Italy', 'France', 'EU', 'Asia').\n"
            "- Set significance: high=major world impact, medium=notable, low=minor.\n"
            "- top_headlines: the 5-10 most important stories as simple title/source/link.\n"
            "- summary: a 2-3 sentence overview of the day.\n"
            "- Preserve ALL original links from the RSS items and Wikipedia sources.\n\n"
            f"Data:\n{data[:12000]}"
        )
        return prompt

    def _call_ai(self, data):
        _log(f" Calling AI with {len(data)} chars...")
        return self._send_ai_query(data, temperature=0.2, max_tokens=99999)

    def _send_ai_query(self, prompt, temperature=0.1, max_tokens=300):
        rid = str(uuid.uuid4())
        msg = json.dumps({
            "type": "cmd",
            "cmd": "ai_query",
            "request_id": rid,
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "extra_body": {"disable_thinking": True},
        }) + "\n"
        resp = self._send_and_wait(rid, msg, "ai_response", timeout=1800)
        if resp is None:
            return None
        raw = (resp.get("response", "") or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`").strip()
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def _merge_events(self, data, new_events, today):
        events = data.get("events", {})

        # Try to extract the day's data from the AI response
        incoming = None
        if "events" in new_events and isinstance(new_events["events"], dict):
            day_events = new_events["events"]
            if today in day_events:
                incoming = day_events[today]
            elif day_events:
                # AI used a different date key — take the first one
                first_key = next(iter(day_events))
                incoming = day_events[first_key]
                _log(f" AI used date key '{first_key}' instead of '{today}' — forcing '{today}'")
            else:
                incoming = None
        elif "summary" in new_events or "articles" in new_events:
            incoming = new_events

        if incoming is None:
            _log(f" AI response has no recognized content, keys={list(new_events.keys())[:5]}")
            if "events" in new_events:
                _log(f" events inner keys: {list(new_events['events'].keys())[:5]}")
            return data

        articles = incoming.get("articles", [])
        summary = incoming.get("summary", "")

        _log(f" AI response: summary={len(summary)} chars, articles={len(articles)}, "
             f"keys={list(incoming.keys())[:10]}")

        if not articles and not summary:
            _log(f" AI returned empty content, skipping merge")
            return data

        if today not in events:
            events[today] = {
                "summary": "",
                "articles": [],
                "categories": [],
                "top_headlines": [],
            }

        day = events[today]
        day["summary"] = summary or day["summary"]
        incoming_articles = incoming.get("articles", [])
        existing_links = {a.get("link") for a in day.get("articles", []) if a.get("link")}
        for art in incoming_articles:
            if art.get("link") and art["link"] in existing_links:
                continue
            if art.get("link"):
                existing_links.add(art["link"])
            day.setdefault("articles", []).append(art)

        # Cap articles per day
        max_events = self._config["max_events_per_day"]
        if len(day.get("articles", [])) > max_events:
            day["articles"] = day["articles"][-max_events:]

        # Update categories
        all_cats = set(day.get("categories", []))
        for art in day.get("articles", []):
            cat = art.get("category", "")
            if cat:
                all_cats.add(cat)
        day["categories"] = sorted(all_cats)

        # Update top_headlines
        incoming_headlines = incoming.get("top_headlines", [])
        existing_hl = {h.get("link") for h in day.get("top_headlines", []) if h.get("link")}
        for hl in incoming_headlines:
            if hl.get("link") and hl["link"] not in existing_hl:
                if hl.get("link"):
                    existing_hl.add(hl["link"])
                day.setdefault("top_headlines", []).append(hl)

        data["events"] = events
        return data

    def _clean_old_events(self, data):
        max_age = self._config["max_age_days"]
        cutoff = (date.today() - timedelta(days=max_age)).isoformat()
        events = data.get("events", {})
        for d in list(events):
            if d < cutoff:
                # Keep summary as historical record, clear heavy fields
                day = events[d]
                events[d] = {
                    "summary": day.get("summary", ""),
                    "articles": [],
                    "categories": [],
                    "top_headlines": [],
                }
        data["events"] = events
        return data

    def _notify_significant(self, data, today):
        threshold = self._config["notify_significance"]
        if threshold == "none":
            return
        levels = {"low": 0, "medium": 1, "high": 2}
        min_level = levels.get(threshold, 2)

        events = data.get("events", {}).get(today, {})
        articles = events.get("articles", [])
        for art in articles:
            sig = art.get("significance", "low")
            if levels.get(sig, 0) >= min_level:
                title = art.get("title", "Event")
                location = art.get("location", "")
                prefix = f"[{location}] " if location else ""
                self._send_cmd("notify", {
                    "text": f"{prefix}{title}",
                    "priority": 6,
                    "data": {"type": "world_event", "link": art.get("link", ""), "title": title},
                })

    @staticmethod
    def _resolve_root():
        return os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


if __name__ == "__main__":
    plugin = WorldEventsPlugin()
    plugin.run()
