import base64
import json
import logging
import os
import time
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
SESSION_FILE = Path(__file__).parent / ".auth_session.json"


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


def _session_payload(
    user_email: Optional[str] = None,
    user_oid: Optional[str] = None,
    access_token: Optional[str] = None,
    token_expires_on: Optional[float] = None,
) -> dict:
    now = time.time()
    payload: dict[str, Any] = {
        "authenticated_at": now,
        "expires_at": now + (SESSION_DAYS * 24 * 60 * 60),
    }
    if user_email:
        payload["user_email"] = user_email
    if user_oid:
        payload["user_oid"] = user_oid
    if access_token:
        payload["access_token"] = access_token
    if token_expires_on:
        payload["token_expires_on"] = token_expires_on
    return payload


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


def save_session(
    user_email: Optional[str] = None,
    user_oid: Optional[str] = None,
    access_token: Optional[str] = None,
    token_expires_on: Optional[float] = None,
) -> dict:
    payload = _session_payload(
        user_email=user_email,
        user_oid=user_oid,
        access_token=access_token,
        token_expires_on=token_expires_on,
    )
    SESSION_FILE.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def clear_session() -> None:
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


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


def _acquire_delegated_fabric_token() -> StoredAccessToken:
    if not is_session_valid():
        raise PermissionError("Microsoft login required. Please sign in again.")

    session = read_session() or {}
    access_token = session.get("access_token")
    token_expires_on = float(session.get("token_expires_on", 0))

    if not access_token or time.time() >= token_expires_on - 60:
        raise PermissionError("Microsoft login required. Please sign in again.")

    return StoredAccessToken(access_token, token_expires_on)


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
        "user_email": session.get("user_email"),
        "fabric_token_mode": get_active_fabric_token_mode(),
    }


def login_with_access_token(access_token: str, token_expires_on: Optional[float] = None) -> dict:
    user_email = _email_from_token(access_token)
    if not user_email:
        raise ValueError("Could not read user details from Microsoft token.")

    user_oid = _user_oid_from_token(access_token)
    expires_on = token_expires_on or _expires_on_from_token(access_token)
    if not expires_on or time.time() >= expires_on:
        raise ValueError("Microsoft token is expired. Please sign in again.")

    session = save_session(
        user_email=user_email,
        user_oid=user_oid,
        access_token=access_token,
        token_expires_on=expires_on,
    )
    return {
        "authenticated": True,
        "expires_at": session["expires_at"],
        "token_expires_at": expires_on,
        "session_days": SESSION_DAYS,
        "user_email": user_email,
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


def login_with_auth_code(code: str, redirect_uri: str, code_verifier: str) -> dict:
    token_payload = exchange_auth_code(code, redirect_uri, code_verifier)
    access_token = token_payload.get("access_token")
    if not access_token:
        raise ValueError("Microsoft login did not return an access token.")

    expires_in = int(token_payload.get("expires_in", 3600))
    expires_on = time.time() + expires_in
    return login_with_access_token(access_token, expires_on)


def acquire_fabric_token() -> StoredAccessToken:
    global _active_fabric_token_mode

    # Web sign-in must drive Fabric calls. Mixing az-login / service-principal tokens
    # with a user's browser token causes Fabric "User ID's don't match" (403) errors.
    if is_session_valid():
        session = read_session() or {}
        if session.get("access_token"):
            _active_fabric_token_mode = "delegated"
            return _acquire_delegated_fabric_token()

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
            token = _acquire_delegated_fabric_token()
            _active_fabric_token_mode = "delegated"
            return token

    if FABRIC_TOKEN_MODE == "delegated":
        _active_fabric_token_mode = "delegated"
        return _acquire_delegated_fabric_token()

    _active_fabric_token_mode = "delegated"
    return _acquire_delegated_fabric_token()


def get_authenticated_session() -> Optional[dict]:
    session = read_session()
    if not is_session_valid():
        return None
    return {
        "user_email": session.get("user_email"),
        "user_oid": session.get("user_oid"),
        "expires_at": session.get("expires_at"),
    }


def logout() -> dict:
    clear_session()
    clear_fabric_token_caches()
    return {"authenticated": False}
