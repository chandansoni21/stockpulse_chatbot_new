import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Optional

DB_PATH = Path(__file__).parent / "chat_history.db"
HISTORY_RETENTION_DAYS = int(os.getenv("CHAT_HISTORY_RETENTION_DAYS", "90"))


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def _migrate_legacy_history(conn: sqlite3.Connection) -> None:
    columns = _table_columns(conn, "chat_history")
    if "auth_expires_at" not in columns:
        return

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_history_v2 (
            user_email TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            backend_session_id TEXT NOT NULL,
            messages_json TEXT NOT NULL DEFAULT '[]',
            updated_at REAL NOT NULL,
            PRIMARY KEY (user_email, agent_id)
        )
        """
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO chat_history_v2 (
            user_email,
            agent_id,
            backend_session_id,
            messages_json,
            updated_at
        )
        SELECT
            user_email,
            agent_id,
            backend_session_id,
            messages_json,
            updated_at
        FROM chat_history
        WHERE rowid IN (
            SELECT MAX(rowid)
            FROM chat_history
            GROUP BY user_email, agent_id
        )
        """
    )

    conn.execute("DROP TABLE chat_history")
    conn.execute("ALTER TABLE chat_history_v2 RENAME TO chat_history")


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_history (
                user_email TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                backend_session_id TEXT NOT NULL,
                messages_json TEXT NOT NULL DEFAULT '[]',
                updated_at REAL NOT NULL,
                PRIMARY KEY (user_email, agent_id)
            )
            """
        )
        _migrate_legacy_history(conn)
        conn.commit()


def purge_expired_chat_history() -> None:
    init_db()
    cutoff = time.time() - (HISTORY_RETENTION_DAYS * 24 * 60 * 60)
    with _connect() as conn:
        conn.execute("DELETE FROM chat_history WHERE updated_at < ?", (cutoff,))
        conn.commit()


def get_chat_history(user_email: str, agent_id: str) -> dict[str, Any]:
    init_db()
    purge_expired_chat_history()

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT backend_session_id, messages_json
            FROM chat_history
            WHERE user_email = ? AND agent_id = ?
            """,
            (user_email, agent_id),
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
            "suggestions": message.get("suggestions") or [],
        }
        for message in messages
    ]

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO chat_history (
                user_email,
                agent_id,
                backend_session_id,
                messages_json,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_email, agent_id) DO UPDATE SET
                backend_session_id = excluded.backend_session_id,
                messages_json = excluded.messages_json,
                updated_at = excluded.updated_at
            """,
            (
                user_email,
                agent_id,
                backend_session_id,
                json.dumps(stored_messages),
                now,
            ),
        )
        conn.commit()


def clear_chat_history_for_user(user_email: Optional[str]) -> None:
    if not user_email:
        return

    init_db()
    with _connect() as conn:
        conn.execute(
            "DELETE FROM chat_history WHERE user_email = ?",
            (user_email,),
        )
        conn.commit()
