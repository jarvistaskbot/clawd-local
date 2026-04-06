import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
if _chat_id:
    TELEGRAM_ALLOWED_USERS = [int(_chat_id)]
else:
    TELEGRAM_ALLOWED_USERS = [
        int(uid.strip())
        for uid in os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",")
        if uid.strip()
    ]
CLAUDE_CLI_PATH = os.getenv("CLAUDE_CLI_PATH", "claude")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
CLAUDE_TIMEOUT = int(os.getenv("CLAUDE_TIMEOUT", "120"))
DB_PATH = os.getenv("DB_PATH", "history.db")
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "20"))
WORKSPACE_DIR = os.getenv("WORKSPACE_DIR", ".")
