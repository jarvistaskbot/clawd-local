import sqlite3
from datetime import datetime, timezone
from typing import Optional

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
        CREATE TABLE IF NOT EXISTS project_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            claude_session_id TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            last_used_at TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, name)
        );
        CREATE TABLE IF NOT EXISTS active_project (
            user_id INTEGER PRIMARY KEY,
            project_name TEXT NOT NULL DEFAULT 'general'
        );
        CREATE TABLE IF NOT EXISTS telegram_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_message_id INTEGER,
            chat_id INTEGER NOT NULL,
            thread_id INTEGER,
            sender_id INTEGER,
            sender_name TEXT,
            direction TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS thread_projects (
            chat_id INTEGER NOT NULL,
            thread_id INTEGER NOT NULL,
            project_name TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (chat_id, thread_id)
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
        CREATE INDEX IF NOT EXISTS idx_telegram_log_chat ON telegram_log(chat_id, thread_id);
        CREATE INDEX IF NOT EXISTS idx_telegram_log_msg ON telegram_log(telegram_message_id);
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
        "SELECT role, content FROM messages WHERE session_id = ? AND role != 'system' ORDER BY id DESC LIMIT ?",
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


def clear_last_messages(session_id: int, count: int = 5) -> int:
    """Delete the last N messages from current session. Returns how many deleted."""
    conn = _connect()
    rows = conn.execute(
        "SELECT id FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
        (session_id, count),
    ).fetchall()
    deleted = len(rows)
    if deleted > 0:
        ids = [r["id"] for r in rows]
        placeholders = ",".join("?" * len(ids))
        conn.execute(f"DELETE FROM messages WHERE id IN ({placeholders})", ids)
        conn.commit()
    conn.close()
    return deleted


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


# --- Project Sessions ---

def get_active_project(user_id: int) -> str:
    """Return the currently active project name for the user (default: 'general')."""
    conn = _connect()
    row = conn.execute(
        "SELECT project_name FROM active_project WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return row["project_name"] if row else "general"


def set_active_project(user_id: int, project_name: str) -> None:
    """Set the active project for the user."""
    conn = _connect()
    conn.execute(
        "INSERT INTO active_project (user_id, project_name) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET project_name = excluded.project_name",
        (user_id, project_name),
    )
    conn.commit()
    conn.close()


def get_or_create_project_session(user_id: int, project_name: str) -> dict:
    """Return project session dict. Creates if it doesn't exist."""
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    row = conn.execute(
        "SELECT id, name, claude_session_id, created_at, last_used_at "
        "FROM project_sessions WHERE user_id = ? AND name = ?",
        (user_id, project_name),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE project_sessions SET last_used_at = ? WHERE id = ?",
            (now, row["id"]),
        )
        conn.commit()
        result = dict(row)
    else:
        cur = conn.execute(
            "INSERT INTO project_sessions (user_id, name, created_at, last_used_at) VALUES (?, ?, ?, ?)",
            (user_id, project_name, now, now),
        )
        conn.commit()
        result = {
            "id": cur.lastrowid,
            "name": project_name,
            "claude_session_id": None,
            "created_at": now,
            "last_used_at": now,
        }
    conn.close()
    return result


def update_project_claude_session(user_id: int, project_name: str, claude_session_id: str) -> None:
    """Save the Claude CLI session ID for a project session."""
    conn = _connect()
    conn.execute(
        "UPDATE project_sessions SET claude_session_id = ? WHERE user_id = ? AND name = ?",
        (claude_session_id, user_id, project_name),
    )
    conn.commit()
    conn.close()


def get_project_claude_session_id(user_id: int, project_name: str) -> Optional[str]:
    """Return the saved Claude CLI session ID, or None if not set."""
    conn = _connect()
    row = conn.execute(
        "SELECT claude_session_id FROM project_sessions WHERE user_id = ? AND name = ?",
        (user_id, project_name),
    ).fetchone()
    conn.close()
    return row["claude_session_id"] if row else None


def list_project_sessions(user_id: int) -> list:
    """Return all project sessions for the user."""
    conn = _connect()
    rows = conn.execute(
        "SELECT ps.name, ps.claude_session_id, ps.last_used_at, "
        "(SELECT COUNT(*) FROM messages m JOIN sessions s ON m.session_id = s.id "
        " WHERE s.user_id = ? AND s.id = ("
        "   SELECT ss.id FROM sessions ss WHERE ss.user_id = ps.user_id "
        "   ORDER BY ss.created_at DESC LIMIT 1"
        " )) as msg_count "
        "FROM project_sessions ps WHERE ps.user_id = ? ORDER BY ps.last_used_at DESC",
        (user_id, user_id),
    ).fetchall()
    conn.close()
    active = get_active_project(user_id)
    result = []
    for r in rows:
        # Count messages for this project's chat session
        msg_count = _count_project_messages(user_id, r["name"])
        result.append({
            "name": r["name"],
            "has_claude_session": r["claude_session_id"] is not None,
            "last_used_at": r["last_used_at"],
            "message_count": msg_count,
            "is_active": r["name"] == active,
        })
    return result


def _count_project_messages(user_id: int, project_name: str) -> int:
    """Count messages in the chat session for a given project."""
    session_id = _get_project_chat_session_id(user_id, project_name)
    if session_id is None:
        return 0
    conn = _connect()
    row = conn.execute(
        "SELECT COUNT(*) as c FROM messages WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    conn.close()
    return row["c"]


def delete_project_session(user_id: int, project_name: str) -> bool:
    """Delete a project session. Returns True if deleted."""
    conn = _connect()
    cur = conn.execute(
        "DELETE FROM project_sessions WHERE user_id = ? AND name = ?",
        (user_id, project_name),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def _get_project_chat_session_id(user_id: int, project_name: str) -> Optional[int]:
    """Internal: find the chat session ID tagged for a project (via session note pattern)."""
    conn = _connect()
    # We tag project sessions by storing a marker message as the first message
    # Look for the session with a project marker
    rows = conn.execute(
        "SELECT s.id FROM sessions s "
        "JOIN messages m ON m.session_id = s.id "
        "WHERE s.user_id = ? AND m.role = 'system' AND m.content = ? "
        "ORDER BY s.created_at DESC LIMIT 1",
        (user_id, f"__project__:{project_name}"),
    ).fetchone()
    conn.close()
    return rows["id"] if rows else None


def get_or_create_project_chat_session(user_id: int, project_name: str) -> int:
    """Return the chat session ID for a project. Creates one if needed.
    Each project gets its own separate chat history session."""
    existing = _get_project_chat_session_id(user_id, project_name)
    if existing is not None:
        return existing

    # Create a new session and tag it with a project marker
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO sessions (user_id, created_at, updated_at) VALUES (?, ?, ?)",
        (user_id, now, now),
    )
    session_id = cur.lastrowid
    # Tag with project marker
    conn.execute(
        "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, 'system', ?, ?)",
        (session_id, f"__project__:{project_name}", now),
    )
    conn.commit()
    conn.close()
    return session_id


# --- Telegram Message Log ---

def log_telegram_message(
    chat_id: int,
    direction: str,  # "in" or "out"
    content: str,
    telegram_message_id: Optional[int] = None,
    thread_id: Optional[int] = None,
    sender_id: Optional[int] = None,
    sender_name: Optional[str] = None,
) -> int:
    """Log a Telegram message (incoming or outgoing). Returns the log row id."""
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO telegram_log (telegram_message_id, chat_id, thread_id, sender_id, sender_name, direction, content, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (telegram_message_id, chat_id, thread_id, sender_id, sender_name, direction, content, now),
    )
    conn.commit()
    conn.close()
    return cur.lastrowid


def search_telegram_log(query: str, limit: int = 20) -> list[dict]:
    """Full-text search over telegram_log content."""
    conn = _connect()
    rows = conn.execute(
        "SELECT telegram_message_id, chat_id, thread_id, sender_name, direction, content, timestamp "
        "FROM telegram_log WHERE content LIKE ? ORDER BY id DESC LIMIT ?",
        (f"%{query}%", limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Thread → Project Mapping ---

def get_thread_project(chat_id: int, thread_id: int) -> Optional[str]:
    """Return the project name mapped to this thread, or None."""
    conn = _connect()
    row = conn.execute(
        "SELECT project_name FROM thread_projects WHERE chat_id = ? AND thread_id = ?",
        (chat_id, thread_id),
    ).fetchone()
    conn.close()
    return row["project_name"] if row else None


def set_thread_project(chat_id: int, thread_id: int, project_name: str) -> None:
    """Map a thread to a project session."""
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO thread_projects (chat_id, thread_id, project_name, created_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(chat_id, thread_id) DO UPDATE SET project_name = excluded.project_name",
        (chat_id, thread_id, project_name, now),
    )
    conn.commit()
    conn.close()


def list_thread_projects(chat_id: int) -> list[dict]:
    """List all thread→project mappings for a chat."""
    conn = _connect()
    rows = conn.execute(
        "SELECT thread_id, project_name, created_at FROM thread_projects WHERE chat_id = ? ORDER BY created_at DESC",
        (chat_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def reset_project_session(user_id: int, project_name: str) -> int:
    """Reset the chat session for a specific project. Returns new session ID."""
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO sessions (user_id, created_at, updated_at) VALUES (?, ?, ?)",
        (user_id, now, now),
    )
    session_id = cur.lastrowid
    conn.execute(
        "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, 'system', ?, ?)",
        (session_id, f"__project__:{project_name}", now),
    )
    conn.commit()
    conn.close()
    # Clear Claude session ID too
    update_project_claude_session(user_id, project_name, None)
    return session_id
