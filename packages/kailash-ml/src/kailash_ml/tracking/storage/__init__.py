# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Storage backends for the ``km.track()`` experiment tracker.

W14b split the monolithic ``sqlite_backend.py`` into:

- :mod:`kailash_ml.tracking.storage.base` — the
  :class:`AbstractTrackerStore` Protocol every backend satisfies.
- :mod:`kailash_ml.tracking.storage.sqlite` — SQLite via
  :class:`kailash.core.pool.AsyncSQLitePool`.
- :mod:`kailash_ml.tracking.storage.postgres` — PostgreSQL via
  :class:`kailash.db.connection.ConnectionManager`.

Per ``specs/ml-tracking.md`` §6 the two backends MUST produce
byte-identical ``list_runs`` / ``list_metrics`` / ``list_artifacts``
output for the same run history; the parity test in
``tests/integration/test_tracker_store_parity.py`` is the structural
defense.
"""
from __future__ import annotations

from kailash_ml.tracking.storage.base import AbstractTrackerStore
from kailash_ml.tracking.storage.postgres import PostgresTrackerStore
from kailash_ml.tracking.storage.sqlite import SqliteTrackerStore

__all__ = [
    "AbstractTrackerStore",
    "PostgresTrackerStore",
    "SqliteTrackerStore",
]
