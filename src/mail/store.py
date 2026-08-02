import datetime
import json
import os
from utils import get_project_root, encrypt_fields

ROOT = os.path.join(get_project_root(), "Allowed_root", "private_mail.json")
MAX_ENTRIES = 500


def load():
    try:
        with open(ROOT, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"version": 2, "messages": []}


def save(data):
    os.makedirs(os.path.dirname(ROOT), exist_ok=True)
    with open(ROOT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_seen_ids():
    data = load()
    return {m["id"] for m in data.get("messages", [])}


def append_new(messages, source, account):
    data = load()
    for msg in messages:
        entry = {
            "id": msg["id"],
            "source": source,
            "account": account,
            "date": datetime.datetime.utcnow().isoformat(),
            "sent_date": msg.get("sent_date", msg.get("date", "")),
            "from": msg["from"],
            "subject": msg["subject"],
            "snippet": msg["snippet"],
            "important": msg.get("important", False),
        }
        data["messages"].append(
            encrypt_fields(entry, keep_plain={"id", "source", "account"}))
    data["messages"] = data["messages"][-MAX_ENTRIES:]
    save(data)


def fix_account(source, old_account, new_account):
    data = load()
    for m in data.get("messages", []):
        if m.get("source") == source and m.get("account") == old_account:
            m["account"] = new_account
    save(data)
