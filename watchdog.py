"""
watchdog.py — Monitors Claude CLI health and manages log rotation.
"""

import asyncio
import logging
import logging.handlers

from config import CLAUDE_CLI_PATH, LOG_ROTATION_MAX_BYTES, LOG_ROTATION_BACKUP_COUNT

logger = logging.getLogger(__name__)

_consecutive_failures = 0
_healthy = True


async def check_claude_health() -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            CLAUDE_CLI_PATH, "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.wait(), timeout=5)
        return proc.returncode == 0
    except Exception:
        return False


def is_healthy() -> bool:
    return _healthy


def setup_log_rotation(log_dir: str):
    root_logger = logging.getLogger()

    stdout_handler = logging.handlers.RotatingFileHandler(
        f"{log_dir}/stdout.log",
        maxBytes=LOG_ROTATION_MAX_BYTES,
        backupCount=LOG_ROTATION_BACKUP_COUNT,
    )
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

    stderr_handler = logging.handlers.RotatingFileHandler(
        f"{log_dir}/stderr.log",
        maxBytes=LOG_ROTATION_MAX_BYTES,
        backupCount=LOG_ROTATION_BACKUP_COUNT,
    )
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(stderr_handler)


async def run_watchdog(interval_seconds: int = 60, send_alert=None):
    global _consecutive_failures, _healthy

    while True:
        await asyncio.sleep(interval_seconds)
        healthy = await check_claude_health()

        if healthy:
            _consecutive_failures = 0
            _healthy = True
            logger.debug("Claude CLI health check: OK")
        else:
            _consecutive_failures += 1
            logger.warning("Claude CLI health check failed (%d consecutive)", _consecutive_failures)

            if _consecutive_failures >= 3:
                _healthy = False
                if send_alert:
                    try:
                        await send_alert("⚠️ Claude CLI is unhealthy — 3 consecutive health checks failed.")
                    except Exception as e:
                        logger.error("Failed to send watchdog alert: %s", e)
