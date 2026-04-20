"""
subagent.py — Manages background Claude CLI subagent processes.
Subagents run independently and send results to Telegram when done.
"""
import asyncio
import logging
import os
import signal
import uuid
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Track running subagents: {id: {process, started_at, task_desc, user_id}}
_subagents: dict = {}


def list_subagents() -> list:
    """Return list of running subagent dicts (without process objects)."""
    return [
        {k: v for k, v in agent.items() if k != "process"}
        for agent in _subagents.values()
    ]


def get_subagent(agent_id: str) -> Optional[dict]:
    """Get subagent by ID."""
    return _subagents.get(agent_id)


async def spawn_subagent(user_id: int, task: str, notify_callback) -> str:
    """Spawn a background Claude CLI process for a task.

    Returns agent_id. When done, calls notify_callback(user_id, agent_id, result, success).
    """
    agent_id = str(uuid.uuid4())[:8]

    from config import CLAUDE_CLI_PATH, CLAUDE_MODEL, WORKSPACE_DIR
    from context import get_context
    system_context = get_context()
    full_prompt = f"{system_context}\n\n[Background task requested by user:]\n{task}" if system_context else task
    cmd = [
        CLAUDE_CLI_PATH,
        "--print",
        "--model", CLAUDE_MODEL,
        "--permission-mode", "bypassPermissions",
        full_prompt,
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=WORKSPACE_DIR,
        start_new_session=True,
    )

    _subagents[agent_id] = {
        "id": agent_id,
        "user_id": user_id,
        "task": task[:100] + ("..." if len(task) > 100 else ""),
        "process": process,
        "pid": process.pid,
        "started_at": datetime.now(),
        "status": "running",
    }

    asyncio.create_task(_monitor_subagent(agent_id, process, notify_callback))

    return agent_id


async def _monitor_subagent(agent_id: str, process, notify_callback):
    """Wait for subagent to finish and call notify_callback."""
    try:
        stdout, stderr = await process.communicate()
        result = stdout.decode("utf-8", errors="replace").strip()
        if not result and stderr:
            result = stderr.decode("utf-8", errors="replace").strip()
        success = process.returncode == 0

        if agent_id in _subagents:
            _subagents[agent_id]["status"] = "done" if success else "failed"
            _subagents[agent_id]["result"] = result[:4000]

        user_id = _subagents.get(agent_id, {}).get("user_id")
        if user_id and notify_callback:
            await notify_callback(user_id, agent_id, result, success)
    except Exception as e:
        logger.exception("Subagent %s crashed: %s", agent_id, e)
        if agent_id in _subagents:
            _subagents[agent_id]["status"] = "crashed"


def kill_subagent(agent_id: str) -> bool:
    """Kill a running subagent. Returns True if killed."""
    agent = _subagents.get(agent_id)
    if not agent or agent.get("status") != "running":
        return False
    try:
        os.kill(agent["pid"], signal.SIGTERM)
        _subagents[agent_id]["status"] = "killed"
        return True
    except Exception:
        return False


def cleanup_done_subagents():
    """Remove finished subagents from tracking dict."""
    done = [k for k, v in _subagents.items() if v.get("status") in ("done", "failed", "killed", "crashed")]
    for k in done:
        del _subagents[k]
