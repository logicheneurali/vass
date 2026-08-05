import datetime
from i18n import t


def _format_email_ago(sent_date, lang):
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


def announce(emails, tts, notification_manager, memory, language, source="gmail", router=None):
    from utils import clean_for_tts
    for em in emails:
        from_parts = clean_for_tts(em["from"], 80)
        subj = clean_for_tts(em["subject"], 120)
        snip = clean_for_tts(em["snippet"], 200, " " + t("notifications.email_truncated", language))
        date_str = _format_email_ago(em.get("sent_date", ""), language)
        text = t("mail.tts_new_email", language) \
            .replace("{from}", from_parts) \
            .replace("{date}", date_str) \
            .replace("{subject}", subj) \
            .replace("{snippet}", snip)
        notif = t("notifications.new_email", language) \
            .replace("{from}", from_parts) \
            .replace("{date}", date_str) \
            .replace("{subject}", subj)
        priority = 7 if em.get("important") else 5
        data = {"type": "mail", "msg_id": em["id"]}
        if source == "gmail":
            data["link"] = f"https://mail.google.com/mail/u/0/#inbox/{em['id']}"
        if router is not None:
            router.emit("email", text, priority=priority, data=data,
                        tts_kwargs={"defer_if_busy": True})
        else:
            tts.enqueue(text, defer_if_busy=True)
            notification_manager.add(notif, priority=priority, data=data)
        if memory and memory.is_source_enabled("email"):
            classify_content = (
                f"From: {from_parts}\n"
                f"Subject: {subj}\n"
                f"Snippet: {snip}"
            )
            memory.enqueue_external(classify_content, em["id"], "email")
