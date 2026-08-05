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
            "body": msg.get("body", ""),
            "message_id": msg.get("message_id", ""),
            "references": msg.get("references", ""),
            "in_reply_to": msg.get("in_reply_to", ""),
            "thread_id": msg.get("thread_id", ""),
            "important": msg.get("important", False),
        }
        data["messages"].append(
            encrypt_fields(entry, keep_plain={"id", "source", "account"}))
    data["messages"] = data["messages"][-MAX_ENTRIES:]
    save(data)
    for msg in messages:
        from mail.contacts import add_from_message
        add_from_message(msg)


def get_message(msg_id):
    """Return a decrypted message by ID. Returns None if not found."""
    from utils import _get_fernet
    f = _get_fernet()
    data = load()
    for m in data.get("messages", []):
        if m.get("id") == msg_id:
            if not f:
                return dict(m)
            out = {}
            for k, v in m.items():
                if isinstance(v, str) and v.startswith("gAAAAA"):
                    try:
                        out[k] = f.decrypt(v.encode()).decode()
                    except Exception:
                        out[k] = v
                else:
                    out[k] = v
            return out
    return None


def search_emails(keywords):
    """Search encrypted mail.json by keywords. Returns decrypted matches."""
    from utils import _get_fernet
    f = _get_fernet()
    data = load()
    terms = [k.lower() for k in keywords.split()]
    matches = []
    for m in data.get("messages", []):
        decrypted = {}
        for k, v in m.items():
            if isinstance(v, str) and v.startswith("gAAAAA") and f:
                try:
                    decrypted[k] = f.decrypt(v.encode()).decode()
                except Exception:
                    decrypted[k] = v
            else:
                decrypted[k] = v
        text = (
            decrypted.get("from", "") + " " +
            decrypted.get("subject", "") + " " +
            decrypted.get("snippet", "") + " " +
            decrypted.get("body", "")
        ).lower()
        if any(t in text for t in terms):
            matches.append(decrypted)
    return matches


def fix_account(source, old_account, new_account):
    data = load()
    for m in data.get("messages", []):
        if m.get("source") == source and m.get("account") == old_account:
            m["account"] = new_account
    save(data)
