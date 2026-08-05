"""Email contacts manager — encrypted list of contacts with email + display name."""
import json
import os
import re
from difflib import SequenceMatcher
from utils import get_project_root, encrypt_fields, _get_fernet

CONTACTS_PATH = os.path.join(get_project_root(), "Allowed_root", "private_mail_contacts.json")


def _load():
    try:
        with open(CONTACTS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"version": 1, "contacts": []}


def _save(data):
    os.makedirs(os.path.dirname(CONTACTS_PATH), exist_ok=True)
    with open(CONTACTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _decrypt(entry, f):
    if isinstance(entry, str) and entry.startswith("gAAAAA") and f:
        try:
            return f.decrypt(entry.encode()).decode()
        except Exception:
            return entry
    return entry


def add(email_address, display_name=""):
    """Add a contact. Deduplicates by email address."""
    if not email_address or email_address == "?":
        return
    data = _load()
    f = _get_fernet()

    # Check if email already exists — handle both old format (plain string) and new (dict)
    for i, entry in enumerate(data.get("contacts", [])):
        stored_email = _decrypt(entry, f) if isinstance(entry, str) else _decrypt(entry.get("email", ""), f)
        if stored_email.lower() == email_address.lower():
            stored_name = "" if isinstance(entry, str) else _decrypt(entry.get("display_name", ""), f)
            if display_name and (not stored_name or len(display_name) > len(stored_name)):
                encrypted = encrypt_fields(
                    {"email": email_address, "display_name": display_name},
                    keep_plain=set())
                data["contacts"][i] = encrypted
                _save(data)
            return

    encrypted = encrypt_fields(
        {"email": email_address, "display_name": display_name or ""}, keep_plain=set())
    data["contacts"].append(encrypted)
    _save(data)


def get_all():
    """Return all contacts as list of {email, display_name} dicts, sorted by display_name."""
    f = _get_fernet()
    data = _load()
    results = []
    for entry in data.get("contacts", []):
        if isinstance(entry, str):
            email_addr = _decrypt(entry, f)
            results.append({"email": email_addr, "display_name": email_addr})
        else:
            email_addr = _decrypt(entry.get("email", ""), f)
            display = _decrypt(entry.get("display_name", ""), f)
            if email_addr:
                results.append({"email": email_addr, "display_name": display or email_addr})
    results.sort(key=lambda c: c["display_name"].lower())
    return results


def as_strings():
    """Return contacts as strings for QComboBox: 'Display Name <email>' or just email."""
    return [c["email"] if not c["display_name"] else f"{c['display_name']} <{c['email']}>"
            for c in get_all()]


def search(keywords, threshold=0.60, max_results=20):
    """Fuzzy search contacts by keywords. Returns sorted by match score (highest first).
    threshold: minimum SequenceMatcher ratio (0.0-1.0). Higher = stricter matching.
    """
    terms = keywords.lower().split()
    all_contacts = get_all()
    scored = []

    for c in all_contacts:
        text = (c["display_name"] + " " + c["email"]).lower()
        # Score each term against the contact text
        best_score = 0.0
        for term in terms:
            # Exact substring match gives 1.0
            if term in text:
                best_score = max(best_score, 1.0)
            else:
                # Fuzzy match via SequenceMatcher
                for i in range(len(text) - min(3, len(term)) + 1):
                    window = text[i:i + len(term) + 5]
                    ratio = SequenceMatcher(None, term, window).ratio()
                    best_score = max(best_score, ratio)
        if best_score >= threshold:
            scored.append((best_score, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:max_results]]


def add_from_message(msg):
    """Extract and add both email and display name from an incoming message's 'from' field."""
    from_addr = msg.get("from", "")
    if not from_addr or from_addr == "?":
        return
    # Extract "Name <email>" format
    match = re.match(r'"?([^"]*)"?\s*<([^>]+)>', from_addr)
    if match:
        display_name = match.group(1).strip()
        email_addr = match.group(2).strip()
        add(email_addr, display_name)
    else:
        # Just an email, no display name
        add(from_addr.strip())
