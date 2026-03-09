import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

DB_PATH = Path("support.db")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                full_name TEXT,
                topic_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                first_message TEXT,
                created_at TEXT NOT NULL,
                closed_at TEXT,
                rating INTEGER,
                message_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS duty_staff (
                username TEXT PRIMARY KEY
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_ticket(
    user_id: int,
    username: Optional[str],
    full_name: Optional[str],
    topic_id: int,
    first_message: str,
) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tickets (user_id, username, full_name, topic_id, status, first_message, created_at, message_count)
            VALUES (?, ?, ?, ?, 'open', ?, ?, 1)
            """,
            (user_id, username, full_name, topic_id, first_message, _now()),
        )
        conn.commit()
        return cur.lastrowid


def increment_message_count(ticket_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE tickets SET message_count = message_count + 1 WHERE id = ?",
            (ticket_id,),
        )
        conn.commit()


def get_open_ticket_by_user(user_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM tickets WHERE user_id = ? AND status = 'open' ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        )
        return cur.fetchone()


def get_ticket_by_topic(topic_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM tickets WHERE topic_id = ? ORDER BY created_at DESC LIMIT 1",
            (topic_id,),
        )
        return cur.fetchone()


def close_ticket(ticket_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE tickets SET status = 'closed', closed_at = ? WHERE id = ?",
            (_now(), ticket_id),
        )
        conn.commit()


def set_rating(ticket_id: int, rating: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE tickets SET rating = ? WHERE id = ?",
            (rating, ticket_id),
        )
        conn.commit()


def get_ticket_by_id(ticket_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        return cur.fetchone()


def stats_summary() -> Dict[str, Any]:
    with get_conn() as conn:
        cur = conn.cursor()
        total = cur.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        open_cnt = cur.execute(
            "SELECT COUNT(*) FROM tickets WHERE status = 'open'"
        ).fetchone()[0]
        closed_cnt = cur.execute(
            "SELECT COUNT(*) FROM tickets WHERE status = 'closed'"
        ).fetchone()[0]
        avg_rating = cur.execute(
            "SELECT AVG(rating) FROM tickets WHERE rating IS NOT NULL"
        ).fetchone()[0]
        top_users = cur.execute(
            """
            SELECT user_id, COALESCE(username, '') AS username, COUNT(*) AS cnt
            FROM tickets
            GROUP BY user_id, username
            ORDER BY cnt DESC
            LIMIT 5
            """
        ).fetchall()
        return {
            "total": total,
            "open": open_cnt,
            "closed": closed_cnt,
            "avg_rating": avg_rating,
            "top_users": top_users,
        }


def list_duty_staff() -> List[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT username FROM duty_staff ORDER BY username").fetchall()
        return [r["username"] for r in rows]


def add_duty(username: str):
    username = username.lstrip("@")
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO duty_staff (username) VALUES (?)", (username,)
        )
        conn.commit()


def remove_duty(username: str):
    username = username.lstrip("@")
    with get_conn() as conn:
        conn.execute("DELETE FROM duty_staff WHERE username = ?", (username,))
        conn.commit()


# --- Settings helpers (key-value) ---

def set_setting(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()


def get_setting(key: str) -> Optional[str]:
    with get_conn() as conn:
        cur = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
        return row["value"] if row else None


# --- Maintenance helpers ---

def reset_stats():
    """Удалить все заявки и оценки."""
    with get_conn() as conn:
        conn.execute("DELETE FROM tickets")
        conn.commit()


def all_ticket_topics() -> List[int]:
    with get_conn() as conn:
        rows = conn.execute("SELECT DISTINCT topic_id FROM tickets").fetchall()
        return [r["topic_id"] for r in rows]


def user_ticket_count(user_id: int) -> int:
    with get_conn() as conn:
        cur = conn.execute("SELECT COUNT(*) FROM tickets WHERE user_id = ?", (user_id,))
        return cur.fetchone()[0] or 0
