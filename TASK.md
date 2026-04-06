# Build Task: clawd-local

You are a senior Python automation engineer. Build a complete project called "clawd-local" — a local AI operator that uses Claude Code CLI as the AI backend, controlled via Telegram.

## Architecture
Telegram Bot → Local Python Agent (controller) → Claude Code CLI (local execution)

## Project Structure to Create
```
clawd-local/
├── main.py              # Entry point — starts the Telegram bot
├── agent.py             # Core agent: receives prompts, calls Claude CLI, returns responses
├── memory.py            # Conversation history: SQLite-based persistent storage
├── config.py            # Configuration loading from .env
├── requirements.txt     # Dependencies
├── .env.example         # Example environment file
├── setup.sh             # One-command setup script
├── README.md            # Full setup and usage guide
└── tests/
    ├── test_agent.py    # Test Claude CLI execution
    ├── test_memory.py   # Test conversation storage
    └── test_bot.py      # Test Telegram integration
```

## Detailed Requirements

### config.py
Load from .env:
- TELEGRAM_BOT_TOKEN
- TELEGRAM_ALLOWED_USERS (comma-separated chat IDs, whitelist)
- CLAUDE_CLI_PATH (default: "claude")
- CLAUDE_MODEL (default: "claude-sonnet-4-6")
- CLAUDE_TIMEOUT (default: 120 seconds)
- DB_PATH (default: "history.db")
- MAX_HISTORY_MESSAGES (default: 20)
- WORKSPACE_DIR (default: current dir)

### memory.py
SQLite-based conversation memory:
- Table: sessions(id, user_id, created_at, updated_at)
- Table: messages(id, session_id, role, content, timestamp)
- Methods:
  - get_or_create_session(user_id) -> session_id
  - add_message(session_id, role, content)
  - get_history(session_id, limit=20) -> list of {role, content}
  - reset_session(user_id) -> new session_id
  - get_stats(user_id) -> {total_messages, session_count}

### agent.py
Core agent logic:
- Call Claude CLI: claude --print --model {model} --permission-mode bypassPermissions "{prompt}"
- Pass conversation history as context in the prompt (last N messages formatted as Human:/Assistant: turns)
- Capture stdout/stderr with subprocess
- Handle timeouts gracefully
- Return clean response text
- On error: return descriptive error message

IMPORTANT: Claude CLI --print mode does NOT accept conversation history as CLI flags.
Instead, format history INTO the prompt itself:

[Previous conversation:]
Human: {msg1}
Assistant: {msg2}
Human: {msg3}
...

[Current message:]
Human: {current_prompt}

Pass this as a single string argument to claude --print.
Use subprocess.run with capture_output=True, text=True, timeout=CLAUDE_TIMEOUT.
Do NOT use shell=True (security risk).

### main.py
Telegram bot using python-telegram-bot (v20+, async):
- Commands:
  - /start -> welcome message + usage instructions
  - /reset -> reset conversation history, start fresh
  - /history -> show last 10 messages from current session
  - /stats -> show session statistics
- Message handler: pass any non-command message to agent
- User whitelist: only respond to TELEGRAM_ALLOWED_USERS
- Long message handling: split responses >4096 chars into multiple Telegram messages
- Show "typing..." indicator while Claude is processing
- Error handling: catch all exceptions, send user-friendly error message

### requirements.txt
python-telegram-bot>=20.0
python-dotenv>=1.0.0

No heavy frameworks. No FastAPI. No Redis. Just these two deps.

### setup.sh
#!/bin/bash
- Create virtual environment
- Install requirements
- Copy .env.example to .env if not exists
- Print setup complete message with next steps

### .env.example
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_ALLOWED_USERS=123456789,987654321
CLAUDE_CLI_PATH=claude
CLAUDE_MODEL=claude-sonnet-4-6
CLAUDE_TIMEOUT=120
DB_PATH=history.db
MAX_HISTORY_MESSAGES=20
WORKSPACE_DIR=.

### README.md
Include:
- What it is and why (local Claude Code CLI via Telegram, no API costs)
- Prerequisites (Python 3.10+, Claude Code CLI installed and authenticated)
- Quick start (5 steps)
- Configuration reference
- Command reference
- How conversation memory works
- Troubleshooting section

### tests/test_agent.py
Test:
- Claude CLI is callable (check claude --version)
- Simple prompt returns non-empty response
- Timeout handling works
- History formatting is correct

### tests/test_memory.py
Test:
- Session creation
- Message storage and retrieval
- History limit respected
- Session reset works
- Stats are accurate

### tests/test_bot.py
Test:
- Config loads correctly from .env.example values
- Message splitting works for long responses
- Whitelist check works

## After Implementation

1. Run all tests: python -m pytest tests/ -v
2. Fix any failures
3. Create GitHub repo: gh repo create artomnats/clawd-local --public --description "Local Claude Code CLI operator via Telegram"
4. Push all code
5. Print summary of what was built

When completely finished, run:
openclaw system event --text "Done: clawd-local built and pushed to GitHub — Telegram bot + Claude Code CLI + SQLite memory" --mode now
