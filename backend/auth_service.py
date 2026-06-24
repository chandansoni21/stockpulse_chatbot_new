import base64
import json
import logging
import os
import time
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

AZURE_AUTHORITY = os.getenv("AZURE_AUTHORITY", "common")
CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "04b07795-8ddb-461a-bbee-02f9e1bf7b46")
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"


def _service_principal_credentials() -> tuple[Optional[str], Optional[str], Optional[str]]:
    tenant = os.getenv("FABRIC_SP_TENANT_ID") or os.getenv("TENANT_ID")
    if tenant in ("common", "organizations", "consumers", None, ""):
        tenant = os.getenv("TENANT_ID")
    client_id = os.getenv("FABRIC_SP_CLIENT_ID") or os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("FABRIC_SP_CLIENT_SECRET") or os.getenv("AZURE_CLIENT_SECRET")
    return tenant, client_id, client_secret


def _resolve_fabric_token_mode() -> str:
    explicit = os.getenv("FABRIC_TOKEN_MODE", "").strip().lower()
    if explicit:
        return explicit
    tenant, client_id, client_secret = _service_principal_credentials()
    if tenant and client_id and client_secret:
        return "service_principal"
    return "default_credential"


FABRIC_TOKEN_MODE = _resolve_fabric_token_mode()
SESSION_DAYS = int(os.getenv("AUTH_SESSION_DAYS", "7"))
SESSIONS_FILE = Path(__file__).parent / ".auth_sessions.json"
LEGACY_SESSION_FILE = Path(__file__).parent / ".auth_session.json"

current_auth_session_id: ContextVar[Optional[str]] = ContextVar("current_auth_session_id", default=None)


def set_request_session_id(session_id: Optional[str]):
    return current_auth_session_id.set(session_id)


def reset_request_session_id(token) -> None:
    current_auth_session_id.reset(token)


def get_request_session_id() -> Optional[str]:
    return current_auth_session_id.get()


def create_auth_session_id() -> str:
    return str(uuid.uuid4())


class StoredAccessToken:
    def __init__(self, token: str, expires_on: float):
        self.token = token
        self.expires_on = expires_on


_service_principal_token: Optional[StoredAccessToken] = None
_default_credential_token: Optional[StoredAccessToken] = None
_active_fabric_token_mode: str = FABRIC_TOKEN_MODE


def _decode_token_claims(token_str: str) -> Optional[dict]:
    try:
        payload = token_str.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, json.JSONDecodeError, ValueError, TypeError):
        return None


def _email_from_token(token_str: str) -> Optional[str]:
    claims = _decode_token_claims(token_str)
    if not claims:
        return None

    emails = claims.get("emails")
    if isinstance(emails, list) and emails:
        return str(emails[0]).strip().lower()

    for key in ("preferred_username", "upn", "email", "unique_name"):
        value = claims.get(key)
        if value:
            return str(value).strip().lower()

    return None


def _user_oid_from_token(token_str: str) -> Optional[str]:
    claims = _decode_token_claims(token_str)
    if not claims:
        return None
    oid = claims.get("oid") or claims.get("sub")
    return str(oid) if oid else None


def _expires_on_from_token(token_str: str) -> Optional[float]:
    claims = _decode_token_claims(token_str)
    if not claims:
        return None
    exp = claims.get("exp")
    return float(exp) if exp is not None else None


def _tenant_from_token(token_str: str) -> Optional[str]:
    claims = _decode_token_claims(token_str)
    if not claims:
        return None
    tenant = claims.get("tid")
    return str(tenant) if tenant else None


def _session_payload(
    user_email: Optional[str] = None,
    user_oid: Optional[str] = None,
    access_token: Optional[str] = None,
    token_expires_on: Optional[float] = None,
    refresh_token: Optional[str] = None,
    tenant_id: Optional[str] = None,
    expires_at: Optional[float] = None,
    authenticated_at: Optional[float] = None,
) -> dict:
    now = time.time()
    payload: dict[str, Any] = {
        "authenticated_at": authenticated_at if authenticated_at is not None else now,
        "expires_at": expires_at if expires_at is not None else now + (SESSION_DAYS * 24 * 60 * 60),
    }
    if user_email:
        payload["user_email"] = user_email
    if user_oid:
        payload["user_oid"] = user_oid
    if tenant_id:
        payload["tenant_id"] = tenant_id
    if access_token:
        payload["access_token"] = access_token
    if token_expires_on:
        payload["token_expires_on"] = token_expires_on
    if refresh_token:
        payload["refresh_token"] = refresh_token
    return payload


def _read_all_sessions() -> dict[str, dict]:
    if SESSIONS_FILE.exists():
        try:
            payload = json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _write_all_sessions(sessions: dict[str, dict]) -> None:
    SESSIONS_FILE.write_text(json.dumps(sessions), encoding="utf-8")


def _purge_expired_sessions(sessions: dict[str, dict]) -> dict[str, dict]:
    now = time.time()
    active = {
        session_id: session
        for session_id, session in sessions.items()
        if now < float(session.get("expires_at", 0))
    }
    if len(active) != len(sessions):
        _write_all_sessions(active)
    return active


def read_session(session_id: Optional[str] = None) -> Optional[dict]:
    resolved_id = session_id or get_request_session_id()
    if not resolved_id:
        return None

    sessions = _purge_expired_sessions(_read_all_sessions())
    return sessions.get(resolved_id)


def is_session_valid(session_id: Optional[str] = None) -> bool:
    session = read_session(session_id)
    if not session:
        return False
    return time.time() < float(session.get("expires_at", 0))


def save_session(
    session_id: str,
    user_email: Optional[str] = None,
    user_oid: Optional[str] = None,
    access_token: Optional[str] = None,
    token_expires_on: Optional[float] = None,
    refresh_token: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> dict:
    existing = read_session(session_id) or {}
    payload = _session_payload(
        user_email=user_email or existing.get("user_email"),
        user_oid=user_oid or existing.get("user_oid"),
        tenant_id=tenant_id or existing.get("tenant_id"),
        access_token=access_token or existing.get("access_token"),
        token_expires_on=token_expires_on or existing.get("token_expires_on"),
        refresh_token=refresh_token or existing.get("refresh_token"),
        expires_at=existing.get("expires_at"),
        authenticated_at=existing.get("authenticated_at"),
    )
    sessions = _purge_expired_sessions(_read_all_sessions())
    sessions[session_id] = payload
    _write_all_sessions(sessions)
    return payload


def update_session_tokens(
    session_id: str,
    access_token: str,
    token_expires_on: float,
    refresh_token: Optional[str] = None,
) -> dict:
    sessions = _purge_expired_sessions(_read_all_sessions())
    session = sessions.get(session_id)
    if not session:
        raise PermissionError("Microsoft login required. Please sign in again.")

    session["access_token"] = access_token
    session["token_expires_on"] = token_expires_on
    if refresh_token:
        session["refresh_token"] = refresh_token

    sessions[session_id] = session
    _write_all_sessions(sessions)
    return session


def clear_session(session_id: Optional[str] = None) -> None:
    resolved_id = session_id or get_request_session_id()
    if not resolved_id:
        return

    sessions = _read_all_sessions()
    if resolved_id not in sessions:
        return

    sessions.pop(resolved_id, None)
    _write_all_sessions(sessions)


def clear_service_principal_token() -> None:
    global _service_principal_token
    _service_principal_token = None


def clear_default_credential_token() -> None:
    global _default_credential_token
    _default_credential_token = None


def clear_fabric_token_caches() -> None:
    clear_service_principal_token()
    clear_default_credential_token()


def get_active_fabric_token_mode() -> str:
    return _active_fabric_token_mode


def _acquire_service_principal_fabric_token() -> StoredAccessToken:
    global _service_principal_token

    now = time.time()
    if _service_principal_token and _service_principal_token.expires_on > (now + 60):
        return _service_principal_token

    tenant, client_id, client_secret = _service_principal_credentials()
    if not tenant or not client_id or not client_secret:
        raise PermissionError(
            "Fabric service principal is not configured. "
            "Add FABRIC_SP_CLIENT_ID, FABRIC_SP_CLIENT_SECRET, and TENANT_ID to backend/.env"
        )

    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    response = requests.post(
        token_url,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": FABRIC_SCOPE,
            "grant_type": "client_credentials",
        },
        timeout=30,
    )
    payload = response.json()
    if response.status_code >= 400:
        error = payload.get("error_description") or payload.get("error") or "Fabric service principal login failed."
        raise PermissionError(error)

    access_token = payload.get("access_token")
    if not access_token:
        raise PermissionError("Fabric service principal login did not return an access token.")

    expires_in = int(payload.get("expires_in", 3600))
    _service_principal_token = StoredAccessToken(access_token, now + expires_in)
    return _service_principal_token


def _acquire_default_credential_fabric_token() -> StoredAccessToken:
    global _default_credential_token

    now = time.time()
    if _default_credential_token and _default_credential_token.expires_on > (now + 60):
        return _default_credential_token

    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential(
        exclude_interactive_browser_credential=True,
        exclude_powershell_credential=False,
        exclude_shared_token_cache_credential=False,
    )
    token = credential.get_token(FABRIC_SCOPE)
    _default_credential_token = StoredAccessToken(token.token, float(token.expires_on))
    return _default_credential_token


def _access_token_valid(session: dict) -> bool:
    access_token = session.get("access_token")
    token_expires_on = float(session.get("token_expires_on", 0))
    return bool(access_token) and time.time() < token_expires_on - 60


def _token_endpoint(session: dict) -> str:
    tenant = session.get("tenant_id") or AZURE_AUTHORITY
    return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"


def _refresh_delegated_access_token(session_id: str) -> None:
    session = read_session(session_id) or {}
    refresh_token = session.get("refresh_token")
    if not refresh_token:
        logger.warning("Session %s has no refresh token; user must sign in again.", session_id[:8])
        raise PermissionError("Microsoft login required. Please sign in again.")

    token_urls = [_token_endpoint(session)]
    fallback_url = f"https://login.microsoftonline.com/{AZURE_AUTHORITY}/oauth2/v2.0/token"
    if fallback_url not in token_urls:
        token_urls.append(fallback_url)

    last_error = "Microsoft token refresh failed."
    for token_url in token_urls:
        response = requests.post(
            token_url,
            data={
                "client_id": CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": f"{FABRIC_SCOPE} openid profile offline_access",
            },
            timeout=30,
        )
        payload = response.json()
        if response.status_code < 400 and payload.get("access_token"):
            expires_in = int(payload.get("expires_in", 3600))
            expires_on = time.time() + expires_in
            update_session_tokens(
                session_id,
                access_token=payload["access_token"],
                token_expires_on=expires_on,
                refresh_token=payload.get("refresh_token") or refresh_token,
            )
            logger.info("Refreshed Microsoft access token for session %s", session_id[:8])
            return

        last_error = payload.get("error_description") or payload.get("error") or last_error
        logger.warning("Token refresh failed for session %s via %s: %s", session_id[:8], token_url, last_error)

    raise PermissionError(last_error)


def _ensure_delegated_access_token(session_id: str) -> dict:
    session = read_session(session_id) or {}
    if _access_token_valid(session):
        return session

    _refresh_delegated_access_token(session_id)
    refreshed = read_session(session_id) or {}
    if not _access_token_valid(refreshed):
        raise PermissionError("Microsoft login required. Please sign in again.")
    return refreshed


def _acquire_delegated_fabric_token(session_id: Optional[str] = None) -> StoredAccessToken:
    resolved_id = session_id or get_request_session_id()
    if not is_session_valid(resolved_id):
        raise PermissionError("Microsoft login required. Please sign in again.")

    session = _ensure_delegated_access_token(resolved_id)
    access_token = session.get("access_token")
    token_expires_on = float(session.get("token_expires_on", 0))
    return StoredAccessToken(access_token, token_expires_on)


def get_auth_status(session_id: Optional[str] = None) -> dict:
    resolved_id = session_id or get_request_session_id()
    if not resolved_id:
        return {
            "authenticated": False,
            "expires_at": None,
            "session_days": SESSION_DAYS,
        }

    session = read_session(resolved_id)
    if not is_session_valid(resolved_id) or not session:
        return {
            "authenticated": False,
            "expires_at": None,
            "session_days": SESSION_DAYS,
        }

    if not _access_token_valid(session):
        if not session.get("refresh_token"):
            return {
                "authenticated": False,
                "expires_at": None,
                "session_days": SESSION_DAYS,
            }
        try:
            _refresh_delegated_access_token(resolved_id)
            session = read_session(resolved_id) or {}
        except PermissionError:
            return {
                "authenticated": False,
                "expires_at": None,
                "session_days": SESSION_DAYS,
            }

    return {
        "authenticated": True,
        "expires_at": session.get("expires_at"),
        "session_days": SESSION_DAYS,
        "user_email": session.get("user_email"),
        "session_id": resolved_id,
        "fabric_token_mode": get_active_fabric_token_mode(),
    }


def login_with_access_token(
    access_token: str,
    token_expires_on: Optional[float] = None,
    session_id: Optional[str] = None,
    refresh_token: Optional[str] = None,
) -> dict:
    user_email = _email_from_token(access_token)
    if not user_email:
        raise ValueError("Could not read user details from Microsoft token.")

    user_oid = _user_oid_from_token(access_token)
    tenant_id = _tenant_from_token(access_token)
    expires_on = token_expires_on or _expires_on_from_token(access_token)
    if not expires_on or time.time() >= expires_on:
        raise ValueError("Microsoft token is expired. Please sign in again.")

    resolved_id = session_id or create_auth_session_id()
    session = save_session(
        resolved_id,
        user_email=user_email,
        user_oid=user_oid,
        access_token=access_token,
        token_expires_on=expires_on,
        refresh_token=refresh_token,
        tenant_id=tenant_id,
    )
    if not refresh_token:
        logger.warning(
            "Login for %s did not receive a refresh token. Session will expire when the access token does (~1 hour). "
            "Register your own Azure app with offline_access, or verify AZURE_CLIENT_ID.",
            user_email,
        )
    return {
        "authenticated": True,
        "expires_at": session["expires_at"],
        "token_expires_at": expires_on,
        "session_days": SESSION_DAYS,
        "user_email": user_email,
        "user_oid": user_oid,
        "session_id": resolved_id,
        "refresh_available": bool(refresh_token),
        "fabric_token_mode": get_active_fabric_token_mode(),
    }


def exchange_auth_code(code: str, redirect_uri: str, code_verifier: str) -> dict[str, Any]:
    token_url = f"https://login.microsoftonline.com/{AZURE_AUTHORITY}/oauth2/v2.0/token"
    response = requests.post(
        token_url,
        data={
            "client_id": CLIENT_ID,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
            "scope": f"{FABRIC_SCOPE} openid profile offline_access",
        },
        timeout=30,
    )
    payload = response.json()
    if response.status_code >= 400:
        error = payload.get("error_description") or payload.get("error") or "Microsoft token exchange failed."
        raise ValueError(error)
    return payload


def login_with_auth_code(
    code: str,
    redirect_uri: str,
    code_verifier: str,
    session_id: Optional[str] = None,
) -> dict:
    token_payload = exchange_auth_code(code, redirect_uri, code_verifier)
    access_token = token_payload.get("access_token")
    if not access_token:
        raise ValueError("Microsoft login did not return an access token.")

    expires_in = int(token_payload.get("expires_in", 3600))
    expires_on = time.time() + expires_in
    return login_with_access_token(
        access_token,
        expires_on,
        session_id=session_id,
        refresh_token=token_payload.get("refresh_token"),
    )


def acquire_fabric_token(session_id: Optional[str] = None) -> StoredAccessToken:
    global _active_fabric_token_mode

    resolved_id = session_id or get_request_session_id()

    # Web sign-in must drive Fabric calls. Mixing az-login / service-principal tokens
    # with a user's browser token causes Fabric "User ID's don't match" (403) errors.
    if is_session_valid(resolved_id):
        session = read_session(resolved_id) or {}
        if session.get("access_token"):
            _active_fabric_token_mode = "delegated"
            return _acquire_delegated_fabric_token(resolved_id)

    if FABRIC_TOKEN_MODE == "service_principal":
        _active_fabric_token_mode = "service_principal"
        return _acquire_service_principal_fabric_token()

    if FABRIC_TOKEN_MODE == "default_credential":
        try:
            token = _acquire_default_credential_fabric_token()
            _active_fabric_token_mode = "default_credential"
            return token
        except Exception as exc:
            logger.warning("Shared Fabric credential unavailable, using signed-in user token: %s", exc)
            token = _acquire_delegated_fabric_token(resolved_id)
            _active_fabric_token_mode = "delegated"
            return token

    if FABRIC_TOKEN_MODE == "delegated":
        _active_fabric_token_mode = "delegated"
        return _acquire_delegated_fabric_token(resolved_id)

    _active_fabric_token_mode = "delegated"
    return _acquire_delegated_fabric_token(resolved_id)


def get_authenticated_session(session_id: Optional[str] = None) -> Optional[dict]:
    resolved_id = session_id or get_request_session_id()
    if not is_session_valid(resolved_id):
        return None

    try:
        session = _ensure_delegated_access_token(resolved_id)
    except PermissionError:
        return None

    return {
        "user_email": session.get("user_email"),
        "user_oid": session.get("user_oid"),
        "expires_at": session.get("expires_at"),
        "session_id": resolved_id,
    }


def logout(session_id: Optional[str] = None) -> dict:
    clear_session(session_id)
    clear_fabric_token_caches()
    return {"authenticated": False}
