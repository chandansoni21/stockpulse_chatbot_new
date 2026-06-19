import json
import os
import time
from pathlib import Path
from typing import Optional

from azure.identity import InteractiveBrowserCredential, TokenCachePersistenceOptions

TENANT_ID = os.getenv("TENANT_ID", "aca0b239-69e9-4246-87ba-8e07ad0a9249")
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
SESSION_DAYS = int(os.getenv("AUTH_SESSION_DAYS", "7"))
SESSION_FILE = Path(__file__).parent / ".auth_session.json"
CACHE_NAME = "fabric-stock-pulse-msal-cache"

_credential: Optional[InteractiveBrowserCredential] = None


def _session_payload() -> dict:
    now = time.time()
    return {
        "authenticated_at": now,
        "expires_at": now + (SESSION_DAYS * 24 * 60 * 60),
    }


def get_credential() -> InteractiveBrowserCredential:
    global _credential
    if _credential is None:
        _credential = InteractiveBrowserCredential(
            tenant_id=TENANT_ID,
            cache_persistence_options=TokenCachePersistenceOptions(name=CACHE_NAME),
        )
    return _credential


def read_session() -> Optional[dict]:
    if not SESSION_FILE.exists():
        return None
    try:
        return json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def is_session_valid() -> bool:
    session = read_session()
    if not session:
        return False
    return time.time() < float(session.get("expires_at", 0))


def save_session() -> dict:
    payload = _session_payload()
    SESSION_FILE.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def clear_session() -> None:
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


def try_acquire_token_silent() -> bool:
    if not is_session_valid():
        return False
    try:
        get_credential().get_token(FABRIC_SCOPE)
        return True
    except Exception:
        return False


def get_auth_status() -> dict:
    session = read_session()
    if not is_session_valid():
        return {
            "authenticated": False,
            "expires_at": None,
            "session_days": SESSION_DAYS,
        }

    return {
        "authenticated": True,
        "expires_at": session.get("expires_at"),
        "session_days": SESSION_DAYS,
    }


def acquire_fabric_token():
    if not is_session_valid():
        raise PermissionError("Microsoft login required. Please sign in again.")
    return get_credential().get_token(FABRIC_SCOPE)


def login_interactive() -> dict:
    token = get_credential().get_token(FABRIC_SCOPE)
    session = save_session()
    return {
        "authenticated": True,
        "expires_at": session["expires_at"],
        "token_expires_at": token.expires_on,
        "session_days": SESSION_DAYS,
    }


def logout() -> dict:
    clear_session()
    return {"authenticated": False}
