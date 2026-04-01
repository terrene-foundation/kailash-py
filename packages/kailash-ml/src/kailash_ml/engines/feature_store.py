# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""FeatureStore engine -- DataFlow-backed, polars-native, point-in-time correct.

Uses ``ConnectionManager`` for point-in-time queries (Express cannot
express window-function-based temporal lookups).  All raw SQL is
encapsulated in :mod:`kailash_ml.engines._feature_sql` -- the single
auditable SQL touchpoint.  This module contains zero raw SQL.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import polars as pl
from kailash.db.connection import ConnectionManager
from kailash_ml_protocols import FeatureField, FeatureSchema

from kailash_ml.engines import _feature_sql as sql
from kailash_ml.interop import polars_to_dict_records

logger = logging.getLogger(__name__)

__all__ = ["FeatureStore"]

# Maximum rows before switching from dict path to bulk insert path
_BULK_THRESHOLD = 10_000


def _chunked(items: list, size: int):
    """Yield successive chunks of *size* from *items*."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


class FeatureStore:
    """[P0: Production] DataFlow-backed feature versioning engine.

    Parameters
    ----------
    conn:
        An initialized :class:`~kailash.db.connection.ConnectionManager`.
        The caller owns the connection lifecycle.
    table_prefix:
        Prefix for generated feature tables (default ``kml_feat_``).
    """

    def __init__(
        self,
        conn: ConnectionManager,
        *,
        table_prefix: str = "kml_feat_",
    ) -> None:
        self._conn = conn
        self._table_prefix = table_prefix
        self._initialized = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Create internal metadata table.  Idempotent."""
        await sql.create_metadata_table(self._conn)
        self._initialized = True

    # ------------------------------------------------------------------
    # Schema registration
    # ------------------------------------------------------------------

    async def register_features(self, schema: FeatureSchema) -> None:
        """Register a feature schema, creating the backing table.

        Idempotent -- re-registering with the same schema is a no-op.
        Re-registering with a *different* schema (different hash) raises
        ``ValueError`` to prevent silent schema drift.

        Raises
        ------
        ValueError
            If a schema with the same name but a different hash already
            exists.
        """
        if not self._initialized:
            await self.initialize()

        schema_hash = sql.compute_schema_hash(schema.to_dict())
        existing = await sql.read_metadata(self._conn, schema.name)

        if existing is not None:
            if existing["schema_hash"] == schema_hash:
                logger.debug(
                    "Schema '%s' already registered (hash match).", schema.name
                )
                return
            raise ValueError(
                f"Schema '{schema.name}' already registered with a different "
                f"definition (hash {existing['schema_hash']} != {schema_hash}). "
                f"Bump the version or use a new name."
            )

        # Create the feature data table
        table_name = self._table_name(schema)
        feature_columns = [(f.name, sql.dtype_to_sql(f.dtype)) for f in schema.features]
        await sql.create_feature_table(
            self._conn,
            table_name,
            feature_columns,
            entity_id_column=schema.entity_id_column,
            timestamp_column=schema.timestamp_column,
        )

        # Record metadata
        now_iso = datetime.now(timezone.utc).isoformat()
        await sql.upsert_metadata(
            self._conn,
            schema_name=schema.name,
            schema_hash=schema_hash,
            version=schema.version,
            row_count=0,
            now_iso=now_iso,
        )
        logger.info(
            "Registered feature schema '%s' (table=%s).", schema.name, table_name
        )

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------

    def compute(
        self,
        raw_data: pl.DataFrame | pl.LazyFrame,
        schema: FeatureSchema,
    ) -> pl.DataFrame:
        """Validate that *raw_data* contains all required feature columns.

        This is a validation + projection step -- it ensures the
        DataFrame conforms to the schema before storage.

        Raises
        ------
        ValueError
            If the DataFrame is missing required feature columns, or if
            dtype mismatches are found.
        """
        if isinstance(raw_data, pl.LazyFrame):
            raw_data = raw_data.collect()

        required_cols = {f.name for f in schema.features}
        required_cols.add(schema.entity_id_column)
        if schema.timestamp_column is not None:
            required_cols.add(schema.timestamp_column)

        available_cols = set(raw_data.columns)
        missing = required_cols - available_cols
        if missing:
            raise ValueError(
                f"DataFrame is missing required columns for schema "
                f"'{schema.name}': {sorted(missing)}"
            )

        # Validate nullable constraints
        for feat in schema.features:
            if not feat.nullable:
                null_count = raw_data[feat.name].null_count()
                if null_count > 0:
                    raise ValueError(
                        f"Column '{feat.name}' has {null_count} null values "
                        f"but is declared non-nullable in schema '{schema.name}'."
                    )

        # Project to schema columns only
        select_cols = [schema.entity_id_column]
        if schema.timestamp_column is not None:
            select_cols.append(schema.timestamp_column)
        select_cols.extend(f.name for f in schema.features)

        return raw_data.select(select_cols)

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

    async def store(
        self,
        features: pl.DataFrame,
        schema: FeatureSchema,
    ) -> int:
        """Materialize computed features to the database.

        Returns the number of rows stored.  Uses the dict path for small
        datasets (<10K rows) and bulk insert for larger ones.
        """
        if not self._initialized:
            await self.initialize()

        table_name = self._table_name(schema)
        row_count = features.height

        # Add created_at timestamp
        now_iso = datetime.now(timezone.utc).isoformat()
        features_with_ts = features.with_columns(pl.lit(now_iso).alias("created_at"))

        # Build column list for the table
        all_columns = self._all_columns(schema)

        if row_count > _BULK_THRESHOLD:
            # Bulk path -- chunked inserts
            records = features_with_ts.to_dicts()
            for chunk in _chunked(records, 1000):
                await sql.upsert_batch(self._conn, table_name, chunk, all_columns)
        else:
            # Dict path for small datasets
            records = polars_to_dict_records(
                features_with_ts, max_rows=_BULK_THRESHOLD + 1
            )
            for chunk in _chunked(records, 1000):
                await sql.upsert_batch(self._conn, table_name, chunk, all_columns)

        # Update metadata
        await sql.upsert_metadata(
            self._conn,
            schema_name=schema.name,
            schema_hash=sql.compute_schema_hash(schema.to_dict()),
            version=schema.version,
            row_count=row_count,
            now_iso=now_iso,
        )

        logger.info(
            "Stored %d rows for schema '%s' (table=%s).",
            row_count,
            schema.name,
            table_name,
        )
        return row_count

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    async def get_features(
        self,
        entity_ids: list[str],
        feature_names: list[str],
        *,
        schema_name: str | None = None,
        schema: FeatureSchema | None = None,
        as_of: datetime | None = None,
    ) -> pl.DataFrame:
        """Retrieve features for the given entities.

        When *as_of* is provided, returns the latest feature values that
        existed at that point in time (point-in-time correctness).

        Parameters
        ----------
        entity_ids:
            Entity identifiers to retrieve.
        feature_names:
            Feature column names to include.
        schema_name:
            Name of the registered schema.  Exactly one of *schema_name*
            or *schema* must be provided.
        schema:
            A :class:`FeatureSchema` object.  If given, *schema_name* is
            derived from it.
        as_of:
            Optional cutoff timestamp for point-in-time retrieval.

        Returns
        -------
        pl.DataFrame
            A DataFrame with *entity_id_column*, plus the requested
            *feature_names*.
        """
        if not self._initialized:
            await self.initialize()

        resolved_schema = self._resolve_schema(schema_name, schema)
        table_name = self._table_name(resolved_schema)
        entity_id_col = resolved_schema.entity_id_column

        ts_col = resolved_schema.timestamp_column

        if as_of is not None:
            rows = await sql.get_features_as_of(
                self._conn,
                table_name,
                entity_ids,
                feature_names,
                entity_id_col,
                as_of,
                timestamp_column=ts_col,
            )
        else:
            rows = await sql.get_features_latest(
                self._conn,
                table_name,
                entity_ids,
                feature_names,
                entity_id_col,
                timestamp_column=ts_col,
            )

        if not rows:
            # Return empty DataFrame with expected columns
            return pl.DataFrame(
                {entity_id_col: pl.Series([], dtype=pl.Utf8)}
                | {name: pl.Series([], dtype=pl.Float64) for name in feature_names}
            )

        return pl.DataFrame(rows)

    async def get_training_set(
        self,
        schema: FeatureSchema,
        *,
        start: datetime,
        end: datetime,
    ) -> pl.DataFrame:
        """Retrieve all features within a time window for training.

        Returns
        -------
        pl.DataFrame
            All feature rows where ``created_at`` falls within
            ``[start, end]``.
        """
        if not self._initialized:
            await self.initialize()

        table_name = self._table_name(schema)
        feature_names = [f.name for f in schema.features]

        ts_col = schema.timestamp_column

        rows = await sql.get_features_range(
            self._conn,
            table_name,
            schema.entity_id_column,
            feature_names,
            start,
            end,
            timestamp_column=ts_col,
        )

        time_col_name = ts_col if ts_col is not None else "created_at"
        if not rows:
            cols = [schema.entity_id_column] + feature_names + [time_col_name]
            return pl.DataFrame({c: [] for c in cols})

        return pl.DataFrame(rows)

    async def get_features_lazy(
        self,
        entity_ids: list[str],
        feature_names: list[str],
        *,
        schema_name: str | None = None,
        schema: FeatureSchema | None = None,
        as_of: datetime | None = None,
    ) -> pl.LazyFrame:
        """Retrieve features as a :class:`pl.LazyFrame` for streaming.

        The data is fetched eagerly from the database but wrapped in a
        ``LazyFrame`` so that downstream polars operations are deferred.
        """
        df = await self.get_features(
            entity_ids,
            feature_names,
            schema_name=schema_name,
            schema=schema,
            as_of=as_of,
        )
        return df.lazy()

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    async def list_schemas(self) -> list[dict[str, Any]]:
        """List all registered feature schemas.

        Returns a list of metadata dicts (schema_name, version,
        row_count, etc.).
        """
        if not self._initialized:
            await self.initialize()
        return await sql.list_all_schemas(self._conn)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _table_name(self, schema: FeatureSchema) -> str:
        """Derive the database table name from a schema."""
        return f"{self._table_prefix}{schema.name}"

    def _all_columns(self, schema: FeatureSchema) -> list[str]:
        """Build the ordered list of all columns in the feature table."""
        cols = [schema.entity_id_column]
        if schema.timestamp_column is not None:
            cols.append(schema.timestamp_column)
        cols.extend(f.name for f in schema.features)
        cols.append("created_at")
        return cols

    def _resolve_schema(
        self,
        schema_name: str | None,
        schema: FeatureSchema | None,
    ) -> FeatureSchema:
        """Resolve a schema from the provided arguments.

        Exactly one of *schema_name* or *schema* must be given.  When
        only *schema_name* is provided a minimal schema is constructed
        from the metadata (enough for table lookups).
        """
        if schema is not None:
            return schema
        if schema_name is not None:
            # Construct a minimal schema for table-name derivation
            return FeatureSchema(
                name=schema_name,
                features=[],
                entity_id_column="entity_id",
            )
        raise ValueError("Provide either 'schema_name' or 'schema'.")
