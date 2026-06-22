import base64
import json
import os
import time
from pathlib import Path
from typing import Any, Optional

import os
import time
from pathlib import Path
from typing import Any, Optional

import requests

TENANT_ID = os.getenv("TENANT_ID", "aca0b239-69e9-4246-87ba-8e07ad0a9249")
CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "04b07795-8ddb-461a-bbee-02f9e1bf7b46")
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
SESSION_DAYS = int(os.getenv("AUTH_SESSION_DAYS", "7"))
SESSION_FILE = Path(__file__).parent / ".auth_session.json"


class StoredAccessToken:
    def __init__(self, token: str, expires_on: float):
        self.token = token
        self.expires_on = expires_on


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
    return (
        claims.get("preferred_username")
        or claims.get("upn")
        or claims.get("email")
        or claims.get("unique_name")
    )


def _expires_on_from_token(token_str: str) -> Optional[float]:
    claims = _decode_token_claims(token_str)
    if not claims:
        return None
    exp = claims.get("exp")
    return float(exp) if exp is not None else None


def _session_payload(
    user_email: Optional[str] = None,
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
    access_token: Optional[str] = None,
    token_expires_on: Optional[float] = None,
) -> dict:
    payload = _session_payload(
        user_email=user_email,
        access_token=access_token,
        token_expires_on=token_expires_on,
    )
    SESSION_FILE.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def clear_session() -> None:
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


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
    }


def login_with_access_token(access_token: str, token_expires_on: Optional[float] = None) -> dict:
    user_email = _email_from_token(access_token)
    if not user_email:
        raise ValueError("Could not read user details from Microsoft token.")

    expires_on = token_expires_on or _expires_on_from_token(access_token)
    if not expires_on or time.time() >= expires_on:
        raise ValueError("Microsoft token is expired. Please sign in again.")

    session = save_session(
        user_email=user_email,
        access_token=access_token,
        token_expires_on=expires_on,
    )
    return {
        "authenticated": True,
        "expires_at": session["expires_at"],
        "token_expires_at": expires_on,
        "session_days": SESSION_DAYS,
        "user_email": user_email,
    }


def exchange_auth_code(code: str, redirect_uri: str, code_verifier: str) -> dict[str, Any]:
    token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    response = requests.post(
        token_url,
        data={
            "client_id": CLIENT_ID,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
            "scope": FABRIC_SCOPE,
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
    if not is_session_valid():
        raise PermissionError("Microsoft login required. Please sign in again.")

    session = read_session() or {}
    access_token = session.get("access_token")
    token_expires_on = float(session.get("token_expires_on", 0))

    if not access_token or time.time() >= token_expires_on - 60:
        raise PermissionError("Microsoft login required. Please sign in again.")

    return StoredAccessToken(access_token, token_expires_on)


def get_authenticated_session() -> Optional[dict]:
    session = read_session()
    if not is_session_valid():
        return None
    return {
        "user_email": session.get("user_email"),
        "expires_at": session.get("expires_at"),
    }


def logout() -> dict:
    clear_session()
    return {"authenticated": False}
