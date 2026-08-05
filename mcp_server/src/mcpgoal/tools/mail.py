"""MCP email tools — compose and queue emails, search local mail archive."""
import json
import os
import sys

_QUEUE = None


def _get_queue():
    global _QUEUE
    if _QUEUE is None:
        src = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))), "src")
        if src not in sys.path:
            sys.path.insert(0, src)
        from mail.queue import add as qadd, count
        from mail.store import get_message, search_emails
        _QUEUE = type("_Q", (), {
            "add": qadd, "count": count,
            "get_message": get_message, "search_emails": search_emails,
        })
    return _QUEUE


def _find_account():
    """Find the first Gmail account from mail.ini, or the first IMAP account."""
    import configparser
    from utils import get_project_root
    path = os.path.join(get_project_root(), "config", "mail.ini")
    if not os.path.exists(path):
        return "", "unknown"
    cfg = configparser.ConfigParser()
    cfg.read(path, encoding="utf-8")
    active = [a.strip() for a in cfg.get("sources", "active", fallback="").split(",") if a.strip()]
    for account in active:
        stype = cfg.get(account, "type", fallback="")
        if stype in ("gmail", "imap", "pop"):
            return account, stype
    return "", "unknown"


async def send_email(to: str, subject: str, body: str) -> str:
    """Compose a new email and add it to the outbox queue for user approval.
    The email is NOT sent until the user reviews and approves it.
    Args:
        to: recipient email address
        subject: email subject
        body: plain text email body
    Returns JSON with queue status.
    """
    q = _get_queue()
    account, provider = _find_account()
    if not account:
        return json.dumps({"status": "error", "message": "No mail account configured. Add an account in Settings > Email accounts."}, ensure_ascii=False)
    qid = q.add(account, provider, to, subject, body, created_by="ai")
    return json.dumps({"status": "queued", "queue_id": qid,
                        "message": "Email added to outbox. The user will review and send it."}, ensure_ascii=False)


async def reply_email(msg_id: str, body: str) -> str:
    """Reply to a received email. Composes a reply and adds it to the outbox queue.
    The email is NOT sent until the user reviews and approves it.
    Args:
        msg_id: ID of the original message to reply to
        body: your reply text (without quoting, quoting is added automatically)
    Returns JSON with queue status.
    """
    q = _get_queue()
    original = q.get_message(msg_id)
    if not original:
        return json.dumps({"status": "error", "message": f"Message {msg_id} not found in local archive"}, ensure_ascii=False)

    account = original.get("account", "")
    provider = original.get("source", "gmail")
    from_addr = original.get("from", "")
    subject = original.get("subject", "")
    original_body = original.get("body", "")
    in_reply_to = original.get("message_id", "")
    references = original.get("references", "")

    reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    quoted = "\n".join(f"> {line}" for line in original_body.split("\n"))
    full_body = f"{body}\n\n{quoted}"

    qid = q.add(account, provider, from_addr, reply_subject, full_body,
                in_reply_to=in_reply_to, references=references, created_by="ai")
    return json.dumps({"status": "queued", "queue_id": qid,
                        "message": "Reply added to outbox. The user will review and send it."}, ensure_ascii=False)


async def forward_email(msg_id: str, to: str) -> str:
    """Forward a received email to another recipient.
    The email is NOT sent until the user reviews and approves it.
    Args:
        msg_id: ID of the original message to forward
        to: recipient email address
    Returns JSON with queue status.
    """
    q = _get_queue()
    original = q.get_message(msg_id)
    if not original:
        return json.dumps({"status": "error", "message": f"Message {msg_id} not found in local archive"}, ensure_ascii=False)

    account = original.get("account", "")
    provider = original.get("source", "gmail")
    subject = original.get("subject", "")
    original_body = original.get("body", "")
    from_addr = original.get("from", "")

    fwd_subject = subject if subject.lower().startswith("fwd:") else f"Fwd: {subject}"
    fwd_body = f"Forwarded message from {from_addr}:\n\n{original_body}"

    qid = q.add(account, provider, to, fwd_subject, fwd_body, created_by="ai")
    return json.dumps({"status": "queued", "queue_id": qid,
                        "message": "Forward added to outbox. The user will review and send it."}, ensure_ascii=False)


async def search_emails(keywords: str) -> str:
    """Search the local email archive by keywords.
    Args:
        keywords: space-separated search terms
    Returns JSON with matching emails sorted by date (newest first).
    """
    q = _get_queue()
    matches = q.search_emails(keywords)
    if not matches:
        return json.dumps({"results": [], "message": f"No emails matching '{keywords}' found"}, ensure_ascii=False)
    results = []
    for m in matches[:50]:
        results.append({
            "id": m.get("id", ""),
            "from": m.get("from", ""),
            "subject": m.get("subject", ""),
            "date": m.get("sent_date", ""),
            "snippet": m.get("snippet", ""),
            "account": m.get("account", ""),
        })
    return json.dumps({"results": results}, ensure_ascii=False)


async def search_contacts(keywords: str) -> str:
    """Search email contacts by name or email address using fuzzy matching.
    Use to find recipient email addresses before composing an email.
    Args:
        keywords: space-separated search terms (name fragments, email parts)
    Returns JSON with matching contacts sorted by relevance.
    """
    q = _get_queue()
    from mail.contacts import search
    matches = search(keywords, threshold=0.55, max_results=15)
    if not matches:
        return json.dumps({"results": [], "message": f"No contacts matching '{keywords}'"}, ensure_ascii=False)
    results = [{"email": c["email"], "display_name": c["display_name"]} for c in matches]
    return json.dumps({"results": results}, ensure_ascii=False)
