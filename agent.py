import asyncio
import subprocess

from config import (
    CLAUDE_CLI_PATH, CLAUDE_MODEL, CLAUDE_TIMEOUT,
    MAX_HISTORY_MESSAGES, WORKSPACE_DIR, OPENAI_ENABLED,
)
from memory import get_or_create_session, add_message, get_history
from context import get_context
from optimizer import optimize_prompt

MAX_PROMPT_LENGTH = 10000


def sanitize_prompt(text: str) -> str:
    text = text.replace("\x00", "")
    text = text[:MAX_PROMPT_LENGTH]
    return text


def escape_backticks(text: str) -> str:
    return text.replace("```", "\\`\\`\\`")


def format_prompt(history: list[dict], current_message: str) -> str:
    parts = []

    # Inject OpenClaw persistent context
    system_context = get_context()
    if system_context:
        parts.append(system_context)

    if history:
        parts.append("[Previous conversation in this session:]")
        for msg in history:
            label = "Human" if msg["role"] == "user" else "Assistant"
            parts.append(f"{label}: {escape_backticks(msg['content'])}")
        parts.append("")
    parts.append("[Current message:]")
    parts.append(f"Human: {escape_backticks(current_message)}")
    return "\n".join(parts)


def call_claude(prompt: str) -> str:
    cmd = [
        CLAUDE_CLI_PATH,
        "--print",
        "--model", CLAUDE_MODEL,
        "--permission-mode", "bypassPermissions",
        prompt,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
            cwd=WORKSPACE_DIR,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if stderr:
                return f"Error from Claude CLI:\n{stderr}"
            return f"Claude CLI exited with code {result.returncode}"
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return f"Claude CLI timed out after {CLAUDE_TIMEOUT} seconds. Try a simpler prompt."
    except FileNotFoundError:
        return f"Claude CLI not found at '{CLAUDE_CLI_PATH}'. Make sure it's installed and in your PATH."
    except Exception as e:
        return f"Unexpected error calling Claude CLI: {e}"


async def handle_message(user_id: int, message: str) -> str:
    message = sanitize_prompt(message)
    if not message.strip():
        return "Empty prompt. Please send a message with some content."

    session_id = get_or_create_session(user_id)
    history = get_history(session_id, limit=MAX_HISTORY_MESSAGES)

    # Optimize prompt via OpenAI
    optimized = await optimize_prompt(message)
    was_optimized = OPENAI_ENABLED and optimized != message

    prompt = format_prompt(history, optimized)
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(None, call_claude, prompt)

    add_message(session_id, "user", message)
    add_message(session_id, "assistant", response)

    if was_optimized:
        response += "\n\n_[prompt optimized by OpenAI]_"

    return response
