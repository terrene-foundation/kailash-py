# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Encapsulated SQL for the FeatureStore engine.

ALL raw SQL used by :class:`~kailash_ml.engines.feature_store.FeatureStore`
lives here.  The engine itself contains zero raw SQL -- it delegates
every database operation through the functions in this module.

Rules applied:
  - ``infrastructure-sql.md``: ``_validate_identifier()`` on every
    interpolated identifier, ``?`` canonical placeholders, transactions
    for multi-statement operations.
  - ``R2-12``: single auditable SQL touchpoint.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any

from kailash.db.connection import ConnectionManager
from kailash.db.dialect import _validate_identifier

logger = logging.getLogger(__name__)

# Allowlist of valid SQL column types to prevent SQL injection via type names
_ALLOWED_SQL_TYPES = frozenset({"INTEGER", "REAL", "TEXT", "BLOB", "NUMERIC"})


def _validate_sql_type(sql_type: str) -> None:
    """Validate a SQL column type against the allowlist."""
    if sql_type.upper() not in _ALLOWED_SQL_TYPES:
        raise ValueError(
            f"Invalid SQL type '{sql_type}': must be one of {sorted(_ALLOWED_SQL_TYPES)}"
        )


__all__ = [
    "create_feature_table",
    "create_metadata_table",
    "get_features_latest",
    "get_features_as_of",
    "get_features_range",
    "upsert_batch",
    "read_metadata",
    "upsert_metadata",
    "list_all_schemas",
]


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------


async def create_feature_table(
    conn: ConnectionManager,
    table_name: str,
    feature_columns: list[tuple[str, str]],
    entity_id_column: str,
    timestamp_column: str | None,
) -> None:
    """Create the feature data table if it does not exist.

    Parameters
    ----------
    feature_columns:
        List of ``(column_name, sql_type)`` pairs.
    """
    _validate_identifier(table_name)
    _validate_identifier(entity_id_column)
    if timestamp_column is not None:
        _validate_identifier(timestamp_column)
    for col_name, sql_type in feature_columns:
        _validate_identifier(col_name)
        _validate_sql_type(sql_type)

    col_defs = [f"{entity_id_column} TEXT NOT NULL"]
    if timestamp_column is not None:
        col_defs.append(f"{timestamp_column} TEXT NOT NULL")
    for col_name, sql_type in feature_columns:
        col_defs.append(f"{col_name} {sql_type}")
    col_defs.append("created_at TEXT NOT NULL")

    cols_sql = ", ".join(col_defs)
    await conn.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({cols_sql})")

    # Index for point-in-time lookups
    idx_name = f"idx_{table_name}_{entity_id_column}_created_at"
    _validate_identifier(idx_name)
    await conn.create_index(idx_name, table_name, f"{entity_id_column}, created_at")


async def create_metadata_table(conn: ConnectionManager) -> None:
    """Create the ``_kml_feature_metadata`` table if it does not exist."""
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS _kml_feature_metadata ("
        "  schema_name TEXT PRIMARY KEY,"
        "  schema_hash TEXT NOT NULL,"
        "  version INTEGER NOT NULL DEFAULT 1,"
        "  last_computed_at TEXT,"
        "  row_count INTEGER NOT NULL DEFAULT 0,"
        "  created_at TEXT NOT NULL,"
        "  updated_at TEXT NOT NULL"
        ")"
    )


# ---------------------------------------------------------------------------
# Feature retrieval
# ---------------------------------------------------------------------------


async def get_features_latest(
    conn: ConnectionManager,
    table_name: str,
    entity_ids: list[str],
    feature_names: list[str],
    entity_id_column: str,
    timestamp_column: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve the latest feature row per entity (no time constraint)."""
    _validate_identifier(table_name)
    _validate_identifier(entity_id_column)
    for name in feature_names:
        _validate_identifier(name)

    time_col = "created_at"
    if timestamp_column is not None:
        _validate_identifier(timestamp_column)
        time_col = timestamp_column

    cols = ", ".join(feature_names)
    placeholders = ", ".join("?" for _ in entity_ids)

    sql = (
        f"SELECT {entity_id_column}, {cols} "
        f"FROM ("
        f"  SELECT {entity_id_column}, {cols},"
        f"    ROW_NUMBER() OVER (PARTITION BY {entity_id_column} ORDER BY {time_col} DESC) AS rn"
        f"  FROM {table_name}"
        f"  WHERE {entity_id_column} IN ({placeholders})"
        f") sub WHERE rn = 1"
    )
    return await conn.fetch(sql, *entity_ids)


async def get_features_as_of(
    conn: ConnectionManager,
    table_name: str,
    entity_ids: list[str],
    feature_names: list[str],
    entity_id_column: str,
    as_of: datetime,
    timestamp_column: str | None = None,
) -> list[dict[str, Any]]:
    """Point-in-time feature retrieval -- latest row per entity before *as_of*.

    When *timestamp_column* is provided (schema has an explicit time
    column), the filter and ordering use that column.  Otherwise
    ``created_at`` (ingestion time) is used.
    """
    _validate_identifier(table_name)
    _validate_identifier(entity_id_column)
    for name in feature_names:
        _validate_identifier(name)

    time_col = "created_at"
    if timestamp_column is not None:
        _validate_identifier(timestamp_column)
        time_col = timestamp_column

    cols = ", ".join(feature_names)
    placeholders = ", ".join("?" for _ in entity_ids)

    sql = (
        f"SELECT {entity_id_column}, {cols} "
        f"FROM ("
        f"  SELECT {entity_id_column}, {cols},"
        f"    ROW_NUMBER() OVER (PARTITION BY {entity_id_column} ORDER BY {time_col} DESC) AS rn"
        f"  FROM {table_name}"
        f"  WHERE {entity_id_column} IN ({placeholders}) AND {time_col} <= ?"
        f") sub WHERE rn = 1"
    )
    return await conn.fetch(sql, *entity_ids, as_of.isoformat())


async def get_features_range(
    conn: ConnectionManager,
    table_name: str,
    entity_id_column: str,
    feature_names: list[str],
    start: datetime,
    end: datetime,
    timestamp_column: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve all feature rows within [start, end] time window."""
    _validate_identifier(table_name)
    _validate_identifier(entity_id_column)
    for name in feature_names:
        _validate_identifier(name)

    time_col = "created_at"
    if timestamp_column is not None:
        _validate_identifier(timestamp_column)
        time_col = timestamp_column

    cols = ", ".join(feature_names)
    sql = (
        f"SELECT {entity_id_column}, {cols}, {time_col} "
        f"FROM {table_name} "
        f"WHERE {time_col} >= ? AND {time_col} <= ? "
        f"ORDER BY {time_col}"
    )
    return await conn.fetch(sql, start.isoformat(), end.isoformat())


# ---------------------------------------------------------------------------
# Feature writes
# ---------------------------------------------------------------------------


async def upsert_batch(
    conn: ConnectionManager,
    table_name: str,
    records: list[dict[str, Any]],
    all_columns: list[str],
) -> None:
    """Insert a batch of feature records.

    Uses a transaction for atomicity.
    """
    _validate_identifier(table_name)
    for col in all_columns:
        _validate_identifier(col)

    if not records:
        return

    col_list = ", ".join(all_columns)
    placeholders = ", ".join("?" for _ in all_columns)
    insert_sql = f"INSERT INTO {table_name} ({col_list}) VALUES ({placeholders})"

    async with conn.transaction() as tx:
        for record in records:
            values = [record.get(col) for col in all_columns]
            await tx.execute(insert_sql, *values)


# ---------------------------------------------------------------------------
# Metadata CRUD
# ---------------------------------------------------------------------------


async def read_metadata(
    conn: ConnectionManager,
    schema_name: str,
) -> dict[str, Any] | None:
    """Read metadata for a feature schema, or ``None`` if not registered."""
    return await conn.fetchone(
        "SELECT * FROM _kml_feature_metadata WHERE schema_name = ?",
        schema_name,
    )


async def upsert_metadata(
    conn: ConnectionManager,
    schema_name: str,
    schema_hash: str,
    version: int,
    row_count: int,
    now_iso: str,
) -> None:
    """Insert or update metadata for a feature schema."""
    # Wrap in transaction to eliminate TOCTOU race between read and write (H3)
    async with conn.transaction() as tx:
        existing = await tx.fetchone(
            "SELECT * FROM _kml_feature_metadata WHERE schema_name = ?",
            schema_name,
        )
        if existing is None:
            await tx.execute(
                "INSERT INTO _kml_feature_metadata "
                "(schema_name, schema_hash, version, last_computed_at, row_count, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                schema_name,
                schema_hash,
                version,
                now_iso,
                row_count,
                now_iso,
                now_iso,
            )
        else:
            await tx.execute(
                "UPDATE _kml_feature_metadata "
                "SET schema_hash = ?, version = ?, last_computed_at = ?, "
                "    row_count = row_count + ?, updated_at = ? "
                "WHERE schema_name = ?",
                schema_hash,
                version,
                now_iso,
                row_count,
                now_iso,
                schema_name,
            )


async def list_all_schemas(conn: ConnectionManager) -> list[dict[str, Any]]:
    """List all registered feature schemas from the metadata table."""
    return await conn.fetch(
        "SELECT schema_name, schema_hash, version, last_computed_at, "
        "       row_count, created_at, updated_at "
        "FROM _kml_feature_metadata ORDER BY schema_name"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def compute_schema_hash(schema_dict: dict[str, Any]) -> str:
    """Deterministic hash of a FeatureSchema for drift detection."""
    canonical = json.dumps(schema_dict, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def dtype_to_sql(dtype: str) -> str:
    """Map a FeatureField dtype string to a portable SQL type."""
    mapping = {
        "int64": "INTEGER",
        "float64": "REAL",
        "float32": "REAL",
        "utf8": "TEXT",
        "bool": "INTEGER",
        "datetime": "TEXT",
        "categorical": "TEXT",
    }
    return mapping.get(dtype, "TEXT")
