import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Optional

DB_PATH = Path(__file__).parent / "chat_history.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_history (
                user_email TEXT NOT NULL,
                auth_expires_at REAL NOT NULL,
                agent_id TEXT NOT NULL,
                backend_session_id TEXT NOT NULL,
                messages_json TEXT NOT NULL DEFAULT '[]',
                updated_at REAL NOT NULL,
                PRIMARY KEY (user_email, auth_expires_at, agent_id)
            )
            """
        )
        conn.commit()


def purge_expired_chat_history() -> None:
    init_db()
    now = time.time()
    with _connect() as conn:
        conn.execute("DELETE FROM chat_history WHERE auth_expires_at < ?", (now,))
        conn.commit()


def get_chat_history(
    user_email: str,
    auth_expires_at: float,
    agent_id: str,
) -> dict[str, Any]:
    init_db()
    purge_expired_chat_history()

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT backend_session_id, messages_json
            FROM chat_history
            WHERE user_email = ? AND auth_expires_at = ? AND agent_id = ?
            """,
            (user_email, float(auth_expires_at), agent_id),
        ).fetchone()

    if not row:
        return {
            "messages": [],
            "backend_session_id": str(uuid.uuid4()),
        }

    try:
        messages = json.loads(row["messages_json"])
    except json.JSONDecodeError:
        messages = []

    if not isinstance(messages, list):
        messages = []

    return {
        "messages": messages,
        "backend_session_id": row["backend_session_id"],
    }


def save_chat_history(
    user_email: str,
    auth_expires_at: float,
    agent_id: str,
    messages: list[dict[str, Any]],
    backend_session_id: str,
) -> None:
    init_db()
    now = time.time()
    stored_messages = [
        {
            **message,
            "animate": False,
            "typewriter": False,
        }
        for message in messages
    ]

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO chat_history (
                user_email,
                auth_expires_at,
                agent_id,
                backend_session_id,
                messages_json,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_email, auth_expires_at, agent_id) DO UPDATE SET
                backend_session_id = excluded.backend_session_id,
                messages_json = excluded.messages_json,
                updated_at = excluded.updated_at
            """,
            (
                user_email,
                float(auth_expires_at),
                agent_id,
                backend_session_id,
                json.dumps(stored_messages),
                now,
            ),
        )
        conn.commit()


def clear_chat_history_for_session(
    user_email: Optional[str],
    auth_expires_at: Optional[float],
) -> None:
    if not user_email or auth_expires_at is None:
        return

    init_db()
    with _connect() as conn:
        conn.execute(
            """
            DELETE FROM chat_history
            WHERE user_email = ? AND auth_expires_at = ?
            """,
            (user_email, float(auth_expires_at)),
        )
        conn.commit()
