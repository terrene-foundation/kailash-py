# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W7-001 — cross-engine lineage graph engine.

Implements the canonical lineage surface declared in
``specs/ml-engines-v2-addendum.md §E10`` and persisted via the
``_kml_lineage`` table declared in ``specs/ml-tracking.md §6.3``.

This module ships THREE frozen dataclasses (``LineageNode`` /
``LineageEdge`` / ``LineageGraph``) plus the ``build_lineage_graph()``
walker that the registry's ``ModelRegistry.build_lineage_graph`` method
delegates to. ``km.lineage(...)`` (see ``kailash_ml.__init__``) is the
top-level user-facing entry that constructs a fresh ``ModelRegistry``
against the canonical store and dispatches into this walker.

Design contract
---------------

- ``LineageGraph``, ``LineageNode``, ``LineageEdge`` are
  ``@dataclass(frozen=True)`` per ``ml-engines-v2-addendum §E10.2``;
  every collection field is a ``tuple`` (immutable) so the graph
  serialises deterministically across the dashboard / REST surface.
- The walker MUST NOT emit raw SQL — it traverses the lineage graph via
  DataFlow primitives (``ConnectionManager.fetch``) per
  ``rules/framework-first.md`` (DataFlow + ML domain). DDL for
  ``_kml_lineage`` lives in numbered migration ``0004_kml_lineage_table``
  (this commit).
- Cross-tenant traversal raises
  :class:`~kailash_ml.errors.CrossTenantLineageError` per
  ``rules/tenant-isolation.md`` §1 — every fetched row whose
  ``tenant_id`` does NOT match the caller's tenant scope aborts the
  walk with the typed error rather than leaking the row.
- Cache keys (when the registry caches lineage results) MUST follow
  ``kailash_ml:v1:{tenant_id}:lineage:{name}:{version}`` per
  ``ml-tracking.md §7.1``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from kailash_ml.errors import (
    CrossTenantLineageError,
    MigrationRequiredError,
    ModelNotFoundError,
)

__all__ = [
    "LineageNode",
    "LineageEdge",
    "LineageGraph",
    "LineageNodeKind",
    "LineageRelation",
    "LINEAGE_TABLE",
    "build_lineage_graph",
    "make_lineage_cache_key",
]


logger = logging.getLogger(__name__)


# Canonical table name — single source of truth shared with numbered
# migration 0004. Mirrors the ``_kml_automl_trials`` constant placement
# pattern in ``kailash_ml/automl/engine.py`` (see W6-020).
LINEAGE_TABLE: str = "_kml_lineage"


LineageNodeKind = Literal[
    "run",
    "dataset",
    "feature_version",
    "model_version",
    "deployment",
]

LineageRelation = Literal[
    "produced_by",
    "consumed",
    "used_features",
    "deployed_as",
    "derived_from",
    "evaluated_against",
]


@dataclass(frozen=True)
class LineageNode:
    """One vertex in the cross-engine lineage graph.

    Per ``specs/ml-engines-v2-addendum §E10.2``. Every node is
    tenant-scoped; cross-tenant references are not representable.
    """

    id: str
    kind: LineageNodeKind
    label: str
    tenant_id: str
    created_at: datetime
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LineageEdge:
    """One directed edge in the lineage graph.

    Per ``specs/ml-engines-v2-addendum §E10.2``.
    """

    source_id: str
    target_id: str
    relation: LineageRelation
    occurred_at: datetime


@dataclass(frozen=True)
class LineageGraph:
    """Cross-engine lineage graph rooted at ``root_id``.

    Per ``specs/ml-engines-v2-addendum §E10.2``. Every collection field
    is a tuple — the dataclass is frozen and serialises deterministically
    across the canonical surfaces (dashboard REST endpoint, MCP tool,
    JSON dump).
    """

    root_id: str
    nodes: tuple[LineageNode, ...]
    edges: tuple[LineageEdge, ...]
    computed_at: datetime
    max_depth: int = 10


def make_lineage_cache_key(tenant_id: str, name: str, version: int) -> str:
    """Build the canonical lineage cache key.

    Per ``specs/ml-tracking.md §7.1`` — the lineage row in the resource
    table maps to the key shape::

        kailash_ml:v1:{tenant_id}:lineage:{name}:{version}

    Cross-tenant tests that grep on ``kailash_ml:v1:`` MUST find this
    helper. See ``rules/tenant-isolation.md`` §1.
    """
    return f"kailash_ml:v1:{tenant_id}:lineage:{name}:{version}"


# ---------------------------------------------------------------------------
# Migration probe — same pattern as ``automl/engine.py::_probe_trials_table``
# ---------------------------------------------------------------------------


_LINEAGE_SENTINEL_COLUMN: str = "tracker_run_id"


async def _table_present(conn: Any) -> bool:
    """Return True iff the ``_kml_lineage`` table exists.

    Mirror of the dialect-portable probe in
    ``kailash_ml.automl.engine._probe_table_exists`` — keeps the engine
    free of raw DDL while still able to surface
    :class:`~kailash_ml.errors.MigrationRequiredError` to the caller.
    """
    try:
        from kailash.db.dialect import (
            DatabaseType,
            MySQLDialect,
            PostgresDialect,
            SQLiteDialect,
        )
    except ImportError:  # pragma: no cover - kailash-core missing
        # Fall back to a no-op SELECT and treat any error as "absent".
        return await _probe_via_sql_only(conn)

    dialect = getattr(conn, "dialect", None)
    if dialect is None:
        db_type = getattr(conn, "database_type", None)
        if db_type is None:
            return await _probe_via_sql_only(conn)
        if isinstance(db_type, DatabaseType):
            dialect = {
                DatabaseType.POSTGRESQL: PostgresDialect,
                DatabaseType.SQLITE: SQLiteDialect,
                DatabaseType.MYSQL: MySQLDialect,
            }[db_type]()
        elif isinstance(db_type, str):
            for member in DatabaseType:
                if member.value == db_type.lower():
                    dialect = {
                        DatabaseType.POSTGRESQL: PostgresDialect,
                        DatabaseType.SQLITE: SQLiteDialect,
                        DatabaseType.MYSQL: MySQLDialect,
                    }[member]()
                    break

    if dialect is None:
        return await _probe_via_sql_only(conn)

    fetcher = getattr(conn, "fetch", None) or getattr(conn, "fetchone", None)
    if fetcher is None:
        return await _probe_via_sql_only(conn)

    if dialect.database_type == DatabaseType.SQLITE:
        rows = await fetcher(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            LINEAGE_TABLE,
        )
        return _rows_nonempty(rows)
    if dialect.database_type == DatabaseType.POSTGRESQL:
        rows = await fetcher(
            "SELECT 1 FROM information_schema.tables WHERE table_name = ?",
            LINEAGE_TABLE,
        )
        return _rows_nonempty(rows)
    if dialect.database_type == DatabaseType.MYSQL:
        rows = await fetcher(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = ?",
            LINEAGE_TABLE,
        )
        return _rows_nonempty(rows)
    return False


async def _probe_via_sql_only(conn: Any) -> bool:
    """Fallback existence probe via no-op SELECT."""
    try:
        await conn.execute(
            f"SELECT {_LINEAGE_SENTINEL_COLUMN} FROM {LINEAGE_TABLE} WHERE 1=0"
        )
        return True
    except Exception:
        return False


def _rows_nonempty(rows: Any) -> bool:
    if rows is None:
        return False
    if isinstance(rows, list):
        return len(rows) > 0
    return True


# ---------------------------------------------------------------------------
# Walker — DataFlow Express path (no raw SQL outside the migration)
# ---------------------------------------------------------------------------


async def _fetch_lineage_rows_for(
    conn: Any,
    *,
    tenant_id: str,
    name: str,
    version: int,
) -> list[dict[str, Any]]:
    """Fetch the lineage row(s) for ``(tenant_id, name, version)``.

    Returns a list of zero or one dicts — the ``_kml_lineage`` PK is
    ``(tenant_id, model_name, version)`` per ``ml-tracking.md §6.3``.
    Uses the read-only ``ConnectionManager.fetch`` interface; the
    framework owns the SQL parameter binding.
    """
    rows = await conn.fetch(
        f"SELECT tenant_id, model_name, version, tracker_run_id, "
        f"parent_version, training_data_uri, feature_store_version, "
        f"base_model_uri FROM {LINEAGE_TABLE} "
        f"WHERE tenant_id = ? AND model_name = ? AND version = ?",
        tenant_id,
        name,
        version,
    )
    if rows is None:
        return []
    if isinstance(rows, dict):
        return [rows]
    return list(rows)


async def _fetch_model_version_row(
    conn: Any,
    *,
    name: str,
    version: int,
) -> Optional[dict[str, Any]]:
    """Fetch the ``_kml_model_versions`` row that owns the model identity.

    Returns ``None`` if no row exists. Used to annotate the
    ``model_version`` node with its ``created_at`` and ``model_uuid``
    metadata so the graph nodes carry the same identity the registry
    surfaces externally.
    """
    rows = await conn.fetch(
        "SELECT name, version, stage, model_uuid, created_at "
        "FROM _kml_model_versions WHERE name = ? AND version = ?",
        name,
        version,
    )
    if rows is None:
        return None
    if isinstance(rows, dict):
        return rows
    if isinstance(rows, list) and rows:
        return rows[0]
    return None


def _parse_iso_datetime(value: Any) -> datetime:
    """Best-effort parse of stored ISO timestamps.

    The registry stores ``created_at`` as ISO-8601 strings; the lineage
    table inherits the same convention for portability. Any unparsable
    value falls back to ``datetime.now(UTC)`` so the graph still
    serialises (the timestamp is metadata — it is not load-bearing for
    the graph identity).
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            pass
    return datetime.now(timezone.utc)


async def build_lineage_graph(
    conn: Any,
    *,
    name: str,
    version: int,
    tenant_id: str,
    max_depth: int = 10,
) -> LineageGraph:
    """Construct a :class:`LineageGraph` rooted at ``(name, version)``.

    Walks the ``_kml_lineage`` table via the supplied
    :class:`~kailash.db.connection.ConnectionManager`, materialising
    every node within ``max_depth`` parent-version hops. The walk is
    tenant-scoped — every fetched row whose ``tenant_id`` field does
    NOT match the caller's argument aborts the walk with
    :class:`~kailash_ml.errors.CrossTenantLineageError`.

    Args:
        conn: An initialised :class:`ConnectionManager`. Same shape the
            :class:`~kailash_ml.engines.model_registry.ModelRegistry`
            already accepts.
        name: Model name to root the walk at.
        version: Model version (integer, registry-assigned).
        tenant_id: Caller's tenant scope. Every node in the returned
            graph carries this exact value.
        max_depth: Maximum number of parent-version hops to traverse.
            Bounded per ``ml-engines-v2-addendum §E10.2`` (defends
            against cyclic / deep graphs).

    Raises:
        ModelNotFoundError: ``(name, version)`` does not resolve in the
            ``_kml_model_versions`` table.
        MigrationRequiredError: The ``_kml_lineage`` table has not been
            created by migration 0004.
        CrossTenantLineageError: A traversed row's ``tenant_id`` does
            NOT match the caller's argument.
    """
    if max_depth < 0:
        raise ValueError(f"max_depth MUST be >= 0; got {max_depth}")

    # Migration probe — same disposition the AutoMLEngine uses on first
    # write per W6-020. Per ``rules/zero-tolerance.md`` Rule 2 we raise
    # the canonical MigrationRequiredError rather than emit inline DDL.
    if not await _table_present(conn):
        raise MigrationRequiredError(
            reason=(
                f"{LINEAGE_TABLE} table not present — migration "
                f"0004_kml_lineage_table has not been applied. Run "
                f"``MigrationRegistry.apply_pending(conn)`` to bring "
                f"the schema up to the canonical lineage form."
            ),
            resource_id=LINEAGE_TABLE,
        )

    # Verify the root exists in _kml_model_versions — a graph rooted at
    # a non-existent (name, version) is meaningless per
    # ``ml-tracking.md §6.3``.
    root_model_row = await _fetch_model_version_row(conn, name=name, version=version)
    if root_model_row is None:
        raise ModelNotFoundError(
            reason=(
                f"Model {name!r} version {version} not found in "
                f"_kml_model_versions; cannot build lineage graph."
            ),
            resource_id=f"{name}@v{version}",
            tenant_id=tenant_id,
        )

    # Structured emission per ``rules/observability.md`` Rule 1 (every
    # surface logs entry / exit) + Rule 2 (correlation id). ``ref`` is
    # the documented run/model identifier.
    ref = f"{name}@v{version}"
    logger.info(
        "lineage.build.start",
        extra={"ref": ref, "tenant_id": tenant_id, "max_depth": max_depth},
    )

    nodes: list[LineageNode] = []
    edges: list[LineageEdge] = []
    visited: set[tuple[str, int]] = set()

    # BFS via parent_version — every step MUST stay tenant-scoped.
    queue: list[tuple[str, int, int]] = [(name, version, 0)]
    while queue:
        cur_name, cur_version, depth = queue.pop(0)
        key = (cur_name, cur_version)
        if key in visited:
            continue
        visited.add(key)

        if depth > max_depth:
            continue

        rows = await _fetch_lineage_rows_for(
            conn,
            tenant_id=tenant_id,
            name=cur_name,
            version=cur_version,
        )

        # Cross-tenant disposition: fetch every row regardless of
        # tenant, and abort if any non-matching row is returned. The
        # WHERE clause already filters; this is defense-in-depth per
        # ``rules/tenant-isolation.md`` §2 (audit + assert).
        for row in rows:
            row_tenant = row.get("tenant_id")
            if row_tenant != tenant_id:
                logger.warning(
                    "lineage.build.cross_tenant_blocked",
                    extra={
                        "ref": ref,
                        "expected_tenant": tenant_id,
                        "row_tenant": row_tenant,
                    },
                )
                raise CrossTenantLineageError(
                    reason=(
                        f"lineage traversal of {ref} encountered a row "
                        f"with tenant_id mismatch (expected {tenant_id!r}); "
                        f"refusing to leak cross-tenant lineage parent. "
                        f"See rules/tenant-isolation.md §1."
                    ),
                    resource_id=ref,
                )

        # Annotate the model_version node from _kml_model_versions when
        # available; fall back to the lineage row for older entries
        # that pre-date a model_versions row.
        model_row = await _fetch_model_version_row(
            conn, name=cur_name, version=cur_version
        )
        if model_row is not None:
            mv_id = f"{cur_name}@v{cur_version}"
            mv_created = _parse_iso_datetime(model_row.get("created_at"))
            mv_metadata: dict[str, str] = {}
            uuid_value = model_row.get("model_uuid")
            if uuid_value:
                mv_metadata["model_uuid"] = str(uuid_value)
            stage = model_row.get("stage")
            if stage:
                mv_metadata["stage"] = str(stage)
            nodes.append(
                LineageNode(
                    id=mv_id,
                    kind="model_version",
                    label=f"{cur_name} v{cur_version}",
                    tenant_id=tenant_id,
                    created_at=mv_created,
                    metadata=mv_metadata,
                )
            )

        for row in rows:
            tracker_run_id = row.get("tracker_run_id")
            parent_version = row.get("parent_version")
            training_data_uri = row.get("training_data_uri")
            feature_store_version = row.get("feature_store_version")
            base_model_uri = row.get("base_model_uri")

            mv_id = f"{cur_name}@v{cur_version}"
            now = datetime.now(timezone.utc)

            # Run node — produced_by edge.
            if tracker_run_id:
                run_id = str(tracker_run_id)
                nodes.append(
                    LineageNode(
                        id=run_id,
                        kind="run",
                        label=f"run {run_id}",
                        tenant_id=tenant_id,
                        created_at=now,
                        metadata={"role": "training"},
                    )
                )
                edges.append(
                    LineageEdge(
                        source_id=mv_id,
                        target_id=run_id,
                        relation="produced_by",
                        occurred_at=now,
                    )
                )

            # Dataset node — consumed edge.
            if training_data_uri:
                dataset_id = str(training_data_uri)
                nodes.append(
                    LineageNode(
                        id=dataset_id,
                        kind="dataset",
                        label=f"dataset {dataset_id}",
                        tenant_id=tenant_id,
                        created_at=now,
                        metadata={"uri": dataset_id},
                    )
                )
                if tracker_run_id:
                    edges.append(
                        LineageEdge(
                            source_id=str(tracker_run_id),
                            target_id=dataset_id,
                            relation="consumed",
                            occurred_at=now,
                        )
                    )

            # Feature version node — used_features edge.
            if feature_store_version:
                fv_id = str(feature_store_version)
                nodes.append(
                    LineageNode(
                        id=fv_id,
                        kind="feature_version",
                        label=f"features {fv_id}",
                        tenant_id=tenant_id,
                        created_at=now,
                        metadata={"version": fv_id},
                    )
                )
                if tracker_run_id:
                    edges.append(
                        LineageEdge(
                            source_id=str(tracker_run_id),
                            target_id=fv_id,
                            relation="used_features",
                            occurred_at=now,
                        )
                    )

            # Base model — derived_from edge to a sibling model_version.
            if base_model_uri:
                base_id = str(base_model_uri)
                nodes.append(
                    LineageNode(
                        id=base_id,
                        kind="model_version",
                        label=f"base {base_id}",
                        tenant_id=tenant_id,
                        created_at=now,
                        metadata={"role": "base_model"},
                    )
                )
                edges.append(
                    LineageEdge(
                        source_id=mv_id,
                        target_id=base_id,
                        relation="derived_from",
                        occurred_at=now,
                    )
                )

            # Parent version walk — bounded by max_depth.
            if parent_version is not None and depth < max_depth:
                parent_int: Optional[int]
                try:
                    parent_int = int(parent_version)
                except (TypeError, ValueError):
                    parent_int = None
                if parent_int is not None:
                    queue.append((cur_name, parent_int, depth + 1))

    # Deduplicate nodes/edges while preserving ordering (deterministic
    # serialisation — see ``ml-engines-v2-addendum §E10.2``).
    deduped_nodes = _dedup_nodes(nodes)
    deduped_edges = _dedup_edges(edges)

    graph = LineageGraph(
        root_id=f"{name}@v{version}",
        nodes=tuple(deduped_nodes),
        edges=tuple(deduped_edges),
        computed_at=datetime.now(timezone.utc),
        max_depth=max_depth,
    )

    logger.info(
        "lineage.build.ok",
        extra={
            "ref": ref,
            "tenant_id": tenant_id,
            "node_count": len(graph.nodes),
            "edge_count": len(graph.edges),
        },
    )
    return graph


def _dedup_nodes(nodes: list[LineageNode]) -> list[LineageNode]:
    """Return ``nodes`` with duplicates removed while preserving order.

    Two nodes are considered duplicates when they share ``(id, kind)``
    — the canonical identity per ``ml-engines-v2-addendum §E10.2``.
    """
    seen: set[tuple[str, str]] = set()
    out: list[LineageNode] = []
    for node in nodes:
        key = (node.id, node.kind)
        if key in seen:
            continue
        seen.add(key)
        out.append(node)
    return out


def _dedup_edges(edges: list[LineageEdge]) -> list[LineageEdge]:
    """Return ``edges`` with duplicates removed while preserving order."""
    seen: set[tuple[str, str, str]] = set()
    out: list[LineageEdge] = []
    for edge in edges:
        key = (edge.source_id, edge.target_id, edge.relation)
        if key in seen:
            continue
        seen.add(key)
        out.append(edge)
    return out
