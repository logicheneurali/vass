# RSS Feed Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add RSS feed reading to VASS with background polling notifications and voice-command consumption.

**Architecture:** New `src/rss_reader.py` singleton backend handles fetch/cache/polling. `main.py` starts polling thread, routes new items through `NotificationManager`. Bell popup in `gui.py` replaced with QDialog+QTextBrowser showing clickable article links that open a reusable `HTMLViewer` modal. VASScript `rss_fetch()` function enables voice commands via `scripts/rss_read.vass`.

**Tech Stack:** Python 3.13, `feedparser` (new), PySide6 QWebEngineView + QTextBrowser

## Global Constraints

- Python 3.13 required
- All settings keys are FLAT (no nested dicts)
- Italian primary language, 9-language i18n
- No test framework — verify via `python vass.py --debug`
- All editor windows import `BASE_STYLESHEET` from `theme.py`
- VASScript dispatch: `if/elif` chain in `_call_function`. Add `elif name == "rss_fetch":`
- Always call `set_state("listening")` before early returns

---

### Task 1: Add `feedparser` dependency + initial cache file

**Files:**
- Modify: `requirements.txt`
- Create: `Allowed_root/rss_cache.json`

**Interfaces:**
- Produces: `feedparser` library available, empty cache file that RssReader will populate

- [ ] **Step 1: Add `feedparser` to requirements.txt**

At end of file, add:
```
feedparser
```

- [ ] **Step 2: Install feedparser**

Run: `pip install feedparser`
Expected: installs successfully

- [ ] **Step 3: Create empty `rss_cache.json`**

Create `Allowed_root/rss_cache.json` with:
```json
{
  "feeds": {}
}
```

- [ ] **Step 4: Verify cache file exists**

Run: `python -c "import json; d=json.load(open('Allowed_root/rss_cache.json')); assert d=={'feeds':{}}"`
Expected: no output (assertion passes)

---

### Task 2: Backend `src/rss_reader.py`

**Files:**
- Create: `src/rss_reader.py`

**Interfaces:**
- Produces: `RssReader` class with public API:
  - `__init__(feeds_path, cache_path, on_new_items=None)`
  - `reload_feeds()` → `None`
  - `get_feeds()` → `list[dict]`
  - `fetch_feed(feed: dict)` → `list[dict]`
  - `fetch_now(feed_id=None)` → `list[dict]`
  - `get_new_items()` → `list[dict]`
  - `get_cached(feed_id=None, limit=20)` → `list[dict]`
  - `mark_seen(guid)` → `None`
  - `start_polling()` → `None`
  - `stop_polling()` → `None`

- [ ] **Step 1: Create `src/rss_reader.py`**

```python
import json
import os
import threading
import time
import feedparser

from datetime import datetime, timezone


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
            guid = entry.get("id") or entry.get("link", "")
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
                existing_links = {it.get("link") for it in cache_entry.get("items", [])}
                cache_entry["last_poll"] = now
                for item in items:
                    if item.get("link") not in existing_links:
                        cache_entry.setdefault("items", []).append(item)
                if len(cache_entry.get("items", [])) > 20:
                    cache_entry["items"] = cache_entry["items"][-20:]
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

    def start_polling(self):
        self._stop_event.clear()
        t = threading.Thread(target=self._poll_loop, daemon=True)
        t.start()

    def stop_polling(self):
        self._stop_event.set()

    def _poll_loop(self):
        while not self._stop_event.is_set():
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
                unit = feed.get("interval_unit", "minuti")
                if unit in ("ore", "hours"):
                    interval_sec = interval_val * 3600
                elif unit in ("giorni", "days"):
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
                        existing_links = {it.get("link") for it in cache_entry.get("items", [])}
                        cache_entry["last_poll"] = now_iso
                        for item in items:
                            if item.get("link") not in existing_links:
                                cache_entry.setdefault("items", []).append(item)
                                new_items.append(item)
                        if len(cache_entry.get("items", [])) > 20:
                            cache_entry["items"] = cache_entry["items"][-20:]
                        self._cache[fid2] = cache_entry
                    self._save_cache()
                    if new_items and self._on_new_items:
                        try:
                            self._on_new_items(new_items)
                        except Exception as e:
                            print(f"[RSS] on_new_items callback error: {e}")
            if min_sleep < 30:
                min_sleep = 30
            if self._stop_event.wait(min_sleep):
                break
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "compile(open('src/rss_reader.py').read(), 'src/rss_reader.py', 'exec')"`
Expected: no output

---

### Task 3: Integrate `RssReader` in `src/main.py`

**Files:**
- Modify: `src/main.py`

**Interfaces:**
- Consumes: `RssReader` from `src/rss_reader.py`
- Produces: `self.rss_reader` attribute on `VassApp`, polling started in init, `_on_rss_items` callback

- [ ] **Step 1: Add `data` parameter to `NotificationManager.add()`**

In `src/notification_manager.py`, change the `add` method signature and dict:
```python
    def add(self, text, priority=1, data=None):
        n = {
            "id": uuid4().hex[:6],
            "text": text,
            "priority": max(1, min(10, int(priority or 1))),
            "ts": _time.strftime("%H:%M:%S"),
            "read": False,
            "data": data if isinstance(data, dict) else {},
        }
```

Verify syntax: `python -c "compile(open('src/notification_manager.py').read(), 'src/notification_manager.py', 'exec')"`

- [ ] **Step 2: Import RssReader**

In `src/main.py`, after the `from notification_manager import NotificationManager` line (~line 356), add:
```python
        from rss_reader import RssReader
        self.rss_reader = None
```

- [ ] **Step 3: Add RSS initialization method**

In `VassApp` class, after existing init methods, add:
```python
    def _start_rss(self):
        try:
            feeds_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Allowed_root", "rss_feeds.json")
            cache_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Allowed_root", "rss_cache.json")
            from rss_reader import RssReader
            self.rss_reader = RssReader(feeds_path, cache_path, on_new_items=self._on_rss_items)
            self.rss_reader.start_polling()
            print("[RSS] Polling started")
        except Exception as e:
            print(f"[RSS] Failed to start: {e}")

    def _on_rss_items(self, items):
        for item in items:
            source = item.get("source", "RSS")
            title = item.get("title", "")
            link = item.get("link", "")
            guid = item.get("guid", "")
            msg = f"{source}: {title}"
            self.notification_manager.add(
                msg, priority=5,
                data={"type": "rss", "link": link, "guid": guid, "title": title, "source": source}
            )
```

- [ ] **Step 4: Call `_start_rss` at end of `__init__`**

At the end of `VassApp.__init__`, after `self._ensure_memory_file()` and before the class definition ends, add:
```python
        self._start_rss()
```

- [ ] **Step 5: Add RSS stop to `stop()` method**

In the `stop()` method, add before `self.running = False`:
```python
        if self.rss_reader:
            self.rss_reader.stop_polling()
```

- [ ] **Step 6: Verify syntax**

Run: `python -c "compile(open('src/main.py').read(), 'src/main.py', 'exec')"`
Expected: no output

---

### Task 4: Add `rss_fetch()` to VASScript engine

**Files:**
- Modify: `src/script_engine.py`

**Interfaces:**
- Produces: VASScript function `rss_fetch(name?)` callable from `.vass` scripts

- [ ] **Step 1: Add `rss_fetch` to `_SIDE_EFFECT_FUNCTIONS`**

In line 11, add `"rss_fetch"` to the set:
```python
_SIDE_EFFECT_FUNCTIONS = {"ai", "say", "run", "screen_search", "screen_click", "screen_highlight", "listen", "sendtext", "setactivewindow", "addevent", "listevents", "removeevent", "readinfo", "writeinfo", "clipboardget", "clipboardset", "savetags", "timer_start", "timer_list", "timer_cancel", "notify", "inject", "inject_memory", "fetch_text", "search_web", "gcal_today", "gcal_tomorrow", "gcal_add", "gcal_search", "google_home_command", "google_home_ask", "get_weather", "getidle", "rss_fetch"}
```

- [ ] **Step 2: Add `rss_fetch` handler to `_call_function`**

In `_call_function`, before the final `raise ValueError(f"unknown function: {name}()")` line, add:
```python
        if name == "rss_fetch":
            feed_name = evaluated[0] if evaluated else ""
            if not self.app.rss_reader:
                return "error: RSS reader not initialized"
            feed_id = None
            if feed_name:
                feeds = self.app.rss_reader.get_feeds()
                for f in feeds:
                    if f.get("name", "").lower() == feed_name.lower():
                        feed_id = f.get("id")
                        break
                if not feed_id:
                    return f"error: feed '{feed_name}' not found"
            items = self.app.rss_reader.fetch_now(feed_id)
            return json.dumps(items, ensure_ascii=False)
```

- [ ] **Step 3: Verify syntax**

Run: `python -c "compile(open('src/script_engine.py').read(), 'src/script_engine.py', 'exec')"`
Expected: no output

---

### Task 5: Voice command + script

**Files:**
- Create: `scripts/rss_read.vass`
- Modify: `config/commands_it.ini`, `config/commands_en.ini`, `config/commands_de.ini`, `config/commands_fr.ini`, `config/commands_es.ini`, `config/commands_pt.ini`, `config/commands_ja.ini`, `config/commands_ko.ini`, `config/commands_zh.ini`

**Interfaces:**
- Consumes: `rss_fetch()` VASScript function from Task 4
- Produces: voice command "leggi feed RSS" → script execution → AI summary

- [ ] **Step 1: Create `scripts/rss_read.vass`**

```vass
# rss_read.vass - read and summarize RSS feeds
say($_exec_message)
$param1 = "{$param1}"
$items = ""
ifempty($param1,
    $items = rss_fetch(),
    $items = rss_fetch($param1)
)
$summary = ai("Ecco alcuni articoli RSS. Riassumi i piu importanti in italiano in poche frasi: " + $items)
say($summary)
```

- [ ] **Step 2: Add voice commands to all 9 `config/commands_*.ini`**

Add to each file:

`config/commands_it.ini`:
```ini
[rss]
leggi feed rss = script:rss_read
leggi feed RSS = script:rss_read
leggi i feed RSS = script:rss_read
leggi feed {param1} = script:rss_read
```

`config/commands_en.ini`:
```ini
[rss]
read rss feeds = script:rss_read
read RSS feeds = script:rss_read
read the RSS feeds = script:rss_read
read rss feed = script:rss_read
read feed {param1} = script:rss_read
```

`config/commands_de.ini`:
```ini
[rss]
lies RSS feeds = script:rss_read
lies die RSS Feeds = script:rss_read
lies feed {param1} = script:rss_read
```

`config/commands_fr.ini`:
```ini
[rss]
lis les flux RSS = script:rss_read
lire flux RSS = script:rss_read
lis le flux {param1} = script:rss_read
```

`config/commands_es.ini`:
```ini
[rss]
lee feeds RSS = script:rss_read
leer feeds RSS = script:rss_read
lee feed {param1} = script:rss_read
```

`config/commands_pt.ini`:
```ini
[rss]
le feeds RSS = script:rss_read
ler feeds RSS = script:rss_read
le feed {param1} = script:rss_read
```

`config/commands_ja.ini`:
```ini
[rss]
RSSフィードを読んで = script:rss_read
RSSを読んで = script:rss_read
{param1}フィードを読んで = script:rss_read
```

`config/commands_ko.ini`:
```ini
[rss]
RSS 피드 읽어줘 = script:rss_read
RSS 읽어줘 = script:rss_read
{param1} 피드 읽어줘 = script:rss_read
```

`config/commands_zh.ini`:
```ini
[rss]
读RSS订阅 = script:rss_read
读取RSS = script:rss_read
读{param1}订阅 = script:rss_read
```

- [ ] **Step 3: Verify syntax of all modified files**

Run: `python -c "import configparser; c=configparser.ConfigParser(); [c.read(f'config/commands_{x}.ini', encoding='utf-8') for x in ['it','en','de','fr','es','pt','ja','ko','zh']]; print('OK')"`
Expected: `OK`

---

### Task 6: GUI — `HTMLViewer` modal

**Files:**
- Modify: `src/gui.py`

**Interfaces:**
- Produces: `HTMLViewer` class — modal QMainWindow with QWebEngineView, request interceptor, dark theme injection, navigation bar

- [ ] **Step 1: Add imports**

In `gui.py`, modify the `from PySide6.QtWidgets` block to include `QDialog`, `QTextBrowser`:
```python
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QLabel,
    QVBoxLayout, QHBoxLayout, QStackedWidget, QMenu, QMessageBox,
    QLineEdit, QSpacerItem, QSizePolicy, QWidgetAction, QDialog,
    QTextBrowser,
)
```

Add below the existing import block:
```python
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor, QWebEngineProfile
from PySide6.QtCore import QUrl
```

- [ ] **Step 2: Add request interceptor class**

Before `VassGUI` class, add:
```python
class _RssRequestInterceptor(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        url = info.requestUrl().toString()
        first_party = info.firstPartyUrl().toString()
        if info.resourceType() == 0 and not first_party:
            return
        restype = info.resourceType()
        if restype in (0, 1):
            return
        if first_party:
            import urllib.parse
            try:
                dom1 = urllib.parse.urlparse(url).hostname
                dom2 = urllib.parse.urlparse(first_party).hostname
                if dom1 and dom2 and dom1.endswith(dom2.split(".")[-2:] if dom2.count(".") >= 1 else ""):
                    return
                if dom2 and dom1 and dom2.endswith(dom1.split(".")[-2:] if dom1.count(".") >= 1 else ""):
                    return
            except Exception:
                pass
        info.block(True)
```

- [ ] **Step 3: Add `HTMLViewer` class**

After the interceptor, before `VassGUI`, add:
```python
class HTMLViewer(QMainWindow):
    def __init__(self, url="", parent=None):
        super().__init__(parent)
        self._url = url
        self.setWindowTitle("HTML Viewer")
        self.resize(800, 600)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Window)
        self.setStyleSheet(f"QMainWindow {{ background-color: {BG}; }}")

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(8, 4, 8, 4)
        self._back_btn = QPushButton("<-")
        self._back_btn.setFixedWidth(36)
        self._back_btn.setStyleSheet(f"background-color: {BTN_BG}; color: {BTN_FG}; border: none; border-radius: 3px; padding: 4px 8px;")
        self._back_btn.clicked.connect(self._go_back)
        top_bar.addWidget(self._back_btn)

        self._fwd_btn = QPushButton("->")
        self._fwd_btn.setFixedWidth(36)
        self._fwd_btn.setStyleSheet(f"background-color: {BTN_BG}; color: {BTN_FG}; border: none; border-radius: 3px; padding: 4px 8px;")
        self._fwd_btn.clicked.connect(self._go_forward)
        top_bar.addWidget(self._fwd_btn)

        self._title_lbl = QLabel("")
        self._title_lbl.setStyleSheet(f"color: {LABEL_FG}; margin-left: 6px;")
        top_bar.addWidget(self._title_lbl, 1)

        open_btn = QPushButton("Apri nel browser")
        open_btn.setStyleSheet(f"background-color: {BTN_BG}; color: {BTN_FG}; border: none; border-radius: 3px; padding: 4px 10px;")
        open_btn.clicked.connect(self._open_external)
        top_bar.addWidget(open_btn)

        close_btn = QPushButton("x")
        close_btn.setFixedWidth(30)
        close_btn.setStyleSheet(f"background-color: {BTN_DEL_BG}; color: {BTN_DEL_FG}; border: none; border-radius: 3px; padding: 4px 8px;")
        close_btn.clicked.connect(self.close)
        top_bar.addWidget(close_btn)

        top_widget = QWidget()
        top_widget.setLayout(top_bar)
        top_widget.setStyleSheet(f"background-color: #252525;")
        layout.addWidget(top_widget)

        self._web = QWebEngineView()
        profile = self._web.page().profile()
        interceptor = _RssRequestInterceptor()
        profile.setUrlRequestInterceptor(interceptor)
        self._web.loadFinished.connect(self._on_load_finished)
        layout.addWidget(self._web)

        if url:
            self._web.load(QUrl(url))

    def load(self, url):
        self._url = url
        self._web.load(QUrl(url))

    def _go_back(self):
        self._web.back()

    def _go_forward(self):
        self._web.forward()

    def _open_external(self):
        import webbrowser
        current = self._web.url().toString()
        if current:
            webbrowser.open(current)

    def _on_load_finished(self, ok):
        if not ok:
            return
        css = """
        (function(){
            var style = document.createElement('style');
            style.textContent = `
                body { background-color: #1e1e1e !important; color: #e0e0e0 !important; }
                * { font-family: 'Segoe UI', sans-serif !important; }
                img { max-width: 700px !important; }
                a { color: #4ec9b0 !important; }
                #cookie-consent, #cookie-banner, .cookie-notice,
                .gdpr-banner, .consent-banner, [class*="cookie"],
                [id*="cookie"], .sidebar, .advertisement, .ads { display: none !important; }
                article, main, .content, .article, .post, .entry {
                    max-width: 700px !important; margin: 0 auto !important;
                }
            `;
            document.head.appendChild(style);
            var meta = document.createElement('meta');
            meta.name = 'color-scheme';
            meta.content = 'dark';
            document.head.appendChild(meta);
        })();
        """
        self._web.page().runJavaScript(css)
```

- [ ] **Step 4: Verify syntax**

Run: `python -c "compile(open('src/gui.py').read(), 'src/gui.py', 'exec')"`
Expected: no output

---

### Task 7: GUI — Replace bell popup with QDialog + QTextBrowser

**Files:**
- Modify: `src/gui.py`

**Interfaces:**
- Consumes: `HTMLViewer` from Task 6, `notification_manager` data with `type: "rss"` items
- Produces: Bell button click opens QDialog with QTextBrowser showing all notifications, RSS links clickable → HTMLViewer

- [ ] **Step 1: Replace `_bell_btn.clicked.connect` handler**

In `_build_ui`, find the bell button setup (~line 287). Replace:
```python
        self._bell_btn.clicked.connect(
            lambda: self._bell_menu.exec(self._bell_btn.mapToGlobal(self._bell_btn.rect().bottomLeft()))
        )
```
With:
```python
        self._bell_btn.clicked.connect(self._show_bell_dialog)
```

- [ ] **Step 2: Add `_show_bell_dialog` method to `VassGUI`**

Add method to `VassGUI` class:
```python
    def _show_bell_dialog(self):
        if not self.app:
            return
        notifs = self.app.notification_manager.list_all()
        if self.app.rss_reader:
            for n in notifs:
                data = n.get("data")
                if isinstance(data, dict) and data.get("type") == "rss":
                    guid = data.get("guid", "")
                    if guid:
                        self.app.rss_reader.mark_seen(guid)
        dlg = QDialog(self)
        dlg.setWindowTitle(self._t("gui.notifications"))
        dlg.resize(400, 450)
        dlg.setStyleSheet(f"QDialog {{ background-color: {BG}; }}")

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(8, 8, 8, 8)

        title_bar = QHBoxLayout()
        title_lbl = QLabel(f"Notifiche ({len(notifs)})")
        title_lbl.setStyleSheet(f"color: {SECTION_FG}; font-weight: bold; font-size: 13px;")
        title_bar.addWidget(title_lbl)
        title_bar.addStretch()
        close_btn = QPushButton("x")
        close_btn.setFixedWidth(30)
        close_btn.setStyleSheet(f"background-color: {BTN_DEL_BG}; color: {BTN_DEL_FG}; border: none; border-radius: 3px;")
        close_btn.clicked.connect(dlg.close)
        title_bar.addWidget(close_btn)
        layout.addLayout(title_bar)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setStyleSheet(f"background-color: {BG}; color: {FG}; border: 1px solid {FRAME_BORDER}; border-radius: 3px; padding: 6px; font-size: 12px;")
        html_parts = []
        if not notifs:
            html_parts.append(f'<p style="color:{LABEL_FG};">{self._t("gui.no_notifications")}</p>')
        else:
            for n in notifs:
                color = self.app.notification_manager.color_for(n["priority"])
                ts = n.get("ts", "")
                txt = n.get("text", "")
                data = n.get("data")
                if isinstance(data, dict) and data.get("type") == "rss":
                    link = data.get("link", "")
                    escaped_link = link.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
                    html_parts.append(
                        f'<p><span style="color:{color};">●</span> '
                        f'<span style="color:{LABEL_FG};">[{ts}]</span> '
                        f'{txt}<br>'
                        f'<a href="{escaped_link}" style="color:{BTN_BG};">Leggi articolo completo</a></p>'
                    )
                else:
                    html_parts.append(
                        f'<p><span style="color:{color};">●</span> '
                        f'<span style="color:{LABEL_FG};">[{ts}]</span> '
                        f'{txt}</p>'
                    )
                html_parts.append(f'<hr style="border: none; border-top: 1px solid {FRAME_BORDER};">')
        browser.setHtml("<html><body>" + "".join(html_parts) + "</body></html>")

        def on_link_clicked(qurl):
            url = qurl.toString()
            viewer = HTMLViewer(url)
            viewer.show()
        browser.anchorClicked.connect(on_link_clicked)

        layout.addWidget(browser)

        mark_btn = QPushButton(self._t("gui.mark_read"))
        mark_btn.setStyleSheet(f"background-color: {BTN_BG}; color: {BTN_FG}; border: none; border-radius: 3px; padding: 6px;")
        mark_btn.clicked.connect(lambda: self.app.notification_manager.mark_all_read())
        mark_btn.clicked.connect(dlg.close)
        layout.addWidget(mark_btn)

        dlg.exec()
        self._update_bell()
```

- [ ] **Step 3: Remove `_bell_menu` initialization and `_populate_bell_menu` usage**

In `_build_ui`, remove these lines:
```python
        self._bell_menu = QMenu()
        self._bell_menu.setStyleSheet(
            "QMenu { background-color: #2d2d2d; color: #e0e0e0; "
            "QMenu::item { padding: 6px 20px; }"
            "QMenu::item:selected { background-color: #3d3d3d; }"
        )
```

In `_update_bell`, remove the line:
```python
        self._populate_bell_menu()
```

Optionally remove the `_populate_bell_menu` method entirely (lines 680-704).

- [ ] **Step 4: Verify syntax**

Run: `python -c "compile(open('src/gui.py').read(), 'src/gui.py', 'exec')"`
Expected: no output

---

### Task 8: i18n — Add RSS section to all locale files

**Files:**
- Modify: `locales/it.json`, `locales/en.json`, `locales/de.json`, `locales/fr.json`, `locales/es.json`, `locales/pt.json`, `locales/ja.json`, `locales/ko.json`, `locales/zh.json`

- [ ] **Step 1: Add `rss` section to `locales/it.json`**

Add before the closing `}`:
```json
  "rss": {
    "notifications_title": "Notifiche",
    "read_article": "Leggi articolo completo",
    "viewer_title": "HTML Viewer",
    "open_in_browser": "Apri nel browser",
    "new_articles_count": "{count} nuovi articoli"
  }
```

- [ ] **Step 2: Add `rss` section to all other 8 locale files**

`en.json`:
```json
  "rss": {
    "notifications_title": "Notifications",
    "read_article": "Read full article",
    "viewer_title": "HTML Viewer",
    "open_in_browser": "Open in browser",
    "new_articles_count": "{count} new articles"
  }
```

`de.json`:
```json
  "rss": {
    "notifications_title": "Benachrichtigungen",
    "read_article": "Artikel lesen",
    "viewer_title": "HTML Viewer",
    "open_in_browser": "Im Browser öffnen",
    "new_articles_count": "{count} neue Artikel"
  }
```

`fr.json`:
```json
  "rss": {
    "notifications_title": "Notifications",
    "read_article": "Lire l'article complet",
    "viewer_title": "HTML Viewer",
    "open_in_browser": "Ouvrir dans le navigateur",
    "new_articles_count": "{count} nouveaux articles"
  }
```

`es.json`:
```json
  "rss": {
    "notifications_title": "Notificaciones",
    "read_article": "Leer artículo completo",
    "viewer_title": "HTML Viewer",
    "open_in_browser": "Abrir en el navegador",
    "new_articles_count": "{count} nuevos artículos"
  }
```

`pt.json`:
```json
  "rss": {
    "notifications_title": "Notificações",
    "read_article": "Ler artigo completo",
    "viewer_title": "HTML Viewer",
    "open_in_browser": "Abrir no navegador",
    "new_articles_count": "{count} novos artigos"
  }
```

`ja.json`:
```json
  "rss": {
    "notifications_title": "通知",
    "read_article": "記事を読む",
    "viewer_title": "HTML Viewer",
    "open_in_browser": "ブラウザで開く",
    "new_articles_count": "{count}件の新しい記事"
  }
```

`ko.json`:
```json
  "rss": {
    "notifications_title": "알림",
    "read_article": "기사 읽기",
    "viewer_title": "HTML Viewer",
    "open_in_browser": "브라우저에서 열기",
    "new_articles_count": "{count}개의 새 기사"
  }
```

`zh.json`:
```json
  "rss": {
    "notifications_title": "通知",
    "read_article": "阅读全文",
    "viewer_title": "HTML Viewer",
    "open_in_browser": "在浏览器中打开",
    "new_articles_count": "{count} 篇新文章"
  }
```

- [ ] **Step 3: Validate all 9 JSON files**

Run: `python -c "import json, os; [json.load(open(os.path.join('locales', f'{x}.json'), encoding='utf-8')) for x in ['it','en','de','fr','es','pt','ja','ko','zh']]; print('OK')"`
Expected: `OK`

---

### Task 9: Final integration test

- [ ] **Step 1: Full syntax check of all modified files**

Run:
```bash
python -c "compile(open('src/rss_reader.py').read(), 'src/rss_reader.py', 'exec'); compile(open('src/main.py').read(), 'src/main.py', 'exec'); compile(open('src/script_engine.py').read(), 'src/script_engine.py', 'exec'); compile(open('src/gui.py').read(), 'src/gui.py', 'exec'); print('All OK')"
```
Expected: `All OK`

- [ ] **Step 2: Verify RssReader import works**

Run: `python -c "from src.rss_reader import RssReader; print('Import OK')"`
Expected: `Import OK`

- [ ] **Step 3: Verify rss_cache.json is valid JSON**

Run: `python -c "import json; d=json.load(open('Allowed_root/rss_cache.json')); assert 'feeds' in d; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Test feedparser parse**

Run: `python -c "import feedparser; d=feedparser.parse('https://feeds.bbci.co.uk/news/rss.xml'); print('Entries:', len(d.entries), 'Bozo:', d.bozo)"`
Expected: shows number of entries (may be 0 if offline, but should not crash)
