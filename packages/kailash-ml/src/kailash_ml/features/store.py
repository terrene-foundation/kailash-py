# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""FeatureStore — kailash-ml 1.0.0 polars-native, DataFlow-integrated.

Single source of truth for feature retrieval at training + serving time.
Reads route through ``dataflow.ml_feature_source(feature_group)`` (specced
in ``specs/dataflow-ml-integration.md §1.1``). This module BLOCKS silent
fallback: when the DataFlow binding is absent, a descriptive
:class:`ImportError` cites the canonical sibling spec per
``rules/dependencies.md`` § "Exception: Optional Extras with Loud Failure".

Per ``rules/facade-manager-detection.md``:

1. The class is a ``*Store`` manager exposed via the kailash-ml public
   surface; every method takes ``tenant_id`` as a kwarg so cross-tenant
   callers cannot collide.
2. Constructor accepts the live ``DataFlow`` instance (Rule 3 — explicit
   framework dependency, no global lookup, no self-construction).
3. The companion ``tests/integration/test_feature_store_wiring.py`` is the
   Tier-2 wiring gate for Rule 1.

Per ``rules/tenant-isolation.md``:

- Every cache key includes ``tenant_id`` (Rule 1).
- Missing ``tenant_id`` raises ``TenantRequiredError`` with kwarg-only
  ``reason=`` per ``MLError.__init__`` (Rule 2).
- Invalidation via :meth:`invalidate_schema` accepts ``tenant_id`` and
  emits a version-wildcard sweep (Rule 3 / 3a).

Per ``rules/observability.md``:

- Every ``get_features`` call emits a structured log line carrying
  ``source='dataflow'``, ``mode='real'`` (never ``'fake'`` in production),
  ``tenant_id``, ``schema``, ``version``, ``latency_ms``.
- Schema / column names appear ONLY at DEBUG level per Rule 8; the INFO
  line reports scalar counts only.

Per ``rules/framework-first.md``:

- Zero raw SQL in this file. Every DDL / materialisation / read path
  delegates to ``DataFlow`` primitives. DDL lives in orchestrator-owned
  numbered migrations per ``rules/schema-migration.md``.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

import polars as pl
from kailash_ml.errors import FeatureStoreError, TenantRequiredError
from kailash_ml.features._schema_feature_group import SchemaFeatureGroup
from kailash_ml.features.cache_keys import (
    make_feature_cache_key,
    make_feature_group_wildcard,
    validate_tenant_id,
)
from kailash_ml.features.schema import FeatureSchema

if TYPE_CHECKING:
    # Avoid importing DataFlow eagerly — kailash-ml depends on kailash-dataflow
    # as a wave peer but downstream callers may import FeatureStore on paths
    # that never touch DataFlow (e.g. type-only utility imports).
    from kailash_ml.features.feature_group import FeatureGroup

    from dataflow.core.engine import DataFlow

__all__ = ["FeatureStore"]


logger = logging.getLogger(__name__)

# Structured-logger field name 'module' collides with LogRecord.module
# (`rules/observability.md` Rule 9). We use 'store_module' etc. when we
# log any class-level metadata.


class FeatureStore:
    """[P0: Production] Polars-native, DataFlow-integrated feature store.

    Parameters
    ----------
    dataflow:
        A live :class:`dataflow.DataFlow` instance. The store does NOT
        construct its own DataFlow — Rule 3 of
        ``rules/facade-manager-detection.md`` requires the parent
        framework instance to be passed in explicitly. This ensures the
        store's reads hit the same connection pool / audit trail / cache
        that user operations see.
    default_tenant_id:
        Optional default tenant_id. When supplied it is used by any
        method call that omits ``tenant_id=``. Passing the canonical
        sentinel ``"_single"`` opts the store into single-tenant mode
        per ``ml-tracking.md §7.2``. When ``None`` (the default), every
        method call MUST specify ``tenant_id`` explicitly or
        :class:`~kailash_ml.errors.TenantRequiredError` is raised.
    """

    def __init__(
        self,
        dataflow: "DataFlow",
        *,
        default_tenant_id: str | None = None,
    ) -> None:
        if dataflow is None:
            raise TypeError(
                "FeatureStore(dataflow=...) is required — construct via "
                "DataFlow(...) and pass the instance in. See "
                "rules/facade-manager-detection.md Rule 3."
            )
        self._df = dataflow
        if default_tenant_id is not None:
            # Eager-validate to fail loudly at construction.
            validate_tenant_id(default_tenant_id, operation="FeatureStore.__init__")
        self._default_tenant_id = default_tenant_id

    # ------------------------------------------------------------------
    # Tenant resolution
    # ------------------------------------------------------------------

    def _resolve_tenant(self, tenant_id: str | None, *, operation: str) -> str:
        """Resolve the effective tenant_id for a method call.

        Falls back to ``default_tenant_id`` when the caller omits
        ``tenant_id``. Raises :class:`TenantRequiredError` via
        :func:`validate_tenant_id` when neither is available.
        """
        effective = tenant_id if tenant_id is not None else self._default_tenant_id
        return validate_tenant_id(effective, operation=operation)

    # ------------------------------------------------------------------
    # Retrieval — point-in-time correct
    # ------------------------------------------------------------------

    async def get_features(
        self,
        schema: FeatureSchema,
        timestamp: datetime | None = None,
        *,
        tenant_id: str | None = None,
        entity_ids: list[str] | None = None,
    ) -> pl.DataFrame:
        """Retrieve features for a schema.

        Returns a polars DataFrame containing the schema's
        ``entity_id_column`` plus every column in ``schema.fields``. No
        pandas at any point in the public API (invariant #1).

        When ``timestamp`` is provided the returned values are the
        point-in-time correct feature values AS OF that timestamp — i.e.
        every row reflects events with ``event_time <= timestamp``, and
        no row carries a value materialised strictly after ``timestamp``
        (``specs/ml-feature-store.md §6.2 MUST 1``). When ``timestamp``
        is ``None`` the latest values are returned.

        Missing ``tenant_id`` (and no default on the store) raises
        :class:`~kailash_ml.errors.TenantRequiredError` per
        ``rules/tenant-isolation.md`` Rule 2.

        Absent ``dataflow.ml_feature_source`` raises :class:`ImportError`
        with an actionable message that cites
        ``specs/dataflow-ml-integration.md §1.1`` per
        ``rules/dependencies.md`` § "Exception: Optional Extras with Loud
        Failure".
        """
        if not isinstance(schema, FeatureSchema):
            raise TypeError(
                f"FeatureStore.get_features: schema must be FeatureSchema, "
                f"got {type(schema).__name__}"
            )
        effective_tenant = self._resolve_tenant(
            tenant_id, operation="FeatureStore.get_features"
        )
        if timestamp is not None and not isinstance(timestamp, datetime):
            raise TypeError(
                f"FeatureStore.get_features: timestamp must be datetime, got "
                f"{type(timestamp).__name__}"
            )

        ml_feature_source = _import_ml_feature_source()
        # Structured log — INFO entry
        started_at = time.monotonic()
        logger.info(
            "feature_store.get_features.start",
            extra={
                "source": "dataflow",
                "mode": "real",
                "tenant_id": effective_tenant,
                "schema": schema.name,
                "version": schema.version,
                "has_timestamp": timestamp is not None,
                "entity_count": len(entity_ids) if entity_ids is not None else None,
            },
        )
        try:
            # The DataFlow binding (ml_feature_source) consumes a
            # FeatureGroup-shaped object that owns its backing-store query, NOT
            # the declarative FeatureSchema. Wrap the schema in the read adapter
            # (issue #1241): it reads the backing DataFlow table named after the
            # schema (schema.name == model name) and applies point-in-time /
            # tenant / window scoping. See _schema_feature_group for the
            # FeatureSchema -> FeatureGroup bridge and the as-of contract.
            group = SchemaFeatureGroup(
                dataflow=self._df,
                schema=schema,
                multi_tenant=self._df.config.security.multi_tenant,
            )
            # Delegate to DataFlow's polars-LazyFrame binding. The binding
            # itself enforces SQL-identifier safety + parameterized VALUES
            # per specs/dataflow-ml-integration.md §2.4.
            lazy = ml_feature_source(
                group,
                tenant_id=effective_tenant,
                point_in_time=timestamp,
            )
            # Always collect to a concrete polars.DataFrame — invariant #1
            # mandates DataFrame (not LazyFrame) at the public API boundary.
            df = lazy.collect() if isinstance(lazy, pl.LazyFrame) else lazy
            if not isinstance(df, pl.DataFrame):
                # Defensive — the binding contract promises polars; any
                # other return type is a wiring bug worth failing loudly.
                raise FeatureStoreError(
                    reason=(
                        "dataflow.ml_feature_source returned "
                        f"{type(df).__name__}, expected polars.DataFrame"
                    ),
                    tenant_id=effective_tenant,
                )
            if entity_ids is not None:
                df = df.filter(pl.col(schema.entity_id_column).is_in(entity_ids))

            latency_ms = (time.monotonic() - started_at) * 1000.0
            logger.info(
                "feature_store.get_features.ok",
                extra={
                    "source": "dataflow",
                    "mode": "real",
                    "tenant_id": effective_tenant,
                    "schema": schema.name,
                    "version": schema.version,
                    "row_count": df.height,
                    "latency_ms": latency_ms,
                },
            )
            return df
        except TenantRequiredError:
            # Let TenantRequiredError surface as-is (already raised by the
            # validator with a specific reason). Do NOT reclassify as
            # FeatureStoreError — the tenant contract is a hard gate.
            raise
        except ImportError:
            # Re-raise loud import — do NOT reclassify as FeatureStoreError
            # (operators must see the dependency gap clearly).
            raise
        except Exception as exc:
            latency_ms = (time.monotonic() - started_at) * 1000.0
            logger.exception(
                "feature_store.get_features.error",
                extra={
                    "source": "dataflow",
                    "mode": "real",
                    "tenant_id": effective_tenant,
                    "schema": schema.name,
                    "version": schema.version,
                    "latency_ms": latency_ms,
                },
            )
            raise FeatureStoreError(
                reason=f"get_features failed: {type(exc).__name__}",
                tenant_id=effective_tenant,
            ) from exc

    # ------------------------------------------------------------------
    # Write-through materialisation (FM2 Shard B — composed, not a kwarg)
    # ------------------------------------------------------------------

    async def materialize(
        self,
        group: "FeatureGroup",
        data: pl.DataFrame,
        *,
        tenant_id: str | None = None,
    ) -> Any:
        """Write-through a :class:`FeatureGroup`'s rows; register lineage.

        Thin facade over the composed
        :class:`~kailash_ml.features.materialiser.FeatureMaterialiser`
        (constructed internally from the bound ``self._df`` — NO new
        ``FeatureStore.__init__`` kwarg, per spec §11.6 / composition over
        constructor-flag bloat, ``rules/facade-manager-detection.md`` Rule 3).

        Computes the group's declared ``@feature`` derived columns on ``data``
        via the shipped ``dataflow.transform`` binding, persists the resulting
        feature table through DataFlow Express (no raw SQL — the backing table is
        a ``@db.model`` driven by ``auto_migrate``), and registers the
        materialized dataset's lineage hash via ``dataflow.hash``.

        Idempotent: re-running the same ``materialize(...)`` upserts the same
        content-addressed rows and does NOT duplicate them.

        Async per the sibling :meth:`get_features` — both are ``async def`` so the
        canonical read+write pipeline composes under any event loop
        (``rules/patterns.md`` § Paired Public Surface).

        Parameters
        ----------
        group:
            The authored :class:`FeatureGroup` to materialise.
        data:
            The input ``polars.DataFrame`` carrying the base columns the group's
            schema + ``@feature`` expressions read.
        tenant_id:
            Tenant scope; resolved via the store's tenant policy
            (:meth:`_resolve_tenant`). Missing tenant raises
            :class:`~kailash_ml.errors.TenantRequiredError`. A cross-tenant
            materialise raises
            :class:`~kailash_ml.errors.CrossTenantReadError`.

        Per-row event-time is read from the schema's ``timestamp_column`` in
        ``data`` so a later :meth:`get_features` ``timestamp=T`` read is
        point-in-time correct. The write path takes no ``point_in_time`` —
        point-in-time is a READ concern.

        Returns
        -------
        kailash_ml.features.materialiser.MaterializeResult
            ``frame`` (redacted persisted DataFrame), ``lineage_hash``,
            ``row_count``, ``group``, ``version``, ``tenant_id``,
            ``invalidation_pattern``.
        """
        effective_tenant = self._resolve_tenant(
            tenant_id, operation="FeatureStore.materialize"
        )
        # Compose the materialiser from the bound DataFlow instance — NOT a
        # constructor flag (spec §11.6). Constructed per-call so the facade adds
        # no state to FeatureStore.
        from kailash_ml.features.materialiser import FeatureMaterialiser

        materialiser = FeatureMaterialiser(self._df)
        return await materialiser.materialize(
            group,
            data,
            tenant_id=effective_tenant,
        )

    # ------------------------------------------------------------------
    # GDPR tenant erasure (FM2 Shard F — composed helper, not a kwarg)
    # ------------------------------------------------------------------

    async def erase_tenant(
        self,
        *,
        tenant_id: str | None = None,
        force: bool = False,
    ) -> Any:
        """Erase every feature trace of a tenant: materialized rows + registry.

        Thin facade over the composed
        :func:`~kailash_ml.features.erasure.erase_tenant` helper (called with the
        bound ``self._df`` — NO new ``FeatureStore.__init__`` kwarg, per spec
        §11.6 / composition over constructor-flag bloat,
        ``rules/facade-manager-detection.md`` Rule 3).

        Deletes, for the given tenant, (a) every materialized feature-table row
        persisted by :class:`~kailash_ml.features.materialiser.FeatureMaterialiser`
        AND (b) every :class:`~kailash_ml.features.registry.FeatureRegistry` row —
        through DataFlow Express (``express.list`` + ``express.delete``, NO raw
        SQL). The registry is the authoritative per-tenant index of feature
        tables; materialized rows are tenant-scoped via the deterministic
        content-addressed id (no tenant column needed). The returned
        ``invalidation_patterns`` drive any online-store cache eviction.

        Async per the sibling :meth:`get_features` / :meth:`materialize` — all
        three are ``async def`` so the canonical read+write+erase pipeline
        composes under any event loop (``rules/patterns.md`` § Paired Public
        Surface).

        Parameters
        ----------
        tenant_id:
            The tenant to erase; resolved via the store's tenant policy
            (:meth:`_resolve_tenant`). Missing / invalid tenant raises
            :class:`~kailash_ml.errors.TenantRequiredError` — a destructive
            operation MUST NOT run unscoped (``rules/security.md``).
        force:
            When ``True``, bypass the alias-protection refusal hook (operator
            override). Defaults to ``False`` (refusal hook active).

        Returns
        -------
        kailash_ml.features.erasure.EraseTenantResult
            ``tenant_fingerprint``, ``feature_rows``, ``registry_rows``,
            ``feature_groups``, ``invalidation_patterns``, ``audit_emitted``.

        Raises
        ------
        kailash_ml.errors.TenantRequiredError
            ``tenant_id`` missing / invalid / a forbidden sentinel.
        kailash_ml.errors.ErasureRefusedError
            The tenant has a feature group linked to a protected resource and
            ``force`` is ``False`` (REUSED canonical error, not redefined).
        kailash_ml.errors.FeatureStoreError
            A delete leg failed — the erase is PARTIAL; surfaced (fail-closed),
            never swallowed (``rules/zero-tolerance.md`` Rule 3).
        """
        effective_tenant = self._resolve_tenant(
            tenant_id, operation="FeatureStore.erase_tenant"
        )
        # Compose the erasure helper from the bound DataFlow instance — NOT a
        # constructor flag (spec §11.6).
        from kailash_ml.features.erasure import erase_tenant as _erase_tenant

        return await _erase_tenant(self._df, tenant_id=effective_tenant, force=force)

    # ------------------------------------------------------------------
    # Cache key helpers (read-path, tenant-scoped)
    # ------------------------------------------------------------------

    def cache_key_for_row(
        self,
        schema: FeatureSchema,
        row_key: str,
        *,
        tenant_id: str | None = None,
    ) -> str:
        """Return the canonical tenant-scoped cache key for a feature row.

        Keeps the cache-key contract auditable from a single call site:
        every code path that reaches the cache goes through this helper,
        so a future keyspace bump (``rules/tenant-isolation.md`` Rule 3a)
        patches one method.
        """
        effective_tenant = self._resolve_tenant(
            tenant_id, operation="FeatureStore.cache_key_for_row"
        )
        return make_feature_cache_key(
            tenant_id=effective_tenant,
            schema_name=schema.name,
            version=schema.version,
            row_key=row_key,
        )

    def invalidation_pattern(
        self,
        schema: FeatureSchema,
        *,
        tenant_id: str | None = None,
        all_versions: bool = False,
    ) -> str:
        """Return the tenant-scoped wildcard for cache invalidation.

        Per ``rules/tenant-isolation.md`` Rule 3 invalidation is scoped
        by tenant; missing tenant_id raises. Per Rule 3a the wildcard
        uses ``v*`` so a future keyspace-version bump sweeps every
        historical key without invalidator-side edits.
        """
        effective_tenant = self._resolve_tenant(
            tenant_id, operation="FeatureStore.invalidation_pattern"
        )
        return make_feature_group_wildcard(
            tenant_id=effective_tenant,
            schema_name=schema.name,
            version=None if all_versions else schema.version,
        )

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    @property
    def dataflow(self) -> "DataFlow":
        """Return the bound DataFlow instance (read-only)."""
        return self._df

    @property
    def default_tenant_id(self) -> str | None:
        return self._default_tenant_id


# ---------------------------------------------------------------------------
# Deferred DataFlow binding — loud failure when ml_feature_source is not landed.
# ---------------------------------------------------------------------------


def _import_ml_feature_source() -> Any:
    """Resolve ``ml_feature_source`` at call time.

    Per ``rules/dependencies.md`` § "Exception: Optional Extras with Loud
    Failure", a missing dependency MUST NOT silently degrade to ``None``.
    The loud ImportError tells operators exactly which sibling spec
    owns the binding so the cross-spec trail is discoverable.

    Three resolution paths, in priority order:

    1. ``dataflow.ml_feature_source`` — top-level re-export, future
       canonical home (kept for forward compatibility).
    2. ``dataflow.ml.ml_feature_source`` — current canonical location
       per ``specs/dataflow-ml-integration.md §1.1``; kailash-dataflow
       2.1+ exports the helper from the ``dataflow.ml`` sub-package.
    3. ``dataflow.ml_integration.ml_feature_source`` — legacy probe
       kept for back-compat with downstream forks that placed the
       binding at the older location.

    Deferred import also means test code that monkey-patches the
    binding at its original module can do so without the store having
    to be re-imported.
    """
    try:
        # Path 1: top-level re-export (forward-compatible canonical).
        from dataflow import ml_feature_source  # type: ignore[attr-defined]

        return ml_feature_source
    except (ImportError, AttributeError):
        pass
    try:
        # Path 2: current canonical location (DataFlow 2.1+).
        from dataflow.ml import ml_feature_source  # type: ignore[attr-defined]

        return ml_feature_source
    except (ImportError, AttributeError):
        pass
    try:
        # Path 3: legacy back-compat probe (guarded; module may be absent).
        from dataflow.ml_integration import (
            ml_feature_source,  # pyright: ignore[reportMissingImports]; type: ignore[import-not-found]
        )

        return ml_feature_source
    except (ImportError, AttributeError) as exc:
        # Loud actionable failure — cite the sibling spec, not workspace
        # history. Per `rules/specs-authority.md` § 1 user-facing strings
        # cite specs (durable cross-references), not ad-hoc workspace IDs.
        raise ImportError(
            "ml_feature_source is not available. kailash-ml 1.0+ "
            "FeatureStore.get_features requires DataFlow 2.1.0's polars "
            "binding — see specs/dataflow-ml-integration.md §1.1 for the "
            "canonical contract. Upgrade kailash-dataflow to a version "
            "that exports ml_feature_source from `dataflow.ml`, or wire "
            "the binding into dataflow/ml_integration.py."
        ) from exc
