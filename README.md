# clawd-local

Local AI operator that runs Claude Code CLI on your machine, controlled via Telegram. No API keys needed — uses your existing Claude Code CLI authentication.

## Architecture

```
Telegram Bot → Local Python Agent → Claude Code CLI (local execution)
```

## Prerequisites

- Python 3.10+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))

## Quick Start

1. Clone the repo:
   ```bash
   git clone https://github.com/artomnats/clawd-local.git
   cd clawd-local
   ```

2. Run setup:
   ```bash
   chmod +x setup.sh && ./setup.sh
   ```

3. Edit `.env` with your Telegram bot token and your Telegram user ID(s).

4. Activate the virtual environment:
   ```bash
   source venv/bin/activate
   ```

5. Start the bot:
   ```bash
   python main.py
   ```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | (required) | Bot token from BotFather |
| `TELEGRAM_ALLOWED_USERS` | (required) | Comma-separated Telegram user IDs |
| `CLAUDE_CLI_PATH` | `claude` | Path to Claude Code CLI binary |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | Model to use |
| `CLAUDE_TIMEOUT` | `120` | CLI timeout in seconds |
| `DB_PATH` | `history.db` | SQLite database path |
| `MAX_HISTORY_MESSAGES` | `20` | Context window size |
| `WORKSPACE_DIR` | `.` | Working directory for Claude CLI |

## Commands

| Command | Description |
|---|---|
| `/start` | Welcome message and usage info |
| `/reset` | Clear conversation history, start fresh |
| `/history` | Show last 10 messages |
| `/stats` | Show session statistics |

Any non-command message is sent to Claude Code CLI with conversation context.

## Conversation Memory

- Each user gets their own session stored in SQLite
- The last N messages (configurable) are included as context in each prompt
- `/reset` creates a new session — old history is preserved in the database but not sent as context
- History is formatted directly into the prompt since Claude CLI `--print` mode doesn't support conversation turns

## Troubleshooting

**"Claude CLI not found"** — Make sure `claude` is in your PATH, or set `CLAUDE_CLI_PATH` in `.env` to the full path.

**"Claude CLI timed out"** — Increase `CLAUDE_TIMEOUT` in `.env`. Complex prompts may need more time.

**Bot doesn't respond** — Check that your Telegram user ID is in `TELEGRAM_ALLOWED_USERS`. You can find your ID by messaging [@userinfobot](https://t.me/userinfobot).

**Long responses get cut off** — Responses over 4096 characters are automatically split into multiple messages.
