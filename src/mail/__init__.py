import configparser
import os
import threading
import time

from utils import get_project_root
from activity_tracker import get_tracker

CONFIG_PATH = os.path.join(get_project_root(), "config", "mail.ini")
SEEN_OLD_PATH = os.path.join(get_project_root(), "Allowed_root", "gmail_seen.json")

_state = {"sources": [], "mtime": 0, "running": False}


def start(app):
    if os.path.exists(CONFIG_PATH):
        _start_loop(app)
        return

    if _migrate_from_settings(app):
        _start_loop(app)
        return

    t = threading.Thread(target=_watch_config, args=(app,), daemon=True)
    t.start()


def _watch_config(app):
    while app.running:
        if os.path.exists(CONFIG_PATH) and _load_sources():
            print("[Mail] Detected mail.ini, starting mail system")
            _start_loop(app)
            return
        time.sleep(10)


def _migrate_from_settings(app):
    gmail_enabled = getattr(app, 'settings', {}).get("gmail_enabled", "false")
    if gmail_enabled.lower() != "true":
        return False

    sync_minutes = getattr(app, 'settings', {}).get("gmail_sync_minutes", "5")
    max_results = getattr(app, 'settings', {}).get("gmail_max_results", "10")

    cfg = configparser.ConfigParser()
    cfg["sources"] = {"active": "primary@gmail.com"}
    cfg["primary@gmail.com"] = {
        "type": "gmail",
        "sync_minutes": str(sync_minutes),
        "max_results": str(max_results),
    }
    cfg["primary@gmail.com"]["note"] = "; Update with your real Gmail address"
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        cfg.write(f)
    print("[Mail] Migrated gmail settings from settings.ini to mail.ini")

    if os.path.exists(SEEN_OLD_PATH):
        _migrate_seen_file()
    return True


def _migrate_seen_file():
    import json
    from utils import _get_fernet
    f = _get_fernet()
    if not f:
        print("[Mail] Cannot migrate gmail_seen.json: no Fernet key")
        return
    try:
        with open(SEEN_OLD_PATH, encoding="utf-8") as fp:
            seen = json.load(fp)
    except Exception:
        return

    messages = []
    for entry in seen.get("seen", []):
        if isinstance(entry, dict):
            msg = {}
            for k, v in entry.items():
                try:
                    msg[k] = f.decrypt(v.encode()).decode()
                except Exception:
                    msg[k] = v
            msg["source"] = "gmail"
            msg["account"] = "primary@gmail.com"
            messages.append(msg)

    if messages:
        from mail.store import append_new
        append_new(messages, "gmail", "primary@gmail.com")
        backup_path = SEEN_OLD_PATH + ".bk"
        os.rename(SEEN_OLD_PATH, backup_path)
        print(f"[Mail] Migrated {len(messages)} seen emails to private_mail.json, backed up to {backup_path}")


def _load_sources():
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH, encoding="utf-8")
    active = [a.strip() for a in cfg.get("sources", "active", fallback="").split(",") if a.strip()]
    sources = []
    for account in active:
        if not cfg.has_section(account):
            continue
        stype = cfg.get(account, "type", fallback="")
        sync_minutes = cfg.getint(account, "sync_minutes", fallback=5)
        max_results = cfg.getint(account, "max_results", fallback=10)
        if stype == "gmail":
            from mail.gmail import GmailSource
            sources.append((GmailSource(account, max_results), sync_minutes))
        elif stype in ("imap", "pop"):
            from mail.imap import ImapSource
            host = cfg.get(account, "host", fallback="")
            port = cfg.getint(account, "port", fallback=993 if stype == "imap" else 995)
            ssl_mode = cfg.get(account, "ssl", fallback="ssl")
            auth_mode = cfg.get(account, "auth", fallback="login")
            username = cfg.get(account, "username", fallback=account)
            sources.append((ImapSource(account, username, host, port, ssl_mode, auth_mode, stype, max_results), sync_minutes))
    return sources


def _start_loop(app):
    if _state["running"]:
        return
    _state["sources"] = _load_sources()
    if not _state["sources"]:
        return
    _state["mtime"] = os.path.getmtime(CONFIG_PATH)
    _state["running"] = True
    t = threading.Thread(target=_sync_loop, args=(app,), daemon=True)
    t.start()


def _sync_loop(app):
    time.sleep(5)
    last_sync = {}
    for source, _ in _state["sources"]:
        try:
            _do_sync(app, source)
            last_sync[source.account] = time.time()
        except Exception:
            last_sync[source.account] = time.time()

    while app.running:
        if os.path.exists(CONFIG_PATH):
            cur_mtime = os.path.getmtime(CONFIG_PATH)
            if cur_mtime != _state["mtime"]:
                _state["sources"] = _load_sources()
                _state["mtime"] = cur_mtime
                last_sync = {s.account: last_sync.get(s.account, time.time())
                              for s, _ in _state["sources"]}
                print("[Mail] Reloaded configuration")

        for source, interval_min in _state["sources"]:
            elapsed = time.time() - last_sync.get(source.account, 0)
            if elapsed < interval_min * 60:
                continue
            try:
                _do_sync(app, source)
            except Exception:
                pass
            last_sync[source.account] = time.time()
        if not app.running:
            break
        _sleep_interval(app, 10)


def _do_sync(app, source):
    tracker = get_tracker()
    tracker.start("Gmail sync", "sync")
    try:
        new = source.check_new()
    except Exception as e:
        print(f"[Mail:{source.account}] check_new error: {e}")
        tracker.end("Gmail sync")
        return
    tracker.end("Gmail sync")

    if source.account == "primary@gmail.com" and source.name == "gmail":
        real = _resolve_gmail_account(source)
        if real and real != source.account:
            old = source.account
            _update_account(old, real)
            source._account = real
            from mail.store import fix_account
            fix_account(source.name, old, real)

    if not new:
        return
    from mail.store import append_new
    append_new(new, source.name, source.account)
    from mail.notifier import announce
    announce(new, app.tts, app.notification_manager, app.memory, app.language, source.name)


def _resolve_gmail_account(source):
    try:
        svc = source.service
        if not svc:
            return None
        profile = svc.users().getProfile(userId="me").execute()
        return profile.get("emailAddress")
    except Exception as e:
        print(f"[Mail:{source.account}] getProfile error: {e}")
        return None


def _update_account(old_account, new_account):
    import configparser
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH, encoding="utf-8")
    active = [a.strip() for a in cfg.get("sources", "active", fallback="").split(",") if a.strip()]
    active = [new_account if a == old_account else a for a in active]
    cfg["sources"]["active"] = ", ".join(active)
    items = dict(cfg[old_account])
    cfg.remove_section(old_account)
    cfg[new_account] = items
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        cfg.write(f)
    print(f"[Mail] Updated account: {old_account} -> {new_account}")


def _sleep_interval(app, total_seconds):
    step = min(10, total_seconds)
    slept = 0
    while slept < total_seconds and app.running:
        time.sleep(step)
        slept += step
