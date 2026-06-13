"""Shared Google OAuth2 credential loader with auto-refresh and keyring persistence."""
import json
import time as _time

_last_refresh = 0
_REFRESH_INTERVAL = 300


def get_google_credentials():
    global _last_refresh
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
        if creds.refresh_token and _time.time() - _last_refresh > _REFRESH_INTERVAL:
            import google.auth.transport.requests
            request = google.auth.transport.requests.Request()
            creds.refresh(request)
            _last_refresh = _time.time()
            try:
                import keyring as kr
                kr.set_password("vass", "google_token", creds.to_json())
            except Exception:
                pass
        return creds
    except Exception as e:
        print(f"[GoogleAuth] Error: {e}")
        return None


def check_google_auth():
    creds = get_google_credentials()
    if not creds:
        return False, "Credentials missing"
    try:
        from googleapiclient.discovery import build
        svc = build("calendar", "v3", credentials=creds)
        svc.events().list(calendarId="primary", maxResults=1).execute()
        return True, ""
    except Exception as e:
        return False, str(e)
