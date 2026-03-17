# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Dialect-portable infrastructure backends for Kailash SDK.

Provides database-backed implementations of the EventStore, Checkpoint,
and Dead Letter Queue storage backends using the :mod:`kailash.db`
ConnectionManager and QueryDialect abstraction layer.

All SQL uses canonical ``?`` placeholders — ConnectionManager translates
to the target dialect automatically.

Usage::

    from kailash.db import ConnectionManager
    from kailash.infrastructure import (
        DBCheckpointStore,
        DBDeadLetterQueue,
        DBEventStoreBackend,
    )

    mgr = ConnectionManager("sqlite:///app.db")
    await mgr.initialize()

    events = DBEventStoreBackend(mgr)
    await events.initialize()

    checkpoints = DBCheckpointStore(mgr)
    await checkpoints.initialize()

    dlq = DBDeadLetterQueue(mgr)
    await dlq.initialize()
"""

from __future__ import annotations

from kailash.infrastructure.checkpoint_store import DBCheckpointStore
from kailash.infrastructure.dlq import DBDeadLetterQueue
from kailash.infrastructure.event_store import DBEventStoreBackend

__all__ = [
    "DBCheckpointStore",
    "DBDeadLetterQueue",
    "DBEventStoreBackend",
]
