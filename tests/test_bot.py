import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env.example for testing config parsing
os.environ["TELEGRAM_BOT_TOKEN"] = "test_token_123"
os.environ["TELEGRAM_ALLOWED_USERS"] = "111,222,333"
os.environ["CLAUDE_CLI_PATH"] = "claude"
os.environ["CLAUDE_MODEL"] = "claude-sonnet-4-6"
os.environ["CLAUDE_TIMEOUT"] = "60"

# Re-import to pick up test env vars
import importlib
import config
importlib.reload(config)


def test_config_loads():
    assert config.TELEGRAM_BOT_TOKEN == "test_token_123"
    assert config.TELEGRAM_ALLOWED_USERS == [111, 222, 333]
    assert config.CLAUDE_CLI_PATH == "claude"
    assert config.CLAUDE_MODEL == "claude-sonnet-4-6"
    assert config.CLAUDE_TIMEOUT == 60


def test_message_splitting():
    from main import split_message

    # Short message — no split
    chunks = split_message("hello")
    assert chunks == ["hello"]

    # Long message — split at newlines
    text = ("line\n" * 2000)  # ~10000 chars
    chunks = split_message(text, max_len=4096)
    assert all(len(c) <= 4096 for c in chunks)
    # Reassembled text should contain all content
    assert sum(c.count("line") for c in chunks) == 2000


def test_whitelist_check():
    from main import is_allowed
    # Reload main to use our test config
    import main
    importlib.reload(main)
    from main import is_allowed

    assert is_allowed(111) is True
    assert is_allowed(222) is True
    assert is_allowed(999) is False


def test_empty_whitelist_allows_all():
    config.TELEGRAM_ALLOWED_USERS = []
    import main
    importlib.reload(main)
    from main import is_allowed
    assert is_allowed(999) is True
    # Restore
    config.TELEGRAM_ALLOWED_USERS = [111, 222, 333]
