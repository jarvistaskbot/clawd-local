import os
import sys
import importlib
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Override env for testing — must happen before any imports
os.environ["TELEGRAM_BOT_TOKEN"] = "test_token_123"
os.environ["TELEGRAM_ALLOWED_USERS"] = "111,222,333"
os.environ["CLAUDE_CLI_PATH"] = "claude"
os.environ["CLAUDE_MODEL"] = "claude-sonnet-4-6"
os.environ["CLAUDE_TIMEOUT"] = "60"
os.environ["TELEGRAM_CHAT_ID"] = ""  # empty so ALLOWED_USERS takes effect

# Re-import to pick up test env vars
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


def test_single_chat_id_whitelist():
    """TELEGRAM_CHAT_ID takes priority over TELEGRAM_ALLOWED_USERS."""
    os.environ["TELEGRAM_CHAT_ID"] = "42"
    os.environ["TELEGRAM_ALLOWED_USERS"] = "111,222,333"
    importlib.reload(config)
    assert config.TELEGRAM_ALLOWED_USERS == [42]
    # Cleanup
    os.environ.pop("TELEGRAM_CHAT_ID", None)
    os.environ["TELEGRAM_ALLOWED_USERS"] = "111,222,333"
    importlib.reload(config)


def test_stop_command_sends_message():
    """stop_command sends 'Shutting down...' then calls os._exit."""
    # Ensure whitelist allows user 111
    os.environ["TELEGRAM_ALLOWED_USERS"] = "111,222,333"
    os.environ["TELEGRAM_CHAT_ID"] = ""
    import config as cfg
    importlib.reload(cfg)
    import main
    importlib.reload(main)

    update = MagicMock()
    update.effective_user.id = 111
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()

    import asyncio
    with patch("main.os._exit") as mock_exit:
        asyncio.get_event_loop().run_until_complete(main.stop_command(update, ctx))
        update.message.reply_text.assert_awaited_once_with("Shutting down...")
        mock_exit.assert_called_once_with(0)


def test_restart_command_sends_message():
    """restart_command sends 'Restarting...' then calls os.execv."""
    os.environ["TELEGRAM_ALLOWED_USERS"] = "111,222,333"
    os.environ["TELEGRAM_CHAT_ID"] = ""
    import config as cfg
    importlib.reload(cfg)
    import main
    importlib.reload(main)

    update = MagicMock()
    update.effective_user.id = 111
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()

    import asyncio
    with patch("main.os.execv") as mock_execv:
        asyncio.get_event_loop().run_until_complete(main.restart_command(update, ctx))
        update.message.reply_text.assert_awaited_once_with("Restarting...")
        mock_execv.assert_called_once()
