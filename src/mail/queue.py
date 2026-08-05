"""Email queue manager — stores pending emails and sends them after user confirmation."""
import json
import os
import uuid
from datetime import datetime

from utils import get_project_root

QUEUE_PATH = os.path.join(get_project_root(), "Allowed_root", "private_mail_queue.json")


def _load():
    try:
        with open(QUEUE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"queue": []}


def _save(data):
    os.makedirs(os.path.dirname(QUEUE_PATH), exist_ok=True)
    with open(QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add(account, provider, to, subject, body, cc="", in_reply_to="", references="", created_by="ai"):
    """Add email to queue. Returns queue_id."""
    data = _load()
    qid = str(uuid.uuid4())[:12]
    entry = {
        "id": qid,
        "status": "pending",
        "account": account,
        "provider": provider,
        "to": to,
        "subject": subject,
        "body": body,
        "cc": cc,
        "in_reply_to": in_reply_to,
        "references": references,
        "created_at": datetime.utcnow().isoformat(),
        "created_by": created_by,
    }
    data["queue"].append(entry)
    _save(data)
    if to:
        from mail.contacts import add
        add(to.strip())
    return qid


def get_all():
    """Return all pending emails."""
    data = _load()
    return data.get("queue", [])


def get(qid):
    """Return a queue entry by ID or None."""
    for item in get_all():
        if item["id"] == qid:
            return item
    return None


def update(qid, body=None, subject=None, to=None):
    """Update body/subject/to of a queued email."""
    data = _load()
    for item in data.get("queue", []):
        if item["id"] == qid:
            if body is not None:
                item["body"] = body
            if subject is not None:
                item["subject"] = subject
            if to is not None:
                item["to"] = to
            _save(data)
            return True
    return False


def remove(qid):
    """Remove from queue without sending."""
    data = _load()
    data["queue"] = [i for i in data["queue"] if i["id"] != qid]
    _save(data)


def send(qid):
    """Send a queued email and remove it on success. Returns (success, message)."""
    item = get(qid)
    if not item:
        return False, "Not found"
    from mail.send import send_email
    ok, msg = send_email(
        item["account"], item["to"], item["subject"], item["body"],
        item.get("cc"), item.get("in_reply_to"), item.get("references"),
    )
    if ok:
        remove(qid)
    return ok, msg


def send_all():
    """Send all queued emails. Returns count of successfully sent."""
    sent = 0
    for item in get_all():
        ok, _ = send(item["id"])
        if ok:
            sent += 1
    return sent


def count():
    """Return number of pending emails."""
    return len(get_all())
