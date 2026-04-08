import asyncio
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Optional

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USERS, TELEGRAM_CHAT_ID,
    CLAUDE_CLI_PATH, CLAUDE_MODEL, OPENAI_ENABLED, OPENAI_MODEL,
)
from memory import (
    init_db, get_or_create_session, get_history, reset_session, get_stats, clear_last_messages,
    get_active_project, set_active_project, get_or_create_project_session,
    get_or_create_project_chat_session, list_project_sessions, delete_project_session,
    reset_project_session, get_project_claude_session_id,
)
from agent import handle_message

async def handle_message_direct(user_id: int, message: str) -> str:
    """Handle message skipping OpenAI optimization — used for media (images, voice, video)."""
    return await handle_message(user_id, message, skip_optimize=True)


async def run_with_typing(bot, chat_id: int, coro):
    """Run a coroutine while keeping the Telegram typing indicator alive every 4s."""
    stop_typing = asyncio.Event()

    async def keep_typing():
        while not stop_typing.is_set():
            try:
                await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            except Exception:
                pass
            try:
                await asyncio.wait_for(asyncio.shield(stop_typing.wait()), timeout=4.0)
            except asyncio.TimeoutError:
                pass

    typing_task = asyncio.create_task(keep_typing())
    try:
        return await coro
    finally:
        stop_typing.set()
        typing_task.cancel()
from context import get_context, MEMORY_DIR, CONTEXT_FILES
from queue_manager import queue_manager, QueueFullError
from watchdog import run_watchdog, check_claude_health, is_healthy, setup_log_rotation
from media_handler import (
    download_telegram_file, process_image, transcribe_audio,
    extract_video_frame, cleanup_temp_file, is_text_file, is_image_file,
    read_text_file,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

_last_activity: Optional[str] = None
_start_time: Optional[datetime] = None


def is_allowed(user_id: int) -> bool:
    if not TELEGRAM_ALLOWED_USERS:
        return True
    return user_id in TELEGRAM_ALLOWED_USERS


def split_message(text: str, max_len: int = 4096) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


async def safe_reply(message, text: str):
    """Send with Markdown, fall back to plain text if parsing fails."""
    try:
        await message.reply_text(text, parse_mode="Markdown")
    except Exception:
        # Strip markdown syntax and send plain
        import re
        plain = re.sub(r'[*_`\[\]()]', '', text)
        await message.reply_text(plain)


def _check_claude_cli() -> str:
    try:
        result = subprocess.run(
            [CLAUDE_CLI_PATH, "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return f"available ({result.stdout.strip()})"
    except Exception:
        pass
    return "unavailable"


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    user_id = update.effective_user.id
    project_name = get_active_project(user_id)
    session_id = get_or_create_project_chat_session(user_id, project_name)
    history = get_history(session_id)
    cli_status = _check_claude_cli()
    last = _last_activity or "no activity yet"
    await update.message.reply_text(
        "clawd-local status\n\n"
        f"Bot running: OK\n"
        f"Claude CLI: {cli_status}\n"
        f"Project: {project_name}\n"
        f"Memory: {len(history)} messages in current session\n"
        f"Last activity: {last}\n\n"
        "Commands:\n"
        "/start - Bot status\n"
        "/session <name> - Switch project\n"
        "/sessions - List projects\n"
        "/models - List available models\n"
        "/reset - Start a fresh conversation\n"
        "/history - Show recent messages\n"
        "/stats - Show session statistics\n"
        "/status - System health status\n"
        "/stop - Shut down the bot\n"
        "/restart - Restart the bot\n"
        "/help - Show this help"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    await update.message.reply_text(
        "Available commands:\n\n"
        "/start - Bot status and diagnostics\n"
        "/session <name> - Switch to project session\n"
        "/sessions - List all project sessions\n"
        "/session delete <name> - Delete a project session\n"
        "/models - List available Claude models\n"
        "/new - Start new session (history preserved)\n"
        "/reset - Start a fresh conversation\n"
        "/clear [N] - Remove last N messages from context (default 5)\n"
        "/history - Show recent messages\n"
        "/stats - Show session statistics\n"
        "/status - System health status\n"
        "/stop - Shut down the bot\n"
        "/restart - Restart the bot\n"
        "/help - Show this help\n\n"
        "Send any text message to chat with Claude."
    )


async def models_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    models = [
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-haiku-3-5",
    ]
    lines = ["Available models:\n"]
    for m in models:
        marker = " (current)" if m == CLAUDE_MODEL else ""
        lines.append(f"  - {m}{marker}")
    lines.append(f"\nConfigured model: {CLAUDE_MODEL}")
    await update.message.reply_text("\n".join(lines))


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    await update.message.reply_text("Shutting down...")
    logger.info("Stop command received. Exiting.")
    os._exit(0)


async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    await update.message.reply_text("Restarting...")
    logger.info("Restart command received. Re-executing process.")
    os.execv(sys.executable, [sys.executable] + sys.argv)


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    user_id = update.effective_user.id
    project_name = get_active_project(user_id)
    reset_project_session(user_id, project_name)
    await update.message.reply_text(f"Conversation reset for project '{project_name}'. Starting fresh!")


async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    user_id = update.effective_user.id
    project_name = get_active_project(user_id)
    reset_project_session(user_id, project_name)
    await update.message.reply_text(
        f"🆕 New session started for project '{project_name}'. Previous history preserved but not active."
    )


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    user_id = update.effective_user.id
    count = 5
    if context.args:
        try:
            count = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Usage: /clear [N] — N must be a number.")
            return
    project_name = get_active_project(user_id)
    session_id = get_or_create_project_chat_session(user_id, project_name)
    deleted = clear_last_messages(session_id, count)
    await update.message.reply_text(f"🗑 Cleared last {deleted} messages from project '{project_name}'.")


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    user_id = update.effective_user.id
    project_name = get_active_project(user_id)
    session_id = get_or_create_project_chat_session(user_id, project_name)
    messages = get_history(session_id, limit=10)
    if not messages:
        await update.message.reply_text(f"No messages in project '{project_name}' yet.")
        return
    lines = [f"📁 Project: {project_name}\n"]
    for msg in messages:
        prefix = "You" if msg["role"] == "user" else "Claude"
        content = msg["content"][:200]
        if len(msg["content"]) > 200:
            content += "..."
        lines.append(f"**{prefix}:** {content}")
    await update.message.reply_text("\n\n".join(lines))


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    user_id = update.effective_user.id
    project_name = get_active_project(user_id)
    session_id = get_or_create_project_chat_session(user_id, project_name)
    messages = get_history(session_id, limit=9999)
    claude_sid = get_project_claude_session_id(user_id, project_name)
    s = get_stats(user_id)
    await update.message.reply_text(
        f"📁 Project: {project_name}\n"
        f"Messages in project: {len(messages)}\n"
        f"Claude session: {'active' if claude_sid else 'none'}\n\n"
        f"All projects — Sessions: {s['session_count']}\n"
        f"All projects — Total messages: {s['total_messages']}"
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return

    claude_status = "✅ Healthy" if is_healthy() else "❌ Unhealthy"
    openai_status = f"✅ Enabled ({OPENAI_MODEL})" if OPENAI_ENABLED else "❌ Disabled"
    pending = queue_manager.pending_count

    uptime_str = "unknown"
    if _start_time:
        delta = datetime.now(timezone.utc) - _start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes = remainder // 60
        uptime_str = f"{hours}h {minutes}m"

    await update.message.reply_text(
        "System Status\n\n"
        f"Bot: ✅ Running\n"
        f"Claude CLI: {claude_status}\n"
        f"OpenAI: {openai_status}\n"
        f"Queue: {pending} items pending\n"
        f"Uptime: {uptime_str}"
    )


async def _run_with_progress(update, context, coro):
    """Run a coroutine with typing indicator and progress updates for long tasks."""
    stop_typing = asyncio.Event()
    progress_msg = None
    start = time.time()

    async def keep_typing_and_progress():
        nonlocal progress_msg
        intervals = [30, 60, 120, 180, 240]
        next_idx = 0
        while not stop_typing.is_set():
            try:
                await context.bot.send_chat_action(
                    chat_id=update.effective_chat.id, action=ChatAction.TYPING)
            except Exception:
                pass
            # Check if we should show/update progress
            elapsed = time.time() - start
            if next_idx < len(intervals) and elapsed >= intervals[next_idx]:
                next_idx += 1
                elapsed_int = int(elapsed)
                label = f"{elapsed_int // 60}min" if elapsed_int >= 120 else f"{elapsed_int}s"
                try:
                    if progress_msg is None:
                        progress_msg = await update.message.reply_text(f"⏳ Still working... ({label})")
                    else:
                        await progress_msg.edit_text(f"⏳ Still working... ({label})")
                except Exception:
                    pass
            try:
                await asyncio.wait_for(asyncio.shield(stop_typing.wait()), timeout=4.0)
            except asyncio.TimeoutError:
                pass

    typing_task = asyncio.create_task(keep_typing_and_progress())
    try:
        result = await coro
    finally:
        stop_typing.set()
        typing_task.cancel()
        if progress_msg:
            try:
                await progress_msg.delete()
            except Exception:
                pass
    return result


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _last_activity
    if not is_allowed(update.effective_user.id):
        return
    user_id = update.effective_user.id
    text = update.message.text
    if not text:
        return

    # Reply-to-message context
    if update.message.reply_to_message and update.message.reply_to_message.text:
        quoted = update.message.reply_to_message.text[:500]
        text = f"[Replying to: {quoted}]\n\n{text}"

    try:
        pending = queue_manager.pending_count
        if pending > 0:
            await update.message.reply_text(f"⏳ Queued... ({pending} ahead of you)")

        response = await _run_with_progress(
            update, context,
            queue_manager.enqueue_prompt(user_id, text, handle_message)
        )

        _last_activity = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        for chunk in split_message(response):
            await safe_reply(update.message, chunk)
    except QueueFullError:
        await update.message.reply_text("🚫 Queue is full. Please wait a moment and try again.")
    except Exception as e:
        logger.exception("Error handling message")
        await update.message.reply_text(f"Something went wrong: {e}")


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _last_activity
    if not is_allowed(update.effective_user.id):
        return
    user_id = update.effective_user.id
    local_path = None
    try:
        photo = update.message.photo[-1]  # highest resolution
        local_path = await download_telegram_file(context.bot, photo.file_id, suffix=".jpg")
        caption = update.message.caption or ""
        prompt = await process_image(local_path, caption)

        pending = queue_manager.pending_count
        if pending > 0:
            await update.message.reply_text(f"⏳ Queued... ({pending} ahead of you)")

        response = await _run_with_progress(
            update, context,
            queue_manager.enqueue_prompt(user_id, prompt, handle_message_direct)
        )
        _last_activity = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        for chunk in split_message(response):
            await safe_reply(update.message, chunk)
    except QueueFullError:
        await update.message.reply_text("🚫 Queue is full. Please wait a moment and try again.")
    except Exception as e:
        logger.exception("Error handling photo")
        await update.message.reply_text(f"Something went wrong: {e}")
    finally:
        if local_path:
            cleanup_temp_file(local_path)


async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _last_activity
    if not is_allowed(update.effective_user.id):
        return
    user_id = update.effective_user.id
    local_path = None
    try:
        
        voice = update.message.voice or update.message.audio
        local_path = await download_telegram_file(context.bot, voice.file_id, suffix=".ogg")
        transcription = await transcribe_audio(local_path)
        await update.message.reply_text(f"🎤 Transcribed: {transcription}")

        pending = queue_manager.pending_count
        if pending > 0:
            await update.message.reply_text(f"⏳ Queued... ({pending} ahead of you)")

        response = await _run_with_progress(update, context, queue_manager.enqueue_prompt(user_id, transcription, handle_message_direct))
        _last_activity = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        for chunk in split_message(response):
            await safe_reply(update.message, chunk)
    except QueueFullError:
        await update.message.reply_text("🚫 Queue is full. Please wait a moment and try again.")
    except Exception as e:
        logger.exception("Error handling voice message")
        await update.message.reply_text(f"Something went wrong: {e}")
    finally:
        if local_path:
            cleanup_temp_file(local_path)


async def video_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _last_activity
    if not is_allowed(update.effective_user.id):
        return
    user_id = update.effective_user.id
    local_path = None
    frame_path = None
    try:
        
        video = update.message.video or update.message.video_note
        local_path = await download_telegram_file(context.bot, video.file_id, suffix=".mp4")
        frame_path = await extract_video_frame(local_path)

        if frame_path is None:
            await update.message.reply_text(
                "Video received but ffmpeg not installed for frame extraction. "
                "Please send a screenshot instead."
            )
            return

        caption = update.message.caption or ""
        prompt = await process_image(frame_path, caption)

        pending = queue_manager.pending_count
        if pending > 0:
            await update.message.reply_text(f"⏳ Queued... ({pending} ahead of you)")

        response = await _run_with_progress(update, context, queue_manager.enqueue_prompt(user_id, prompt, handle_message_direct))
        _last_activity = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        for chunk in split_message(response):
            await safe_reply(update.message, chunk)
    except QueueFullError:
        await update.message.reply_text("🚫 Queue is full. Please wait a moment and try again.")
    except Exception as e:
        logger.exception("Error handling video")
        await update.message.reply_text(f"Something went wrong: {e}")
    finally:
        if local_path:
            cleanup_temp_file(local_path)
        if frame_path:
            cleanup_temp_file(frame_path)


async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _last_activity
    if not is_allowed(update.effective_user.id):
        return
    user_id = update.effective_user.id
    local_path = None
    try:
        
        doc = update.message.document
        filename = doc.file_name or "unknown"

        if is_image_file(filename):
            local_path = await download_telegram_file(context.bot, doc.file_id, suffix=os.path.splitext(filename)[1])
            caption = update.message.caption or ""
            prompt = await process_image(local_path, caption)
        elif is_text_file(filename):
            local_path = await download_telegram_file(context.bot, doc.file_id, suffix=os.path.splitext(filename)[1])
            prompt = await read_text_file(local_path, filename)
        else:
            await update.message.reply_text(f"Document type not supported: {filename}")
            return

        pending = queue_manager.pending_count
        if pending > 0:
            await update.message.reply_text(f"⏳ Queued... ({pending} ahead of you)")

        response = await _run_with_progress(update, context, queue_manager.enqueue_prompt(user_id, prompt, handle_message_direct))
        _last_activity = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        for chunk in split_message(response):
            await safe_reply(update.message, chunk)
    except QueueFullError:
        await update.message.reply_text("🚫 Queue is full. Please wait a moment and try again.")
    except Exception as e:
        logger.exception("Error handling document")
        await update.message.reply_text(f"Something went wrong: {e}")
    finally:
        if local_path:
            cleanup_temp_file(local_path)


async def session_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /session <name>, /session new <name>, /session delete <name>."""
    if not is_allowed(update.effective_user.id):
        return
    user_id = update.effective_user.id
    args = context.args or []

    if not args:
        # Show current project
        project_name = get_active_project(user_id)
        session_id = get_or_create_project_chat_session(user_id, project_name)
        messages = get_history(session_id, limit=9999)
        claude_sid = get_project_claude_session_id(user_id, project_name)
        await update.message.reply_text(
            f"📁 Active project: {project_name}\n"
            f"💬 {len(messages)} messages\n"
            f"🤖 Claude session: {'active' if claude_sid else 'none'}\n\n"
            "Usage:\n"
            "/session <name> — switch to project\n"
            "/session delete <name> — delete project\n"
            "/sessions — list all projects"
        )
        return

    if args[0].lower() == "delete":
        if len(args) < 2:
            await update.message.reply_text("Usage: /session delete <name>")
            return
        target = args[1].lower()
        active = get_active_project(user_id)
        if target == active:
            await update.message.reply_text("Cannot delete the active project. Switch to another first.")
            return
        if delete_project_session(user_id, target):
            await update.message.reply_text(f"🗑 Deleted project: {target}")
        else:
            await update.message.reply_text(f"Project '{target}' not found.")
        return

    # Switch to (or create) project
    project_name = args[0].lower()
    set_active_project(user_id, project_name)
    ps = get_or_create_project_session(user_id, project_name)
    session_id = get_or_create_project_chat_session(user_id, project_name)
    messages = get_history(session_id, limit=9999)
    claude_sid = ps.get("claude_session_id")
    await update.message.reply_text(
        f"📁 Switched to project: {project_name}\n"
        f"💬 {len(messages)} messages in this session\n"
        f"🤖 Claude session: {'active' if claude_sid else 'new'}"
    )


async def sessions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all project sessions."""
    if not is_allowed(update.effective_user.id):
        return
    user_id = update.effective_user.id
    sessions = list_project_sessions(user_id)
    if not sessions:
        project_name = get_active_project(user_id)
        await update.message.reply_text(
            f"📁 Active project: {project_name} (no other sessions)\n\n"
            "Use /session <name> to create a new project."
        )
        return

    lines = ["📁 Your project sessions:\n"]
    for s in sessions:
        marker = " (active)" if s["is_active"] else ""
        claude = "🤖" if s["has_claude_session"] else ""
        last = s["last_used_at"][:16] if s["last_used_at"] else "never"
        lines.append(f"• {s['name']}{marker} — {s['message_count']} msgs, last: {last} {claude}")
    lines.append("\nUse /session <name> to switch.")
    await update.message.reply_text("\n".join(lines))


async def context_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    from pathlib import Path
    loaded = []
    for f in CONTEXT_FILES:
        if Path(f).exists():
            loaded.append(f"✅ {Path(f).name}")
        else:
            loaded.append(f"❌ {Path(f).name} (missing)")
    daily_files = sorted(MEMORY_DIR.glob("*.md"), reverse=True)[:7] if MEMORY_DIR.exists() else []
    daily_str = f"{len(daily_files)} daily notes (last 7 days)" if daily_files else "no daily notes found"
    ctx = get_context()
    size_kb = len(ctx.encode()) / 1024
    msg = (
        "📚 Loaded context from OpenClaw workspace:\n\n"
        + "\n".join(loaded)
        + f"\n\n📅 Daily notes: {daily_str}"
        + f"\n📦 Total context size: {size_kb:.1f} KB"
        + "\n\nContext is injected into every Claude prompt automatically."
    )
    await update.message.reply_text(msg)


async def _send_telegram_alert(text: str):
    """Send a watchdog alert via Telegram."""
    from telegram import Bot
    if TELEGRAM_CHAT_ID:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)


def main():
    global _start_time

    if not TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not set. Copy .env.example to .env and configure it.")
        return

    # Set up log rotation
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    setup_log_rotation(log_dir)

    init_db()
    _start_time = datetime.now(timezone.utc)

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("models", models_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("restart", restart_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("new", new_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("session", session_command))
    app.add_handler(CommandHandler("sessions", sessions_command))
    app.add_handler(CommandHandler("context", context_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, voice_handler))
    app.add_handler(MessageHandler(filters.VIDEO | filters.VIDEO_NOTE, video_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))

    async def post_init(application):
        queue_manager.start()
        asyncio.create_task(run_watchdog(interval_seconds=60, send_alert=_send_telegram_alert))
        logger.info("Queue manager and watchdog started.")

    app.post_init = post_init

    logger.info("Bot started. Polling for messages...")
    app.run_polling()


if __name__ == "__main__":
    main()
