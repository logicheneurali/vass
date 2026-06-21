import threading
import time as _time
from uuid import uuid4


def parse_duration(s: str) -> int:
    """Parse '1h', '20m', '1h30m', '90m' -> seconds"""
    total = 0
    s = s.lower().replace(" ", "").strip()
    for ch, mul in [("h", 3600), ("m", 60), ("s", 1)]:
        if ch in s:
            val, _, s = s.partition(ch)
            try:
                total += int(val) * mul if val else 0
            except ValueError:
                pass
    if total == 0 and s.isdigit():
        total = int(s) * 60
    return max(total, 10)


class TimerManager:
    MAX_TIMERS = 5
    MIN_SECONDS = 60

    def __init__(self, app):
        self.app = app
        self._timers = {}

    def start(self, duration_str: str, command_text: str = None) -> str:
        print(f"[Timer] Request: duration_str='{duration_str}'")
        from i18n import t
        lang = getattr(self.app, "language", "en")
        if len(self._timers) >= self.MAX_TIMERS:
            return t("timer.max_reached", lang)
        seconds = parse_duration(duration_str)
        if seconds < self.MIN_SECONDS:
            return t("timer.min_duration", lang).replace("{min}", str(self.MIN_SECONDS // 60))
        tid = uuid4().hex[:6]
        self._timers[tid] = {
            "duration": duration_str,
            "seconds": seconds,
            "remaining": seconds,
            "started": _time.time(),
            "command_text": command_text,
        }
        threading.Thread(target=self._run, args=(tid, seconds, command_text), daemon=True).start()
        print(f"[Timer] Created {tid}: duration={duration_str} ({seconds}s)")
        return t("timer.started", lang)

    def list_all(self) -> str:
        from i18n import t
        lang = getattr(self.app, "language", "en")
        if not self._timers:
            return t("timer.none_active", lang)
        parts = [t("timer.list_header", lang)]
        now = _time.time()
        for tid, info in self._timers.items():
            elapsed = now - info["started"]
            remaining = max(0, info["seconds"] - int(elapsed))
            info["remaining"] = remaining
            rm = self._format_remaining(remaining)
            parts.append(t("timer.list_item", lang).replace("{id}", tid).replace("{duration}", info["duration"]).replace("{remaining}", rm))
        return "\n".join(parts)

    def cancel(self, tid: str) -> str:
        from i18n import t
        lang = getattr(self.app, "language", "en")
        tid = tid.strip()
        if tid in self._timers:
            self._timers.pop(tid)
            return t("timer.cancelled", lang).replace("{id}", tid)
        return t("timer.not_found", lang).replace("{id}", tid)

    def _run(self, tid, seconds, command_text=None):
        _time.sleep(seconds)
        if tid not in self._timers:
            return
        info = self._timers.pop(tid, None)
        if not info:
            return
        state = getattr(self.app, "state", "listening")
        if command_text:
            if state in ("recording", "waiting", "waiting_resources", "playing"):
                print(f"[Timer] Delayed command waiting: state={state}")
                for _ in range(30):
                    _time.sleep(2)
                    if getattr(self.app, "state", "listening") not in ("recording", "waiting", "waiting_resources", "playing"):
                        break
                else:
                    print(f"[Timer] Delayed command abandoned after 60s: state={state}")
                    return
            if hasattr(self.app, '_process_delayed_command'):
                self.app._process_delayed_command(command_text)
            return
        from i18n import t
        lang = getattr(self.app, "language", "en")
        msg = t("timer.expired", lang).replace("{duration}", self._clean_duration(info["duration"]))
        if hasattr(self.app, 'notification_manager'):
            self.app.notification_manager.add(msg, priority=8, data={"type": "timer"})
        if state in ("recording", "playing"):
            print(f"[Timer] Alert waiting: state={state}")
            for _ in range(30):
                _time.sleep(2)
                if getattr(self.app, "state", "listening") not in ("recording", "playing"):
                    break
            else:
                print(f"[Timer] Alert abandoned after 60s: state={state}")
                return
        self._play_alert(2)
        self.app.tts.enqueue(msg, on_done=lambda: self._play_alert(2))

    @staticmethod
    def _play_alert(count=1):
        try:
            import os
            import soundfile as sf
            import sounddevice as sd
            path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sounds", "alert.wav")
            data, sr = sf.read(path)
            for _ in range(count):
                sd.play(data, sr)
                sd.wait()
        except Exception:
            pass

    @staticmethod
    def _clean_duration(dur):
        parts = []
        s = dur.lower()
        for ch in ["h", "m", "s"]:
            if ch in s:
                val, _, s = s.partition(ch)
                if val and val != "0":
                    parts.append(f"{val}{ch}")
        return "".join(parts) if parts else "0s"

    @staticmethod
    def _format_remaining(seconds):
        if seconds < 60:
            return f"{seconds}s"
        mins = seconds // 60
        if mins < 60:
            return f"{mins}m"
        h = mins // 60
        m = mins % 60
        if m == 0:
            return f"{h}h"
        return f"{h}h{m}m"
