# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``FeatureMaterialiser`` — write-through persistence for a :class:`FeatureGroup`.

The materialiser computes a feature group's declared ``@feature`` derived columns
on a caller-supplied ``polars.DataFrame`` (via the shipped ``dataflow.transform``
binding), PERSISTS the resulting feature table through DataFlow Express (no raw
SQL, no inline DDL — the backing table is a ``@db.model`` driven by DataFlow
``auto_migrate``), and registers the materialized dataset's lineage hash via the
shipped ``dataflow.hash`` binding.

**Composition, not a constructor flag (spec §11.6).** The materialiser is a
SEPARATE object the caller (or :class:`~kailash_ml.features.store.FeatureStore`)
constructs and holds — it is NOT a ``FeatureStore.__init__`` kwarg.
``FeatureStore``'s constructor surface stays intentionally narrow
(``rules/facade-manager-detection.md`` Rule 3); ``FeatureStore.materialize`` is a
thin facade that delegates here.

**Framework-first (``rules/framework-first.md`` / zero-tolerance Rule 4).** Compute
routes through ``dataflow.transform`` (the shipped polars-Expr binding);
persistence routes through DataFlow Express ``upsert``/``bulk_create`` against the
backing ``@db.model``; lineage routes through ``dataflow.hash``. No raw SQL, no
re-implementation of any DataFlow primitive lives here.

**Idempotent re-materialise.** Each materialized row carries a deterministic
content-addressed primary key — ``id = sha256(tenant, group, version,
entity_id, timestamp)``. Re-running the same ``materialize(...)`` ``upsert``\\s the
same rows under the same keys, so re-materialisation does NOT duplicate rows; it
is a well-defined no-op when the inputs are unchanged.

**Tenant isolation (``rules/tenant-isolation.md`` Rule 2).** The caller-supplied
``tenant_id`` is validated and bound to the DataFlow tenant context for the
write. When the group declares its OWN ``tenant_id`` (e.g. one rehydrated from the
registry) and it does NOT match the caller's tenant, the materialiser refuses with
:class:`~kailash_ml.errors.CrossTenantReadError` rather than writing one tenant's
feature data under another tenant's scope.

**Observability (``rules/observability.md`` Rule 8 / spec MUST-7).** Structured
``feature_materialise.{start,ok,error}`` lines carry ``source='dataflow'``,
``mode='real'``, ``tenant_id``, ``schema``, ``version``, ``row_count``,
``latency_ms``. Schema/column names appear ONLY at DEBUG level.

See ``specs/ml-feature-store.md §11.2`` (materialise — now shipped) + §4
(point-in-time write integrity).
"""
from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

import polars as pl
from kailash_ml.features.cache_keys import (
    make_feature_group_wildcard,
    validate_tenant_id,
)

if TYPE_CHECKING:  # avoid eager DataFlow import on type-only paths
    from kailash_ml.features.feature_group import FeatureGroup

    from dataflow.core.engine import DataFlow

__all__ = ["FeatureMaterialiser", "MaterializeResult"]

logger = logging.getLogger(__name__)

# Polars dtype string -> Python annotation type for dynamic @db.model field
# declaration. The backing table is created by DataFlow auto_migrate from these
# annotations; only the coarse Python type matters for DDL (DataFlow maps to the
# dialect column type). Unknown dtypes fall back to str (safe, never silently
# drops a column).
_DTYPE_TO_PYTYPE: dict[str, type] = {
    "int8": int,
    "int16": int,
    "int32": int,
    "int64": int,
    "uint8": int,
    "uint16": int,
    "uint32": int,
    "uint64": int,
    "float32": float,
    "float64": float,
    "bool": bool,
    "utf8": str,
    "string": str,
    "datetime": datetime,
}


class MaterializeResult(dict):
    """Structured return of :meth:`FeatureMaterialiser.materialize`.

    A ``dict`` subclass (JSON-friendly, drop-in for callers that treat the
    result as a mapping) carrying:

    * ``frame`` — the redacted ``polars.DataFrame`` that was persisted (entity_id
      + declared columns + timestamp), with classified columns routed through the
      read-path redaction the read surface uses.
    * ``lineage_hash`` — the ``"sha256:<64hex>"`` content hash of the materialized
      dataset (stable across identical re-materialisation), produced by
      ``dataflow.hash``.
    * ``row_count`` — number of rows persisted.
    * ``group`` — the group / backing-table name.
    * ``version`` — the schema version materialized.
    * ``tenant_id`` — the effective tenant the rows were written under.
    """


class FeatureMaterialiser:
    """Write-through materialiser for a :class:`FeatureGroup` (FM2 Shard B).

    Mirrors the ``FeatureStore`` / ``FeatureRegistry`` Rule-3 constructor shape:
    takes the live ``DataFlow`` instance it persists + reads through. The backing
    feature table is registered lazily (DataFlow ``auto_migrate``) on first
    :meth:`materialize`, so constructing a materialiser is cheap + import-safe.

    Parameters
    ----------
    dataflow:
        The live ``DataFlow`` instance backing persistence + lineage. Required —
        a materialiser with no backing store cannot write (composition,
        ``rules/facade-manager-detection.md`` Rule 3, NOT a global lookup, NOT
        self-construction).
    """

    def __init__(self, dataflow: "DataFlow") -> None:
        if dataflow is None:
            raise TypeError(
                "FeatureMaterialiser(dataflow=...) requires a live DataFlow "
                "instance (composition, not a FeatureStore kwarg — spec §11.6; "
                "rules/facade-manager-detection.md Rule 3)."
            )
        self._df = dataflow
        # Track which backing models we have already registered (keyed by the
        # backing-table name) so repeated materialise calls don't re-run @df.model.
        self._models_ready: set[str] = set()

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    async def materialize(
        self,
        group: "FeatureGroup",
        data: pl.DataFrame,
        *,
        tenant_id: str | None = None,
        point_in_time: datetime | None = None,
    ) -> MaterializeResult:
        """Compute + persist a feature group's rows; register lineage.

        Computes every declared ``@feature`` derived column on ``data`` via the
        shipped ``dataflow.transform`` binding, persists the resulting feature
        table through DataFlow Express ``upsert`` (idempotent — keyed by a
        deterministic content-addressed ``id``), and registers the materialized
        dataset's lineage hash via ``dataflow.hash``.

        Parameters
        ----------
        group:
            The authored :class:`FeatureGroup` to materialise. Its
            :class:`~kailash_ml.features.schema.FeatureSchema` declares the
            entity / timestamp / field columns; its ``@feature`` definitions are
            the derived columns computed here.
        data:
            The input ``polars.DataFrame`` carrying at least the schema's
            ``entity_id_column`` (and ``timestamp_column`` when declared) plus the
            base columns each ``@feature`` expression reads. Non-polars input is
            rejected (``rules/framework-first.md`` — polars-native).
        tenant_id:
            Tenant scope for the write. Validated; bound to the DataFlow tenant
            context around the persist. Missing tenant raises
            :class:`~kailash_ml.errors.TenantRequiredError`. A multi-tenant group
            whose own ``tenant_id`` differs raises
            :class:`~kailash_ml.errors.CrossTenantReadError`.
        point_in_time:
            Optional materialise-time stamp recorded for observability. Per-row
            event-time is read from the schema's ``timestamp_column`` in ``data``
            (NOT synthesised here) so a later
            :meth:`~kailash_ml.features.store.FeatureStore.get_features`
            ``timestamp=T`` read is point-in-time correct (spec §4 MUST-5).

        Returns
        -------
        MaterializeResult
            ``frame`` (redacted persisted DataFrame), ``lineage_hash``,
            ``row_count``, ``group``, ``version``, ``tenant_id``.

        Raises
        ------
        kailash_ml.errors.TenantRequiredError
            ``tenant_id`` missing / invalid.
        kailash_ml.errors.CrossTenantReadError
            The group declares a tenant that does not match ``tenant_id``.
        kailash_ml.errors.FeatureStoreError
            Persistence or compute failure (wrapping the underlying error).
        """
        # Local imports keep DataFlow / FeatureGroup off the type-only import path.
        from kailash_ml.errors import CrossTenantReadError, FeatureStoreError
        from kailash_ml.features.feature_group import FeatureGroup

        if not isinstance(group, FeatureGroup):
            raise TypeError(
                "FeatureMaterialiser.materialize(group=...) expects a "
                f"FeatureGroup, got {type(group).__name__}"
            )
        if not isinstance(data, pl.DataFrame):
            raise TypeError(
                "FeatureMaterialiser.materialize(data=...) must be a "
                f"polars.DataFrame (polars-native), got {type(data).__name__}"
            )

        schema = group.schema
        tenant = validate_tenant_id(
            tenant_id, operation=f"FeatureMaterialiser[{group.name}].materialize"
        )

        # Tenant-isolation gate: a group rehydrated/registered under a SPECIFIC
        # tenant MUST NOT be materialised under a different caller tenant — that
        # would write one tenant's feature data into another's scope
        # (rules/tenant-isolation.md Rule 2). The group carries its tenant via
        # the `classification` dict (registry stores it there) when bound.
        group_tenant = self._group_declared_tenant(group)
        if group_tenant is not None and group_tenant != tenant:
            # Fingerprint both tenants — never echo raw tenant ids
            # (rules/dataflow-identifier-safety.md error-message discipline).
            raise CrossTenantReadError(
                reason=(
                    f"feature group {group.name!r} is bound to a different tenant "
                    f"(group_fingerprint={hash(group_tenant) & 0xFFFF:04x}, "
                    f"caller_fingerprint={hash(tenant) & 0xFFFF:04x}); refusing to "
                    f"materialise across the tenant boundary"
                ),
                tenant_id=tenant,
            )

        started_at = time.monotonic()
        logger.info(
            "feature_materialise.start",
            extra={
                "source": "dataflow",
                "mode": "real",
                "tenant_id": tenant,
                "schema": group.name,
                "version": schema.version,
                "input_rows": data.height,
            },
        )

        try:
            # 1. Compute derived columns via the shipped dataflow.transform binding.
            computed = self._compute(group, data, tenant_id=tenant)

            # 2. Project to the persisted shape: entity_id + timestamp (if any) +
            #    declared field columns + derived columns. Drop everything else so
            #    the backing table matches the schema contract.
            persisted = self._project(group, computed)

            # 3. Lineage hash of the materialized dataset (stable across identical
            #    re-materialisation) via the shipped dataflow.hash binding.
            lineage_hash = self._lineage_hash(persisted)

            # 4. Persist through DataFlow Express (no raw SQL) — idempotent upsert
            #    keyed by a deterministic content-addressed id.
            row_count = await self._persist(group, persisted, tenant=tenant)

            # 5. Cache invalidation: a materialise that supersedes cached rows
            #    emits the tenant-scoped v* wildcard (tenant-isolation Rule 3a).
            #    Returned so the caller (FeatureStore) can sweep its cache; the
            #    pattern is computed here so the write + invalidation contract is
            #    co-located.
            invalidation = make_feature_group_wildcard(
                tenant_id=tenant, schema_name=group.name, version=schema.version
            )

            # 6. Redact the return frame on the mutation return-path
            #    (rules/dataflow-classification.md MUST-1).
            redacted = self._redact(group, persisted)

            latency_ms = (time.monotonic() - started_at) * 1000.0
            logger.info(
                "feature_materialise.ok",
                extra={
                    "source": "dataflow",
                    "mode": "real",
                    "tenant_id": tenant,
                    "schema": group.name,
                    "version": schema.version,
                    "row_count": row_count,
                    "lineage_hash": lineage_hash,
                    "latency_ms": latency_ms,
                },
            )

            result = MaterializeResult()
            result["frame"] = redacted
            result["lineage_hash"] = lineage_hash
            result["row_count"] = row_count
            result["group"] = group.name
            result["version"] = schema.version
            result["tenant_id"] = tenant
            result["invalidation_pattern"] = invalidation
            return result
        except FeatureStoreError:
            # Already typed (incl. CrossTenantReadError) — surface unchanged.
            # (TenantRequiredError is raised by validate_tenant_id ABOVE the try,
            # so it never reaches here.)
            raise
        except Exception as exc:
            latency_ms = (time.monotonic() - started_at) * 1000.0
            logger.exception(
                "feature_materialise.error",
                extra={
                    "source": "dataflow",
                    "mode": "real",
                    "tenant_id": tenant,
                    "schema": group.name,
                    "version": schema.version,
                    "latency_ms": latency_ms,
                },
            )
            raise FeatureStoreError(
                reason=f"materialize failed: {type(exc).__name__}",
                tenant_id=tenant,
            ) from exc

    # ------------------------------------------------------------------
    # Compute (dataflow.transform) — no raw compute
    # ------------------------------------------------------------------

    def _compute(
        self, group: "FeatureGroup", data: pl.DataFrame, *, tenant_id: str
    ) -> pl.DataFrame:
        """Apply each declared ``@feature`` derived column via dataflow.transform.

        Routes every ``FeatureDefinition``'s polars ``Expr`` through the shipped
        ``dataflow.transform`` binding (classification + lineage tagging
        preserved). When the group declares no derived features the input frame
        passes through unchanged.
        """
        if not group.features:
            return data

        from kailash_ml.features.feature_group import _import_transform

        transform = _import_transform()
        frame: Any = data
        for definition in group.features:
            frame = transform(
                definition.expr(),
                frame,
                name=definition.name,
                tenant_id=tenant_id,
            )
        # transform returns a LazyFrame — collect to a concrete DataFrame for the
        # persist + hash steps (the write path needs materialised rows).
        if isinstance(frame, pl.LazyFrame):
            frame = frame.collect()
        logger.debug(
            "feature_materialise.compute",
            extra={
                "schema": group.name,
                "tenant_id": tenant_id,
                "derived_count": len(group.features),
                "derived_columns": [d.name for d in group.features],
            },
        )
        return frame

    # ------------------------------------------------------------------
    # Projection + lineage + persistence helpers
    # ------------------------------------------------------------------

    def _persisted_columns(self, group: "FeatureGroup") -> list[str]:
        """Ordered persisted columns: entity_id + timestamp + fields + derived."""
        schema = group.schema
        cols: list[str] = [schema.entity_id_column]
        if schema.timestamp_column is not None:
            cols.append(schema.timestamp_column)
        for name in schema.field_names:
            if name not in cols:
                cols.append(name)
        for definition in group.features:
            if definition.name not in cols:
                cols.append(definition.name)
        return cols

    def _project(self, group: "FeatureGroup", frame: pl.DataFrame) -> pl.DataFrame:
        """Project the computed frame to the persisted column shape."""
        wanted = self._persisted_columns(group)
        present = [c for c in wanted if c in frame.columns]
        return frame.select(present)

    def _lineage_hash(self, frame: pl.DataFrame) -> str:
        """Content hash of the materialized dataset via dataflow.hash.

        Stable across semantically-identical re-materialisation (dataflow.hash
        canonicalises column + row order). Used by the registry/store as the
        lineage provenance field (spec §4.4).
        """
        from kailash_ml.features.feature_group import _import_dataflow_hash

        df_hash = _import_dataflow_hash()
        return df_hash(frame, stable=True)

    async def _persist(
        self, group: "FeatureGroup", frame: pl.DataFrame, *, tenant: str
    ) -> int:
        """Persist the feature table through DataFlow Express (no raw SQL).

        Registers the backing ``@db.model`` lazily (auto_migrate), then upserts
        every row keyed by a deterministic content-addressed ``id`` so re-running
        the same materialise is idempotent (no duplicate rows). Multi-tenant
        groups bind the tenant context around the write so DataFlow auto-scopes.
        """
        self._ensure_model(group)
        records = self._rows_for_persist(group, frame, tenant=tenant)
        if not records:
            return 0

        if group.multi_tenant:
            with self._df.tenant_context.switch(tenant):
                await self._upsert_rows(group.name, records)
        else:
            await self._upsert_rows(group.name, records)
        return len(records)

    async def _upsert_rows(
        self, model_name: str, records: list[dict[str, Any]]
    ) -> None:
        """Idempotent per-row upsert keyed on the deterministic ``id``."""
        for record in records:
            await self._df.express.upsert(model_name, record, conflict_on=["id"])

    def _rows_for_persist(
        self, group: "FeatureGroup", frame: pl.DataFrame, *, tenant: str
    ) -> list[dict[str, Any]]:
        """Build the row dicts to upsert, each with a deterministic ``id``.

        ``id = sha256(tenant | group | version | entity_id | timestamp)[:32]`` —
        re-materialising the same logical row produces the same id, so the upsert
        conflict-resolves to the existing row instead of inserting a duplicate.
        """
        schema = group.schema
        entity_col = schema.entity_id_column
        ts_col = schema.timestamp_column
        persisted_cols = self._persisted_columns(group)
        present = [c for c in persisted_cols if c in frame.columns]

        records: list[dict[str, Any]] = []
        for row in frame.select(present).iter_rows(named=True):
            entity_val = row.get(entity_col)
            ts_val = row.get(ts_col) if ts_col is not None else None
            row_id = self._row_id(
                tenant=tenant,
                group=group.name,
                version=schema.version,
                entity_id=entity_val,
                timestamp=ts_val,
            )
            record: dict[str, Any] = {"id": row_id}
            record.update(row)
            records.append(record)
        return records

    @staticmethod
    def _row_id(
        *,
        tenant: str,
        group: str,
        version: int,
        entity_id: Any,
        timestamp: Any,
    ) -> str:
        """Deterministic content-addressed primary key for a materialized row."""
        payload = "|".join(
            [
                tenant,
                group,
                str(version),
                str(entity_id),
                (
                    timestamp.isoformat()
                    if isinstance(timestamp, datetime)
                    else str(timestamp)
                ),
            ]
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:32]

    # ------------------------------------------------------------------
    # Lazy model registration (auto_migrate; no inline DDL)
    # ------------------------------------------------------------------

    def _ensure_model(self, group: "FeatureGroup") -> None:
        """Register the backing ``@db.model`` once (schema-migration Rule 1).

        The backing table is a DataFlow ``@db.model`` whose columns are derived
        from the schema (entity_id + timestamp + declared fields + derived
        features) plus a content-addressed ``id`` primary key. DataFlow
        ``auto_migrate`` emits the ``CREATE TABLE`` — NO inline DDL, NO raw SQL
        (``rules/schema-migration.md`` Rule 1, ``rules/framework-first.md``).
        """
        model_name = group.name
        df = self._df

        # Idempotency across materialiser INSTANCES: model registration is
        # per-DataFlow-instance, and FeatureStore.materialize constructs a fresh
        # FeatureMaterialiser per call. Consult the DataFlow registry of record
        # (``_models``) — not just this instance's cache — so a re-materialise on
        # a new materialiser over the SAME DataFlow does not re-register (which
        # DataFlow rejects with "Model already registered"). The local set is the
        # fast-path cache for repeated calls on one instance.
        if model_name in self._models_ready:
            return
        if model_name in getattr(df, "_models", {}):
            self._models_ready.add(model_name)
            df._ensure_connected()
            return

        schema = group.schema

        # Build the field annotations for the dynamic model. id (PK str) first,
        # then entity_id, timestamp, declared fields, derived feature columns.
        annotations: dict[str, type] = {"id": str, schema.entity_id_column: str}
        if schema.timestamp_column is not None:
            annotations[schema.timestamp_column] = datetime
        for fld in schema.fields:
            annotations[fld.name] = _DTYPE_TO_PYTYPE.get(fld.dtype, str)
        for definition in group.features:
            annotations[definition.name] = _DTYPE_TO_PYTYPE.get(definition.dtype, str)

        # Construct the model class dynamically so the backing table matches the
        # authored schema (mirrors registry._ensure_model's dynamic @df.model).
        model_cls = type(model_name, (), {"__annotations__": annotations})
        df.model(model_cls)

        # auto_migrate creates the table on first connect.
        df._ensure_connected()
        self._models_ready.add(model_name)

    # ------------------------------------------------------------------
    # Classification redaction (mutation return-path) + tenant resolution
    # ------------------------------------------------------------------

    def _group_declared_tenant(self, group: "FeatureGroup") -> str | None:
        """Resolve the tenant a group is bound to, if any.

        A group rehydrated from the registry (or constructed with a tenant scope)
        carries its tenant in the ``classification`` dict under the canonical
        ``"tenant_id"`` key. A pure-declarative group (authored inline, not bound
        to a tenant) returns ``None`` — it can be materialised under any caller
        tenant.
        """
        classification = getattr(group, "classification", None)
        if isinstance(classification, dict):
            value = classification.get("tenant_id")
            if isinstance(value, str) and value:
                return value
        return None

    def _redact(self, group: "FeatureGroup", frame: pl.DataFrame) -> pl.DataFrame:
        """Apply read-path classification redaction to the mutation return frame.

        Per ``rules/dataflow-classification.md`` MUST-1, a mutation return-path
        MUST route classified columns through the same redaction the read path
        uses. The group's ``classification`` dict names classified columns
        (``{column: (level, strategy)}``); a column flagged for REDACT is replaced
        with the canonical ``"[REDACTED]"`` sentinel in the returned summary
        frame. Unclassified columns pass through unchanged.

        The PERSISTED rows are NOT redacted (the backing store holds real
        values); only the returned summary frame is — exactly the mutation
        return-path contract.
        """
        classification = getattr(group, "classification", None)
        if not isinstance(classification, dict) or not classification:
            return frame

        redacted = frame
        for col, policy in classification.items():
            if col not in redacted.columns:
                continue
            strategy = None
            if isinstance(policy, (tuple, list)) and len(policy) >= 2:
                strategy = str(policy[1]).upper()
            if strategy == "REDACT":
                redacted = redacted.with_columns(pl.lit("[REDACTED]").alias(col))
        return redacted
