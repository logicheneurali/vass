"""Email sending module — Gmail API and SMTP senders. Used only by the queue system, never by AI directly."""
import configparser
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import ssl

from utils import get_project_root

CONFIG_PATH = os.path.join(get_project_root(), "config", "mail.ini")


def _get_sender_info(account_email):
    """Return (provider, config_dict) for an account from mail.ini."""
    cfg = configparser.ConfigParser()
    if os.path.exists(CONFIG_PATH):
        cfg.read(CONFIG_PATH, encoding="utf-8")
    if not cfg.has_section(account_email):
        return "unknown", {}
    stype = cfg.get(account_email, "type", fallback="gmail")
    info = dict(cfg[account_email])
    info["type"] = stype
    return stype, info


def send_email(account_email, to, subject, body, cc=None, in_reply_to=None, references=None):
    """Send an email. Returns (success: bool, message: str)."""
    stype, info = _get_sender_info(account_email)
    if stype == "gmail":
        return _send_gmail(account_email, to, subject, body, cc, in_reply_to, references)
    elif stype in ("imap", "pop"):
        return _send_smtp(account_email, info, to, subject, body, cc, in_reply_to, references)
    return False, f"Unknown provider type: {stype}"


def _send_gmail(from_email, to, subject, body, cc=None, in_reply_to=None, references=None):
    try:
        import json
        import base64
        import keyring

        raw = keyring.get_password("vass", "google_token")
        if not raw:
            return False, "Google not authenticated"
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
        from googleapiclient.discovery import build
        svc = build("gmail", "v1", credentials=creds)

        msg = MIMEMultipart()
        msg["From"] = from_email
        msg["To"] = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references
        msg.attach(MIMEText(body, "plain", "utf-8"))

        raw_bytes = msg.as_bytes()
        raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode()
        svc.users().messages().send(userId="me", body={"raw": raw_b64}).execute()
        return True, "Sent via Gmail"
    except Exception as e:
        return False, str(e)


def _send_smtp(from_email, info, to, subject, body, cc=None, in_reply_to=None, references=None):
    try:
        import keyring
        pw = keyring.get_password("vass", f"imap_pass_{from_email}")
        if not pw:
            return False, "SMTP password not found in keyring"

        host = info.get("smtp_host", "")
        if not host:
            return False, "SMTP host not configured. Add smtp_host to mail.ini"
        port = int(info.get("smtp_port", "587"))
        ssl_mode = info.get("smtp_ssl", "starttls")

        msg = MIMEMultipart()
        msg["From"] = from_email
        msg["To"] = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references
        msg.attach(MIMEText(body, "plain", "utf-8"))

        if ssl_mode == "ssl":
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context) as server:
                server.login(info.get("username", from_email), pw)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port) as server:
                if ssl_mode == "starttls":
                    server.starttls(context=ssl.create_default_context())
                server.login(info.get("username", from_email), pw)
                server.send_message(msg)
        return True, "Sent via SMTP"
    except Exception as e:
        return False, str(e)
