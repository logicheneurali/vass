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
_MAX_LOG = 100_000


def _log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [WorldEvents] {msg}"
    print(line)
    try:
        if os.path.isfile(_LOG_PATH) and os.path.getsize(_LOG_PATH) > _MAX_LOG:
            with open(_LOG_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
            with open(_LOG_PATH, "w", encoding="utf-8") as f:
                f.writelines(lines[-len(lines)//2:])
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
            "history_days": cfg.getint("storage", "history_days", fallback=365),
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
            "finalize": cfg.get("summary", "finalize", fallback="on").lower() in ("on", "1", "true", "yes"),
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

        # Finalize summaries of past days (one per cycle) before processing today
        if self._config.get("finalize", True):
            self._finalize_summaries(data, today)

        # Backfill structured actor/action fields on one past day per cycle
        # (oldest first, before its articles are cleaned up).
        self._backfill_one_day(data, today)

        rss_items = self._fetch_rss_items()
        if rss_items:
            new_items, _ = self._filter_new_items(rss_items, data)
            if new_items:
                _log(f" {len(new_items)} new RSS items today")
            else:
                new_items = []
                _log(" No new RSS items today")
        else:
            new_items = []

        wiki_text = self._fetch_wikipedia_events()
        if wiki_text:
            wiki_items = self._parse_wikipedia_events(wiki_text)
            wiki_new = self._filter_wiki_items(wiki_items, data)
            _log(f" Wikipedia new items: {len(wiki_new)}")
        else:
            wiki_new = []

        if not new_items and not wiki_new:
            return "Skip: no new items to process"

        # Process RSS items in batches of 10
        BATCH_SIZE = 10
        batches = [new_items[i:i + BATCH_SIZE] for i in range(0, len(new_items), BATCH_SIZE)]
        if not batches:
            batches = [[]]

        all_new_events = None
        for batch_num, batch in enumerate(batches):
            # Pass accumulated summary to subsequent batches as context
            existing_summary = self._extract_summary(all_new_events) if all_new_events else None
            wiki_for_batch = wiki_new if batch_num == 0 else None
            prompt = self._build_prompt(batch, wiki_for_batch, existing_summary=existing_summary)
            if not prompt:
                continue
            _log(f" Batch {batch_num + 1}/{len(batches)}: {len(prompt)} chars, calling AI...")
            result = self._call_ai(prompt)

            if result and isinstance(result, dict) and "error" not in result:
                if all_new_events is None:
                    all_new_events = result
                else:
                    all_new_events = self._merge_batch_results(all_new_events, result)

                # Save immediately so completed batches are never lost
                data = self._merge_events(data, result, today)
                data = self._clean_old_events(data)
                data["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                self._save_data(data)
                _log(f" Batch {batch_num + 1}/{len(batches)}: OK (saved)")
            elif result and isinstance(result, dict) and "error" in result:
                _log(f" Batch {batch_num + 1}/{len(batches)}: AI error: {result.get('error')}")
            else:
                _log(f" Batch {batch_num + 1}/{len(batches)}: timeout/error, skipping")

        if all_new_events is None:
            return "Skip: all batches failed"

        # Notify significant events from the newly processed batch only
        self._notify_significant(all_new_events, today)
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

    def _build_prompt(self, rss_items, wiki_items, existing_summary=None):
        parts = []
        if existing_summary:
            parts.append(
                "=== Current Day Summary (already written) ===\n"
                f"{existing_summary}\n\n"
                "Add new articles below without duplicating events already covered above. "
                "Update the summary to incorporate these new events alongside existing ones."
            )
        if rss_items:
            lines = []
            for item in rss_items:
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
            '          "actor": "main entity doing the action (e.g. leader europei, Trump)",\n'
            '          "action": "short verb/noun phrase (e.g. riunione, attacco, sanzioni)",\n'
            '          "outcome": "brief result/outcome (optional)",\n'
            '          "summary": "concise summary"\n'
            "        }\n"
            "      ],\n"
            '      "categories": ["politics", "science", ...]\n'
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
            "- actor/action: short phrases (max 8 words), in the same language as the article.\n"
            "- If an article contains MULTIPLE distinct actions, list each action in a "
            "separate article entry (same actor/location, one per action).\n"
            "- summary: a 2-3 sentence overview of the day.\n"
            "- Preserve ALL original links from the RSS items and Wikipedia sources.\n"
            "- Write ALL text (titles, summaries, categories) in the same language as the source articles.\n"
            f"  Prefer {self._config['wikipedia_lang']} language when sources are mixed.\n\n"
            f"Data:\n{data[:12000]}"
        )
        return prompt

    def _call_ai(self, data, parse_json=True, max_tokens=4096):
        _log(f" Calling AI with {len(data)} chars...")
        return self._send_ai_query(data, temperature=0.2, max_tokens=max_tokens,
                                   parse_json=parse_json)

    def _send_ai_query(self, prompt, temperature=0.1, max_tokens=300, parse_json=True):
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
        if not parse_json:
            return raw
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
            }

        day = events[today]
        if summary:
            existing = day.get("summary", "")
            day["summary"] = (existing + "\n" + summary).strip() if existing else summary
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

        data["events"] = events
        return data

    def _extract_summary(self, data):
        if not data or not isinstance(data, dict):
            return None
        events = data.get("events", {})
        if self._today_str in events:
            return events[self._today_str].get("summary", "")
        # If AI used a different date key, take the first one
        for day_key in events:
            return events[day_key].get("summary", "")
        return None

    def _merge_batch_results(self, base, incoming):
        """Merge two AI response dicts from different batches."""
        base_events = base.get("events", {})
        inc_events = incoming.get("events", {})
        for day_key, day_data in inc_events.items():
            if day_key not in base_events:
                base_events[day_key] = day_data
                continue
            bd = base_events[day_key]
            existing_links = {a.get("link") for a in bd.get("articles", []) if a.get("link")}
            for art in day_data.get("articles", []):
                if art.get("link") and art["link"] in existing_links:
                    continue
                if art.get("link"):
                    existing_links.add(art["link"])
                bd.setdefault("articles", []).append(art)
            all_cats = set(bd.get("categories", []))
            for art in bd.get("articles", []):
                cat = art.get("category", "")
                if cat:
                    all_cats.add(cat)
            bd["categories"] = sorted(all_cats)
            if day_data.get("summary"):
                existing = bd.get("summary", "")
                bd["summary"] = (existing + "\n" + day_data["summary"]).strip() if existing else day_data["summary"]
        base["events"] = base_events
        return base

    @staticmethod
    def _dedup_events(articles, day):
        """One row per distinct (actor, action, location): the same event from
        multiple sources collapses to a single row, while distinct actions in
        one article stay as separate rows. Returns list of compact dicts."""
        seen = set()
        out = []
        for a in articles:
            actor = (a.get("actor") or "").strip()
            action = (a.get("action") or "").strip()
            if not actor and not action:
                continue
            key = (actor.lower(), action.lower(), (a.get("location") or "").lower())
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "date": day,
                "location": a.get("location", ""),
                "actor": actor,
                "action": action,
                "title": (a.get("title") or "")[:90],
                "outcome": (a.get("outcome") or a.get("reactions") or "")[:120],
                "significance": a.get("significance", ""),
            })
        return out

    def _clean_old_events(self, data):
        max_age = self._config["max_age_days"]
        history = self._config.get("history_days", 365)
        cutoff = (date.today() - timedelta(days=max_age)).isoformat()
        hist_cutoff = (date.today() - timedelta(days=history)).isoformat()
        events = data.get("events", {})
        for d in list(events):
            if d < hist_cutoff:
                # Beyond history_days: drop structured events too, keep summary.
                day = events[d]
                events[d] = {
                    "summary": day.get("summary", ""),
                    "articles": [],
                    "categories": [],
                    "category_summaries": day.get("category_summaries", []),
                    "finalized": day.get("finalized", False),
                    "cat_finalized": day.get("cat_finalized", False),
                }
            elif d < cutoff:
                # Keep summary + per-category summaries as historical record,
                # clear heavy article fields but keep structured events_fixed.
                day = events[d]
                events[d] = {
                    "summary": day.get("summary", ""),
                    "articles": [],
                    "categories": [],
                    "events_fixed": self._dedup_events(
                        day.get("articles", []), d),
                    "category_summaries": day.get("category_summaries", []),
                    "finalized": day.get("finalized", False),
                    "cat_finalized": day.get("cat_finalized", False),
                }
        data["events"] = events
        return data

    def _notify_significant(self, data, today):
        threshold = self._config["notify_significance"]
        if threshold == "none":
            return

        # Extract today's summary from the newly processed data
        summary = self._extract_summary(data)
        if not summary:
            return

        self._send_cmd("notify", {
            "text": summary,
            "priority": 5,
            "data": {"type": "world_event"},
        })

    _FINALIZE_PROMPT = """You are a news editor. Below is the RAW daily world events summary for {day}, accumulated by concatenating several partial elaborations: it contains repetitions, and the same story appears multiple times (often from different sources).

--- RAW SUMMARY START ---
{summary}
--- RAW SUMMARY END ---

Rewrite the FINAL day summary: coherent, readable, no repetitions. The same story mentioned multiple times = a single mention. Group related events by theme, order by importance. Maximum 4 short paragraphs. Use ONLY facts present in the text above, do not invent anything. Respond ONLY with the summary: no preamble, no JSON, no code fences."""

    _CATEGORY_SUMMARIES_PROMPT = """You are a news editor producing a PER-CATEGORY summary of the world events of {day}.

Below are the day's articles, each with category, significance and a short summary. Produce one concise summary PER CATEGORY that has content, plus at most 2 reference links per category (the most significant articles' links).

Return ONLY valid JSON, no other text, in this exact structure:
{{
  "categories": [
    {{"category": "politics", "summary": "2-3 sentences covering the key political events of the day", "links": ["https://...", "https://..."]}},
    {{"category": "technology", "summary": "...", "links": ["https://..."]}}
  ]
}}

Rules:
- Include ONLY categories that have actual content (no empty categories).
- Each summary: 2-3 sentences, factual, in the same language as the articles.
- links: up to 2 URLs of the most significant articles for that category (empty array if none).
- Do NOT invent links: use only links present in the input below.
- Keep it concise; the whole JSON must stay under 4000 characters.

--- ARTICLES OF {day} ---
{articles}
"""

    def _finalize_summaries(self, data, today):
        """Rewrite the summary of every past day (d < today) that has no
        'finalized' flag. Input is ONLY the accumulated raw summary — no article
        re-processing. The new summary REPLACES the old one.
        Also builds per-category summaries (category_summaries) for every past
        day that still has articles and lacks a 'cat_finalized' flag."""
        events = data.get("events", {})
        days = sorted(d for d in events if d < today and not events[d].get("finalized"))
        for day in days:
            summary = (events[day].get("summary") or "").strip()
            if not summary:
                events[day]["finalized"] = True
                continue
            _log(f" Finalizing summary for {day} ({len(summary)} chars input)")
            prompt = self._FINALIZE_PROMPT.format(day=day, summary=summary[:12000])
            result = self._call_ai(prompt, parse_json=False, max_tokens=4096)
            if not result:
                _log(f" Finalize {day}: AI error/timeout, will retry next cycle")
                continue
            new_summary = result.strip()[:4000]
            events[day]["summary"] = new_summary
            events[day]["finalized"] = True
            data["events"] = events
            data["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            self._save_data(data)
            _log(f" Finalize {day}: {len(summary)} -> {len(new_summary)} chars (saved)")

        # Per-category summaries: any past day with articles but no cat_finalized
        cat_days = sorted(
            d for d in events
            if d < today and events[d].get("articles")
            and not events[d].get("cat_finalized"))
        for day in cat_days:
            arts = events[day].get("articles", [])
            _log(f" Building per-category summaries for {day} ({len(arts)} articles)")
            summary_text = self._build_category_summaries(day, arts)
            if summary_text is None:
                _log(f" Category summaries {day}: AI error/timeout, will retry next cycle")
                continue
            events[day]["category_summaries"] = summary_text
            events[day]["cat_finalized"] = True
            data["events"] = events
            data["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            self._save_data(data)
            _log(f" Category summaries {day}: {len(summary_text)} categories (saved)")

    def _build_category_summaries(self, day, articles):
        """Ask AI for per-category summaries. Returns a list of
        {"category", "summary", "links"} or None on failure."""
        # Keep the most significant articles per category to bound the prompt
        from collections import OrderedDict
        per_cat = OrderedDict()
        for a in articles:
            cat = a.get("category") or "other"
            per_cat.setdefault(cat, []).append(a)
        sig_order = {"high": 0, "medium": 1, "low": 2}
        selected = []
        for cat, arts in per_cat.items():
            arts.sort(key=lambda a: sig_order.get(a.get("significance"), 3))
            for a in arts[:4]:
                selected.append({
                    "category": cat,
                    "significance": a.get("significance", "low"),
                    "title": a.get("title", ""),
                    "summary": (a.get("summary") or "")[:300],
                    "link": a.get("link", ""),
                })
        if not selected:
            return []
        lines = json.dumps(selected, ensure_ascii=False, indent=1)
        prompt = self._CATEGORY_SUMMARIES_PROMPT.format(day=day, articles=lines[:12000])
        result = self._call_ai(prompt, parse_json=True, max_tokens=4096)
        if not result or not isinstance(result, dict):
            return None
        cats = result.get("categories")
        if not isinstance(cats, list):
            return None
        out = []
        for c in cats:
            if not isinstance(c, dict):
                continue
            category = str(c.get("category", "")).strip()
            summary = str(c.get("summary", "")).strip()
            if not category or not summary:
                continue
            links = c.get("links") or []
            if not isinstance(links, list):
                links = []
            out.append({
                "category": category,
                "summary": summary,
                "links": [str(l) for l in links if isinstance(l, str)][:2],
            })
        return out if out else None

    _BACKFILL_PROMPT = """Extract structured fields for each news article. Return ONLY valid JSON as a list, one entry per article in the SAME order:
[{{"index": 0, "actor": "...", "action": "...", "outcome": "..."}}, ...]

Rules:
- actor: the main entity doing the action (e.g. "leader europei", "Trump").
- action: a short verb/noun phrase (e.g. "riunione", "attacco", "sanzioni").
- outcome: the brief result/outcome (optional, empty string if none).
- Keep every field short (max 8 words), in the same language as the article.
- If an article contains MULTIPLE distinct actions, return one list entry per action (same actor, one per action).
- Return EXACTLY one list entry per article (same count as the input articles); never skip or merge.

Articles:
{articles}
"""

    @staticmethod
    def _article_complete(a):
        """An article is complete when it has actor+action and an outcome
        (or its legacy reactions field to be normalized)."""
        if not (a.get("actor") or a.get("action")):
            return False
        return bool(a.get("outcome") or a.get("reactions"))

    def _backfill_one_day(self, data, today):
        """Arrichisce con actor/action/outcome un giorno passato per ciclo (dal
        più vecchio) che ha articoli incompleti. 1 giorno per ciclo per non
        bloccare il flusso odierno; salva subito quando riesce. Un giorno resta
        candidato finché tutti i suoi articoli sono completi (o viene ripulito)."""
        events = data.get("events", {})
        candidates = [
            d for d in events
            if d < today and events[d].get("articles")
            and any(not self._article_complete(a) for a in events[d]["articles"])
        ]
        if not candidates:
            return False
        day = min(candidates)  # oldest first (closest to cleanup)
        articles = events[day]["articles"]
        done = [a for a in articles if self._article_complete(a)]
        missing = [a for a in articles if not self._article_complete(a)]
        _log(f" Backfill structured fields for {day}: "
             f"{len(done)}/{len(articles)} done, {len(missing)} missing")

        # Process in chunks to bound the AI prompt.
        chunk = 170
        got_any = False
        for start in range(0, len(missing), chunk):
            part = missing[start:start + chunk]
            attempts = 0
            while attempts < 2:
                attempts += 1
                lines = json.dumps([
                    {"index": i, "title": a.get("title", ""),
                     "summary": (a.get("summary") or "")[:300],
                     "location": a.get("location", "")}
                    for i, a in enumerate(part)
                ], ensure_ascii=False, indent=1)
                result = self._call_ai(
                    self._BACKFILL_PROMPT.format(articles=lines[:12000]),
                    parse_json=True, max_tokens=4096)
                if not isinstance(result, list):
                    _log(f" Backfill {day}: AI error/no list, will retry next cycle")
                    return got_any
                filled = set()
                for item in result:
                    if not isinstance(item, dict):
                        continue
                    idx = item.get("index")
                    if not isinstance(idx, int) or not (0 <= idx < len(part)):
                        continue
                    art = part[idx]
                    # Only overwrite fields that are missing; never clobber
                    # already-extracted actor/action/outcome.
                    actor = str(item.get("actor", "")).strip()
                    action = str(item.get("action", "")).strip()
                    outcome = str(item.get("outcome", "")).strip()
                    if not actor and not action and not outcome:
                        continue
                    if not art.get("actor") and actor:
                        art["actor"] = actor
                    if not art.get("action") and action:
                        art["action"] = action
                    if not art.get("outcome"):
                        art["outcome"] = outcome or str(
                            item.get("reactions", "")).strip()
                    art.pop("reactions", None)
                    filled.add(idx)
                    got_any = True
                remaining = [i for i in range(len(part)) if i not in filled]
                if not remaining:
                    break
                # Retry only the articles the AI skipped.
                part = [part[i] for i in remaining]
                _log(f" Backfill {day}: chunk attempt {attempts} filled "
                     f"{len(filled)}/{len(part)+len(filled)}, retrying {len(remaining)}")
        if got_any:
            # Keep the day as a candidate unless every article is complete.
            if all(self._article_complete(a) for a in articles):
                events[day]["backfilled"] = True
            data["events"] = events
            data["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            self._save_data(data)
            _log(f" Backfill {day}: saved "
                 f"({sum(1 for a in articles if self._article_complete(a))}"
                 f"/{len(articles)})")
        return got_any

    @staticmethod
    def _resolve_root():
        return os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


if __name__ == "__main__":
    plugin = WorldEventsPlugin()
    plugin.run()
