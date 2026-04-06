import subprocess

from config import CLAUDE_CLI_PATH, CLAUDE_MODEL, CLAUDE_TIMEOUT, MAX_HISTORY_MESSAGES, WORKSPACE_DIR
from memory import get_or_create_session, add_message, get_history


def format_prompt(history: list[dict], current_message: str) -> str:
    parts = []
    if history:
        parts.append("[Previous conversation:]")
        for msg in history:
            label = "Human" if msg["role"] == "user" else "Assistant"
            parts.append(f"{label}: {msg['content']}")
        parts.append("")
    parts.append("[Current message:]")
    parts.append(f"Human: {current_message}")
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


def handle_message(user_id: int, message: str) -> str:
    session_id = get_or_create_session(user_id)
    history = get_history(session_id, limit=MAX_HISTORY_MESSAGES)
    prompt = format_prompt(history, message)
    response = call_claude(prompt)
    add_message(session_id, "user", message)
    add_message(session_id, "assistant", response)
    return response
