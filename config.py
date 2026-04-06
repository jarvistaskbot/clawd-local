import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
if TELEGRAM_CHAT_ID:
    TELEGRAM_ALLOWED_USERS = [int(TELEGRAM_CHAT_ID)]
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

# OpenAI prompt optimizer
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_ENABLED = os.getenv("OPENAI_ENABLED", "true").lower() == "true"
MAX_OPTIMIZED_PROMPT_LENGTH = int(os.getenv("MAX_OPTIMIZED_PROMPT_LENGTH", "4000"))

# Queue and concurrency
CLAUDE_QUEUE_SIZE = int(os.getenv("CLAUDE_QUEUE_SIZE", "10"))
CLAUDE_MAX_CONCURRENCY = int(os.getenv("CLAUDE_MAX_CONCURRENCY", "1"))

# Log rotation
LOG_ROTATION_MAX_BYTES = int(os.getenv("LOG_ROTATION_MAX_BYTES", "10485760"))
LOG_ROTATION_BACKUP_COUNT = int(os.getenv("LOG_ROTATION_BACKUP_COUNT", "5"))

# Media handling
MEDIA_TEMP_DIR = os.getenv("MEDIA_TEMP_DIR", os.path.expanduser("~/clawd-local/media_temp"))
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
