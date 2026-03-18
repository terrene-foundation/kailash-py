# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Task queue factory with auto-detection from KAILASH_QUEUE_URL.

Provides a single entry point for creating task queue backends based on the
``KAILASH_QUEUE_URL`` environment variable.  The factory inspects the URL scheme
and returns the appropriate backend:

* **No URL configured** (Level 0/1): Returns ``None`` -- no task queue.
* **redis:// or rediss://** (Level 2): Returns
  :class:`~kailash.runtime.distributed.TaskQueue` (Redis-backed).
* **postgresql://, mysql://, sqlite://** (Level 2): Returns
  :class:`~kailash.infrastructure.task_queue.SQLTaskQueue` (SQL-backed).

All optional-dependency imports are **lazy** (inside factory function) so that
this module has no dependency on ``redis``, ``asyncpg``, ``aiomysql``, or
``aiosqlite`` at import time.

Usage::

    from kailash.infrastructure.queue_factory import create_task_queue

    queue = await create_task_queue()         # auto-detect from env
    queue = await create_task_queue("redis://localhost:6379/0")  # explicit
    queue = await create_task_queue("sqlite:///queue.db")        # SQL-backed

    if queue is None:
        # Level 0/1: no queue configured, single-process execution only
        pass
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from kailash.db.registry import resolve_queue_url

logger = logging.getLogger(__name__)

__all__ = [
    "create_task_queue",
]


async def create_task_queue(queue_url: Optional[str] = None) -> Optional[Any]:
    """Create a task queue from a URL, or auto-detect from environment.

    Parameters
    ----------
    queue_url:
        Explicit queue URL.  If ``None``, auto-detects from the
        ``KAILASH_QUEUE_URL`` environment variable via
        :func:`~kailash.db.registry.resolve_queue_url`.

    Returns
    -------
    TaskQueue, SQLTaskQueue, or None
        * ``None`` if no queue URL is configured (Level 0/1 -- single process).
        * :class:`~kailash.runtime.distributed.TaskQueue` for ``redis://``
          or ``rediss://`` URLs.
        * :class:`~kailash.infrastructure.task_queue.SQLTaskQueue` for
          ``postgresql://``, ``mysql://``, or ``sqlite://`` URLs.

    Raises
    ------
    ValueError
        If the URL scheme is not recognized.

    URL Schemes
    -----------
    redis://   → Redis-backed TaskQueue (requires ``redis`` package)
    rediss://  → Redis-backed TaskQueue with TLS
    postgresql:// → SQL-backed SQLTaskQueue via asyncpg
    postgres://   → SQL-backed SQLTaskQueue via asyncpg
    mysql://      → SQL-backed SQLTaskQueue via aiomysql
    sqlite:///    → SQL-backed SQLTaskQueue via aiosqlite
    """
    url = queue_url or resolve_queue_url()
    if not url:
        logger.debug("No queue URL configured -- task queue disabled (Level 0/1)")
        return None

    if url.startswith(("redis://", "rediss://")):
        logger.info("Creating Redis-backed TaskQueue from URL")
        from kailash.runtime.distributed import TaskQueue

        return TaskQueue(redis_url=url)

    # SQL-backed queue: any URL that ConnectionManager understands
    url_lower = url.lower()
    if url_lower.startswith(
        (
            "postgresql://",
            "postgresql+",
            "postgres://",
            "mysql://",
            "mysql+",
            "sqlite://",
        )
    ):
        logger.info("Creating SQL-backed SQLTaskQueue from URL")
        from kailash.db.connection import ConnectionManager
        from kailash.infrastructure.task_queue import SQLTaskQueue

        conn = ConnectionManager(url)
        await conn.initialize()
        queue = SQLTaskQueue(conn)
        await queue.initialize()
        return queue

    # Check for plain file paths (treated as SQLite by ConnectionManager)
    import re

    if url.startswith(("/", "./", "../")) or not re.match(
        r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url
    ):
        logger.info("Creating SQL-backed SQLTaskQueue from file path (SQLite)")
        from kailash.db.connection import ConnectionManager
        from kailash.infrastructure.task_queue import SQLTaskQueue

        conn = ConnectionManager(url)
        await conn.initialize()
        queue = SQLTaskQueue(conn)
        await queue.initialize()
        return queue

    scheme = url.split("://", 1)[0]
    raise ValueError(
        f"Unsupported queue URL scheme '{scheme}'. "
        f"Supported: redis, rediss, postgresql, mysql, sqlite, or a file path."
    )
