import asyncio
import json
import logging
import subprocess
import threading

logger = logging.getLogger(__name__)

# ── Active process tracking — allows /kill to abort in-flight Claude calls ────
_active_proc = None  # type: subprocess.Popen | None
_active_proc_lock = threading.Lock()
_task_aborted = threading.Event()


def abort_current_task():
    """Kill the active Claude subprocess and mark the task as aborted.
    Called by /kill — safe to call from the asyncio thread."""
    global _active_proc
    _task_aborted.set()
    with _active_proc_lock:
        proc = _active_proc
    if proc is not None:
        try:
            proc.kill()
        except Exception:
            pass

from config import (
    CLAUDE_CLI_PATH, CLAUDE_MODEL, CLAUDE_TIMEOUT,
    MAX_HISTORY_MESSAGES, WORKSPACE_DIR, OPENAI_ENABLED,
)
from memory import (
    get_or_create_session, add_message, get_history,
    get_active_project, set_active_project, get_or_create_project_session,
    get_or_create_project_chat_session, get_project_claude_session_id,
    update_project_claude_session,
)
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
    """Max 20 minutes — prevents infinite hang."""
    return 1200  # 20 minutes hard cap


def call_claude(prompt: str, timeout=None, claude_session_id: str = None) -> dict:
    """Call Claude CLI. Returns dict: {response: str, session_id: str | None}.
    Uses --resume if claude_session_id is provided for session continuity.
    Tracks the active Popen so abort_current_task() can kill it mid-run.
    """
    global _active_proc
    dynamic_timeout = timeout or estimate_timeout(prompt)
    cmd = [
        CLAUDE_CLI_PATH,
        "--print",
        "--model", CLAUDE_MODEL,
        "--permission-mode", "bypassPermissions",
        "--output-format", "json",
    ]
    if claude_session_id:
        cmd.extend(["--resume", claude_session_id])
    cmd.append(prompt)
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=WORKSPACE_DIR,
            start_new_session=True,
        )
        with _active_proc_lock:
            _active_proc = proc

        try:
            stdout_raw, stderr_raw = proc.communicate(timeout=dynamic_timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return {"response": f"Claude CLI timed out after {dynamic_timeout}s. Try breaking the task into smaller steps.", "session_id": None}
        finally:
            with _active_proc_lock:
                _active_proc = None

        # If task was aborted externally, return sentinel so handle_message skips the response
        if _task_aborted.is_set():
            return {"response": None, "session_id": None, "aborted": True}

        returncode = proc.returncode
        stderr = stderr_raw.strip()
        if returncode != 0:
            stderr_lower = stderr.lower()
            is_auth_error = (
                "authentication_error" in stderr_lower or
                "invalid authentication" in stderr_lower or
                "invalid api key" in stderr_lower or
                ("401" in stderr_lower and ("anthropic" in stderr_lower or "api" in stderr_lower))
            )
            if is_auth_error:
                logger.error("[Claude] Auth failure detected (code %s) — notify user", returncode)
                return {"response": (
                    "Claude authentication failed (401).\n\n"
                    "Check Anthropic Extra Usage balance at console.anthropic.com\n"
                    "Or re-login: `claude logout && claude login`"
                ), "session_id": None, "auth_error": True}
            if stderr:
                return {"response": f"Error from Claude CLI:\n{stderr}", "session_id": None}
            return {"response": f"Claude CLI exited with code {returncode}", "session_id": None}

        # Parse JSON output to extract response and session ID
        stdout = stdout_raw.strip()
        try:
            data = json.loads(stdout)
            response_text = data.get("result", "") or data.get("content", "") or ""
            # Handle content blocks format
            if not response_text and isinstance(data.get("content"), list):
                parts = []
                for block in data["content"]:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
                response_text = "\n".join(parts)
            new_session_id = data.get("session_id") or data.get("sessionId")
            return {"response": response_text.strip(), "session_id": new_session_id}
        except (json.JSONDecodeError, TypeError):
            # Fallback: treat as plain text
            return {"response": stdout, "session_id": None}

    except FileNotFoundError:
        return {"response": f"Claude CLI not found at '{CLAUDE_CLI_PATH}'. Make sure it's installed and in your PATH.", "session_id": None}
    except Exception as e:
        return {"response": f"Unexpected error calling Claude CLI: {e}", "session_id": None}


async def handle_message(user_id: int, message: str, skip_optimize: bool = False) -> str:
    message = sanitize_prompt(message)
    if not message.strip():
        return "Empty prompt. Please send a message with some content."

    # Auto-detect project from message keywords, then get session
    project_name = get_active_project(user_id)
    detected = detect_project(message, project_name)
    if detected != project_name:
        set_active_project(user_id, detected)
        project_name = detected
        logger.info("[Agent] Auto-switched to project: %s", project_name)
    get_or_create_project_session(user_id, project_name)
    session_id = get_or_create_project_chat_session(user_id, project_name)
    history = get_history(session_id, limit=MAX_HISTORY_MESSAGES)

    # Get saved Claude CLI session ID for resume
    claude_session_id = get_project_claude_session_id(user_id, project_name)

    # Optimize prompt via OpenAI only when user explicitly asks for it
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
    result = await loop.run_in_executor(
        None, call_claude, prompt, estimate_timeout(optimized), claude_session_id
    )

    # Task was aborted by /kill — discard result, send nothing
    if result.get("aborted"):
        _task_aborted.clear()
        return ""

    response = result["response"]

    # Save new Claude session ID if returned
    if result.get("session_id"):
        update_project_claude_session(user_id, project_name, result["session_id"])

    add_message(session_id, "user", message)
    add_message(session_id, "assistant", response)

    # Check for file send marker in response
    import re
    file_to_send = None
    file_match = re.search(r"\[SEND_FILE:\s*([^\]]+)\]", response)
    if file_match:
        file_to_send = file_match.group(1).strip()
        response = re.sub(r"\[SEND_FILE:\s*[^\]]+\]", "", response).strip()

    # Check for subagent spawn marker in response
    spawn_task = None
    spawn_match = re.search(r"\[SPAWN_AGENT:\s*([^\]]+)\]", response)
    if spawn_match:
        spawn_task = spawn_match.group(1).strip()
        response = re.sub(r"\[SPAWN_AGENT:\s*[^\]]+\]", "", response).strip()

    return {"text": response, "file": file_to_send, "spawn_task": spawn_task}

# Project auto-detection keywords
PROJECT_KEYWORDS = {
    "arbitrage": [
        "arbitrage", "trading", "bot", "bybit", "funding", "basis", "position",
        "profit", "pnl", "trade", "entry", "exit", "hedge", "spot", "perp",
        "futures", "delivery", "borrow", "fee", "slippage", "vps", "docker",
        "mongo", "scanner", "breakeven", "mnt", "xaut", "doge", "xrp"
    ],
    "tls": [
        "tls", "visa", "appointment", "slot", "booking", "extension", "chrome",
        "germany", "italy", "cyprus", "tlscontact", "cloudflare", "cf", "rsc",
        "safari", "polling", "country", "vac", "keycloak", "session"
    ],
}

def detect_project(message: str, current_project: str) -> str:
    """Detect which project a message belongs to based on keywords.
    Returns the detected project name, or current_project if no match.
    """
    msg_lower = message.lower()
    scores = {}
    for project, keywords in PROJECT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in msg_lower)
        if score > 0:
            scores[project] = score
    if not scores:
        return current_project
    best = max(scores, key=scores.get)
    # Only switch if score >= 2 (at least 2 keyword matches) to avoid false positives
    if scores[best] >= 2:
        return best
    return current_project
