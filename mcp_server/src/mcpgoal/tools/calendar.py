"""MCP tools for Google Calendar integration."""
import json


async def calendar_list(from_date: str = "", max_results: int = 10, enabled: bool = False) -> str:
    """List upcoming Google Calendar events. from_date='YYYY-MM-DD' (optional)."""
    if not enabled:
        return json.dumps({"error": "Google Calendar is not enabled (calendar_enabled=false in tools.yaml)"})
    time_min = None
    if from_date:
        time_min = f"{from_date}T00:00:00Z"
    cal = _get_calendar()
    if not cal:
        return json.dumps({"error": "Google Calendar not configured"})
    return cal.list_events(int(max_results), time_min=time_min)


async def calendar_add(summary: str, start: str, end: str, description: str = "", enabled: bool = False) -> str:
    """Add an event to Google Calendar. start/end in ISO format 'YYYY-MM-DDTHH:MM:SS'."""
    if not enabled:
        return json.dumps({"error": "Google Calendar is not enabled (calendar_enabled=false in tools.yaml)"})
    cal = _get_calendar()
    if not cal:
        return json.dumps({"error": "Google Calendar not configured"})
    return cal.add_event(summary, start, end, description)


async def calendar_search(query: str, max_results: int = 10, enabled: bool = False) -> str:
    """Search Google Calendar events by keyword."""
    if not enabled:
        return json.dumps({"error": "Google Calendar is not enabled (calendar_enabled=false in tools.yaml)"})
    cal = _get_calendar()
    if not cal:
        return json.dumps({"error": "Google Calendar not configured"})
    return cal.search_events(query, int(max_results))


def _get_calendar():
    try:
        from google_calendar import GoogleCalendar
        return GoogleCalendar()
    except Exception:
        return None
