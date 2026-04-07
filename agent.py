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


def estimate_timeout(prompt: str):
    """Return None = no timeout. Claude runs until it finishes, no matter how long."""
    return None


def call_claude(prompt: str, timeout: int = None) -> str:
    dynamic_timeout = timeout or estimate_timeout(prompt)
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
            timeout=dynamic_timeout,
            cwd=WORKSPACE_DIR,
            start_new_session=True,  # Isolate from parent process group — prevents SIGTERM kill
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if stderr:
                return f"Error from Claude CLI:\n{stderr}"
            return f"Claude CLI exited with code {result.returncode}"
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return f"Claude CLI timed out after {dynamic_timeout}s. Try breaking the task into smaller steps."
    except FileNotFoundError:
        return f"Claude CLI not found at '{CLAUDE_CLI_PATH}'. Make sure it's installed and in your PATH."
    except Exception as e:
        return f"Unexpected error calling Claude CLI: {e}"


async def handle_message(user_id: int, message: str, skip_optimize: bool = False) -> str:
    message = sanitize_prompt(message)
    if not message.strip():
        return "Empty prompt. Please send a message with some content."

    session_id = get_or_create_session(user_id)
    history = get_history(session_id, limit=MAX_HISTORY_MESSAGES)

    # Optimize prompt via OpenAI only when user explicitly asks for it
    # Triggers: message contains "create a prompt", "create prompt", or starts with "prompt:"
    # All other messages go directly to Claude as-is to preserve natural conversation flow
    msg_lower = message.lower()
    wants_optimization = (
        "create a prompt" in msg_lower or
        "create prompt" in msg_lower or
        "generate a prompt" in msg_lower or
        "generate prompt" in msg_lower or
        msg_lower.startswith("prompt:")
    )
    if skip_optimize:
        optimized = message
    elif wants_optimization:
        optimized = await optimize_prompt(message)
    else:
        optimized = message

    prompt = format_prompt(history, optimized)
    loop = asyncio.get_event_loop()
    dynamic_timeout = estimate_timeout(optimized)
    response = await loop.run_in_executor(None, call_claude, prompt, dynamic_timeout)

    add_message(session_id, "user", message)
    add_message(session_id, "assistant", response)
    return response
