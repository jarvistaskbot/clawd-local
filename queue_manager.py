"""
queue_manager.py — Async queue to serialize Claude CLI calls (max concurrency = 1).
Prevents concurrent Claude runs which could cause resource issues.
"""

import asyncio
import logging
from typing import Any, Callable, Coroutine

from config import CLAUDE_QUEUE_SIZE, CLAUDE_MAX_CONCURRENCY

logger = logging.getLogger(__name__)


class QueueFullError(Exception):
    """Raised when the Claude execution queue is full."""
    pass


class QueueManager:
    def __init__(self):
        self._queue: asyncio.Queue = None
        self._semaphore: asyncio.Semaphore = None
        self._worker_task: asyncio.Task = None
        self._pending_count = 0

    def start(self):
        self._queue = asyncio.Queue(maxsize=CLAUDE_QUEUE_SIZE)
        self._semaphore = asyncio.Semaphore(CLAUDE_MAX_CONCURRENCY)
        self._worker_task = asyncio.create_task(self._worker())
        logger.info("Queue manager started (size=%d, concurrency=%d)", CLAUDE_QUEUE_SIZE, CLAUDE_MAX_CONCURRENCY)

    @property
    def pending_count(self) -> int:
        return self._pending_count

    async def enqueue_prompt(self, user_id: int, message: str, callback: Callable[..., Coroutine]) -> None:
        if self._queue.full():
            raise QueueFullError("The queue is full. Please wait a moment and try again.")
        future = asyncio.get_event_loop().create_future()
        self._queue.put_nowait((user_id, message, callback, future))
        self._pending_count += 1
        return await future

    async def _worker(self):
        while True:
            user_id, message, callback, future = await self._queue.get()
            try:
                async with self._semaphore:
                    result = await callback(user_id, message)
                    future.set_result(result)
            except Exception as e:
                future.set_exception(e)
            finally:
                self._pending_count -= 1
                self._queue.task_done()


queue_manager = QueueManager()
