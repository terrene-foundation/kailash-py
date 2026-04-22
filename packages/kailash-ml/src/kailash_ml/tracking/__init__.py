# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""kailash-ml tracking module — ``km.track()`` experiment runs.

Implements the Phase 6 / ``specs/ml-tracking.md`` §2 contract for the
``km.track()`` async-context entry point. The public surface is:

- :class:`ExperimentRun` — async context manager yielded by ``km.track()``
- :class:`AbstractTrackerStore` — Protocol both backends satisfy
- :class:`SqliteTrackerStore` — SQLite via :class:`AsyncSQLitePool`
  (default — W14b ``specs/ml-tracking.md`` §6.1)
- :class:`PostgresTrackerStore` — PostgreSQL via
  :class:`kailash.db.connection.ConnectionManager` (production multi-user)
- :func:`track` — the async-context factory (``km.track`` is an alias)

The SQLite backend is the default because it closes user pain point
#8 in ``workspaces/kailash-ml-audit/analysis/00-synthesis-redesign-proposal.md``
(no external tracker infrastructure for single-laptop workflows).
"""
from __future__ import annotations

from typing import Optional

from kailash_ml.tracking.query import (
    EnvDelta,
    FilterParseError,
    MetricDelta,
    ParamDelta,
    RunDiff,
    RunRecord,
)
from kailash_ml.tracking.runner import ExperimentRun, RunStatus, _current_actor_id
from kailash_ml.tracking.runner import _current_run
from kailash_ml.tracking.runner import _current_run as current_run
from kailash_ml.tracking.runner import _current_tenant_id, track
from kailash_ml.tracking.storage import (
    AbstractTrackerStore,
    PostgresTrackerStore,
    SqliteTrackerStore,
)
from kailash_ml.tracking.tracker import ExperimentTracker


def get_current_run() -> Optional[ExperimentRun]:
    """Return the ambient :class:`ExperimentRun`, or ``None``.

    Public accessor for the `km.track()` contextvar per
    ``specs/ml-tracking.md`` §10.1. Autolog, DL diagnostics, and RL
    diagnostics consume this to discover the run they should log
    against without callers threading the run id manually.
    """
    return _current_run.get()


def get_current_tenant_id() -> Optional[str]:
    """Return the ambient tenant_id for the active ``km.track()`` scope.

    Public accessor per ``specs/ml-tracking.md`` §10.2. Query
    primitives that default ``tenant_id=None`` route through this to
    read the session-level tenant without callers plumbing it per call.
    Returns ``None`` when no ``km.track(...)`` scope is active AND no
    ``KAILASH_TENANT_ID`` env var resolution has fired — callers that
    require tenant scoping check for ``None`` and raise
    :class:`TenantRequiredError` in multi-tenant strict mode (W15).
    """
    return _current_tenant_id.get()


def get_current_actor_id() -> Optional[str]:
    """Return the ambient actor_id for the active ``km.track()`` scope.

    Public accessor per ``specs/ml-tracking.md`` §8.1. Every mutation
    primitive on :class:`ExperimentRun` persists the actor read through
    this accessor — per HIGH-4 round-1 finding the actor is a
    session-level property, NOT a per-call kwarg. The MCP surface
    (§11) is the only caller that reads actor explicitly; every other
    consumer routes through this accessor.
    """
    return _current_actor_id.get()


__all__ = [
    "AbstractTrackerStore",
    "EnvDelta",
    "ExperimentRun",
    "ExperimentTracker",
    "FilterParseError",
    "MetricDelta",
    "ParamDelta",
    "PostgresTrackerStore",
    "RunDiff",
    "RunRecord",
    "RunStatus",
    "SqliteTrackerStore",
    "current_run",
    "get_current_actor_id",
    "get_current_run",
    "get_current_tenant_id",
    "track",
]
