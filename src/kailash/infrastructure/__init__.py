# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Dialect-portable infrastructure backends for Kailash SDK.

Provides database-backed implementations of the EventStore, Checkpoint,
Dead Letter Queue, ExecutionStore, and IdempotencyStore storage backends
using the :mod:`kailash.db` ConnectionManager and QueryDialect abstraction
layer.

All SQL uses canonical ``?`` placeholders — ConnectionManager translates
to the target dialect automatically.

Usage (manual wiring)::

    from kailash.db import ConnectionManager
    from kailash.infrastructure import (
        DBCheckpointStore,
        DBDeadLetterQueue,
        DBEventStoreBackend,
        DBExecutionStore,
        DBIdempotencyStore,
        InMemoryExecutionStore,
    )

    mgr = ConnectionManager("sqlite:///app.db")
    await mgr.initialize()

    events = DBEventStoreBackend(mgr)
    await events.initialize()

    checkpoints = DBCheckpointStore(mgr)
    await checkpoints.initialize()

    dlq = DBDeadLetterQueue(mgr)
    await dlq.initialize()

    executions = DBExecutionStore(mgr)
    await executions.initialize()

    idempotency = DBIdempotencyStore(mgr)
    await idempotency.initialize()

Usage (auto-detection via StoreFactory)::

    from kailash.infrastructure import StoreFactory

    factory = StoreFactory()           # auto-detects from KAILASH_DATABASE_URL
    event_store = await factory.create_event_store()
    checkpoint  = await factory.create_checkpoint_store()
    dlq         = await factory.create_dlq()
    exec_store  = await factory.create_execution_store()
    idempotency = await factory.create_idempotency_store()
    # ... use stores ...
    await factory.close()
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from kailash.infrastructure.checkpoint_store import DBCheckpointStore
from kailash.infrastructure.dlq import DBDeadLetterQueue
from kailash.infrastructure.event_store import DBEventStoreBackend
from kailash.infrastructure.execution_store import (
    DBExecutionStore,
    InMemoryExecutionStore,
)
from kailash.infrastructure.factory import SCHEMA_VERSION, StoreFactory
from kailash.infrastructure.history_store import (
    DowngradeRefusedError,
    PostgresHistoryStore,
    SQLiteHistoryStore,
    WorkflowHistoryStore,
)
from kailash.infrastructure.idempotency import IdempotentExecutor
from kailash.infrastructure.idempotency_store import DBIdempotencyStore
from kailash.infrastructure.lock_store import (
    DBLockBackend,
    DistributedLock,
    Lease,
    LockAcquireError,
    LockBackend,
)
from kailash.infrastructure.queue_factory import create_task_queue
from kailash.infrastructure.task_queue import SQLTaskMessage, SQLTaskQueue
from kailash.infrastructure.worker_registry import SQLWorkerRegistry

if TYPE_CHECKING:
    # RedisLockBackend lives behind the [redis] extra and is imported lazily
    # via __getattr__ so a slim-core install does not pay for redis.asyncio.
    # The TYPE_CHECKING import keeps it resolvable to static analysers
    # (CodeQL py/undefined-export, mypy --strict, Sphinx autodoc) without
    # dragging the optional dep into the eager import path
    # (rules/orphan-detection.md § 6b).
    from kailash.infrastructure.lock_store_redis import RedisLockBackend

__all__ = [
    "DBCheckpointStore",
    "DBDeadLetterQueue",
    "DBEventStoreBackend",
    "DBExecutionStore",
    "DBIdempotencyStore",
    "DBLockBackend",
    "DistributedLock",
    "DowngradeRefusedError",
    "IdempotentExecutor",
    "InMemoryExecutionStore",
    "Lease",
    "LockAcquireError",
    "LockBackend",
    "PostgresHistoryStore",
    "RedisLockBackend",
    "SCHEMA_VERSION",
    "SQLTaskMessage",
    "SQLTaskQueue",
    "SQLWorkerRegistry",
    "SQLiteHistoryStore",
    "StoreFactory",
    "WorkflowHistoryStore",
    "create_task_queue",
]


def __getattr__(name: str) -> Any:
    """Lazily resolve the Redis-backed lock backend behind the [redis] extra.

    ``from kailash.infrastructure import RedisLockBackend`` triggers the
    import of :mod:`kailash.infrastructure.lock_store_redis`, which guards
    ``redis.asyncio`` with a typed, actionable ImportError if the ``[redis]``
    extra is missing.
    """
    if name == "RedisLockBackend":
        from kailash.infrastructure.lock_store_redis import RedisLockBackend

        return RedisLockBackend
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
