# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Encapsulated SQL for :class:`~kailash_ml.engine.MLEngine`.

Same discipline as :mod:`kailash_ml.engines._feature_sql`: every raw SQL
string used by `MLEngine` lives here and nowhere else. `engine.py`
delegates DDL and CRUD through this module so audits find every
identifier-bearing statement in one place.

Two tables:

* ``_kml_engine_versions`` — tenant-aware model version ledger.
  Augments :class:`kailash_ml.engines.ModelRegistry` (which stores the
  registry-wide ``_kml_model_versions`` without a tenant column) by
  carrying the tenant dimension mandated by
  `specs/ml-engines.md` §5.1 MUST 4. Primary key is
  ``(tenant_id, name, version)`` per the spec — ``tenant_id`` is part of
  the identity scope, not a filter column bolted on later. The literal
  ``"global"`` is used for single-tenant deployments (§5.1 MUST 2);
  ``"default"`` is BLOCKED because
  `rules/tenant-isolation.md` § MUST Rule 2 mandates a distinct sentinel.

* ``_kml_engine_audit`` — operation audit trail per §5.2. Every
  ``register()`` writes one row with ``tenant_id`` indexed (§5.2 column
  list: ``tenant_id``, ``actor_id``, ``model_uri``, ``operation``,
  ``occurred_at``, ``duration_ms``, ``outcome``).

Rules applied:

* ``rules/dataflow-identifier-safety.md`` — identifiers routed through
  ``_validate_identifier``; SQL types through an allowlist.
* ``rules/infrastructure-sql.md`` — ``?`` canonical placeholders,
  ``dialect.blob_type()`` for BLOB portability, transactions for
  multi-statement ops.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from kailash.db.connection import ConnectionManager
from kailash.db.dialect import _validate_identifier

logger = logging.getLogger(__name__)

__all__ = [
    "create_engine_tables",
    "insert_version_row",
    "get_next_version",
    "fetch_version_row",
    "insert_audit_row",
    "count_versions",
    "SENTINEL_GLOBAL_TENANT",
]


# ---------------------------------------------------------------------------
# Tenant sentinel (specs/ml-engines.md §5.1 MUST 2)
# ---------------------------------------------------------------------------

# The literal string used in key construction and table rows when the
# Engine is single-tenant. `"default"` is BLOCKED per rules/tenant-
# isolation.md MUST Rule 2 — it silently merges every non-scoped read
# into a shared cache slot.
SENTINEL_GLOBAL_TENANT: str = "global"


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------


async def create_engine_tables(conn: ConnectionManager) -> None:
    """Create the MLEngine auxiliary tables if they do not exist.

    Idempotent: safe to call on every ``register()`` invocation.
    """
    # The tables below use fixed identifiers — no user input is
    # interpolated into the DDL. Defence-in-depth validation per
    # rules/dataflow-identifier-safety.md MUST Rule 5 still applies:
    # if a future refactor makes the name dynamic, the validator is
    # already in place and catches the drift.
    _validate_identifier("_kml_engine_versions")
    _validate_identifier("_kml_engine_audit")
    _validate_identifier("idx_kml_engine_versions_tenant_name")
    _validate_identifier("idx_kml_engine_audit_tenant")

    # `(tenant_id, name, version)` is the identity scope (§5.1 MUST 4).
    # A UNIQUE constraint on `(tenant_id, name, version)` enforces the
    # monotonic-per-tenant versioning contract.
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS _kml_engine_versions ("
        "  tenant_id TEXT NOT NULL,"
        "  name TEXT NOT NULL,"
        "  version INTEGER NOT NULL,"
        "  model_uri TEXT NOT NULL,"
        "  stage TEXT NOT NULL DEFAULT 'staging',"
        "  alias TEXT,"
        "  artifact_uris_json TEXT NOT NULL DEFAULT '{}',"
        "  registered_at REAL NOT NULL,"
        "  PRIMARY KEY (tenant_id, name, version)"
        ")"
    )

    # Tenant-prefix index for the "which models did tenant X promote"
    # post-incident query (rules/tenant-isolation.md § MUST Rule 5).
    await conn.create_index(
        "idx_kml_engine_versions_tenant_name",
        "_kml_engine_versions",
        "tenant_id, name",
    )

    # Audit-row schema per specs/ml-engines.md §5.2. `outcome` is a
    # short enum string; `duration_ms` is a float (fractional ms is
    # useful at training-cycle resolution).
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS _kml_engine_audit ("
        "  id TEXT PRIMARY KEY,"
        "  tenant_id TEXT NOT NULL,"
        "  actor_id TEXT,"
        "  model_uri TEXT,"
        "  operation TEXT NOT NULL,"
        "  occurred_at REAL NOT NULL,"
        "  duration_ms REAL NOT NULL,"
        "  outcome TEXT NOT NULL"
        ")"
    )
    await conn.create_index(
        "idx_kml_engine_audit_tenant",
        "_kml_engine_audit",
        "tenant_id, occurred_at",
    )


# ---------------------------------------------------------------------------
# Version row CRUD
# ---------------------------------------------------------------------------


async def get_next_version(
    tx: Any,
    tenant_id: str,
    name: str,
) -> int:
    """Return the next monotonic version for ``(tenant_id, name)``.

    MUST be called inside a ``conn.transaction()`` — otherwise the
    MAX-then-INSERT pattern has a TOCTOU race window where two
    concurrent callers both read ``MAX(version)`` = N and both insert
    N+1, yielding a UNIQUE constraint violation at best and a silent
    collision at worst.
    """
    row = await tx.fetchone(
        "SELECT MAX(version) AS max_v FROM _kml_engine_versions "
        "WHERE tenant_id = ? AND name = ?",
        tenant_id,
        name,
    )
    max_v = row.get("max_v") if row else None
    if max_v is None:
        return 1
    return int(max_v) + 1


async def insert_version_row(
    tx: Any,
    *,
    tenant_id: str,
    name: str,
    version: int,
    model_uri: str,
    stage: str,
    alias: Optional[str],
    artifact_uris_json: str,
    registered_at: float,
) -> None:
    """Insert a version row into ``_kml_engine_versions``.

    Must be called inside the same transaction as
    :func:`get_next_version` so the MAX→INSERT pair is atomic.
    """
    await tx.execute(
        "INSERT INTO _kml_engine_versions "
        "(tenant_id, name, version, model_uri, stage, alias, "
        " artifact_uris_json, registered_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        tenant_id,
        name,
        version,
        model_uri,
        stage,
        alias,
        artifact_uris_json,
        registered_at,
    )


async def fetch_version_row(
    conn: ConnectionManager,
    *,
    tenant_id: str,
    name: str,
    version: int,
) -> Optional[dict[str, Any]]:
    """Read a version row by ``(tenant_id, name, version)``.

    Returns ``None`` when the row does not exist.
    """
    return await conn.fetchone(
        "SELECT * FROM _kml_engine_versions "
        "WHERE tenant_id = ? AND name = ? AND version = ?",
        tenant_id,
        name,
        version,
    )


async def count_versions(
    conn: ConnectionManager,
    *,
    tenant_id: str,
    name: str,
) -> int:
    """Return the number of version rows for ``(tenant_id, name)``."""
    row = await conn.fetchone(
        "SELECT COUNT(*) AS n FROM _kml_engine_versions "
        "WHERE tenant_id = ? AND name = ?",
        tenant_id,
        name,
    )
    if row is None:
        return 0
    return int(row.get("n", 0))


# ---------------------------------------------------------------------------
# Audit row write
# ---------------------------------------------------------------------------


async def insert_audit_row(
    conn: ConnectionManager,
    *,
    audit_id: str,
    tenant_id: str,
    actor_id: Optional[str],
    model_uri: Optional[str],
    operation: str,
    occurred_at: float,
    duration_ms: float,
    outcome: str,
) -> None:
    """Insert an audit row per specs/ml-engines.md §5.2."""
    await conn.execute(
        "INSERT INTO _kml_engine_audit "
        "(id, tenant_id, actor_id, model_uri, operation, occurred_at, "
        " duration_ms, outcome) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        audit_id,
        tenant_id,
        actor_id,
        model_uri,
        operation,
        occurred_at,
        duration_ms,
        outcome,
    )
