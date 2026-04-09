import os
import re
import sys
import importlib
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Override env for testing — must happen before any imports
os.environ["TELEGRAM_BOT_TOKEN"] = "test_token_123"
os.environ["TELEGRAM_ALLOWED_USERS"] = "111,222,333"
os.environ["CLAUDE_CLI_PATH"] = "claude"
os.environ["CLAUDE_MODEL"] = "claude-sonnet-4-6"
os.environ["CLAUDE_TIMEOUT"] = "60"
os.environ["TELEGRAM_CHAT_ID"] = ""

import config
importlib.reload(config)


def _make_update(user_id=111, args=None):
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_chat.id = 999
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    ctx.args = args
    ctx.bot.send_document = AsyncMock()
    return update, ctx


@pytest.mark.asyncio
async def test_upload_command_no_args():
    from main import upload_command
    update, ctx = _make_update(args=None)
    ctx.args = None
    await upload_command(update, ctx)
    update.message.reply_text.assert_called_once()
    assert "Usage" in update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_upload_command_file_not_found():
    from main import upload_command
    update, ctx = _make_update(args=["/nonexistent/file.txt"])
    await upload_command(update, ctx)
    update.message.reply_text.assert_called_once()
    assert "not found" in update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_upload_command_file_too_large():
    from main import upload_command
    update, ctx = _make_update(args=["/tmp/bigfile.bin"])
    # Mock os.path.exists and os.path.getsize
    with patch("main.os.path.exists", return_value=True), \
         patch("main.os.path.getsize", return_value=60 * 1024 * 1024):
        await upload_command(update, ctx)
    update.message.reply_text.assert_called_once()
    assert "too large" in update.message.reply_text.call_args[0][0]


def test_file_marker_detection_in_response():
    """Test that [SEND_FILE: path] is detected in agent response."""
    pattern = r"\[SEND_FILE:\s*([^\]]+)\]"
    text = "Here is the file [SEND_FILE: /tmp/report.txt] as requested."
    match = re.search(pattern, text)
    assert match is not None
    assert match.group(1).strip() == "/tmp/report.txt"


def test_file_marker_cleaned_from_response():
    """Test that the marker is removed from response text."""
    text = "Here is the file [SEND_FILE: /tmp/report.txt] as requested."
    cleaned = re.sub(r"\[SEND_FILE:\s*[^\]]+\]", "", text).strip()
    assert "[SEND_FILE" not in cleaned
    assert cleaned == "Here is the file  as requested."


def test_no_file_marker_returns_text_unchanged():
    """Test that text without marker passes through unchanged."""
    text = "Just a normal response with no file."
    match = re.search(r"\[SEND_FILE:\s*([^\]]+)\]", text)
    assert match is None


def test_unpack_result_dict():
    from main import _unpack_result
    text, f = _unpack_result({"text": "hello", "file": "/tmp/x.txt"})
    assert text == "hello"
    assert f == "/tmp/x.txt"


def test_unpack_result_dict_no_file():
    from main import _unpack_result
    text, f = _unpack_result({"text": "hello", "file": None})
    assert text == "hello"
    assert f is None


def test_unpack_result_string_fallback():
    from main import _unpack_result
    text, f = _unpack_result("plain string")
    assert text == "plain string"
    assert f is None


@pytest.mark.asyncio
async def test_upload_command_success():
    from main import upload_command
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
        tmp.write(b"test content")
        tmp_path = tmp.name
    try:
        update, ctx = _make_update(args=[tmp_path])
        await upload_command(update, ctx)
        # Should have called reply_text (uploading msg) then send_document
        assert update.message.reply_text.call_count == 1
        assert "Uploading" in update.message.reply_text.call_args[0][0]
        ctx.bot.send_document.assert_called_once()
    finally:
        os.unlink(tmp_path)
