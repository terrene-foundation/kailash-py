# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""kailash-ml tracking module — ``km.track()`` experiment runs.

Implements the Phase 6 / ``specs/ml-tracking.md`` §2 contract for the
``km.track()`` async-context entry point. The public surface is:

- :class:`ExperimentRun` — async context manager yielded by ``km.track()``
- :class:`SQLiteTrackerBackend` — the default SQLite-backed store
- :func:`track` — the async-context factory (``km.track`` is an alias)

The SQLite backend is the default because it closes the user-reported
pain point #8 in ``workspaces/kailash-ml-audit/analysis/00-synthesis-redesign-proposal.md``
(requiring external tracker infrastructure for single-laptop workflows).
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
from kailash_ml.tracking.runner import ExperimentRun, RunStatus
from kailash_ml.tracking.runner import _current_run
from kailash_ml.tracking.runner import _current_run as current_run
from kailash_ml.tracking.runner import track
from kailash_ml.tracking.sqlite_backend import SQLiteTrackerBackend
from kailash_ml.tracking.tracker import ExperimentTracker


def get_current_run() -> Optional[ExperimentRun]:
    """Return the ambient :class:`ExperimentRun`, or ``None``.

    Public accessor for the `km.track()` contextvar per
    ``specs/ml-tracking.md`` §10.1. Autolog, DL diagnostics, and RL
    diagnostics consume this to discover the run they should log
    against without callers threading the run id manually.
    """
    return _current_run.get()


__all__ = [
    "EnvDelta",
    "ExperimentRun",
    "ExperimentTracker",
    "FilterParseError",
    "MetricDelta",
    "ParamDelta",
    "RunDiff",
    "RunRecord",
    "RunStatus",
    "SQLiteTrackerBackend",
    "track",
    "current_run",
    "get_current_run",
]
