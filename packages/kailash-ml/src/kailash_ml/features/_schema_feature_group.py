# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Internal FeatureGroup-shaped read adapter bridging ``FeatureSchema`` to the
``dataflow.ml_feature_source`` polars binding.

``dataflow.ml_feature_source(feature_group)`` (see
``packages/kailash-dataflow/src/dataflow/ml/_feature_source.py``) duck-types on a
*FeatureGroup-shaped* object exposing ``.name`` + a callable
``.materialize(*, tenant_id, point_in_time, since, until, limit) -> polars frame``
that owns its own backing-store query. The canonical 1.x ``FeatureStore`` exposes
only a declarative :class:`~kailash_ml.features.schema.FeatureSchema` (no
``.materialize``), so ``FeatureStore.get_features`` cannot forward the schema to
the binding directly — it must wrap the schema in an adapter that performs the
read. This module is that adapter (issue #1241).

Per ``specs/ml-feature-store.md §1.1`` the store is a *thin polars-native
DataFlow-bridge*: it does NOT own DDL or a registry table. Accordingly the adapter
reads from a backing DataFlow table the user registered via ``@db.model``, using
the convention ``schema.name == DataFlow model name``. Ingestion is the user's
concern (no write path is added here — that is M2 per spec §11).

**Point-in-time correctness (spec §6.2 MUST-1).** When ``point_in_time`` is given,
the adapter returns, per entity, the latest row with ``timestamp_column <=
point_in_time``. DataFlow's read API (``express.list`` + MongoDB ``$lte``/``$gte``
operators, translated to SQL by ``dataflow.database.query_builder``) expresses the
time-window filter but NOT "latest row per entity" (no group-by/distinct-on). So
the split is: **DataFlow filters + fetches the ``<= T`` window; polars computes the
as-of dedup** (``sort(ts, desc).unique(subset=entity, keep="first")``). Each tool
native to its job; consistent with the polars-native feature-store framing.

**Scale bound (documented, not a stub).** The polars-dedup as-of materialises every
candidate row with ``timestamp <= point_in_time`` into memory before deduping.
This is correct for the canonical 1.x feature store (small/medium tables);
DB-side window-function as-of for large tables is deferred to M2 (it requires a
DataFlow aggregation primitive DataFlow does not yet expose without raw SQL).
The caller's ``limit`` caps the *deduped per-entity result*, not the candidate
window, so a low ``limit`` never silently returns a stale "latest".

No raw SQL is used anywhere (``rules/framework-first.md``).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

import polars as pl

if TYPE_CHECKING:  # avoid eager DataFlow import on type-only paths
    from kailash_ml.features.schema import FeatureSchema

    from dataflow.core.engine import DataFlow

__all__ = ["SchemaFeatureGroup"]

logger = logging.getLogger(__name__)

# Candidate-window fetch cap. The as-of dedup needs the full ``timestamp <= T``
# window per entity to be correct; the caller's ``limit`` caps the deduped
# result, not this fetch. Sized generously for 1.x-scale tables; DB-side
# windowed as-of (no in-memory cap) is M2 per the module docstring.
_CANDIDATE_FETCH_LIMIT = 1_000_000


class SchemaFeatureGroup:
    """FeatureGroup-shaped read adapter over a backing DataFlow table.

    Satisfies the shape ``dataflow.ml_feature_source`` consumes:

    * ``.name`` — non-empty string (the DataFlow model name; == ``schema.name``)
    * ``.multi_tenant`` — bool (whether to scope reads by ``tenant_id``)
    * ``.classification`` — optional dict (propagated as polars metadata by the
      binding's ``_classification_metadata``)
    * ``.materialize(...)`` — performs the read, returns a ``polars.LazyFrame``

    Constructed by ``FeatureStore.get_features``; not part of the public API.
    """

    def __init__(
        self,
        *,
        dataflow: "DataFlow",
        schema: "FeatureSchema",
        multi_tenant: bool = False,
        classification: dict | None = None,
    ) -> None:
        self._df = dataflow
        self._schema = schema
        self.name = schema.name
        self.multi_tenant = bool(multi_tenant)
        self.classification = classification or {}

    # ------------------------------------------------------------------
    # FeatureGroup contract
    # ------------------------------------------------------------------

    def materialize(
        self,
        *,
        tenant_id: str | None = None,
        point_in_time: datetime | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> "pl.LazyFrame":
        """Read the schema's features from the backing DataFlow table.

        Returns a ``polars.LazyFrame`` containing ``entity_id_column`` plus every
        column in ``schema.fields``. When ``point_in_time`` is supplied and the
        schema declares a ``timestamp_column``, the result is point-in-time
        correct (latest row per entity with ``timestamp <= point_in_time``).
        """
        schema = self._schema
        entity_col = schema.entity_id_column
        ts_col = schema.timestamp_column
        field_cols = schema.field_names

        rows = self._query_window(
            tenant_id=tenant_id,
            point_in_time=point_in_time,
            since=since,
            until=until,
        )

        # Project shape: entity_id + declared field columns. Used for the
        # empty-table return so the entity_id column is ALWAYS present — the
        # store's downstream `entity_ids` filter does
        # `pl.col(entity_id_column).is_in(...)` and would raise
        # ColumnNotFoundError on a column-less empty frame.
        projection = [entity_col] + [c for c in field_cols if c != entity_col]

        if not rows:
            # Empty (or absent-data) table → empty, column-shaped frame, NOT an
            # error. An actual missing/unmigrated table surfaces as an
            # exception from express.list, which the binding/store wrap as
            # FeatureStoreError.
            return pl.DataFrame(schema=projection).lazy()

        frame = pl.DataFrame(rows)

        # As-of dedup: keep the latest row per entity. The window query already
        # bounded timestamp <= point_in_time, so "latest per entity" within the
        # fetched rows IS the point-in-time-correct value. `nulls_last=True`
        # ensures a row with a NULL timestamp_column can never shadow a real
        # timestamped row (descending sort otherwise places NULLs first, where
        # `unique(keep="first")` would pick them).
        if (
            point_in_time is not None
            and ts_col is not None
            and ts_col in frame.columns
            and entity_col in frame.columns
            and frame.height
        ):
            frame = frame.sort(ts_col, descending=True, nulls_last=True).unique(
                subset=[entity_col], keep="first"
            )

        # Project to entity_id + declared field columns (drop tenant_id,
        # timestamp, and any other backing-table columns).
        present = [c for c in projection if c in frame.columns]
        if present:
            frame = frame.select(present)

        # Apply the caller's row cap to the DEDUPED per-entity result.
        if limit is not None and frame.height > limit:
            frame = frame.head(limit)

        return frame.lazy()

    # ------------------------------------------------------------------
    # Backing-store read (DataFlow primitives only — no raw SQL)
    # ------------------------------------------------------------------

    def _query_window(
        self,
        *,
        tenant_id: str | None,
        point_in_time: datetime | None,
        since: datetime | None,
        until: datetime | None,
    ) -> list[dict[str, Any]]:
        """Fetch the candidate row window from the backing DataFlow table.

        Builds a MongoDB-style timestamp-window filter (translated to SQL by
        ``dataflow.database.query_builder``). Returns raw rows; the caller
        computes the as-of dedup in polars.

        Tenant scoping is NOT a filter key: DataFlow multi-tenancy is
        context-bound — ``express.list`` auto-scopes to the tenant bound via
        ``db.tenant_context.switch(...)`` (see `express.py::_resolve_tenant_id`)
        and raises ``TenantRequiredError`` when none is bound. A ``tenant_id``
        filter would (a) do nothing under the default ``schema`` isolation
        strategy where there is no ``tenant_id`` column, and (b) still fail the
        context-bound read. So for a multi-tenant group we BIND the tenant
        context around the read rather than filtering on it, which works under
        both the ``schema`` and ``row`` isolation strategies.
        """
        schema = self._schema
        ts_col = schema.timestamp_column
        filter_spec: dict[str, Any] = {}

        if ts_col is not None:
            ts_bounds: dict[str, Any] = {}
            # point_in_time supersedes since/until (the store's MUST-5 contract;
            # the binding also rejects both together before reaching here).
            if point_in_time is not None:
                ts_bounds["$lte"] = point_in_time
            else:
                if since is not None:
                    ts_bounds["$gte"] = since
                if until is not None:
                    ts_bounds["$lte"] = until
            if ts_bounds:
                filter_spec[ts_col] = ts_bounds

        order_by = f"-{ts_col}" if ts_col is not None else None

        logger.debug(
            "feature_store.schema_group.query",
            extra={
                "group": self.name,
                "tenant_id": tenant_id,
                "filter_keys": sorted(filter_spec.keys()),
                "order_by": order_by,
            },
        )

        if self.multi_tenant and tenant_id is not None:
            # Bind the tenant context so express.list auto-scopes the read to
            # this tenant (DataFlow-native multi-tenancy; works under both the
            # schema- and row-isolation strategies).
            with self._df.tenant_context.switch(tenant_id):
                return self._df.express_sync.list(
                    schema.name,
                    filter_spec,
                    limit=_CANDIDATE_FETCH_LIMIT,
                    order_by=order_by,
                )

        return self._df.express_sync.list(
            schema.name,
            filter_spec,
            limit=_CANDIDATE_FETCH_LIMIT,
            order_by=order_by,
        )
