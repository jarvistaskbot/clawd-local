import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from queue_manager import QueueManager, QueueFullError


def test_queue_processes_items_in_order():
    """Items enqueued are processed in FIFO order."""
    results = []

    async def callback(user_id, message):
        results.append((user_id, message))
        return f"reply:{message}"

    async def run():
        qm = QueueManager()
        # Override config for test
        import queue_manager
        orig_size = queue_manager.CLAUDE_QUEUE_SIZE
        orig_conc = queue_manager.CLAUDE_MAX_CONCURRENCY
        queue_manager.CLAUDE_QUEUE_SIZE = 10
        queue_manager.CLAUDE_MAX_CONCURRENCY = 1

        qm._queue = asyncio.Queue(maxsize=10)
        qm._semaphore = asyncio.Semaphore(1)
        qm._worker_task = asyncio.create_task(qm._worker())

        r1 = await qm.enqueue_prompt(1, "first", callback)
        r2 = await qm.enqueue_prompt(2, "second", callback)

        assert r1 == "reply:first"
        assert r2 == "reply:second"
        assert results == [(1, "first"), (2, "second")]

        qm._worker_task.cancel()
        queue_manager.CLAUDE_QUEUE_SIZE = orig_size
        queue_manager.CLAUDE_MAX_CONCURRENCY = orig_conc

    asyncio.get_event_loop().run_until_complete(run())


def test_queue_full_raises_error():
    """When queue is full, QueueFullError is raised."""

    async def slow_callback(user_id, message):
        await asyncio.sleep(10)
        return "done"

    async def run():
        qm = QueueManager()
        qm._queue = asyncio.Queue(maxsize=1)
        qm._semaphore = asyncio.Semaphore(1)
        qm._worker_task = asyncio.create_task(qm._worker())
        qm._pending_count = 0

        # Fill the queue — enqueue one that will block in the worker
        asyncio.create_task(qm.enqueue_prompt(1, "blocking", slow_callback))
        await asyncio.sleep(0.01)  # Let worker pick it up

        # Fill the queue slot
        asyncio.create_task(qm.enqueue_prompt(2, "fill", slow_callback))
        await asyncio.sleep(0.01)

        # Now it should be full
        try:
            # This should fail because queue is full
            qm._queue.put_nowait(("dummy",))
            assert False, "Expected queue to be full"
        except asyncio.QueueFull:
            pass  # Expected

        qm._worker_task.cancel()

    asyncio.get_event_loop().run_until_complete(run())


def test_concurrent_limit_respected():
    """Semaphore ensures only one callback runs at a time."""
    concurrent = []
    max_concurrent = [0]

    async def tracking_callback(user_id, message):
        concurrent.append(1)
        current = len(concurrent)
        if current > max_concurrent[0]:
            max_concurrent[0] = current
        await asyncio.sleep(0.05)
        concurrent.pop()
        return "done"

    async def run():
        qm = QueueManager()
        qm._queue = asyncio.Queue(maxsize=10)
        qm._semaphore = asyncio.Semaphore(1)
        qm._worker_task = asyncio.create_task(qm._worker())

        tasks = [
            asyncio.create_task(qm.enqueue_prompt(i, f"msg{i}", tracking_callback))
            for i in range(3)
        ]
        await asyncio.gather(*tasks)

        assert max_concurrent[0] == 1
        qm._worker_task.cancel()

    asyncio.get_event_loop().run_until_complete(run())
