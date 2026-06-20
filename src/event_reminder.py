import json
import os
import re
import subprocess
import sys
import threading
import time


import shutil

_SAFE_CMD_RE = re.compile(r'^[a-zA-Z0-9_\-.:\\/ ]+\.(exe|bat|ps1|py|cmd|vbs|vass)$')


def _validate_command(command, arguments):
    if not command or not command.strip():
        return False
    basename = os.path.basename(command)
    if _SAFE_CMD_RE.search(basename):
        return True
    exe = command.split()[0]
    if shutil.which(exe) or os.path.exists(exe):
        return True
    return False


class EventReminder:
    def __init__(self, app, advance_seconds=3600, language="en", idle_tracker=None):
        self.app = app
        self.advance = advance_seconds
        self.lang = language
        self.idle = idle_tracker
        self._running = False
        self._next_alert_ts = None
        self._next_events = []
        self._alerted = set()
        self._last_mtime = 0
        self._next_schedule_ts = None
        self._next_schedules = []
        self._alerted_schedules = set()
        self._last_schedule_mtime = 0

    def _root_dir(self):
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _events_path(self):
        return os.path.join(self._root_dir(), "Allowed_root", "events.json")

    def _schedules_path(self):
        return os.path.join(self._root_dir(), "Allowed_root", "schedules.json")

    def _load_events(self):
        path = self._events_path()
        if not os.path.exists(path):
            return []
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("events", [])
        except Exception:
            return []

    def _load_schedules(self):
        path = self._schedules_path()
        if not os.path.exists(path):
            return []
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("schedules", [])
        except Exception:
            return []

    def _parse_ts(self, item):
        import datetime
        try:
            dt = datetime.datetime.strptime(f"{item['date']} {item['time']}", "%Y-%m-%d %H:%M")
            return dt.timestamp()
        except Exception:
            try:
                import dateparser
                parsed = dateparser.parse(f"{item['date']} {item['time']}", languages=["it", "en"])
                if parsed:
                    return parsed.timestamp()
            except Exception:
                pass
        return None

    # ── Events ────────────────────────────────────────────────────────────────

    def _calculate_next_alert(self):
        events = self._load_events()
        now = time.time()
        groups = {}

        for ev in events:
            if ev.get("enabled", "true").lower() == "false":
                continue
            event_ts = self._parse_ts(ev)
            if event_ts is None:
                continue
            alert_ts = event_ts - self.advance
            duration = int(ev.get("duration", 0) or 0)
            end_ts = event_ts + (duration * 60)
            already_notified = "notify" in ev

            if alert_ts <= now:
                if not already_notified and now < end_ts:
                    deadline = event_ts - 1800
                    notify_at = now + 5
                    if self.idle:
                        idle_secs = self.idle.get_total_idle_seconds()
                        if idle_secs > 600:
                            notify_at = now + min(idle_secs * 0.5, deadline - now - 10)
                            notify_at = max(now + 5, min(notify_at, deadline))
                    key = int(max(notify_at, now + 1))
                    if key not in groups:
                        groups[key] = []
                    groups[key].append(ev)
                elif ev.get("recur") and now >= end_ts:
                    data = {"events": events}
                    self._advance_and_save(data, ev, self._events_path())
                continue

            key = int(alert_ts)
            if key not in groups:
                groups[key] = []
            groups[key].append(ev)

        # ── Start alerts (at event start time) ────────────────────────────────
        for ev in events:
            event_ts = self._parse_ts(ev)
            if event_ts is None:
                continue
            duration = int(ev.get("duration", 0) or 0)
            end_ts = event_ts + (duration * 60)
            already_started = "notify_start" in ev

            if event_ts <= now:
                if not already_started and now < end_ts:
                    notify_at = now + 5
                    key = int(max(notify_at, now + 1))
                    if key not in groups:
                        groups[key] = []
                    start_ev = dict(ev)
                    start_ev["_start_alert"] = True
                    groups[key].append(start_ev)
            else:
                key = int(event_ts)
                if key not in groups:
                    groups[key] = []
                start_ev = dict(ev)
                start_ev["_start_alert"] = True
                groups[key].append(start_ev)

        if not groups:
            self._next_alert_ts = None
            self._next_events = []
            return

        earliest = min(groups.keys())
        self._next_alert_ts = earliest
        self._next_events = groups[earliest]

    # ── Schedules ─────────────────────────────────────────────────────────────

    def _calculate_next_schedule(self):
        schedules = self._load_schedules()
        now = time.time()
        groups = {}

        for sc in schedules:
            if sc.get("enabled", "true").lower() == "false":
                continue
            sched_ts = self._parse_ts(sc)
            if sched_ts is None:
                continue
            alert_ts = sched_ts  # schedules fire exactly at time, no advance
            duration = sc.get("duration", 0) or 0
            end_ts = sched_ts + (duration * 60)
            already_ran = "notify" in sc

            if alert_ts <= now:
                if not already_ran and now < end_ts:
                    deadline = sched_ts - 1800
                    notify_at = now + 5
                    if self.idle:
                        idle_secs = self.idle.get_total_idle_seconds()
                        if idle_secs > 600:
                            notify_at = now + min(idle_secs * 0.5, deadline - now - 10)
                            notify_at = max(now + 5, min(notify_at, deadline))
                    key = int(max(notify_at, now + 1))
                    if key not in groups:
                        groups[key] = []
                    groups[key].append(sc)
                elif sc.get("recur") and now >= end_ts:
                    data = {"schedules": schedules}
                    self._advance_and_save(data, sc, self._schedules_path())
                continue

            key = int(alert_ts)
            if key not in groups:
                groups[key] = []
            groups[key].append(sc)

        if not groups:
            self._next_schedule_ts = None
            self._next_schedules = []
            return

        earliest = min(groups.keys())
        self._next_schedule_ts = earliest
        self._next_schedules = groups[earliest]
        for s in self._next_schedules:
            print(f"[Schedules] Next: {s.get('description', '?')} at {s.get('date')} {s.get('time')} (ts={earliest})")

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _advance_recurrence(self, date_str, time_str, recur):
        from datetime import datetime as _dt, timedelta as _td
        try:
            from dateutil.relativedelta import relativedelta
        except ImportError:
            relativedelta = None
        m = re.match(r"^(\d+)([mhdwM])$", recur)
        if not m:
            return date_str, time_str
        num, unit = int(m.group(1)), m.group(2)
        try:
            dt = _dt.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        except Exception:
            return date_str, time_str
        if unit == "m":
            dt += _td(minutes=num)
        elif unit == "h":
            dt += _td(hours=num)
        elif unit == "d":
            dt += _td(days=num)
        elif unit == "w":
            dt += _td(weeks=num)
        elif unit == "M":
            if relativedelta:
                dt += relativedelta(months=num)
            else:
                dt += _td(days=num * 30)
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")

    def _advance_and_save(self, data, item, path):
        recur = item.get("recur", "")
        if not recur:
            return
        now_ts = time.time()
        new_date = item["date"]
        new_time = item["time"]
        for _ in range(366):
            try:
                d, t = self._advance_recurrence(new_date, new_time, recur)
                ets = self._parse_ts({"date": d, "time": t})
                if ets and ets > now_ts:
                    item["date"] = d
                    item["time"] = t
                    item["name"] = f"{item['description']}_{d}_{t}".replace(" ", "_").lower()
                    if "notify" in item:
                        del item["notify"]
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    return
                new_date, new_time = d, t
            except Exception:
                return

    def _build_message(self):
        if not self._next_events:
            return ""
        from i18n import t
        default_desc = t("events.event_default", self.lang)
        parts = []
        for ev in self._next_events:
            desc = ev.get("description", default_desc)
            if ev.get("_start_alert"):
                template = t("events.start_message", self.lang)
                parts.append(template.replace("{description}", desc))
            else:
                template = t("events.reminder_message", self.lang)
                parts.append(template.replace("{description}", desc).replace("{time}", ev.get("time", "")))
        return ", ".join(parts) + "."

    def _mark_notified(self):
        path = self._events_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        modified = False
        for event in data.get("events", []):
            for ne in self._next_events:
                match = False
                if ne.get("id") and event.get("id") == ne.get("id"):
                    match = True
                elif (event.get("date") == ne.get("date") and
                      event.get("time") == ne.get("time") and
                      event.get("description") == ne.get("description")):
                    match = True
                if match:
                    if event.get("recur"):
                        new_date, new_time = self._advance_recurrence(
                            event["date"], event["time"], event["recur"])
                        event["date"] = new_date
                        event["time"] = new_time
                        event["name"] = f"{event['description']}_{new_date}_{new_time}".replace(" ", "_").lower()
                        if "notify" in event:
                            del event["notify"]
                        if "notify_start" in event:
                            del event["notify_start"]
                    elif ne.get("_start_alert"):
                        event["notify_start"] = now_str
                    else:
                        event["notify"] = now_str
                    modified = True
                    break
        if modified:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

    # ── Schedule execution ────────────────────────────────────────────────────

    def _mark_schedule_executed(self):
        path = self._schedules_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        modified = False
        for sc in data.get("schedules", []):
            for ns in self._next_schedules:
                match = False
                if ns.get("id") and sc.get("id") == ns.get("id"):
                    match = True
                elif (sc.get("date") == ns.get("date") and
                      sc.get("time") == ns.get("time") and
                      sc.get("description") == ns.get("description")):
                    match = True
                if match:
                    if sc.get("recur"):
                        new_date, new_time = self._advance_recurrence(
                            sc["date"], sc["time"], sc["recur"])
                        sc["date"] = new_date
                        sc["time"] = new_time
                        sc["name"] = f"{sc['description']}_{new_date}_{new_time}".replace(" ", "_").lower()
                        if "notify" in sc:
                            del sc["notify"]
                    else:
                        sc["notify"] = now_str
                    modified = True
                    break
        if modified:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

    def _execute_schedule(self, sc):
        threading.Thread(target=self._execute_schedule_thread, args=(sc,), daemon=True).start()

    def _execute_schedule_thread(self, sc):
        desc = sc.get("description", "Sconosciuta")
        command = sc.get("command", "")
        arguments = sc.get("arguments", "")
        silent = sc.get("silent", "false").lower() == "true"

        try:
            from i18n import t
        except Exception:
            def t(k, lang):
                return k

        if not silent:
            started_msg = t("events.schedule_started", self.lang).replace("{description}", desc)
            self.app.tts.enqueue(started_msg)
        print(f"[Schedules] Started: {desc} -> {command} {arguments}")

        # Check if command is a .vass script
        if command.lower().endswith(".vass") or os.path.splitext(command)[1].lower() == ".vass":
            script_name = os.path.splitext(os.path.basename(command))[0]
            if not os.path.exists(command):
                scripts_dir = os.path.join(self._root_dir(), "scripts")
                candidate = os.path.join(scripts_dir, os.path.basename(command))
                if os.path.exists(candidate):
                    command = candidate
                    script_name = os.path.splitext(os.path.basename(command))[0]
            if hasattr(self.app, '_run_script'):
                self.app._run_script(script_name, silent=silent)
            elif not silent:
                failed_msg = t("events.schedule_failed", self.lang).replace("{description}", desc)
                self.app.tts.enqueue(failed_msg)
            return

        if not _validate_command(command, arguments):
            if not silent:
                failed_msg = t("events.schedule_failed", self.lang).replace("{description}", desc)
                self.app.tts.enqueue(failed_msg)
            return

        try:
            cmd_parts = [command]
            if arguments:
                import shlex
                try:
                    cmd_parts += shlex.split(arguments)
                except ValueError:
                    cmd_parts.append(arguments)
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            dur = int(sc.get("duration", 0) or 0)
            cmd_timeout = max(dur * 60, 60) if dur > 0 else 3600
            wd = sc.get("workingdir", "") or None
            if wd and not os.path.isdir(wd):
                wd = None
            r = subprocess.run(
                cmd_parts,
                capture_output=True, text=True,
                creationflags=creationflags,
                timeout=cmd_timeout,
                cwd=wd,
            )
            if r.returncode == 0:
                msg = t("events.schedule_done", self.lang).replace("{description}", desc)
            else:
                msg = t("events.schedule_failed", self.lang).replace("{description}", desc)
            if not silent:
                self.app.tts.enqueue(msg)
            if hasattr(self.app, 'notification_manager'):
                self.app.notification_manager.add(msg, priority=9 if r.returncode != 0 else 7, data={"type": "schedule"})
        except Exception:
            if not silent:
                failed_msg = t("events.schedule_failed", self.lang).replace("{description}", desc)
                self.app.tts.enqueue(failed_msg)
            if hasattr(self.app, 'notification_manager'):
                self.app.notification_manager.add(failed_msg, priority=9, data={"type": "schedule"})

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self):
        self._running = True
        self._calculate_next_alert()
        self._calculate_next_schedule()

        while self._running:
            try:
                events_path = self._events_path()
                schedules_path = self._schedules_path()

                if os.path.exists(events_path):
                    mtime = os.path.getmtime(events_path)
                    if mtime != self._last_mtime:
                        self._last_mtime = mtime
                        self._calculate_next_alert()
                        print(f"[Events] File changed, recalculated")

                if os.path.exists(schedules_path):
                    mtime = os.path.getmtime(schedules_path)
                    if mtime != self._last_schedule_mtime:
                        self._last_schedule_mtime = mtime
                        self._calculate_next_schedule()
                        print(f"[Schedules] File changed, recalculated")

                self._process_events()
                self._process_schedules()

            except Exception:
                pass

            time.sleep(30)

    def _process_events(self):
        if not self._next_alert_ts or time.time() < self._next_alert_ts:
            return
        alert_key = int(self._next_alert_ts)
        if alert_key in self._alerted:
            return
        self._alerted.add(alert_key)
        msg = self._build_message()
        if not msg:
            self._calculate_next_alert()
            return
        while self.app.state in ("recording", "playing", "waiting_resources"):
            time.sleep(2)
            if not self._running:
                return
        self.app.tts.enqueue(msg)
        if hasattr(self.app, 'notification_manager'):
            self.app.notification_manager.add(msg, priority=7, data={"type": "event"})
        print(f"[Events] Fired: {msg}")
        self._mark_notified()
        self._calculate_next_alert()

    def _process_schedules(self):
        if not self._next_schedule_ts or time.time() < self._next_schedule_ts:
            return
        sched_key = int(self._next_schedule_ts)
        if sched_key in self._alerted_schedules:
            return
        if self.app.state in ("playing", "recording"):
            print("[Schedules] Skipped: app state is playing/recording, will retry next cycle")
            return
        self._alerted_schedules.add(sched_key)
        for sc in list(self._next_schedules):
            self._execute_schedule(sc)
        self._mark_schedule_executed()
        self._calculate_next_schedule()

    def stop(self):
        self._running = False
