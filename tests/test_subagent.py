"""Tests for subagent.py — background Claude CLI subagent management."""
import asyncio
import re
import sys
import os
from datetime import datetime
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def clear_subagents():
    """Clear subagent tracking dict before each test."""
    from subagent import _subagents
    _subagents.clear()
    yield
    _subagents.clear()


@pytest.mark.asyncio
async def test_spawn_subagent_runs():
    """Spawn a simple echo subagent and verify it completes."""
    import subagent as sa
    # Monkey-patch config for test
    import config
    original_cli = config.CLAUDE_CLI_PATH
    original_model = config.CLAUDE_MODEL
    original_ws = config.WORKSPACE_DIR
    config.CLAUDE_CLI_PATH = "echo"
    config.CLAUDE_MODEL = "test"
    config.WORKSPACE_DIR = "."

    results = []

    async def callback(user_id, agent_id, result, success):
        results.append((user_id, agent_id, result, success))

    try:
        # "echo" will receive all args and print them — good enough
        agent_id = await sa.spawn_subagent(123, "hello world", callback)
        assert len(agent_id) == 8

        # Wait for the subagent to finish
        await asyncio.sleep(1)

        assert len(results) == 1
        user_id, aid, result, success = results[0]
        assert user_id == 123
        assert aid == agent_id
        assert success is True
        assert "hello" in result or "--print" in result
    finally:
        config.CLAUDE_CLI_PATH = original_cli
        config.CLAUDE_MODEL = original_model
        config.WORKSPACE_DIR = original_ws


def test_spawn_agent_marker_detected():
    """[SPAWN_AGENT: ...] marker is detected in agent response."""
    text = "I'll analyze that for you. [SPAWN_AGENT: Run full code audit on src/] Let me know if you need anything else."
    match = re.search(r"\[SPAWN_AGENT:\s*([^\]]+)\]", text)
    assert match is not None
    assert match.group(1).strip() == "Run full code audit on src/"


def test_spawn_agent_marker_cleaned_from_response():
    """[SPAWN_AGENT: ...] marker is stripped from response text."""
    text = "Starting audit now. [SPAWN_AGENT: audit all Python files] Will notify when done."
    cleaned = re.sub(r"\[SPAWN_AGENT:\s*[^\]]+\]", "", text).strip()
    assert "[SPAWN_AGENT" not in cleaned
    assert "Starting audit now." in cleaned
    assert "Will notify when done." in cleaned


async def _noop_callback(*a):
    pass


@pytest.mark.asyncio
async def test_kill_subagent():
    """Kill a running subagent."""
    import subagent as sa

    # Start a long-running process directly (sleep ignores extra args on some systems)
    process = await asyncio.create_subprocess_exec(
        "sleep", "60",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )

    agent_id = "test1234"
    sa._subagents[agent_id] = {
        "id": agent_id,
        "user_id": 123,
        "task": "test task",
        "process": process,
        "pid": process.pid,
        "started_at": datetime.now(),
        "status": "running",
    }

    assert sa.kill_subagent(agent_id) is True
    assert sa._subagents[agent_id]["status"] == "killed"

    # Killing again should return False
    assert sa.kill_subagent(agent_id) is False


@pytest.mark.asyncio
async def test_list_subagents():
    """List subagents returns correct info."""
    import subagent as sa

    process = await asyncio.create_subprocess_exec(
        "sleep", "60",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )

    agent_id = "list5678"
    sa._subagents[agent_id] = {
        "id": agent_id,
        "user_id": 123,
        "task": "list test task",
        "process": process,
        "pid": process.pid,
        "started_at": datetime.now(),
        "status": "running",
    }

    agents = sa.list_subagents()
    assert len(agents) == 1
    assert agents[0]["id"] == agent_id
    assert agents[0]["status"] == "running"
    assert agents[0]["user_id"] == 123
    # process object should be excluded from list
    assert "process" not in agents[0]

    sa.kill_subagent(agent_id)


def test_cleanup_done_subagents():
    """cleanup_done_subagents removes finished entries."""
    from subagent import _subagents, cleanup_done_subagents
    from datetime import datetime

    _subagents["abc"] = {"id": "abc", "status": "done", "started_at": datetime.now()}
    _subagents["def"] = {"id": "def", "status": "running", "started_at": datetime.now()}
    _subagents["ghi"] = {"id": "ghi", "status": "failed", "started_at": datetime.now()}

    cleanup_done_subagents()

    assert "abc" not in _subagents
    assert "ghi" not in _subagents
    assert "def" in _subagents
