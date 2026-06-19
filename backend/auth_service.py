import base64
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


def _email_from_token(token_str: str) -> Optional[str]:
    try:
        payload = token_str.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        return (
            claims.get("preferred_username")
            or claims.get("upn")
            or claims.get("email")
            or claims.get("unique_name")
        )
    except (IndexError, json.JSONDecodeError, ValueError, TypeError):
        return None


def _session_payload(user_email: Optional[str] = None) -> dict:
    now = time.time()
    payload = {
        "authenticated_at": now,
        "expires_at": now + (SESSION_DAYS * 24 * 60 * 60),
    }
    if user_email:
        payload["user_email"] = user_email
    return payload


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


def save_session(user_email: Optional[str] = None) -> dict:
    payload = _session_payload(user_email=user_email)
    SESSION_FILE.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def _resolve_user_email(session: dict) -> Optional[str]:
    email = session.get("user_email")
    if email:
        return email
    try:
        token = get_credential().get_token(FABRIC_SCOPE)
        email = _email_from_token(token.token)
        if email:
            session["user_email"] = email
            SESSION_FILE.write_text(json.dumps(session), encoding="utf-8")
        return email
    except Exception:
        return None


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
        "user_email": _resolve_user_email(session),
    }


def acquire_fabric_token():
    if not is_session_valid():
        raise PermissionError("Microsoft login required. Please sign in again.")
    return get_credential().get_token(FABRIC_SCOPE)


def login_interactive() -> dict:
    token = get_credential().get_token(FABRIC_SCOPE)
    user_email = _email_from_token(token.token)
    session = save_session(user_email=user_email)
    return {
        "authenticated": True,
        "expires_at": session["expires_at"],
        "token_expires_at": token.expires_on,
        "session_days": SESSION_DAYS,
        "user_email": user_email,
    }


def logout() -> dict:
    clear_session()
    return {"authenticated": False}
