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

from kailash_ml.tracking.runner import (
    ExperimentRun,
    RunStatus,
    _current_run as current_run,
    track,
)
from kailash_ml.tracking.sqlite_backend import SQLiteTrackerBackend

__all__ = [
    "ExperimentRun",
    "RunStatus",
    "SQLiteTrackerBackend",
    "track",
    "current_run",
]
