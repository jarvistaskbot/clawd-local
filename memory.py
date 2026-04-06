import sqlite3
from datetime import datetime, timezone

from config import DB_PATH


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
    """)
    conn.close()


def get_or_create_session(user_id: int) -> int:
    conn = _connect()
    row = conn.execute(
        "SELECT id FROM sessions WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    if row:
        session_id = row["id"]
    else:
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO sessions (user_id, created_at, updated_at) VALUES (?, ?, ?)",
            (user_id, now, now),
        )
        session_id = cur.lastrowid
        conn.commit()
    conn.close()
    return session_id


def add_message(session_id: int, role: str, content: str):
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (session_id, role, content, now),
    )
    conn.execute(
        "UPDATE sessions SET updated_at = ? WHERE id = ?",
        (now, session_id),
    )
    conn.commit()
    conn.close()


def get_history(session_id: int, limit: int = 20) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def reset_session(user_id: int) -> int:
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO sessions (user_id, created_at, updated_at) VALUES (?, ?, ?)",
        (user_id, now, now),
    )
    session_id = cur.lastrowid
    conn.commit()
    conn.close()
    return session_id


def get_stats(user_id: int) -> dict:
    conn = _connect()
    session_count = conn.execute(
        "SELECT COUNT(*) as c FROM sessions WHERE user_id = ?",
        (user_id,),
    ).fetchone()["c"]
    total_messages = conn.execute(
        "SELECT COUNT(*) as c FROM messages m JOIN sessions s ON m.session_id = s.id WHERE s.user_id = ?",
        (user_id,),
    ).fetchone()["c"]
    conn.close()
    return {"total_messages": total_messages, "session_count": session_count}
