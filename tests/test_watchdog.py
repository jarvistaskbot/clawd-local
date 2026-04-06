import os
import sys
import asyncio
from unittest.mock import patch, AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import watchdog


def test_claude_health_check_returns_bool():
    """check_claude_health returns a boolean."""
    result = asyncio.get_event_loop().run_until_complete(
        watchdog.check_claude_health()
    )
    assert isinstance(result, bool)


def test_health_check_timeout_handled():
    """Health check handles timeout gracefully (returns False)."""

    async def slow_wait(timeout=None):
        raise asyncio.TimeoutError()

    async def run():
        with patch("watchdog.asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.wait = slow_wait
            mock_exec.return_value = mock_proc
            result = await watchdog.check_claude_health()
            assert result is False

    asyncio.get_event_loop().run_until_complete(run())


def test_is_healthy_default():
    """is_healthy returns True by default."""
    watchdog._healthy = True
    assert watchdog.is_healthy() is True
