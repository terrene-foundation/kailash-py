# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Dialect-portable infrastructure backends for Kailash SDK.

Provides database-backed implementations of the EventStore, Checkpoint,
Dead Letter Queue, ExecutionStore, and IdempotencyStore storage backends
using the :mod:`kailash.db` ConnectionManager and QueryDialect abstraction
layer.

All SQL uses canonical ``?`` placeholders — ConnectionManager translates
to the target dialect automatically.

Usage::

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
"""

from __future__ import annotations

from kailash.infrastructure.checkpoint_store import DBCheckpointStore
from kailash.infrastructure.dlq import DBDeadLetterQueue
from kailash.infrastructure.event_store import DBEventStoreBackend
from kailash.infrastructure.execution_store import (
    DBExecutionStore,
    InMemoryExecutionStore,
)
from kailash.infrastructure.idempotency_store import DBIdempotencyStore

__all__ = [
    "DBCheckpointStore",
    "DBDeadLetterQueue",
    "DBEventStoreBackend",
    "DBExecutionStore",
    "DBIdempotencyStore",
    "InMemoryExecutionStore",
]
