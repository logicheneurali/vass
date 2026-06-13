"""Google Calendar integration via keyring-stored OAuth2 credentials."""
import json, os, datetime, re

from datetime import timedelta as _td
from google_auth import get_google_credentials


def _get_service():
    creds = get_google_credentials()
    if not creds:
        return None
    from googleapiclient.discovery import build
    return build("calendar", "v3", credentials=creds)


class GoogleCalendar:
    def __init__(self):
        self._service = None

    @property
    def service(self):
        if self._service is None:
            self._service = _get_service()
        return self._service

    def list_events(self, max_results=10, time_min=None, time_max=None):
        """List upcoming events. Returns JSON string."""
        svc = self.service
        if not svc:
            return json.dumps({"error": "Google Calendar not authenticated. Run setup_google.py first."})

        if time_min is None:
            time_min = datetime.datetime.utcnow().isoformat() + "Z"
        try:
            events_result = svc.events().list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                maxResults=int(max_results),
                singleEvents=True,
                orderBy="startTime",
            ).execute()
        except Exception as e:
            return json.dumps({"error": str(e)})

        items = []
        for ev in events_result.get("items", []):
            start = ev["start"].get("dateTime", ev["start"].get("date", "?"))
            summary = ev.get("summary", "Senza titolo")
            items.append({
                "id": ev["id"],
                "summary": summary,
                "start": start,
                "end": ev["end"].get("dateTime", ev["end"].get("date", "?")),
                "location": ev.get("location", ""),
                "description": ev.get("description", ""),
            })
        return json.dumps(items, ensure_ascii=False, indent=2)

    def list_today(self, max_results=10):
        """List today's events."""
        now = datetime.datetime.utcnow()
        start = now.replace(hour=0, minute=0, second=0).isoformat() + "Z"
        end = now.replace(hour=23, minute=59, second=59).isoformat() + "Z"
        return self.list_events(max_results, start, end)

    def list_tomorrow(self, max_results=10):
        """List tomorrow's events."""
        now = datetime.datetime.utcnow()
        tomorrow = now + datetime.timedelta(days=1)
        start = tomorrow.replace(hour=0, minute=0, second=0).isoformat() + "Z"
        end = tomorrow.replace(hour=23, minute=59, second=59).isoformat() + "Z"
        return self.list_events(max_results, start, end)

    def add_event(self, summary, start_dt, end_dt, description=""):
        """Add an event. start_dt/end_dt in ISO format."""
        svc = self.service
        if not svc:
            return json.dumps({"error": "Google Calendar not authenticated."})
        try:
            body = {
                "summary": summary,
                "description": description or "",
                "start": {"dateTime": start_dt, "timeZone": "Europe/Rome"},
                "end": {"dateTime": end_dt, "timeZone": "Europe/Rome"},
            }
            event = svc.events().insert(calendarId="primary", body=body).execute()
            return json.dumps({"id": event["id"], "summary": summary, "status": "created"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def search_events(self, query, max_results=10):
        """Search events by keyword."""
        svc = self.service
        if not svc:
            return json.dumps({"error": "Google Calendar not authenticated."})
        try:
            events_result = svc.events().list(
                calendarId="primary",
                q=query,
                maxResults=int(max_results),
                singleEvents=True,
            ).execute()
            items = []
            for ev in events_result.get("items", []):
                items.append({
                    "id": ev["id"],
                    "summary": ev.get("summary", "?"),
                    "start": ev["start"].get("dateTime", ev["start"].get("date", "?")),
                })
            return json.dumps(items, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def sync_to_vass(self, events_path, days=7):
        """Sync Google Calendar events to VASS events.json. Deduplicates via gcal_id."""
        svc = self.service
        if not svc:
            return

        print(f"[GCal] Sync: fetching events for next {days} days...")
        now = datetime.datetime.utcnow()
        time_min = now.isoformat() + "Z"
        time_max = (now + _td(days=days)).replace(hour=23, minute=59, second=59).isoformat() + "Z"

        try:
            events_result = svc.events().list(
                calendarId="primary", timeMin=time_min, timeMax=time_max,
                maxResults=250, singleEvents=True, orderBy="startTime",
            ).execute()
        except Exception as e:
            print(f"[GCal] List error: {e}")
            return

        gcal_events = []
        for ev in events_result.get("items", []):
            start_str = ev["start"].get("dateTime", ev["start"].get("date", ""))
            end_str = ev["end"].get("dateTime", ev["end"].get("date", ""))
            if not start_str or not end_str:
                continue
            gcal_events.append({
                "id": ev["id"],
                "summary": ev.get("summary", "Senza titolo"),
                "start": start_str,
                "end": end_str,
            })

        try:
            with open(events_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {"events": []}

        vass_events = data.get("events", [])
        vass_by_gcal = {e["gcal_id"]: i for i, e in enumerate(vass_events) if "gcal_id" in e}
        gcal_ids_seen = set()
        modified = False
        added = 0
        updated = 0

        for ge in gcal_events:
            gid = ge["id"]
            gcal_ids_seen.add(gid)
            vass_item = self._convert_gcal_to_vass(ge)
            if gid in vass_by_gcal:
                idx = vass_by_gcal[gid]
                if self._events_differ(vass_events[idx], vass_item):
                    print(f"[GCal] Updated: {ge['summary']} ({ge['start']})")
                    for k, v in vass_item.items():
                        vass_events[idx][k] = v
                    updated += 1
                    modified = True
            else:
                print(f"[GCal] Added: {ge['summary']} ({ge['start']})")
                vass_events.append(vass_item)
                added += 1
                modified = True

        removed = 0
        new_events = []
        for e in vass_events:
            if e.get("gcal_synced") and e.get("gcal_id") not in gcal_ids_seen:
                print(f"[GCal] Removed: {e.get('description', '?')} (cancelled on Google)")
                removed += 1
                modified = True
                continue
            new_events.append(e)

        if modified:
            data["events"] = new_events
            with open(events_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[GCal] Sync: {len(gcal_events)} from Google, {added} added, {updated} updated, {removed} removed, {len(new_events)} total")

    @staticmethod
    def _convert_gcal_to_vass(ge):
        from datetime import datetime as _dt
        start_str = ge["start"].replace("Z", "+00:00")
        end_str = ge["end"].replace("Z", "+00:00")
        try:
            start_dt = _dt.fromisoformat(start_str)
            end_dt = _dt.fromisoformat(end_str)
        except ValueError:
            start_str = re.sub(r'\.\d+', '', start_str)
            end_str = re.sub(r'\.\d+', '', end_str)
            start_dt = _dt.fromisoformat(start_str)
            end_dt = _dt.fromisoformat(end_str)
        duration = max(1, int((end_dt - start_dt).total_seconds() / 60))
        return {
            "name": f"{ge['summary']}_{start_dt:%Y-%m-%d_%H:%M}".replace(" ", "_").lower(),
            "date": start_dt.strftime("%Y-%m-%d"),
            "time": start_dt.strftime("%H:%M"),
            "duration": duration,
            "description": ge.get("summary", ""),
            "gcal_id": ge["id"],
            "gcal_synced": True,
        }

    @staticmethod
    def _events_differ(a, b):
        for key in ("date", "time", "duration", "description", "recur"):
            if str(a.get(key, "")) != str(b.get(key, "")):
                return True
        return False

