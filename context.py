"""
context.py — Loads persistent context from OpenClaw memory files.
Injected at the top of every Claude prompt so the bot knows everything.
"""

import os
from pathlib import Path
from datetime import datetime

WORKSPACE = Path.home() / ".openclaw" / "workspace"
MEMORY_DIR = WORKSPACE / "memory"

CONTEXT_FILES = [
    WORKSPACE / "SOUL.md",
    WORKSPACE / "USER.md",
    WORKSPACE / "TOOLS.md",
    WORKSPACE / "MEMORY.md",
]


def _read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _load_recent_daily_notes(days: int = 3) -> str:
    """Load the most recent N daily memory files (capped at 3 to keep context small)."""
    if not MEMORY_DIR.exists():
        return ""
    files = sorted(MEMORY_DIR.glob("*.md"), reverse=True)[:days]
    parts = []
    for f in reversed(files):
        content = _read_file(f)
        if content:
            # Cap each daily note at 3000 chars
            if len(content) > 3000:
                content = content[:3000] + "\n... (truncated)"
            parts.append(f"### {f.stem}\n{content}")
    return "\n\n".join(parts)


def build_system_context() -> str:
    """Build the full system context string to prepend to every Claude prompt."""
    sections = []

    # Core identity and user profile (cap MEMORY.md to avoid huge context)
    for path in CONTEXT_FILES:
        content = _read_file(path)
        if content:
            max_len = 8000 if path.name == 'MEMORY.md' else 2000
            if len(content) > max_len:
                content = content[:max_len] + "\n... (truncated)"
            sections.append(f"## {path.name}\n{content}")

    # Recent daily notes
    daily = _load_recent_daily_notes(days=7)
    if daily:
        sections.append(f"## Recent Activity (last 7 days)\n{daily}")

    if not sections:
        return ""

    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    header = (
        f"[SYSTEM CONTEXT — loaded from OpenClaw workspace at {today}]\n"
        "You are Arto's AI assistant. The following is your persistent memory and context.\n"
        "Use it to answer questions about past work, decisions, and ongoing projects.\n"
        "To send a file to the user, include [SEND_FILE: /absolute/path/to/file] anywhere in your response.\n"
        "BACKGROUND TASKS: If the user asks you to do something 'in the background', 'as a background task', or 'don't block', you MUST respond with ONLY [SPAWN_AGENT: <full detailed task description>] and nothing else — do NOT attempt the task yourself inline. The subagent runs as a separate process and reports back to Telegram when done.\n"
        "For other heavy tasks (code audit, file generation, long analysis) you judge should run async, also use [SPAWN_AGENT: detailed task description].\n"
        "To send a file to the user, include [SEND_FILE: /absolute/path/to/file] anywhere in your response.\n"
        "---\n"
    )
    return header + "\n\n".join(sections) + "\n\n[END SYSTEM CONTEXT]\n"


# Cache context for 5 minutes to avoid re-reading files on every message
_cache: dict = {"context": None, "loaded_at": 0}
CACHE_TTL = 300  # seconds


def get_context() -> str:
    """Return cached context, refreshing every 5 minutes."""
    import time
    now = time.time()
    if _cache["context"] is None or (now - _cache["loaded_at"]) > CACHE_TTL:
        _cache["context"] = build_system_context()
        _cache["loaded_at"] = now
    return _cache["context"]
