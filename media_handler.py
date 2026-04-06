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
    """Analyze image using OpenAI Vision API (gpt-4o), then return description as prompt.
    Claude CLI --print doesn't support vision, so we use OpenAI for image analysis.
    """
    import base64
    import mimetypes
    caption_part = f"\nUser caption: {caption}" if caption else ""

    if not OPENAI_API_KEY:
        return f"User sent an image (OpenAI key not set for vision analysis).{caption_part}"

    try:
        mime_type = mimetypes.guess_type(local_path)[0] or "image/jpeg"
        with open(local_path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")

        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_data}"}},
                    {"type": "text", "text": f"Describe this image in detail.{caption_part}"}
                ]
            }],
            max_tokens=500
        )
        description = response.choices[0].message.content
        # Return description as the prompt for Claude
        return f"[Image analyzed by vision AI]\n{description}{caption_part}"
    except Exception as e:
        logger.error("Image vision analysis failed: %s", e)
        return f"User sent an image (vision analysis failed: {e}).{caption_part}"


async def transcribe_audio(local_path: str) -> str:
    """Transcribe audio using OpenAI Whisper API.
    Converts .oga/.ogg (Telegram Opus) to .wav first for better Whisper accuracy.
    """
    if not OPENAI_API_KEY:
        return "Could not transcribe audio: OpenAI API key not configured"

    # Convert to WAV for better Whisper accuracy (.oga Opus can degrade quality)
    wav_path = local_path.rsplit('.', 1)[0] + '_converted.wav'
    converted = False
    try:
        import subprocess as sp
        result = sp.run(
            ['ffmpeg', '-y', '-i', local_path, '-ar', '16000', '-ac', '1', '-f', 'wav', wav_path],
            capture_output=True, timeout=30
        )
        if result.returncode == 0:
            transcribe_path = wav_path
            converted = True
        else:
            transcribe_path = local_path
    except Exception:
        transcribe_path = local_path

    try:
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        with open(transcribe_path, "rb") as audio_file:
            transcript = await client.audio.transcriptions.create(
                model=WHISPER_MODEL,
                file=audio_file,
                language="en",  # Force English — prevents Whisper Turkish hallucination bug
            )
        return transcript.text
    except Exception as e:
        logger.exception("Audio transcription failed")
        return f"Could not transcribe audio: {e}"
    finally:
        if converted:
            cleanup_temp_file(wav_path)


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
