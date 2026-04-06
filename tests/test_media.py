import os
import sys
import tempfile
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ensure test env is set before config import
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_token_123")
os.environ.setdefault("TELEGRAM_CHAT_ID", "")
os.environ.setdefault("TELEGRAM_ALLOWED_USERS", "111,222,333")

from media_handler import (
    get_media_temp_dir,
    cleanup_temp_file,
    transcribe_audio,
    extract_video_frame,
    is_text_file,
    is_image_file,
    process_image,
    read_text_file,
)


def test_get_media_temp_dir_creates_dir():
    """get_media_temp_dir creates the directory if it doesn't exist."""
    with patch("media_handler.MEDIA_TEMP_DIR", tempfile.mkdtemp() + "/subdir") as tmp:
        result = get_media_temp_dir()
        assert os.path.isdir(result)
        os.rmdir(result)


def test_cleanup_temp_file():
    """cleanup_temp_file removes the file without error."""
    fd, path = tempfile.mkstemp()
    os.close(fd)
    assert os.path.exists(path)
    cleanup_temp_file(path)
    assert not os.path.exists(path)


def test_cleanup_temp_file_missing():
    """cleanup_temp_file handles missing files gracefully."""
    cleanup_temp_file("/tmp/nonexistent_file_abc123.xyz")


def test_transcribe_audio_handles_missing_openai_key():
    """transcribe_audio returns error message when API key is missing."""
    with patch("media_handler.OPENAI_API_KEY", ""):
        result = asyncio.get_event_loop().run_until_complete(
            transcribe_audio("/tmp/test.ogg")
        )
        assert "not configured" in result


def test_extract_video_frame_handles_no_ffmpeg():
    """extract_video_frame returns None when ffmpeg is not found."""
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
        result = asyncio.get_event_loop().run_until_complete(
            extract_video_frame("/tmp/test.mp4")
        )
        assert result is None


def test_is_text_file():
    assert is_text_file("main.py") is True
    assert is_text_file("config.json") is True
    assert is_text_file("readme.md") is True
    assert is_text_file("photo.jpg") is False
    assert is_text_file("video.mp4") is False


def test_is_image_file():
    assert is_image_file("photo.jpg") is True
    assert is_image_file("screenshot.PNG") is True
    assert is_image_file("doc.pdf") is False
    assert is_image_file("script.py") is False


def test_process_image():
    result = asyncio.get_event_loop().run_until_complete(
        process_image("/tmp/test.jpg", "a cat")
    )
    assert "/tmp/test.jpg" in result
    assert "a cat" in result


def test_process_image_no_caption():
    result = asyncio.get_event_loop().run_until_complete(
        process_image("/tmp/test.jpg")
    )
    assert "/tmp/test.jpg" in result
    assert "Caption" not in result


def test_read_text_file():
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"print('hello')")
    os.close(fd)
    try:
        result = asyncio.get_event_loop().run_until_complete(
            read_text_file(path, "hello.py")
        )
        assert "hello.py" in result
        assert "print('hello')" in result
    finally:
        os.unlink(path)
