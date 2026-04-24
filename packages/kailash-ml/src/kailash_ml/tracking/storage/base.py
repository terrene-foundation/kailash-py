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

    # ------------------------------------------------------------------
    # Audit + GDPR (spec §8.2 + §8.4 — W15)
    # ------------------------------------------------------------------
    #
    # Audit rows are immutable: every backend MUST install a DDL-level
    # defense (trigger, revoke, or equivalent) that blocks UPDATE and
    # DELETE on the audit table. The erasure path therefore MUST NOT
    # attempt to rewrite existing audit rows — it appends a new row
    # with the erasure event and fingerprinted subject id, per
    # ``rules/event-payload-classification.md`` §2.

    async def insert_audit_row(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        timestamp: str,
        resource_kind: str,
        resource_id: str,
        action: str,
        prev_state: Optional[str] = None,
        new_state: Optional[str] = None,
    ) -> None:
        """Append one audit row. Never mutates existing rows."""
        ...

    async def list_audit_rows(
        self,
        *,
        tenant_id: str,
        actor_id: Optional[str] = None,
        resource_kind: Optional[str] = None,
        resource_id: Optional[str] = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Forensic read over ``_kml_audit`` (indexed on
        ``(tenant_id, actor_id, timestamp)``)."""
        ...

    async def register_run_subjects(
        self,
        *,
        tenant_id: str,
        run_id: str,
        subject_ids: Sequence[str],
    ) -> None:
        """Attach one or more ``data_subject_id`` values to a run so GDPR
        erasure can locate them (spec §8.4). Idempotent."""
        ...

    async def list_subject_runs(
        self,
        *,
        tenant_id: str,
        subject_id: str,
    ) -> list[str]:
        """Return the run_ids associated with ``subject_id`` for the tenant."""
        ...

    async def erase_subject_content(
        self,
        *,
        tenant_id: str,
        subject_id: str,
    ) -> dict[str, int]:
        """Delete params / metrics / artifacts / tags / model-versions
        / subject-links for every run associated with ``subject_id`` on
        the tenant. Audit rows MUST NOT be touched. Returns counters
        ``{resource_kind: rows_deleted}``; callers serialise those
        counters into the new erasure audit row."""
        ...

    # ------------------------------------------------------------------
    # Model registry (spec ``ml-registry.md`` §3-§7 — W16)
    # ------------------------------------------------------------------
    #
    # The run-scoped ``insert_model_version`` above (spec §4.5) remains
    # the per-run snapshot surface used by ``ExperimentRun.log_model``.
    # The tenant-scoped ``insert_model_registration`` below is the
    # :class:`ModelRegistry` primitive: it assigns the next
    # ``(tenant_id, name)`` integer-monotonic version atomically inside
    # a single transaction per ``ml-registry.md`` §3.2 + §7.2.

    async def insert_model_registration(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        name: str,
        format: str,
        artifact_uri: str,
        artifact_sha256: str,
        signature_json: str,
        signature_sha256: str,
        lineage_run_id: str,
        lineage_dataset_hash: str,
        lineage_code_sha: str,
        lineage_parent_version_id: Optional[str],
        idempotency_key: str,
        is_golden: bool,
        onnx_status: Optional[str],
        onnx_unsupported_ops: Optional[str],
        onnx_opset_imports: Optional[str],
        ort_extensions: Optional[str],
        metadata_json: Optional[str],
        created_at: str,
    ) -> dict[str, Any]:
        """Atomically assign the next version and insert one row.

        Returns the inserted row as a dict (including the assigned
        ``version``). The backend computes the next integer inside the
        INSERT using ``COALESCE(MAX(version), 0) + 1`` filtered by
        ``(tenant_id, name)`` so two concurrent callers cannot observe
        the same stale ``max`` and collide on the unique index.
        """
        ...

    async def find_model_registration_by_idempotency_key(
        self,
        *,
        tenant_id: str,
        name: str,
        idempotency_key: str,
    ) -> Optional[dict[str, Any]]:
        """Return an existing version with the same ``idempotency_key``
        under ``(tenant_id, name)``, or ``None``. Implements ``ml-registry.md``
        §7.3 dedup. The key is caller-supplied (defaulting to
        ``sha256(dataset_hash + code_sha + signature_json)``)."""
        ...

    async def get_model_version(
        self,
        *,
        tenant_id: str,
        name: str,
        version: int,
    ) -> Optional[dict[str, Any]]:
        """Look up a registered version, or ``None`` if absent."""
        ...

    async def list_model_versions_by_name(
        self,
        *,
        tenant_id: str,
        name: str,
    ) -> list[dict[str, Any]]:
        """Every registered version for ``(tenant_id, name)`` ordered
        by ``version`` ascending."""
        ...

    async def get_model_version_by_id(
        self,
        *,
        tenant_id: str,
        version_id: str,
    ) -> Optional[dict[str, Any]]:
        """Look up a version row by its UUID, tenant-scoped.

        Used by alias resolution (``_kml_model_aliases.model_version_id``
        → ``_kml_model_versions`` row) and the lineage-DAG walk. The
        tenant filter is the § cross-tenant refusal invariant:
        aliases/lineage in tenant B MUST NOT resolve rows written under
        tenant A (``ml-registry.md`` §6.3).
        """
        ...

    # ------------------------------------------------------------------
    # Registry aliases (spec ``ml-registry.md`` §4 — W18)
    # ------------------------------------------------------------------
    #
    # Aliases are mutable pointers. One row per
    # ``(tenant_id, model_name, alias)``; the audit table is the
    # authoritative history of transitions. ``cleared_at IS NULL``
    # distinguishes the active pointer from the soft-deleted state
    # (§4.1 MUST 5). ``sequence_num`` bumps on every mutation so
    # concurrent set operations resolve last-writer-wins (§4.1 MUST 3).

    async def upsert_alias(
        self,
        *,
        tenant_id: str,
        model_name: str,
        alias: str,
        model_version_id: str,
        actor_id: str,
        set_at: str,
    ) -> dict[str, Any]:
        """Point ``alias`` at ``model_version_id`` under the tenant.

        Atomically inserts-or-updates the ``(tenant_id, model_name,
        alias)`` row. Returns a dict with:

        - ``prev_model_version_id`` — the version the alias pointed at
          before this call, or ``None`` if the alias was absent /
          previously cleared.
        - ``new_model_version_id`` — the version the alias now points
          at (always equal to the input).
        - ``prev_cleared`` — ``True`` if the alias row existed but was
          cleared; ``False`` otherwise.
        - ``sequence_num`` — the incremented LWW counter.
        """
        ...

    async def clear_alias(
        self,
        *,
        tenant_id: str,
        model_name: str,
        alias: str,
        actor_id: str,
        cleared_at: str,
    ) -> Optional[dict[str, Any]]:
        """Soft-delete the alias row per §4.1 MUST 5.

        Sets ``cleared_at = now`` on the existing row and bumps
        ``sequence_num``. Returns a dict with ``prev_model_version_id``
        + ``sequence_num``, or ``None`` when no active alias row
        existed (idempotent no-op).
        """
        ...

    async def get_alias(
        self,
        *,
        tenant_id: str,
        model_name: str,
        alias: str,
    ) -> Optional[dict[str, Any]]:
        """Resolve the currently-active alias row.

        Returns the joined registry-version row (every column of
        ``experiment_registry_versions``) the alias points at, or
        ``None`` if the alias is absent OR cleared.
        """
        ...

    async def list_aliases_for_version(
        self,
        *,
        tenant_id: str,
        model_version_id: str,
    ) -> list[str]:
        """Every active alias currently pointing at ``model_version_id``.

        Used by ``list_models`` to aggregate the alias set per version
        row and by ``demote_model`` to decide whether to auto-set
        ``@archived`` (§8.2 — only when no other alias still points at
        the version).
        """
        ...

    async def list_aliases_for_name(
        self,
        *,
        tenant_id: str,
        model_name: str,
        include_cleared: bool = False,
    ) -> list[dict[str, Any]]:
        """Every alias row for ``(tenant_id, model_name)``.

        Defaults to active aliases only; ``include_cleared=True``
        returns the full history (including soft-deleted rows) for
        diagnostic UIs. Rows carry ``alias``, ``model_version_id``,
        ``set_at``, ``cleared_at``, ``actor_id``, ``sequence_num``.
        """
        ...

    # ------------------------------------------------------------------
    # Registry queries (spec ``ml-registry.md`` §9 — W18)
    # ------------------------------------------------------------------

    async def list_registry_versions(
        self,
        *,
        tenant_id: str,
        name: Optional[str] = None,
        alias: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Tenant-scoped version listing with optional filters.

        - ``name`` filters to a single model name.
        - ``alias`` restricts to versions currently holding that alias
          (join through ``experiment_registry_aliases`` where
          ``cleared_at IS NULL``).
        """
        ...

    async def search_registry_versions(
        self,
        *,
        tenant_id: str,
        where_sql: str,
        params: Sequence[Any],
        order_by_sql: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Execute a validated ``SELECT * FROM experiment_registry_versions
        WHERE tenant_id = ? AND {where_sql} ORDER BY {order_by_sql} LIMIT ?``.

        The caller (:meth:`ModelRegistry.search_models`) validates
        ``where_sql`` + ``order_by_sql`` against a strict allowlist and
        identifier regex (``rules/dataflow-identifier-safety.md`` MUST
        Rule 1). Backends MUST NOT interpolate anything besides
        ``tenant_id`` into the final statement beyond the caller-
        supplied fragments.
        """
        ...
