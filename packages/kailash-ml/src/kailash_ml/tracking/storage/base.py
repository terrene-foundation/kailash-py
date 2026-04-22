# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Abstract tracker-store contract.

Every backend (SQLite, PostgreSQL, future MySQL) MUST satisfy
:class:`AbstractTrackerStore` at runtime. The Protocol captures the
full surface consumed by :class:`kailash_ml.tracking.runner.ExperimentRun`
and :class:`kailash_ml.tracking.tracker.ExperimentTracker`.

The Protocol is ``@runtime_checkable`` so `/redteam` (and the
Tier 2 parity test) can assert ``isinstance(store, AbstractTrackerStore)``
without either backend inheriting from the Protocol class (structural
typing).

Per ``specs/ml-tracking.md`` §6 the two default backends must be
behaviorally interchangeable — same ``list_runs`` output for the
same run history, same ``list_metrics`` ordering, same ``list_tags``
map shape, etc. The parity test in
``tests/integration/test_tracker_store_parity.py`` is the structural
defense against drift.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Protocol, Sequence, runtime_checkable

__all__ = ["AbstractTrackerStore"]


@runtime_checkable
class AbstractTrackerStore(Protocol):
    """Behavioral contract every tracker backend MUST satisfy.

    Implementations MUST be safe to re-enter via ``await initialize()``
    — the method MUST be idempotent; callers (notably
    :class:`ExperimentRun`) invoke it implicitly at the start of every
    public method so the backend can be constructed eagerly and
    lazily initialise its schema.

    Every method is async — the tracker runs inside ``asyncio`` event
    loops (Lightning Trainer, Jupyter, CLI ``asyncio.run``) and a sync
    leak would block the loop.

    :attr:`artifact_root` exposes the filesystem root beneath which
    ``log_artifact`` materialises blobs (W12 — spec §4.3). The SQLite
    backend places blobs next to the DB file; the Postgres backend
    accepts an explicit artifact root at construction. ``None`` is
    returned when the backend has no local root (future S3-backed
    stores), in which case callers MUST supply their own artifact
    writer (W17).
    """

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def artifact_root(self) -> Optional[str]:
        """Filesystem root for ``log_artifact`` blobs, or ``None``."""
        ...

    async def initialize(self) -> None:
        """Create schema + indexes; idempotent across re-entries."""
        ...

    async def close(self) -> None:
        """Release all underlying connections; idempotent."""
        ...

    # ------------------------------------------------------------------
    # Run-level writes (spec §2.4 + §6.3)
    # ------------------------------------------------------------------

    async def insert_run(self, row: Mapping[str, Any]) -> None:
        """Insert a run record. ``row`` MUST carry every schema column."""
        ...

    async def update_run(self, run_id: str, fields: Mapping[str, Any]) -> None:
        """Patch a subset of columns on an existing run row."""
        ...

    async def set_params(self, run_id: str, params: Mapping[str, Any]) -> None:
        """Merge-and-overwrite ``params`` JSON on the run row."""
        ...

    # ------------------------------------------------------------------
    # Run-level reads (spec §5.1 + §5.2)
    # ------------------------------------------------------------------

    async def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        """Return one run row as a dict, or ``None`` if absent."""
        ...

    async def list_runs(self, experiment: Optional[str] = None) -> list[dict[str, Any]]:
        """All runs, optionally filtered by experiment name."""
        ...

    async def query_runs(
        self,
        *,
        experiment: Optional[str] = None,
        tenant_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Typed ``list_runs`` variant with spec §5.1 kwargs."""
        ...

    async def search_runs_raw(
        self, sql: str, params: Sequence[Any]
    ) -> list[dict[str, Any]]:
        """Execute a static-template SELECT built by
        :mod:`kailash_ml.tracking.query`."""
        ...

    async def list_experiments_summary(
        self, *, tenant_id: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Aggregate counts per experiment, tenant-scoped when given."""
        ...

    # ------------------------------------------------------------------
    # Metric writes/reads (spec §4.1)
    # ------------------------------------------------------------------

    async def append_metric(
        self,
        run_id: str,
        key: str,
        value: float,
        step: Optional[int],
        timestamp: str,
    ) -> None:
        """Append-only single metric row."""
        ...

    async def append_metrics_batch(
        self,
        run_id: str,
        rows: list[tuple[str, float, Optional[int], str]],
    ) -> None:
        """Append many metric rows atomically."""
        ...

    async def list_metrics(self, run_id: str) -> list[dict[str, Any]]:
        """Every metric row for a run ordered by ``(key, step)``."""
        ...

    # ------------------------------------------------------------------
    # Artifact writes/reads (spec §4.3)
    # ------------------------------------------------------------------

    async def insert_artifact(
        self,
        run_id: str,
        name: str,
        sha256: str,
        content_type: Optional[str],
        size_bytes: int,
        storage_uri: str,
        created_at: str,
    ) -> bool:
        """Insert, dedupe on ``(run_id, name, sha256)``. Return ``True``
        on new row; ``False`` when the row already existed."""
        ...

    async def list_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        """Artifact rows ordered by ``created_at, name``."""
        ...

    # ------------------------------------------------------------------
    # Tag writes/reads (spec §4.2)
    # ------------------------------------------------------------------

    async def upsert_tag(self, run_id: str, key: str, value: str) -> None:
        """Set one tag; key is unique per run."""
        ...

    async def upsert_tags(self, run_id: str, tags: Mapping[str, str]) -> None:
        """Set many tags atomically."""
        ...

    async def list_tags(self, run_id: str) -> dict[str, str]:
        """Tag map for a run."""
        ...

    # ------------------------------------------------------------------
    # Model-version writes/reads (spec §4.5)
    # ------------------------------------------------------------------

    async def insert_model_version(
        self,
        run_id: str,
        name: str,
        format: str,
        artifact_sha: str,
        signature_json: Optional[str],
        lineage_json: Optional[str],
        created_at: str,
    ) -> None:
        """Insert a run-scoped model-version snapshot."""
        ...

    async def list_model_versions(self, run_id: str) -> list[dict[str, Any]]:
        """Model-version rows ordered by ``created_at, name``."""
        ...
