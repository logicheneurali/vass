"""User profile builder — aggregates data from permanent memory into a
structured JSON profile. Runs in background when system is idle.
"""
import json
import os
import threading
import time

from utils import get_project_root, call_with_retry


class UserProfile:
    def __init__(self, app):
        self._app = app
        self._profile_path = os.path.join(
            get_project_root(), "Allowed_root", "private_profile.json")
        self._lock = threading.Lock()

    # ── Public API ─────────────────────────────────────────────────

    def should_update(self):
        """True if 24h have passed since last update."""
        profile = self._load()
        last = profile.get("last_updated", "")
        if not last:
            return True
        try:
            import datetime
            last_dt = datetime.datetime.strptime(last, "%Y-%m-%d")
            return (datetime.date.today() - last_dt.date()).days >= 1
        except Exception:
            return True

    def is_idle(self):
        """True if system resources are free enough for profile building."""
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

    def build_or_update(self):
        """Build initial profile or incrementally update existing one."""
        with self._lock:
            profile = self._load()
            print(f"[Profile] Existing profile keys: {list(profile.keys())}")
            data = self._collect_data(profile)
            print(f"[Profile] Collected data: {len(data)} chars")
            if not data.strip():
                print("[Profile] No data to process, skipping")
                return
            new_sections = self._call_ai(data)
            print(f"[Profile] AI returned sections: {list(new_sections.keys()) if new_sections else 'None'}")
            if new_sections:
                merged = self._merge(profile, new_sections)
                print(f"[Profile] Merged profile keys: {list(merged.keys())}")
                self._save(merged)
                print(f"[Profile] Saved to {self._profile_path}")

    def get_profile(self):
        return self._load()

    # ── Internal ───────────────────────────────────────────────────

    def _collect_data(self, existing_profile):
        """Gather fresh data from permanent memory for profile building."""
        parts = []
        if existing_profile:
            parts.append(f"Existing profile:\n{json.dumps(existing_profile, ensure_ascii=False, indent=2)}")

        # Summary
        root = get_project_root()
        mem_path = os.path.join(root, "Allowed_root", "memory.json")
        print(f"[Profile] Reading memory.json: {mem_path}")
        try:
            with open(mem_path, encoding="utf-8") as f:
                mem_data = json.load(f)
            sid = mem_data.get("summary_id", "")
            print(f"[Profile] Summary ID: {sid}, history entries: {len(mem_data.get('history', []))}")
            if sid:
                sf_path = os.path.join(root, "Allowed_root", "memory", f"{sid}.json")
                if os.path.exists(sf_path):
                    with open(sf_path, encoding="utf-8") as sf:
                        summary_text = json.load(sf).get("info", "")
                    parts.append(f"Summary:\n{summary_text}")
                    print(f"[Profile] Summary loaded: {len(summary_text)} chars")
                else:
                    print(f"[Profile] Summary file not found: {sf_path}")
        except Exception as e:
            print(f"[Profile] Error loading memory.json: {e}")

        # External entries from memory_tags.json
        tags_path = os.path.join(root, "Allowed_root", "memory_tags.json")
        print(f"[Profile] Reading memory_tags.json: {tags_path}")
        try:
            with open(tags_path, encoding="utf-8") as f:
                tags_data = json.load(f)
            entries = tags_data.get("entries", [])
            print(f"[Profile] Tagged entries: {len(entries)}")
            if entries:
                lines = []
                for e in entries[-50:]:
                    src = e.get("source", "?")
                    tags = ", ".join(e.get("tags", []))
                    content = e.get("content", "")[:300]
                    if content:
                        lines.append(f"[{src}] [{tags}] {content}")
                parts.append("Recent external data:\n" + "\n".join(lines))
                print(f"[Profile] External data lines: {len(lines)}")
        except Exception as e:
            print(f"[Profile] Error loading memory_tags.json: {e}")

        return "\n\n".join(parts)

    def _call_ai(self, data):
        """Send data to AI and return structured profile sections."""
        print(f"[Profile] Calling AI with {len(data)} chars of data...")
        prompt = (
            "You are a profile builder. Based on the data below, extract or update "
            "user facts into this JSON structure. Be concise: max 200 chars per field. "
            "Return ONLY valid JSON, nothing else.\n\n"
            "CRITICAL: Include dates in YYYY-MM-DD format for all time-sensitive data:\n"
            "- finance: each expense/subscription MUST have a 'date' field\n"
            "- health: each appointment/event MUST have a 'date' field\n"
            "- routines: each task MUST include timing or days\n"
            "- Extract dates from filenames, file paths, and content text.\n"
            "- The 'ts' field is the SCAN date, NOT the event/purchase date. IGNORE IT.\n\n"
            "Sections:\n"
            "  personal: {name, family, pets, location}\n"
            "  health: {conditions: [], medications: [{name, dosage, frequency}], "
            "doctors: [{name, specialty}], appointments: [{description, date}]}\n"
            "  finance: {subscriptions: [{name, amount, date}], "
            "recent_expenses: [{description, amount, date}]}\n"
            "  preferences: {food: [], tech: [], habits: [], interests: []}\n"
            "  contacts: [{name, role, context}]\n"
            "  routines: [{task, time, days}]\n\n"
            "Example (with dates): "
            "{\"finance\": {\"subscriptions\": [{\"name\": \"Netflix\", \"amount\": \"19.99 EUR\", \"date\": \"2026-07-08\"}]}, "
            "\"health\": {\"appointments\": [{\"description\": \"ecografia tiroide\", \"date\": \"2026-07-06\"}]}, ...}\n\n"
            f"Data:\n{data[:8000]}"
        )
        try:
            resp = call_with_retry(
                lambda: self._app.openai_client.chat.completions.create(
                    model=self._app.ai_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=1000,
                    extra_body={"disable_thinking": True},
                ),
                retries=2, delays=(3, 6), log_prefix="[Profile]"
            )
            raw = (resp.choices[0].message.content or "").strip()
            print(f"[Profile] AI response ({len(raw)} chars): {raw[:200]}...")
            if raw.startswith("```"):
                raw = raw.strip("`").strip()
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except Exception as e:
            print(f"[Profile] AI call failed: {e}")
            return None

    def _merge(self, old, new):
        """Merge new profile data into existing, avoiding duplicates."""
        for section in new:
            if section in ("last_updated", "last_source_ids"):
                continue
            if section not in old:
                old[section] = new[section]
            elif isinstance(new[section], dict) and isinstance(old.get(section), dict):
                old[section].update(new[section])
            elif isinstance(new[section], list) and isinstance(old.get(section), list):
                existing = {str(v) for v in old[section]}
                for item in new[section]:
                    if str(item) not in existing:
                        old[section].append(item)
                        existing.add(str(item))
        old["last_updated"] = time.strftime("%Y-%m-%d")
        return old

    def _load(self):
        try:
            with open(self._profile_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self, data):
        os.makedirs(os.path.dirname(self._profile_path), exist_ok=True)
        with open(self._profile_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
