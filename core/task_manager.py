"""
Background Task Manager — manages fire-and-forget async tasks
so they don't block the critical trading path.

Architecture:
  Critical path:  Market Data → Strategy Analysis → Risk Check → Trade Execution
  Background:     Charts, Telegram notifications, DB writes, logging
"""
from __future__ import annotations

import asyncio
from typing import Coroutine, Set

from utils.logging_config import get_logger

logger = get_logger("task_manager")


class BackgroundTaskManager:
    """Tracks and manages background async tasks.

    Usage:
        bg = BackgroundTaskManager()
        bg.fire_and_forget(some_coroutine())
        ...
        await bg.shutdown()  # drains remaining tasks on exit
    """

    def __init__(self, max_concurrent: int = 50):
        self._tasks: Set[asyncio.Task] = set()
        self._max_concurrent = max_concurrent
        self._shutting_down = False

    @property
    def pending_count(self) -> int:
        return len(self._tasks)

    def fire_and_forget(self, coro: Coroutine, name: str | None = None) -> None:
        """Schedule a coroutine as a background task.

        The coroutine runs concurrently without blocking the caller.
        Errors are logged but never propagated.
        """
        if self._shutting_down:
            logger.debug("Task rejected — shutting down", task=name)
            return

        if len(self._tasks) >= self._max_concurrent:
            logger.warning("Background task limit reached, dropping task", task=name)
            return

        task = asyncio.create_task(self._safe_run(coro, name), name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _safe_run(self, coro: Coroutine, name: str | None) -> None:
        """Run a coroutine, catching and logging any exception."""
        try:
            await coro
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Background task failed", task=name, error=str(e))

    async def shutdown(self, timeout: float = 10.0) -> None:
        """Wait for pending tasks to finish, then cancel stragglers."""
        self._shutting_down = True
        if not self._tasks:
            return

        logger.info("Draining background tasks", pending=len(self._tasks))
        done, pending = await asyncio.wait(
            self._tasks, timeout=timeout, return_when=asyncio.ALL_COMPLETED
        )

        for task in pending:
            task.cancel()

        if pending:
            logger.warning("Cancelled stale background tasks", count=len(pending))
