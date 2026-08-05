"""IMAP and POP mail sources using stdlib imaplib/poplib + email parser."""

import email
from email.header import decode_header
import imaplib
import poplib
import ssl

from mail.base import MailSource
from mail.store import get_seen_ids


def _decode_header_value(value):
    if value is None:
        return ""
    parts = decode_header(value)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            try:
                result.append(part.decode(charset or "utf-8", errors="replace"))
            except Exception:
                result.append(part.decode("utf-8", errors="replace"))
        else:
            result.append(str(part))
    return " ".join(result)


def _get_first_body_chars(parsed, max_chars=500):
    body = _get_full_body(parsed)
    return body[:max_chars]


def _get_full_body(parsed):
    if parsed.is_multipart():
        for part in parsed.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    try:
                        return payload.decode("utf-8", errors="replace")
                    except Exception:
                        return str(payload)
    payload = parsed.get_payload(decode=True)
    if payload:
        try:
            return payload.decode("utf-8", errors="replace")
        except Exception:
            return str(payload)
    return ""


def _parse_date(msg):
    d = msg.get("Date")
    if d:
        return _decode_header_value(d)
    return ""


class ImapSource(MailSource):
    """IMAP or POP mail source."""

    def __init__(self, account_email, username, host, port, ssl_mode, auth_mode, stype, max_results=20):
        self._account = account_email
        self._username = username
        self._host = host
        self._port = port
        self._ssl_mode = ssl_mode
        self._auth_mode = auth_mode
        self._type = stype
        self._max_results = max_results

    @property
    def name(self):
        return self._type

    @property
    def account(self):
        return self._account

    def _get_password(self):
        try:
            import keyring
            return keyring.get_password("vass", f"imap_pass_{self._account}")
        except Exception:
            return None

    def _connect_imap(self):
        if self._ssl_mode == "ssl":
            conn = imaplib.IMAP4_SSL(self._host, self._port)
        elif self._ssl_mode == "starttls":
            conn = imaplib.IMAP4(self._host, self._port)
            conn.starttls(ssl_context=ssl.create_default_context())
        else:
            conn = imaplib.IMAP4(self._host, self._port)
        return conn

    def _login_imap(self, conn, pw):
        if self._auth_mode == "cram-md5":
            conn.authenticate("CRAM-MD5", lambda challenge: pw.encode())
        else:
            conn.login(self._username, pw)

    def _connect_pop(self):
        if self._ssl_mode == "ssl":
            return poplib.POP3_SSL(self._host, self._port)
        return poplib.POP3(self._host, self._port)

    def _login_pop(self, conn, pw):
        conn.user(self._username)
        conn.pass_(pw)

    def check_new(self):
        pw = self._get_password()
        if not pw:
            print(f"[{self._type.upper()}:{self._account}] No password in keyring")
            return []

        if self._type == "pop":
            return self._check_pop(pw)
        return self._check_imap(pw)

    def _check_imap(self, pw):
        try:
            conn = self._connect_imap()
            self._login_imap(conn, pw)
            conn.select("INBOX", readonly=True)
            status, data = conn.search(None, "UNSEEN")
            conn.close()
            conn.logout()
        except Exception as e:
            print(f"[IMAP:{self._account}] Connection error: {e}")
            return []

        if status != "OK" or not data or not data[0]:
            return []

        uids = data[0].split()[-self._max_results:]
        if not uids:
            return []

        seen_ids = get_seen_ids()
        new_msgs = []

        try:
            conn = self._connect_imap()
            self._login_imap(conn, pw)
            conn.select("INBOX", readonly=True)

            for uid in uids:
                uid_key = f"imap:{uid.decode()}"
                if uid_key in seen_ids:
                    continue
                status, msg_data = conn.fetch(uid, "(RFC822)")
                if status != "OK":
                    continue

                raw = None
                for part in msg_data:
                    if isinstance(part, tuple):
                        raw = part[1]
                        break

                if not raw:
                    continue

                if isinstance(raw, bytes):
                    parsed = email.message_from_bytes(raw)
                else:
                    parsed = email.message_from_string(raw if isinstance(raw, str) else "")

                if not parsed:
                    continue

                full_body = _get_full_body(parsed).replace("\r", " ").replace("\n", " ").strip()
                snippet = full_body[:300]
                priority = "high" in str(parsed.get("X-Priority", "")).lower() or \
                           "important" in str(parsed.get("Importance", "")).lower()

                new_msgs.append({
                    "id": uid_key,
                    "from": _decode_header_value(parsed.get("From", "?")),
                    "subject": _decode_header_value(parsed.get("Subject", "")),
                    "date": _parse_date(parsed),
                    "sent_date": _parse_date(parsed),
                    "snippet": snippet,
                    "body": full_body,
                    "message_id": parsed.get("Message-ID", "").strip(),
                    "references": parsed.get("References", "").strip(),
                    "in_reply_to": parsed.get("In-Reply-To", "").strip(),
                    "thread_id": "",
                    "important": priority,
                })

            conn.close()
            conn.logout()
        except Exception as e:
            print(f"[IMAP:{self._account}] Fetch error: {e}")

        return new_msgs

    def _check_pop(self, pw):
        try:
            conn = self._connect_pop()
            self._login_pop(conn, pw)
            num_msgs = len(conn.list()[1])
            conn.quit()
        except Exception as e:
            print(f"[POP:{self._account}] Connection error: {e}")
            return []

        if num_msgs == 0:
            return []

        seen_ids = get_seen_ids()
        new_msgs = []

        try:
            start = max(1, num_msgs - self._max_results + 1)
            conn = self._connect_pop()
            self._login_pop(conn, pw)

            for i in range(start, num_msgs + 1):
                status, lines, _ = conn.retr(i)
                raw = b"\n".join(lines) if isinstance(lines[0], bytes) else "\n".join(lines)
                parsed = email.message_from_bytes(raw) if isinstance(raw, bytes) else email.message_from_string(raw)
                msg_id = parsed.get("Message-ID", f"pop:{i}").strip()
                msg_key = f"pop:{msg_id}"
                if msg_key in seen_ids:
                    continue

                full_body = _get_full_body(parsed).replace("\r", " ").replace("\n", " ").strip()
                snippet = full_body[:300]
                priority = "high" in str(parsed.get("X-Priority", "")).lower() or \
                           "important" in str(parsed.get("Importance", "")).lower()

                new_msgs.append({
                    "id": msg_key,
                    "from": _decode_header_value(parsed.get("From", "?")),
                    "subject": _decode_header_value(parsed.get("Subject", "")),
                    "date": _parse_date(parsed),
                    "sent_date": _parse_date(parsed),
                    "snippet": snippet,
                    "body": full_body,
                    "message_id": parsed.get("Message-ID", "").strip(),
                    "references": parsed.get("References", "").strip(),
                    "in_reply_to": parsed.get("In-Reply-To", "").strip(),
                    "thread_id": "",
                    "important": priority,
                })

            conn.quit()
        except Exception as e:
            print(f"[POP:{self._account}] Fetch error: {e}")

        return new_msgs
