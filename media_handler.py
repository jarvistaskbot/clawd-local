"""
media_handler.py — Downloads and processes media from Telegram messages.
Supports: images, videos (first frame extraction), voice/audio transcription.
"""

import asyncio
import logging
import os
import uuid
from typing import Optional

from openai import AsyncOpenAI

from config import MEDIA_TEMP_DIR, WHISPER_MODEL, MAX_FILE_SIZE_MB, OPENAI_API_KEY

logger = logging.getLogger(__name__)

# Text/code file extensions that can be read as plain text
TEXT_EXTENSIONS = {
    ".py", ".txt", ".md", ".json", ".yaml", ".yml", ".js", ".ts",
    ".html", ".css", ".csv", ".xml", ".toml", ".ini", ".cfg",
    ".sh", ".bash", ".zsh", ".fish", ".env", ".gitignore",
    ".jsx", ".tsx", ".vue", ".svelte", ".go", ".rs", ".rb",
    ".java", ".kt", ".swift", ".c", ".cpp", ".h", ".hpp",
    ".sql", ".graphql", ".proto", ".dockerfile", ".tf",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}


def get_media_temp_dir() -> str:
    os.makedirs(MEDIA_TEMP_DIR, exist_ok=True)
    return MEDIA_TEMP_DIR


def cleanup_temp_file(path: str):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception as e:
        logger.warning("Failed to clean up temp file %s: %s", path, e)


async def download_telegram_file(bot, file_id: str, suffix: str = "") -> str:
    """Download a Telegram file to a local temp path. Returns local file path."""
    temp_dir = get_media_temp_dir()
    filename = f"{uuid.uuid4().hex}{suffix}"
    dest_path = os.path.join(temp_dir, filename)

    tg_file = await bot.get_file(file_id)

    file_size_mb = (tg_file.file_size or 0) / (1024 * 1024)
    if file_size_mb > MAX_FILE_SIZE_MB:
        raise ValueError(f"File too large ({file_size_mb:.1f} MB, max {MAX_FILE_SIZE_MB} MB)")

    await tg_file.download_to_drive(dest_path)
    return dest_path


async def process_image(local_path: str, caption: str = "") -> str:
    """Build a prompt asking Claude to analyze the image at the given path."""
    caption_part = f"\nCaption from user: {caption}" if caption else ""
    return f"Please analyze the image at this path: {local_path}{caption_part}"


async def transcribe_audio(local_path: str) -> str:
    """Transcribe audio using OpenAI Whisper API."""
    if not OPENAI_API_KEY:
        return "Could not transcribe audio: OpenAI API key not configured"
    try:
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        with open(local_path, "rb") as audio_file:
            transcript = await client.audio.transcriptions.create(
                model=WHISPER_MODEL,
                file=audio_file,
            )
        return transcript.text
    except Exception as e:
        logger.exception("Audio transcription failed")
        return f"Could not transcribe audio: {e}"


async def extract_video_frame(video_path: str) -> Optional[str]:
    """Extract the first frame of a video using ffmpeg. Returns frame path or None."""
    temp_dir = get_media_temp_dir()
    frame_path = os.path.join(temp_dir, f"{uuid.uuid4().hex}_frame.jpg")
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-i", video_path, "-vframes", "1",
            "-f", "image2", frame_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.wait(), timeout=30)
        if proc.returncode == 0 and os.path.exists(frame_path):
            return frame_path
        return None
    except FileNotFoundError:
        logger.warning("ffmpeg not found — cannot extract video frames")
        return None
    except Exception as e:
        logger.warning("Video frame extraction failed: %s", e)
        return None


def is_text_file(filename: str) -> bool:
    _, ext = os.path.splitext(filename.lower())
    return ext in TEXT_EXTENSIONS


def is_image_file(filename: str) -> bool:
    _, ext = os.path.splitext(filename.lower())
    return ext in IMAGE_EXTENSIONS


async def read_text_file(local_path: str, filename: str) -> str:
    """Read a text/code file and return its content as a prompt."""
    try:
        with open(local_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        # Truncate very large files
        if len(content) > 50000:
            content = content[:50000] + "\n... (truncated)"
        return f"User sent a file: {filename}\n\n```\n{content}\n```"
    except Exception as e:
        return f"Could not read file {filename}: {e}"
