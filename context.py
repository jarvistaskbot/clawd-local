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


def build_system_context(for_subagent: bool = False) -> str:
    """Build the full system context string to prepend to every Claude prompt.

    for_subagent=True strips the main-bot protocol (SPAWN_AGENT, SEND_FILE) and
    replaces it with subagent role instructions, so the subagent actually does
    the work instead of recursively emitting [SPAWN_AGENT: ...].
    """
    sections = []

    # Core identity and user profile (cap MEMORY.md to avoid huge context)
    for path in CONTEXT_FILES:
        content = _read_file(path)
        if content:
            max_len = 8000 if path.name == 'MEMORY.md' else 2000
            if len(content) > max_len:
                content = content[:max_len] + "\n... (truncated)"
            sections.append(f"## {path.name}\n{content}")

    # Available skills index (general skills the bot can load on demand).
    # Only the index lives in context; read the SKILL.md file when a trigger matches.
    sections.append(
        "## Available Skills\n"
        "When a task matches a skill's trigger, READ the skill file and follow it before acting. "
        "Do not rely on this summary alone.\n"
        "- **writing-skills** — Use when creating, editing, or verifying a skill (SKILL.md files). "
        "Read `/Users/openclaw/clawd-local/skills/writing-skills/SKILL.md`.\n"
        "- **brainstorming** — Structured design-before-code mode; user starts it with the "
        "`/brainstorm` command. Read `/Users/openclaw/clawd-local/skills/brainstorming/SKILL.md`."
    )

    # Recent daily notes
    daily = _load_recent_daily_notes(days=7)
    if daily:
        sections.append(f"## Recent Activity (last 7 days)\n{daily}")

    if not sections:
        return ""

    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    if for_subagent:
        header = (
            f"[SYSTEM CONTEXT — loaded from OpenClaw workspace at {today}]\n"
            "You are a background subagent for Arto. The persistent memory below is for context only.\n"
            "Your job: complete the task described at the bottom of this prompt and print the result as plain text. Your stdout is captured and forwarded to Arto on Telegram.\n"
            "DO NOT emit [SPAWN_AGENT: ...] — you ARE the subagent; spawning another would recurse.\n"
            "DO NOT emit [SEND_FILE: ...] — you cannot send files; describe paths inline instead.\n"
            "Do the work directly using whatever tools you have, then report the result.\n"
            "---\n"
        )
    else:
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


# Cache contexts for 5 minutes to avoid re-reading files on every message
_cache: dict = {"main": None, "subagent": None, "loaded_at": 0}
CACHE_TTL = 300  # seconds


def get_context(for_subagent: bool = False) -> str:
    """Return cached context, refreshing every 5 minutes."""
    import time
    now = time.time()
    key = "subagent" if for_subagent else "main"
    if _cache[key] is None or (now - _cache["loaded_at"]) > CACHE_TTL:
        _cache["main"] = build_system_context(for_subagent=False)
        _cache["subagent"] = build_system_context(for_subagent=True)
        _cache["loaded_at"] = now
    return _cache[key]
