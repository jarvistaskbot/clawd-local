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


async def _get_video_duration(video_path: str) -> Optional[float]:
    """Return video duration in seconds using ffprobe, or None on failure."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", video_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode == 0:
            return float(stdout.decode().strip())
    except Exception as e:
        logger.warning("ffprobe duration failed: %s", e)
    return None


async def extract_video_frames(video_path: str, count: int = 4) -> list[str]:
    """Extract `count` evenly-spaced frames from a video. Returns list of frame paths."""
    duration = await _get_video_duration(video_path)
    if duration is None or duration <= 0:
        single = await extract_video_frame(video_path)
        return [single] if single else []

    temp_dir = get_media_temp_dir()
    frames: list[str] = []
    # Sample at midpoints of `count` equal segments to avoid edge frames
    timestamps = [duration * (i + 0.5) / count for i in range(count)]
    for ts in timestamps:
        frame_path = os.path.join(temp_dir, f"{uuid.uuid4().hex}_frame.jpg")
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-ss", f"{ts:.2f}", "-i", video_path,
                "-vframes", "1", "-q:v", "3", "-f", "image2", frame_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.wait(), timeout=30)
            if proc.returncode == 0 and os.path.exists(frame_path):
                frames.append(frame_path)
        except Exception as e:
            logger.warning("Frame extraction at %.2fs failed: %s", ts, e)
    return frames


async def extract_audio_from_video(video_path: str) -> Optional[str]:
    """Extract audio from a video as 16kHz mono WAV for Whisper. Returns path or None."""
    temp_dir = get_media_temp_dir()
    audio_path = os.path.join(temp_dir, f"{uuid.uuid4().hex}_audio.wav")
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-i", video_path, "-vn", "-ar", "16000", "-ac", "1",
            "-f", "wav", audio_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.wait(), timeout=60)
        if proc.returncode == 0 and os.path.exists(audio_path) and os.path.getsize(audio_path) > 1024:
            return audio_path
        if os.path.exists(audio_path):
            cleanup_temp_file(audio_path)
        return None
    except Exception as e:
        logger.warning("Audio extraction failed: %s", e)
        return None


async def process_video(video_path: str, caption: str = "", frame_count: int = None) -> str:
    """Analyze a video by extracting multiple frames + audio transcript.
    Sends all frames in a single gpt-4o call so the model can reason about motion.
    frame_count=None means adaptive: 1 frame per 2s, capped at 4–12.
    """
    import base64
    caption_part = f"\nUser caption: {caption}" if caption else ""

    if not OPENAI_API_KEY:
        return f"User sent a video (OpenAI key not set for vision analysis).{caption_part}"

    if frame_count is None:
        duration = await _get_video_duration(video_path)
        if duration and duration > 0:
            frame_count = max(4, min(12, int(duration / 2)))
        else:
            frame_count = 4

    frames = await extract_video_frames(video_path, count=frame_count)
    if not frames:
        return f"User sent a video but frame extraction failed (ffmpeg missing or video unreadable).{caption_part}"

    audio_path = await extract_audio_from_video(video_path)
    transcript = ""
    if audio_path:
        try:
            transcript = await transcribe_audio(audio_path)
        finally:
            cleanup_temp_file(audio_path)

    try:
        coverage_note = f"at ~1 frame per 2 seconds" if frame_count >= 4 else ""
        content = [{
            "type": "text",
            "text": (
                f"These are {len(frames)} evenly-spaced frames from a video {coverage_note}, in chronological order. "
                f"Describe what's happening in the video — consider motion, changes between frames, and what the video appears to show overall."
                f"{caption_part}"
            ),
        }]
        for fp in frames:
            with open(fp, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": content}],
            max_tokens=800,
        )
        description = response.choices[0].message.content
        parts = [f"[Video analyzed by vision AI — {len(frames)} frames]", description]
        if transcript and not transcript.startswith("Could not transcribe"):
            parts.append(f"\nAudio transcript:\n{transcript}")
        if caption:
            parts.append(f"\nUser caption: {caption}")
        return "\n".join(parts)
    except Exception as e:
        logger.exception("Video analysis failed")
        return f"User sent a video (analysis failed: {e}).{caption_part}"
    finally:
        for fp in frames:
            cleanup_temp_file(fp)


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
