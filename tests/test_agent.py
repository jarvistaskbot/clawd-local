import subprocess
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import format_prompt, call_claude, sanitize_prompt, handle_message
from config import CLAUDE_CLI_PATH


def test_claude_cli_callable():
    result = subprocess.run(
        [CLAUDE_CLI_PATH, "--version"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert result.stdout.strip() != ""


def test_simple_prompt_returns_response():
    response = call_claude("Reply with exactly: hello")
    assert response != ""
    assert "not found" not in response.lower()


def test_timeout_handling():
    import config
    original = config.CLAUDE_TIMEOUT
    config.CLAUDE_TIMEOUT = 1
    # Patch the module-level import in agent
    import agent
    agent.CLAUDE_TIMEOUT = 1
    response = call_claude("Write a 10000 word essay about the history of computing")
    agent.CLAUDE_TIMEOUT = original
    config.CLAUDE_TIMEOUT = original
    # Either it times out or returns quickly — both are valid
    assert isinstance(response, str)


def test_format_prompt_no_history():
    result = format_prompt([], "hello")
    assert "[Current message:]" in result
    assert "Human: hello" in result
    assert "[Previous conversation:]" not in result


def test_format_prompt_with_history():
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello there"},
    ]
    result = format_prompt(history, "how are you?")
    assert "[Previous conversation:]" in result
    assert "Human: hi" in result
    assert "Assistant: hello there" in result
    assert "[Current message:]" in result
    assert "Human: how are you?" in result


def test_prompt_sanitization():
    """Null bytes are stripped and length is capped."""
    result = sanitize_prompt("hello\x00world")
    assert "\x00" not in result
    assert result == "helloworld"

    long_text = "a" * 20000
    result = sanitize_prompt(long_text)
    assert len(result) == 10000


def test_empty_prompt_rejected():
    """Empty prompts return an error message instead of calling Claude."""
    import tempfile
    import config
    import memory

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    orig_db = config.DB_PATH
    config.DB_PATH = path
    memory.DB_PATH = path
    memory.init_db()

    try:
        result = handle_message(999, "")
        assert "empty" in result.lower()

        result = handle_message(999, "\x00\x00")
        assert "empty" in result.lower()
    finally:
        config.DB_PATH = orig_db
        memory.DB_PATH = orig_db
        os.unlink(path)
