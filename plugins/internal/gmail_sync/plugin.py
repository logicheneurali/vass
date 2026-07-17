"""Gmail Sync plugin — checks inbox and announces new emails."""
import datetime
import os
import time

from plugins._base import Plugin
from utils import get_project_root, clean_for_tts
from i18n import t


class GmailSyncPlugin(Plugin):
    def __init__(self):
        self._app = None

    def on_load(self, app) -> None:
        self._app = app
        print("[Gmail] Plugin loaded")

    def on_unload(self) -> None:
        self._app = None
        print("[Gmail] Plugin unloaded")

    def get_threads(self) -> list:
        enabled = self._app.settings.get("gmail_enabled", "false").lower() == "true"
        if not enabled:
            print("[Gmail] Disabled in settings, skipping")
            return []
        return [
            (self._gmail_loop, (), {}),
        ]

    def _gmail_loop(self):
        app = self._app
        time.sleep(5)
        from .gmail_handler import GmailHandler
        gmail = GmailHandler()
        minutes = int(app.settings.get("gmail_sync_minutes", 5))
        max_results = int(app.settings.get("gmail_max_results", 10))
        seen_path = os.path.join(get_project_root(), "Allowed_root", "gmail_seen.json")
        print(f"[Gmail] Sync started (every {minutes}m, max {max_results} msgs)")
        try:
            self._announce_emails(gmail.check_new(seen_path, max_results=max_results), app)
        except Exception as e:
            print(f"[Gmail] Sync error: {e}")
        while app.running:
            time.sleep(minutes * 60)
            try:
                self._announce_emails(gmail.check_new(seen_path, max_results=max_results), app)
            except Exception as e:
                print(f"[Gmail] Sync error: {e}")

    def _announce_emails(self, emails, app):
        if not emails:
            return
        for em in emails:
            from_parts = clean_for_tts(em['from'], 80)
            subj = clean_for_tts(em['subject'], 120)
            snip = clean_for_tts(em['snippet'], 200, " " + t("notifications.email_truncated", app.language))
            date_str = self._format_email_ago(em.get('sent_date', ''), app.language)
            text = f"Nuova email da {from_parts} ({date_str}). Oggetto: {subj}. {snip}"
            app.tts.enqueue(text, defer_if_busy=True)
            notif = t("notifications.new_email", app.language)\
                .replace("{from}", from_parts)\
                .replace("{date}", date_str)\
                .replace("{subject}", subj)
            priority = 7 if em.get("important") else 5
            app.notification_manager.add(notif, priority=priority, data={
                "type": "mail",
                "link": f"https://mail.google.com/mail/u/0/#inbox/{em['id']}"
            })
            if app.memory.is_source_enabled("email"):
                classify_content = (
                    f"From: {from_parts}\n"
                    f"Subject: {subj}\n"
                    f"Snippet: {snip}"
                )
                app.memory.enqueue_external(classify_content, em['id'], "email")

    def _format_email_ago(self, sent_date, lang):
        from email.utils import parsedate_to_datetime
        try:
            dt = parsedate_to_datetime(sent_date)
            if dt is None:
                return sent_date
        except Exception:
            return sent_date
        now = datetime.datetime.now(dt.tzinfo) if dt.tzinfo else datetime.datetime.now()
        delta = now - dt
        secs = int(delta.total_seconds())
        if secs < 60:
            return t("notifications.just_now", lang)
        if secs < 3600:
            return t("notifications.ago_minutes", lang).replace("{n}", str(secs // 60))
        if secs < 86400:
            return t("notifications.ago_hours", lang).replace("{n}", str(secs // 3600))
        if secs < 604800:
            return t("notifications.ago_days", lang).replace("{n}", str(secs // 86400))
        if secs < 2419200:
            return t("notifications.ago_weeks", lang).replace("{n}", str(secs // 604800))
        if secs < 31536000:
            return t("notifications.ago_months", lang).replace("{n}", str(secs // 2592000))
        return t("notifications.on_date", lang).replace("{date}", dt.strftime("%Y-%m-%d"))
