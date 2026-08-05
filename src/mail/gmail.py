"""Gmail mail source — adapted from src/gmail_handler.py and src/google_auth.py."""
import json
import time as _time

from mail.base import MailSource

_GOOGLE_AUTH_LAST_REFRESH = 0
_GOOGLE_AUTH_REFRESH_INTERVAL = 300


def _get_google_credentials():
    global _GOOGLE_AUTH_LAST_REFRESH
    try:
        import keyring
        raw = keyring.get_password("vass", "google_token")
        if not raw:
            return None
        token = json.loads(raw)
        from google.oauth2.credentials import Credentials
        creds = Credentials(
            token=token.get("token"),
            refresh_token=token.get("refresh_token"),
            token_uri=token.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token.get("client_id"),
            client_secret=token.get("client_secret"),
            scopes=token.get("scopes"),
        )
        if creds.refresh_token and _time.time() - _GOOGLE_AUTH_LAST_REFRESH > _GOOGLE_AUTH_REFRESH_INTERVAL:
            import google.auth.transport.requests
            request = google.auth.transport.requests.Request()
            creds.refresh(request)
            _GOOGLE_AUTH_LAST_REFRESH = _time.time()
            try:
                import keyring as kr
                kr.set_password("vass", "google_token", creds.to_json())
            except Exception:
                pass
        return creds
    except Exception as e:
        print(f"[Gmail] Auth error: {e}")
        return None


class GmailSource(MailSource):
    def __init__(self, account_email, max_results=10):
        self._account = account_email
        self._max_results = max_results
        self._service = None

    @property
    def name(self):
        return "gmail"

    @property
    def account(self):
        return self._account

    @property
    def service(self):
        if self._service is None:
            creds = _get_google_credentials()
            if not creds:
                return None
            from googleapiclient.discovery import build
            self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def check_new(self):
        svc = self.service
        if not svc:
            print(f"[Gmail:{self._account}] Not authenticated.")
            return []

        try:
            result = svc.users().messages().list(
                userId="me", labelIds=["INBOX"], maxResults=self._max_results
            ).execute()
        except Exception as e:
            print(f"[Gmail:{self._account}] List error: {e}")
            return []

        all_msgs = result.get("messages", [])
        if not all_msgs:
            print(f"[Gmail:{self._account}] Inbox empty")
            return []

        seen_ids = self._get_seen_ids()
        new_msgs = []
        for m in all_msgs:
            if m["id"] in seen_ids:
                continue
            meta = self._get_message_meta(m["id"])
            if meta:
                new_msgs.append(meta)

        return new_msgs

    def _get_message_meta(self, msg_id):
        svc = self.service
        if not svc:
            return None
        try:
            msg = svc.users().messages().get(
                userId="me", id=msg_id, format="full",
                metadataHeaders=["From", "Subject", "Date", "Message-ID",
                                 "References", "In-Reply-To"],
            ).execute()
        except Exception as e:
            print(f"[Gmail:{self._account}] get msg {msg_id}: {e}")
            return None
        headers = {}
        for h in msg.get("payload", {}).get("headers", []):
            headers[h["name"].lower()] = h["value"]
        snippet = msg.get("snippet", "")
        label_ids = msg.get("labelIds", [])
        body = self._extract_body(msg.get("payload", {}))
        return {
            "id": msg["id"],
            "from": headers.get("from", "?"),
            "subject": headers.get("subject", "(nessun oggetto)"),
            "date": headers.get("date", ""),
            "sent_date": headers.get("date", ""),
            "snippet": snippet,
            "body": body or snippet,
            "message_id": headers.get("message-id", ""),
            "references": headers.get("references", ""),
            "in_reply_to": headers.get("in-reply-to", ""),
            "thread_id": msg.get("threadId", ""),
            "important": "IMPORTANT" in label_ids,
        }

    @staticmethod
    def _extract_body(payload):
        if not payload:
            return ""
        if payload.get("mimeType") == "text/plain":
            data = payload.get("body", {}).get("data", "")
            if data:
                import base64
                return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
            return ""
        for part in payload.get("parts", []):
            body = GmailSource._extract_body(part)
            if body:
                return body
        return ""

    def _get_seen_ids(self):
        from mail.store import get_seen_ids
        return get_seen_ids()
