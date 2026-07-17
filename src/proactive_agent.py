"""Proactive agent — analyzes user profile and performs useful background actions
when system resources are idle. Controlled by config/agent.ini.
"""
import configparser
import json
import os
import time

from utils import get_project_root


class ProactiveAgent:
    def __init__(self, app):
        self._app = app
        self._config = self._load_config()
        self._actions_path = os.path.join(
            get_project_root(), "Allowed_root", "private_agent_actions.json")
        self._last_action_ts = 0

    # ── Public ─────────────────────────────────────────────────────

    def check_and_act(self):
        """Main entry: analyze profile, decide actions, execute them."""
        if not self._config.get("enabled", True):
            print("[Agent] Disabled in agent.ini, skipping")
            return
        if not self._should_act():
            return

        profile = self._load_profile()
        if not profile:
            print("[Agent] No profile found, skipping")
            return

        print("[Agent] Analyzing profile for actions...")
        actions = self._analyze(profile)
        if not actions:
            print("[Agent] No actions needed")
            return

        print(f"[Agent] Executing {len(actions)} action(s)...")
        for action in actions:
            self._execute(action)
            self._log_action(action)
            self._last_action_ts = time.time()
            if self._today_count() >= self._config.get("max_actions_per_day", 5):
                print(f"[Agent] Daily limit ({self._config.get('max_actions_per_day', 5)}) reached, stopping")
                break
        print(f"[Agent] Done. Total today: {self._today_count()}")

    # ── Internal ───────────────────────────────────────────────────

    def _load_config(self):
        cfg = configparser.ConfigParser()
        cfg_path = os.path.join(get_project_root(), "config", "agent.ini")
        if os.path.exists(cfg_path):
            cfg.read(cfg_path, encoding="utf-8")
            print(f"[Agent] Config loaded: {cfg_path}")
        else:
            cfg["agent"] = {
                "enabled": "true",
                "interval_min": "60",
                "max_actions_per_day": "5",
                "action_types": "notify,say",
                "notify_on_idle": "true",
            }
            os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
            with open(cfg_path, "w", encoding="utf-8") as f:
                cfg.write(f)
            print(f"[Agent] Config created: {cfg_path}")
        return {
            "enabled": cfg.getboolean("agent", "enabled", fallback=True),
            "interval_min": cfg.getint("agent", "interval_min", fallback=60),
            "max_actions_per_day": cfg.getint("agent", "max_actions_per_day", fallback=5),
            "action_types": cfg.get("agent", "action_types", fallback="notify,say").split(","),
            "notify_on_idle": cfg.getboolean("agent", "notify_on_idle", fallback=True),
        }

    def _should_act(self):
        if not self._is_idle():
            print("[Agent] System not idle, skipping")
            return False
        today = self._today_count()
        max_today = self._config.get("max_actions_per_day", 5)
        if today >= max_today:
            print(f"[Agent] Daily limit reached ({today}/{max_today}), skipping")
            return False
        since_last = time.time() - self._last_action_ts
        if since_last < 300:
            print(f"[Agent] Anti-spam: {since_last:.0f}s since last action, skipping")
            return False
        return True

    def _is_idle(self):
        try:
            from idle_tracker import IdleTracker
            idle = IdleTracker()
            input_idle = idle.get_total_idle_seconds() > 300
        except Exception:
            input_idle = True
        try:
            from resource_monitor import check_resources
            res_ok, _ = check_resources(
                {"cpu_max": 20, "ram_max": 70, "gpu_max": 30, "vram_max": 30})
        except Exception:
            res_ok = True
        return input_idle and res_ok

    def _load_profile(self):
        path = os.path.join(get_project_root(), "Allowed_root", "private_profile.json")
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _today_count(self):
        actions = self._load_actions()
        today = time.strftime("%Y-%m-%d")
        return sum(1 for a in actions if a.get("ts", "").startswith(today))

    def _load_actions(self):
        try:
            with open(self._actions_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _analyze(self, profile):
        today = time.strftime("%Y-%m-%d (%A) %H:%M")
        prompt = (
            f"Today is {today}. Based on this user profile, is there anything "
            f"useful to remind or tell the user RIGHT NOW? "
            f"Consider: appointments within 48 hours, expiring subscriptions, "
            f"deadlines, birthdays, events. "
            f"Only suggest truly urgent or timely items. "
            f"If nothing is time-sensitive, respond with 'NONE'. "
            f"Otherwise respond with a JSON array of actions:\n"
            f"[{{\"action\":\"notify\",\"message\":\"Reminder: ...\",\"trigger\":\"appointment\"}}]\n\n"
            f"Profile:\n{json.dumps(profile, ensure_ascii=False, indent=2)}"
        )
        try:
            from utils import call_with_retry
            resp = call_with_retry(
                lambda: self._app.openai_client.chat.completions.create(
                    model=self._app.ai_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=300,
                    extra_body={"disable_thinking": True},
                ),
                retries=1, delays=(3,), log_prefix="[Agent]"
            )
            raw = (resp.choices[0].message.content or "").strip()
            print(f"[Agent] AI response: {raw[:100]}...")
            if raw.upper() == "NONE" or not raw:
                print("[Agent] AI returned NONE — nothing urgent")
                return []
            if raw.startswith("```"):
                raw = raw.strip("`").strip()
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except Exception as e:
            print(f"[Agent] Analyze failed: {e}")
            return []

    def _execute(self, action):
        action_type = action.get("action", "")
        message = action.get("message", "")
        if not message:
            return

        allowed = [t.strip().lower() for t in self._config.get("action_types", ["notify"])]
        if action_type not in allowed:
            return

        if action_type == "notify":
            try:
                if hasattr(self._app, 'notification_manager'):
                    self._app.notification_manager.add(
                        message, priority=5, data={"type": "agent"})
                    print(f"[Agent] Notify: {message[:80]}...")
            except Exception as e:
                print(f"[Agent] Notify failed: {e}")

        elif action_type == "say":
            if not self._config.get("notify_on_idle", True):
                print(f"[Agent] Say blocked: notify_on_idle=false")
                return
            if not self._can_say():
                print(f"[Agent] Say blocked: user active")
                return
            try:
                self._app.tts.enqueue(message, defer_if_busy=True)
                print(f"[Agent] Say: {message[:80]}...")
            except Exception as e:
                print(f"[Agent] Say failed: {e}")

    def _can_say(self):
        try:
            from idle_tracker import IdleTracker
            idle = IdleTracker()
            return idle.get_total_idle_seconds() > 60
        except Exception:
            return True

    def _log_action(self, action):
        actions = self._load_actions()
        actions.append({
            "action": action.get("action", ""),
            "message": action.get("message", ""),
            "trigger": action.get("trigger", ""),
            "ts": time.strftime("%Y-%m-%dT%H:%M"),
        })
        os.makedirs(os.path.dirname(self._actions_path), exist_ok=True)
        with open(self._actions_path, "w", encoding="utf-8") as f:
            json.dump(actions, f, ensure_ascii=False, indent=2)
