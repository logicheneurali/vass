from contextvars import ContextVar
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from mcpgoal.config import ServerConfig
from mcpgoal.logging_.logger import RequestLogger
from mcpgoal.middleware.acl import check_access
from mcpgoal.tools import calculator, datetime_, executor, filesystem, web
from mcpgoal.tools.vasscript import execute_vasscript as _vasscript
from mcpgoal.tools.vasscript import execute_code as _exec_code
from mcpgoal.tools.vasscript import info_read as _info_read
from mcpgoal.tools.vasscript import info_write as _info_write
from mcpgoal.tools.vasscript import clipboard_get as _clip_get
from mcpgoal.tools.vasscript import clipboard_set as _clip_set
from mcpgoal.tools.playwright import search_web as _search_web
from mcpgoal.tools.playwright import fetch_page as _fetch_page
from mcpgoal.tools.documents import html_to_pdf as _html_to_pdf
from mcpgoal.tools.langcheck import check_language as _check_language
from mcpgoal.tools.memory_tags import save_tags as _save_tags, search_tags as _search_tags
from mcpgoal.tools.calendar import calendar_list as _calendar_list
from mcpgoal.tools.calendar import calendar_add as _calendar_add
from mcpgoal.tools.calendar import calendar_search as _calendar_search
from mcpgoal.tools.places import search_places as _search_places
from mcpgoal.tools.places import search_nearby as _search_nearby
from mcpgoal.tools.news import read_news as _read_news
from mcpgoal.tools.news import read_news_range as _read_news_range
from mcpgoal.tools.news import search_news as _search_news
from mcpgoal.tools.mail import send_email as _send_email
from mcpgoal.tools.mail import reply_email as _reply_email
from mcpgoal.tools.mail import forward_email as _forward_email
from mcpgoal.tools.mail import search_emails as _search_emails
from mcpgoal.tools.mail import search_contacts as _search_contacts
from mcpgoal.tools.browser import browser_open as _browser_open
from mcpgoal.tools.browser import browser_read as _browser_read
from mcpgoal.tools.browser import browser_click as _browser_click
from mcpgoal.tools.browser import browser_fill as _browser_fill
from mcpgoal.tools.browser import browser_submit as _browser_submit
from mcpgoal.tools.browser import browser_download as _browser_download
from mcpgoal.tools.browser import browser_back as _browser_back
from mcpgoal.tools.browser import browser_show as _browser_show
from mcpgoal.tools.browser import browser_check_auth as _browser_check_auth

_GET_IDLE = None
try:
    _PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent.parent / "src")
    import sys as _sys
    if _PROJECT_ROOT not in _sys.path:
        _sys.path.insert(0, _PROJECT_ROOT)
    from idle_tracker import IdleTracker
    _GET_IDLE = IdleTracker().get_total_idle_seconds
except Exception:
    pass

client_ip_var: ContextVar[str] = ContextVar("client_ip", default="unknown")
_loggers: dict[str, RequestLogger] = {}


def _get_logger(ip: str, log_dir: str) -> RequestLogger:
    if ip not in _loggers:
        _loggers[ip] = RequestLogger(ip, log_dir)
    return _loggers[ip]


async def _tool(name: str, params_str: str, coro, config: ServerConfig):
    ip = client_ip_var.get()
    if not check_access(name, ip, config):
        raise PermissionError(f"Access denied for tool '{name}' from {ip}")
    logger = _get_logger(ip, config.log_dir)
    try:
        result = await coro
        logger.log(name, params_str, "ok", result)
        return result
    except TypeError as e:
        syntax = _TOOL_SYNTAX.get(name, f"{name}(...)")
        msg = f"SYNTAX ERROR: {e}. Correct syntax: {syntax}"
        logger.log(name, params_str, "syntax_error", msg)
        return msg
    except Exception as e:
        logger.log(name, params_str, "error", str(e))
        raise


_TOOL_SYNTAX = {
    "browse": "browse(url) — example: browse('https://example.com')",
    "read_file": "read_file(path) — example: read_file('events.json')",
    "write_file": "write_file(path, content) — example: write_file('events.json', '{...}')",
    "current_time": "current_time() — no parameters",
    "to_timestamp": "to_timestamp(date) — example: to_timestamp('2026-06-12 14:30')",
    "calculate": "calculate(expression) — example: calculate('2+2')",
    "execute": "execute(command) — example: execute('ping localhost')",
    "script": "script(script_name) — example: script('eventi') or script('?') to list",
    "interact": "interact(code) — example: interact(\"say('hello')\")",
    "readinfo": "readinfo(id) — example: readinfo('1780394454383')",
    "writeinfo": "writeinfo(text) — example: writeinfo('dati da salvare')",
    "addevent": "addevent(date, time, duration, description, recur?) — example: addevent('2026-06-15', '14:00', '60', 'Meeting')",
    "delevent": "delevent(description, date?, time?) — example: delevent('Meeting', '2026-06-15', '14:00')",
    "listevents": "listevents(from_date?) — example: listevents('2026-06-10') or listevents()",
    "clipboardget": "clipboardget() — no parameters",
    "clipboardset": "clipboardset(text) — example: clipboardset('testo')",
    "websearch": "websearch(query) — example: websearch('latest news')",
    "webfetch": "webfetch(url) — example: webfetch('https://example.com')",
    "savetags": "savetags(tags) — example: savetags('food,health,pets')",
    "calendar_list": "calendar_list(from_date?) — example: calendar_list('2026-06-15')",
    "calendar_add": "calendar_add(summary, start, end, description?) — example: calendar_add('Meeting', '2026-06-15T14:00:00', '2026-06-15T15:00:00')",
    "calendar_search": "calendar_search(query) — example: calendar_search('dentist')",
}


async def _add_event(date, time, duration, description, recur, allowed_root):
    import json
    from datetime import datetime as dt
    try:
        raw = await filesystem.read_file("events.json", allowed_root)
        data = json.loads(raw)
    except Exception:
        data = {"events": []}
    events = data.get("events", [])

    try:
        parsed = dt.strptime(date, "%Y-%m-%d")
    except ValueError:
        return f"error: invalid date format '{date}'. Use YYYY-MM-DD."
    # Verify day-of-week matches if description mentions a day name
    _weekdays_it = {"lunedì": 0, "martedì": 1, "mercoledì": 2, "giovedì": 3,
                    "venerdì": 4, "sabato": 5, "domenica": 6}
    _weekdays_en = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                    "friday": 4, "saturday": 5, "sunday": 6}
    desc_lower = description.lower()
    for name, weekday in {**_weekdays_it, **_weekdays_en}.items():
        if name in desc_lower:
            if parsed.weekday() != weekday:
                actual = parsed.strftime("%A")
                return (f"error: the date {date} is a {actual}, not a {name}. "
                        f"Please correct the date to match {name}.")
            break
    try:
        dt.strptime(time, "%H:%M")
    except ValueError:
        return f"error: invalid time format '{time}'. Use HH:MM."

    import uuid
    safe_desc = description.lower().replace(" ", "_")[:40]
    name = f"{safe_desc}_{date}_{time}_{uuid.uuid4().hex[:4]}"

    event = {
        "name": name,
        "date": date,
        "time": time,
        "duration": str(duration),
        "description": description,
    }
    if recur:
        event["recur"] = recur
    events.append(event)
    data["events"] = events

    target = Path(allowed_root).resolve() / "events.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"Event added: '{description}' on {date} at {time} ({duration}min)"


async def _find_free_slot(date, duration, description, start_hour, end_hour, allowed_root):
    """Find the first free time slot on a date and add an event."""
    import json
    try:
        raw = await filesystem.read_file("events.json", allowed_root)
        data = json.loads(raw)
    except Exception:
        data = {"events": []}
    events = data.get("events", [])

    # Read working hours from settings.ini (fallback to defaults)
    try:
        import configparser
        cp = configparser.ConfigParser()
        cp.read(str(Path(allowed_root).resolve().parent / "config" / "settings.ini"), encoding="utf-8")
        start_hour = int(cp.get("events", "work_start_hour", fallback=str(start_hour)).split(":")[0])
        end_hour = int(cp.get("events", "work_end_hour", fallback=str(end_hour)).split(":")[0])
        ls = cp.get("events", "lunch_start", fallback="13:00")
        le = cp.get("events", "lunch_end", fallback="14:30")
        lh, lm = map(int, ls.split(":"))
        eh, em = map(int, le.split(":"))
        lunch_start = lh * 60 + lm
        lunch_end = eh * 60 + em
    except Exception:
        lunch_start = 13 * 60
        lunch_end = 14 * 60 + 30

    day_events = []
    for ev in events:
        if ev.get("enabled", "true").lower() == "false":
            continue
        if ev.get("date") == date:
            time_str = ev.get("time", "")
            dur = int(ev.get("duration", 60) or 60)
            try:
                h, m = map(int, time_str.split(":"))
                start_min = h * 60 + m
                day_events.append((start_min, start_min + dur))
            except (ValueError, TypeError):
                continue
        recur = ev.get("recur", "")
        if recur and ev.get("date", "") <= date:
            try:
                from utils import generate_recurrences
                for fd, ft in generate_recurrences(ev.get("date", ""), ev.get("time", "00:00"), recur, date):
                    if fd == date:
                        dur = int(ev.get("duration", 60) or 60)
                        h, m = map(int, ft.split(":"))
                        start_min = h * 60 + m
                        day_events.append((start_min, start_min + dur))
            except Exception:
                pass
    day_events.sort()

    # Lunch break as blocked slot
    if lunch_end > lunch_start:
        day_events.append((lunch_start, lunch_end))
        day_events.sort()

    start_day = start_hour * 60
    end_day = end_hour * 60
    cursor = start_day

    for ev_start, ev_end in day_events:
        if ev_start > cursor and ev_start - cursor >= duration:
            hh = cursor // 60
            mm = cursor % 60
            return await _add_event(date, f"{hh:02d}:{mm:02d}", str(duration), description, "", allowed_root)
        cursor = max(cursor, ev_end)

    if end_day - cursor >= duration:
        hh = cursor // 60
        mm = cursor % 60
        return await _add_event(date, f"{hh:02d}:{mm:02d}", str(duration), description, "", allowed_root)

    busy = ", ".join(f"{s//60:02d}:{s%60:02d}-{e//60:02d}:{e%60:02d}" for s, e in day_events)
    return f"error: no free slot of {duration} minutes on {date}. Busy slots: {busy}"


async def _del_event(description, date, time, allowed_root):
    import json
    import difflib
    try:
        raw = await filesystem.read_file("events.json", allowed_root)
        data = json.loads(raw)
    except Exception:
        return "error: no events found"
    events = data.get("events", [])
    if not events:
        return "error: no events found"

    matches = []
    for ev in events:
        ev_desc = ev.get("description", "")
        if difflib.SequenceMatcher(None, description.lower(), ev_desc.lower()).ratio() >= 0.75:
            matches.append(ev)

    if not matches:
        return f"No event found matching '{description}'"

    if date or time:
        matches = [ev for ev in matches
                   if (not date or ev.get("date") == date)
                   and (not time or ev.get("time") == time)]
        if not matches:
            return f"No event found matching '{description}' at {date or 'any date'} {time or 'any time'}"

    if len(matches) > 1 and not date and not time:
        lines = []
        for ev in matches:
            lines.append(f"  - '{ev.get('description')}' on {ev.get('date')} at {ev.get('time')}")
        return "Multiple events match. Specify date and time to disambiguate:\n" + "\n".join(lines)

    removed = matches[0] if len(matches) == 1 else matches[0]
    events = [ev for ev in events if ev != removed]
    data["events"] = events

    target = Path(allowed_root).resolve() / "events.json"
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"Removed event: '{removed.get('description')}' on {removed.get('date')} at {removed.get('time')}"


async def _list_events(from_date, allowed_root):
    import json
    from datetime import datetime as dt, date as d
    try:
        raw = await filesystem.read_file("events.json", allowed_root)
        data = json.loads(raw)
    except Exception:
        return "[]"
    events = data.get("events", [])

    if from_date:
        try:
            from_dt = dt.strptime(from_date, "%Y-%m-%d")
        except ValueError:
            try:
                from_dt = dt.strptime(from_date, "%Y-%m-%d %H:%M")
            except ValueError:
                return f"error: invalid date format '{from_date}'. Use YYYY-MM-DD."
    else:
        from_dt = dt.now().replace(hour=0, minute=0, second=0, microsecond=0)

    upcoming = []
    for ev in events:
        try:
            ev_dt = dt.strptime(f"{ev.get('date')} {ev.get('time')}", "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        if ev_dt >= from_dt:
            upcoming.append(ev)

    upcoming.sort(key=lambda ev: f"{ev.get('date')} {ev.get('time')}")
    clean = []
    for ev in upcoming:
        clean.append({
            "date": ev.get("date", ""),
            "time": ev.get("time", ""),
            "duration": str(ev.get("duration", "0")),
            "description": ev.get("description", ""),
        })
    return json.dumps(clean, ensure_ascii=False, indent=2)


def create_server(config: ServerConfig) -> FastMCP:
    mcp = FastMCP("MCPGoal")
    mcp.settings.streamable_http_path = "/"

    ref_path = Path(__file__).resolve().parent.parent.parent.parent / "Allowed_root" / "VASCRIPT_REFERENCE.md"
    try:
        _interact_doc = ref_path.read_text(encoding="utf-8")
    except Exception:
        _interact_doc = "Execute VASScript code. Full reference: read_file('VASCRIPT_REFERENCE.md')"

    @mcp.tool()
    async def browse(url: str) -> str:
        """Fetch content from a URL and extract readable text. Use for reading web pages."""
        return await _tool("browse", f"url={url}", web.browse(url), config)

    @mcp.tool()
    async def read_file(path: str) -> str:
        """Read ANY file from Allowed_root. Use for memory.json, events.json, schedules.json, VASCRIPT_REFERENCE.md. Provide just the filename."""
        return await _tool("read_file", f"path={path}", filesystem.read_file(path, config.allowed_root), config)

    @mcp.tool()
    async def write_file(path: str, content: str) -> str:
        """Write content to a file in Allowed_root. Cannot overwrite events.json, schedules.json, or memory.json — use dedicated tools for those."""
        return await _tool("write_file", f"path={path}", filesystem.write_file(path, content, config.allowed_root), config)

    @mcp.tool()
    async def current_time() -> str:
        """Get the current date and time."""
        return await _tool("current_time", "", datetime_.current_time(), config)

    @mcp.tool()
    async def to_timestamp(date_str: str) -> str:
        """Convert a date/time string to Unix timestamp. Supports: 'YYYY-MM-DD', 'YYYY-MM-DD HH:MM', 'YYYY-MM-DD HH:MM:SS'"""
        return await _tool("to_timestamp", f"date={date_str}", datetime_.convert_date_to_timestamp(date_str), config)

    @mcp.tool()
    async def calculate(expression: str) -> str:
        """Evaluate a mathematical expression."""
        return await _tool("calculate", f"expr={expression}", calculator.calculate(expression), config)

    @mcp.tool()
    async def execute(command: str) -> str:
        """Execute a system command. Only allowed commands from the configured whitelist can be run."""
        return await _tool("execute", f"cmd={command}", executor.execute(command, config.allowed_commands), config)

    @mcp.tool()
    async def addevent(date: str, time: str, duration: str, description: str, recur: str = "") -> str:
        """Add an event to events.json. date='YYYY-MM-DD', time='HH:MM', duration=minutes (integer), recur='1d'/'7d'/'1m'/'2h' (optional). IMPORTANT: Always verify the date matches the requested day of week (e.g., if user says 'monday', check the date IS actually a Monday). Example: addevent('2026-06-15', '14:00', '60', 'Team meeting', '1d')"""
        return await _tool("addevent", f"desc={description[:40]}", _add_event(date, time, duration, description, recur, config.allowed_root), config)

    @mcp.tool()
    async def find_free_slot(date: str, duration: str, description: str, start_hour: int = 8, end_hour: int = 19) -> str:
        """Find the first free time slot on a date and add an event there. date='YYYY-MM-DD', duration=minutes, start_hour/end_hour=working hours (default 8-19, lunch break 13:00-14:30 excluded). Use when the user wants to schedule something without specifying an exact time. Example: find_free_slot('2026-07-15', '60', 'Team lunch')"""
        return await _tool("find_free_slot", f"desc={description[:40]}", _find_free_slot(date, int(duration), description, start_hour, end_hour, config.allowed_root), config)

    @mcp.tool()
    async def delevent(description: str, date: str = "", time: str = "") -> str:
        """Remove an event by description (fuzzy match). Optional date='YYYY-MM-DD' and time='HH:MM' to disambiguate. If multiple events match and no date/time given, lists them instead of deleting."""
        return await _tool("delevent", f"desc={description[:40]}", _del_event(description, date, time, config.allowed_root), config)

    @mcp.tool()
    async def listevents(from_date: str = "") -> str:
        """List upcoming events from a date onward (YYYY-MM-DD). If no date given, lists from today. Returns JSON array sorted by date/time."""
        return await _tool("listevents", f"from={from_date or 'today'}", _list_events(from_date, config.allowed_root), config)

    @mcp.tool()
    async def nextevent(from_date: str = "") -> str:
        """Get only the NEXT upcoming event (single result, earliest date/time). Always use this tool when the user asks for the next event, upcoming event, or what's coming up. Returns just one event, no list. If no events found, says 'No upcoming events found.'"""
        import json
        result = await _list_events(from_date, config.allowed_root)
        evts = json.loads(result)
        if not evts:
            return "No upcoming events found."
        e = evts[0]
        return f"NEXT: {e['description']} on {e['date']} at {e['time']} ({e['duration']} min)"

    @mcp.tool()
    async def script(script_name: str) -> str:
        """Execute a VASScript file from the scripts folder (without .vass extension). Call with '?' to list available scripts."""
        if not config.allow_scripts:
            return "error: script execution is disabled (set allow_ai_scripts=true in settings.ini)"
        return await _tool("script", f"script={script_name}", _vasscript(script_name), config)

    async def _interact_handler(code: str) -> str:
        return await _tool("interact", f"len={len(code)}", _exec_code(code), config)
    _interact_handler.__doc__ = _interact_doc
    _interact_handler.__name__ = "interact"
    interact = mcp.tool()(_interact_handler)

    # Add server-side gate for interact (must be after registration)
    _orig_interact = interact
    async def _gated_interact(code: str) -> str:
        if not config.allow_scripts:
            return "error: script execution is disabled (set allow_ai_scripts=true in settings.ini)"
        return await _orig_interact(code)
    _gated_interact.__doc__ = _interact_doc
    interact = mcp.tool()(_gated_interact)

    @mcp.tool()
    async def readinfo(id: str) -> str:
        """Read an info/memory file by its numeric ID. NOT for reading memory.json — use read_file('memory.json') instead."""
        return await _tool("readinfo", f"id={id}", _info_read(id), config)

    @mcp.tool()
    async def writeinfo(text: str) -> str:
        """Write text to a new info file. Returns the file ID (timestamp)."""
        return await _tool("writeinfo", f"len={len(text)}", _info_write(text), config)

    @mcp.tool()
    async def clipboardget() -> str:
        """Get the current clipboard text content."""
        return await _tool("clipboardget", "", _clip_get(), config)

    @mcp.tool()
    async def clipboardset(text: str) -> str:
        """Set the clipboard text content."""
        return await _tool("clipboardset", f"len={len(text)}", _clip_set(text), config)

    @mcp.tool()
    async def websearch(query: str) -> str:
        """Search the web using DuckDuckGo. Returns top results with title, URL, and snippet in JSON."""
        return await _tool("websearch", f"q={query[:80]}", _search_web(query), config)

    @mcp.tool()
    async def webfetch(url: str) -> str:
        """Fetch a web page using headless Chromium (Playwright). Extracts rendered text content from JavaScript pages."""
        return await _tool("webfetch", f"url={url[:100]}", _fetch_page(url, timeout=90), config)

    @mcp.tool()
    async def html_to_pdf(html: str, filename: str) -> str:
        """Generate a PDF from HTML content. Provide the full HTML document and a filename (without extension). Auto-renames if exists. Returns path to the generated PDF."""
        return await _tool("html_to_pdf", f"file={filename[:60]}", _html_to_pdf(html, filename, config.allowed_root), config)

    @mcp.tool()
    async def langcheck(text: str, lang: str = "it") -> str:
        """Validate text against Tier 2 linguistic rules (morphology, syntax) for the given language."""
        return await _tool("langcheck", f"lang={lang} len={len(text)}", _check_language(text, lang), config)

    @mcp.tool()
    async def savetags(tags: str, entry_id: str = "", content: str = "", source: str = "chat") -> str:
        """Classify the user's message with comma-separated memory tags. Always call after responding. Example: savetags('food,health,pets')"""
        return await _tool("savetags", f"tags={tags[:80]}", _save_tags(tags, config.allowed_root, entry_id, source=source, content=content), config)

    @mcp.tool()
    async def search_tags(tags: str) -> str:
        """Search tagged memory entries by comma-separated tags. Returns top 10 most relevant. Example: search_tags('health,food')"""
        return await _tool("search_tags", f"tags={tags[:80]}", _search_tags(tags, config.allowed_root), config)

    if _GET_IDLE is not None:
        import json as _json

        async def _getidle_impl() -> str:
            seconds = _GET_IDLE()
            return _json.dumps({"idle_seconds": round(seconds, 1)})

        @mcp.tool()
        async def getidle() -> str:
            """Get system idle time in seconds since last user activity."""
            return await _tool("getidle", "", _getidle_impl(), config)

    def _gcal_enabled(cfg):
        try:
            root = Path(cfg.allowed_root).resolve().parent
            import configparser
            cp = configparser.ConfigParser()
            cp.read(str(root / "config" / "settings.ini"), encoding="utf-8")
            return cp.get("google", "calendar_enabled", fallback="false").lower() == "true"
        except Exception:
            return False

    @mcp.tool()
    async def calendar_list(from_date: str = "") -> str:
        """List upcoming Google Calendar events. Optional from_date='YYYY-MM-DD'. Returns JSON."""
        return await _tool("calendar_list", f"from={from_date or 'today'}", _calendar_list(from_date, enabled=_gcal_enabled(config)), config)

    @mcp.tool()
    async def calendar_add(summary: str, start: str, end: str, description: str = "") -> str:
        """Add an event to Google Calendar. start/end in ISO format 'YYYY-MM-DDTHH:MM:SS'. Requires prior Google OAuth2 setup."""
        return await _tool("calendar_add", f"summary={summary[:40]}", _calendar_add(summary, start, end, description, enabled=_gcal_enabled(config)), config)

    @mcp.tool()
    async def calendar_search(query: str) -> str:
        """Search Google Calendar events by keyword. Returns JSON."""
        return await _tool("calendar_search", f"q={query[:60]}", _calendar_search(query, enabled=_gcal_enabled(config)), config)

    @mcp.tool()
    async def search_places(query: str, near: str = "", limit: int = 5) -> str:
        """Search for places, shops, restaurants, addresses using OpenStreetMap.
        Always provide 'near' with a city/area name to get correct results.
        Returns name, address, coordinates, and OpenStreetMap link for each result.
        Examples: search_places('farmacia', 'Messina'), search_places('ristorante', 'Roma', 3)"""
        return await _tool("search_places", f"q={query[:60]}", _search_places(query, near, limit), config)

    @mcp.tool()
    async def search_nearby(osm_key: str, osm_value: str, near: str, radius: int = 3000, limit: int = 10) -> str:
        """Search nearby places by OpenStreetMap tag. Use osm_key + osm_value.
        Common tags: amenity=pharmacy, amenity=restaurant, shop=supermarket, shop=hardware,
        amenity=bank, amenity=cafe, tourism=hotel, amenity=hospital, shop=bakery, etc.
        Always provide 'near' with a city/address. Returns name, address, distance, map link sorted by distance.
        Examples: search_nearby('amenity', 'pharmacy', 'Messina')
                  search_nearby('shop', 'supermarket', 'via Roma, Milano', 1000)"""
        return await _tool("search_nearby", f"tag={osm_key}={osm_value}", _search_nearby(osm_key, osm_value, near, radius, limit), config)

    @mcp.tool()
    async def read_news(date: str) -> str:
        """Read world events for a specific date from the daily events digest.
        Use for questions like 'what happened today', 'cosa è successo ieri', 'news from July 28'.
        Args: date in YYYY-MM-DD format. Returns summary, articles, categories, and top_headlines."""
        return await _tool("read_news", f"date={date}", _read_news(date), config)

    @mcp.tool()
    async def read_news_range(from_date: str, to_date: str) -> str:
        """Read world events for a date range from the daily events digest.
        Args: from_date, to_date in YYYY-MM-DD format (inclusive).
        Returns summary, articles, categories, and top_headlines for each date in the range."""
        return await _tool("read_news_range", f"from={from_date} to={to_date}", _read_news_range(from_date, to_date), config)

    @mcp.tool()
    async def search_news(keywords: str) -> str:
        """Search world events by keywords across all saved dates.
        Use for questions like 'find news about climate', 'cerca notizie su elezioni', 'search for X'.
        Args: keywords (space-separated). Returns matching articles sorted by date (newest first)."""
        return await _tool("search_news", f"keywords={keywords}", _search_news(keywords), config)

    @mcp.tool()
    async def send_email(to: str, subject: str, body: str) -> str:
        """Send a new email. The email goes to an outbox for user approval.
        Use this for composing NEW emails. For replies, use reply_email() instead.
        Ask the user for the recipient if not specified.
        Args: to (recipient email), subject, body (plain text)."""
        return await _tool("send_email", f"to={to}", _send_email(to, subject, body), config)

    @mcp.tool()
    async def reply_email(msg_id: str, body: str) -> str:
        """Reply to a received email. First find the msg_id using search_emails() with sender/subject keywords.
        The original email body is quoted automatically below your reply.
        The email goes to an outbox for user approval before sending.
        Args: msg_id (from search_emails() result), body (your reply text, quoting is automatic)."""
        return await _tool("reply_email", f"msg_id={msg_id}", _reply_email(msg_id, body), config)

    @mcp.tool()
    async def forward_email(msg_id: str, to: str) -> str:
        """Forward an email. Find msg_id first with search_emails().
        The email goes to an outbox for user approval.
        Args: msg_id (from search_emails()), to (recipient)."""
        return await _tool("forward_email", f"msg_id={msg_id}", _forward_email(msg_id, to), config)

    @mcp.tool()
    async def search_emails(keywords: str) -> str:
        """Search the local email archive by sender name, subject, or content keywords.
        Returns matching emails with their msg_id, sender, subject, date, and snippet.
        Use this to find emails before replying or forwarding. Use sender name as keywords.
        Args: keywords (space-separated, e.g. 'Mario Rossi' or 'fattura')."""
        return await _tool("search_emails", f"keywords={keywords}", _search_emails(keywords), config)

    @mcp.tool()
    async def search_contacts(keywords: str) -> str:
        """Search email contacts by name or email address (fuzzy matching).
        Use this to find recipient email addresses before sending an email.
        Args: keywords (name fragments, e.g. 'Fabio' or 'gmail')."""
        return await _tool("search_contacts", f"keywords={keywords}", _search_contacts(keywords), config)

    @mcp.tool()
    async def browser_open(url: str) -> str:
        """Navigate to a URL in the persistent browser session. Stays on the same page between calls.
        Use for starting a browsing session or navigating to a new page.
        Args: url (full URL with https://)"""
        return await _tool("browser_open", f"url={url}", _browser_open(url), config)

    @mcp.tool()
    async def browser_read() -> str:
        """Read the visible text content of the current browser page."""
        return await _tool("browser_read", "", _browser_read(), config)

    @mcp.tool()
    async def browser_click(text: str) -> str:
        """Click an element by its visible text. Use for buttons, links, or clickable elements.
        Args: text (visible text of the element, e.g. 'Login', 'Submit', 'Download')"""
        return await _tool("browser_click", f"text={text}", _browser_click(text), config)

    @mcp.tool()
    async def browser_fill(label: str, value: str) -> str:
        """Fill an input field by its label or placeholder text.
        Args: label (text near the field), value (text to type)"""
        return await _tool("browser_fill", f"label={label} value={value}", _browser_fill(label, value), config)

    @mcp.tool()
    async def browser_submit() -> str:
        """Submit the current form. Clicks the first submit button."""
        return await _tool("browser_submit", "", _browser_submit(), config)

    @mcp.tool()
    async def browser_download(text: str) -> str:
        """Click a download link and save the file. Returns filename.
        Args: text (visible text of the download link/button)"""
        return await _tool("browser_download", f"text={text}", _browser_download(text), config)

    @mcp.tool()
    async def browser_back() -> str:
        """Go back to the previous page in browser history."""
        return await _tool("browser_back", "", _browser_back(), config)

    @mcp.tool()
    async def browser_show() -> str:
        """Open the browser VISIBLY so the user can manually log in, solve CAPTCHA, etc.
        Use when authentication is needed and not yet saved. Cookies/sessions persist."""
        return await _tool("browser_show", "", _browser_show(), config)

    @mcp.tool()
    async def browser_check_auth(text: str) -> str:
        """Check if logged in by searching for expected text on the page (e.g. 'Dashboard', 'Logout').
        Args: text (text that should be visible after successful login)."""
        return await _tool("browser_check_auth", f"text={text}", _browser_check_auth(text), config)

    return mcp
