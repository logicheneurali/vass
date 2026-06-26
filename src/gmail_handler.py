"""Gmail integration via keyring-stored OAuth2 credentials."""
import json, os, datetime

from google_auth import get_google_credentials
from utils import encrypt_fields


def _get_service():
    creds = get_google_credentials()
    if not creds:
        return None
    from googleapiclient.discovery import build
    return build("gmail", "v1", credentials=creds)


class GmailHandler:
    def __init__(self):
        self._service = None

    @property
    def service(self):
        if self._service is None:
            self._service = _get_service()
        return self._service

    def list_recent(self, max_results=10):
        svc = self.service
        if not svc:
            return json.dumps({"error": "Gmail not authenticated."})
        try:
            result = svc.users().messages().list(
                userId="me", labelIds=["INBOX"], maxResults=int(max_results)
            ).execute()
        except Exception as e:
            return json.dumps({"error": str(e)})
        msgs = result.get("messages", [])
        items = []
        for m in msgs:
            meta = self._get_message_meta(m["id"])
            if meta:
                items.append(meta)
        return json.dumps(items, ensure_ascii=False, indent=2)

    def _get_message_meta(self, msg_id):
        svc = self.service
        if not svc:
            return None
        try:
            msg = svc.users().messages().get(
                userId="me", id=msg_id, format="full",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
        except Exception as e:
            print(f"[GmailHandler] get msg {msg_id}: {e}")
            return None
        headers = {}
        for h in msg.get("payload", {}).get("headers", []):
            headers[h["name"].lower()] = h["value"]
        snippet = msg.get("snippet", "")
        label_ids = msg.get("labelIds", [])
        return {
            "id": msg["id"],
            "from": headers.get("from", "?"),
            "subject": headers.get("subject", "(nessun oggetto)"),
            "date": headers.get("date", ""),
            "snippet": snippet,
            "important": "IMPORTANT" in label_ids,
        }

    def check_new(self, seen_path, max_results=10):
        svc = self.service
        if not svc:
            print("[GmailHandler] Not authenticated.")
            return []

        try:
            result = svc.users().messages().list(
                userId="me", labelIds=["INBOX"], maxResults=int(max_results)
            ).execute()
        except Exception as e:
            print(f"[GmailHandler] list error: {e}")
            return []

        all_ids = [m["id"] for m in result.get("messages", [])]
        if not all_ids:
            print("[GmailHandler] Checked: inbox empty")
            return []

        seen_ids = self._load_seen_ids(seen_path)
        new_msgs = []
        seen_data = self._load_seen_data(seen_path)
        needs_migration = seen_data.get("version") != 2

        if needs_migration:
            seen_data["seen"] = [encrypt_fields(e, keep_plain={"id"}) for e in seen_data.get("seen", [])]
            seen_data["version"] = 2

        for mid in all_ids:
            if mid in seen_ids:
                continue
            meta = self._get_message_meta(mid)
            if not meta:
                continue
            entry = {
                "id": meta["id"],
                "date": datetime.datetime.utcnow().isoformat(),
                "sent_date": meta["date"],
                "from": meta["from"],
                "subject": meta["subject"],
                "snippet": meta["snippet"],
                "important": meta.get("important", False),
            }
            seen_data["seen"].append(encrypt_fields(entry, keep_plain={"id"}))
            new_msgs.append(entry)

        if new_msgs or needs_migration:
            seen_data["seen"] = seen_data["seen"][-500:]
            os.makedirs(os.path.dirname(seen_path), exist_ok=True)
            with open(seen_path, "w", encoding="utf-8") as f:
                json.dump(seen_data, f, ensure_ascii=False, indent=2)
            print(f"[GmailHandler] {len(new_msgs)} new message(s), {len(seen_data['seen'])} total tracked")
        else:
            print(f"[GmailHandler] Checked {len(all_ids)} recent, 0 new ({len(seen_ids)} already seen)")

        return new_msgs

    @staticmethod
    def _load_seen_ids(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return set()
        return {e["id"] for e in data.get("seen", [])}

    @staticmethod
    def _load_seen_data(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"seen": []}
