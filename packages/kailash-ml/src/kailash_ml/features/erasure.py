# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""FeatureStore-layer GDPR tenant erasure (``FeatureStore.erase_tenant``).

Implements ``specs/ml-feature-store.md §11.4`` (Storage / Retention / Eraser —
the eraser portion, now SHIPPED) — the FeatureStore-layer counterpart to the
tracking-layer ``km.erase_subject`` (``tracking/erasure.py``). Where
``erase_subject`` deletes a data subject's run traces, ``erase_tenant`` deletes a
tenant's FEATURE data: every materialized feature-table row AND every
:class:`~kailash_ml.features.registry.FeatureRegistry` row registered under the
tenant.

**Composition, not a constructor flag (spec §11.6).** This is a free function the
:class:`~kailash_ml.features.store.FeatureStore` facade calls, passing the live
``DataFlow`` instance it already holds (``rules/facade-manager-detection.md``
Rule 3 — explicit framework dependency, no global lookup, no self-construction).
``FeatureStore.__init__`` gains no new kwargs.

**Framework-first (``rules/framework-first.md`` / zero-tolerance Rule 4).** Every
delete routes through DataFlow Express (``express.list`` to enumerate +
``express.delete`` per row) — zero raw SQL, zero inline DDL. The registry table is
the authoritative INDEX of which feature tables a tenant has: erasure reads the
registry rows for the tenant, deletes the materialized rows of each registered
feature table, then deletes the registry rows themselves.

**Tenant-scoped delete with NO tenant column.** The materialiser persists each row
under a deterministic content-addressed PK ``id = sha256(tenant, group, version,
entity_id, timestamp)[:32]`` (``materialiser.py``) — the tenant is BAKED INTO the
id, not stored as a filterable column. So erasure scopes the materialized-row
delete by RE-DERIVING each candidate row's id from its ``entity_id`` /
``timestamp`` columns + the registry-known ``(tenant, name, version)`` and deleting
ONLY the rows whose stored ``id`` matches the tenant-derived id. A sibling tenant's
row (different tenant in the hash) yields a different derived id and is left
untouched — structural cross-tenant isolation without a tenant column and without
raw SQL.

**Fail-closed on partial erase (``rules/zero-tolerance.md`` Rule 3).** A delete-leg
failure (registry delete OR materialized-row delete) is NEVER swallowed — it
surfaces as :class:`~kailash_ml.errors.FeatureStoreError` so the caller knows the
erase is incomplete rather than silently leaving half-erased state.

**Audit trail (``rules/observability.md`` Rule 4 — state transition).** Erasure
emits a structured ``feature_store.erase_tenant.{start,ok,error}`` log line. The
tenant id is the only tenant datum logged (Rule 8 — no raw feature data / PII
beyond ``tenant_id``); the structured ``new_state`` carries per-resource counts.

See ``specs/ml-feature-store.md §11.4`` (eraser — shipped) + §5 (tenant cache keys
/ invalidation).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from kailash_ml.errors import (
    ErasureRefusedError,
    FeatureStoreError,
    fingerprint_classified_value,
)
from kailash_ml.features.cache_keys import (
    make_feature_group_wildcard,
    validate_tenant_id,
)
from kailash_ml.features.materialiser import FeatureMaterialiser
from kailash_ml.features.registry import FeatureRegistry
from kailash_ml.features.schema import FeatureSchema

if TYPE_CHECKING:  # avoid eager DataFlow import on type-only paths
    from dataflow.core.engine import DataFlow

__all__ = ["erase_tenant", "EraseTenantResult"]

logger = logging.getLogger(__name__)

# The registry @db.model name — the authoritative per-tenant feature-table index.
# Imported as a private constant from the registry module so the two stay in
# lockstep (a registry model rename would break this import loudly, not silently).
from kailash_ml.features.registry import _MODEL_NAME as _REGISTRY_MODEL  # noqa: E402


class EraseTenantResult(dict):
    """Structured return of :func:`erase_tenant`.

    A ``dict`` subclass (JSON-friendly, drop-in for callers that treat the
    result as a mapping) carrying:

    * ``tenant_fingerprint`` — ``sha256:<8hex>`` of the erased tenant id (never
      the raw tenant id, per the audit discipline).
    * ``feature_rows`` — count of materialized feature-table rows deleted.
    * ``registry_rows`` — count of :class:`FeatureRegistry` rows deleted.
    * ``feature_groups`` — count of distinct ``(name, version)`` feature tables
      swept.
    * ``invalidation_patterns`` — the tenant-scoped cache wildcards swept (one per
      erased feature group), so the caller can drive the online-store eviction.
    * ``audit_emitted`` — always ``True``; present for explicit operator-facing
      confirmation that the state-transition audit log line was emitted.
    """


def _row_timestamp(value: Any) -> Any:
    """Coerce a backing-store timestamp column value back to a ``datetime``.

    DataFlow's SQLite backend round-trips a ``datetime`` column as an ISO-ish
    string (e.g. ``"2026-01-01 00:00:00+00:00"``); the materialiser's
    ``_row_id`` hashes a ``datetime`` via ``.isoformat()`` but a plain string via
    ``str(...)``. To re-derive the SAME id the erasure computed at materialise
    time, parse the stored value back to a ``datetime`` when it round-tripped as a
    string so ``_row_id`` hashes the canonical ``isoformat`` form. A value that is
    already a ``datetime`` passes through; an unparseable value passes through
    unchanged (``_row_id`` then hashes ``str(value)``, matching the persist-time
    behaviour for non-datetime timestamps).
    """
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # DataFlow stores `datetime` as `YYYY-MM-DD HH:MM:SS[.ffffff][+HH:MM]`.
        # Normalise the space separator to `T` for `fromisoformat`.
        candidate = value.replace(" ", "T", 1)
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            return value
    return value


async def _delete_tenant_feature_rows(
    df: "DataFlow",
    *,
    schema: FeatureSchema,
    tenant: str,
) -> int:
    """Delete a tenant's materialized rows from ONE feature table.

    Enumerates the backing table via ``express.list`` (no raw SQL), re-derives
    each row's tenant-scoped content-addressed id from its ``entity_id`` /
    ``timestamp`` columns + ``(tenant, name, version)``, and deletes ONLY the rows
    whose stored ``id`` matches the tenant-derived id. A sibling tenant's row
    yields a different derived id and is left intact.

    Returns the count of rows deleted. Re-raises any delete failure as
    :class:`FeatureStoreError` so a partial erase is never silently swallowed
    (``rules/zero-tolerance.md`` Rule 3 / fail-closed).
    """
    entity_col = schema.entity_id_column
    ts_col = schema.timestamp_column
    fp = fingerprint_classified_value(tenant)  # never echo raw tenant in errors

    try:
        rows = await df.express.list(schema.name, {}, limit=1_000_000)
    except Exception as exc:  # noqa: BLE001 — re-raised typed; not swallowed
        raise FeatureStoreError(
            reason=(
                f"erase_tenant: enumerating feature table {schema.name!r} failed: "
                f"{type(exc).__name__}"
            ),
            tenant_fingerprint=fp,
        ) from exc

    deleted = 0
    for row in rows:
        stored_id = row.get("id")
        if not isinstance(stored_id, str):
            continue
        entity_val = row.get(entity_col)
        ts_val = _row_timestamp(row.get(ts_col)) if ts_col is not None else None
        derived_id = FeatureMaterialiser._row_id(
            tenant=tenant,
            group=schema.name,
            version=schema.version,
            entity_id=entity_val,
            timestamp=ts_val,
        )
        if derived_id != stored_id:
            # Not this tenant's row (different tenant baked into the id hash).
            continue
        try:
            ok = await df.express.delete(schema.name, stored_id)
        except Exception as exc:  # noqa: BLE001 — re-raised typed; not swallowed
            raise FeatureStoreError(
                reason=(
                    f"erase_tenant: deleting feature row from {schema.name!r} "
                    f"failed (PARTIAL ERASE — state is half-deleted): "
                    f"{type(exc).__name__}"
                ),
                tenant_fingerprint=fp,
            ) from exc
        if ok:
            deleted += 1
    return deleted


async def _delete_tenant_registry_rows(
    df: "DataFlow",
    *,
    tenant: str,
) -> int:
    """Delete every :class:`FeatureRegistry` row for ``tenant``.

    The registry @db.model carries an explicit ``tenant_id`` column, so the
    delete scopes by a ``express.list(filter={"tenant_id": tenant})`` enumeration
    + per-row ``express.delete`` (no raw SQL). Fail-closed: a delete failure
    re-raises as :class:`FeatureStoreError`.
    """
    fp = fingerprint_classified_value(tenant)  # never echo raw tenant in errors
    try:
        rows = await df.express.list(
            _REGISTRY_MODEL, {"tenant_id": tenant}, limit=1_000_000
        )
    except Exception as exc:  # noqa: BLE001 — re-raised typed; not swallowed
        raise FeatureStoreError(
            reason=(
                f"erase_tenant: enumerating registry rows failed: "
                f"{type(exc).__name__}"
            ),
            tenant_fingerprint=fp,
        ) from exc

    deleted = 0
    for row in rows:
        row_id = row.get("id")
        if row_id is None:
            continue
        try:
            ok = await df.express.delete(_REGISTRY_MODEL, row_id)
        except Exception as exc:  # noqa: BLE001 — re-raised typed; not swallowed
            raise FeatureStoreError(
                reason=(
                    f"erase_tenant: deleting registry row failed (PARTIAL ERASE — "
                    f"state is half-deleted): {type(exc).__name__}"
                ),
                tenant_fingerprint=fp,
            ) from exc
        if ok:
            deleted += 1
    return deleted


async def erase_tenant(
    df: "DataFlow",
    *,
    tenant_id: str | None = None,
    force: bool = False,
) -> EraseTenantResult:
    """Erase every feature trace of ``tenant_id``: materialized rows + registry.

    The registry is the authoritative INDEX of a tenant's feature tables. Erasure:

    1. Validates ``tenant_id`` (``rules/security.md`` — a destructive operation
       MUST NOT be tricked into a cross-tenant or unscoped delete; an invalid /
       sentinel tenant raises before any delete).
    2. Runs the alias-protection refusal hook — refuses with
       :class:`~kailash_ml.errors.ErasureRefusedError` (REUSED, not redefined)
       when the tenant has a feature group linked to a protected resource. The
       hook is forward-compat (mirrors ``tracking/erasure.py``): absent the
       backend hook, the default disposition is proceed. ``force=True`` bypasses
       the refusal hook (operator override).
    3. Reads the tenant's :class:`FeatureRegistry` rows (the per-tenant table
       index) and, for each registered ``(name, version)`` feature table, deletes
       the tenant's materialized rows (tenant-scoped via the deterministic
       content-addressed id — no tenant column, no raw SQL).
    4. Deletes the tenant's registry rows.
    5. Sweeps the tenant-scoped cache wildcard per erased feature group (the
       returned ``invalidation_patterns`` drive any online-store eviction).
    6. Emits a structured ``feature_store.erase_tenant.ok`` state-transition audit
       log line (``tenant_id`` only — no raw feature data / PII).

    **Idempotent.** A second call on an already-erased tenant finds zero registry
    rows, deletes nothing, and returns zero counts — NOT an error.

    **Fail-closed.** A delete-leg failure raises :class:`FeatureStoreError` so the
    caller knows the erase is incomplete (``rules/zero-tolerance.md`` Rule 3); the
    error message flags PARTIAL ERASE so half-deleted state is never silent.

    Parameters
    ----------
    df:
        The live ``DataFlow`` instance backing both the registry and the
        materialized feature tables. Required (composition,
        ``rules/facade-manager-detection.md`` Rule 3).
    tenant_id:
        The tenant to erase. Validated via
        :func:`~kailash_ml.features.cache_keys.validate_tenant_id`; missing /
        invalid / sentinel raises :class:`~kailash_ml.errors.TenantRequiredError`.
    force:
        When ``True``, bypass the alias-protection refusal hook (operator
        override). Defaults to ``False`` (refusal hook active).

    Returns
    -------
    EraseTenantResult
        ``tenant_fingerprint``, ``feature_rows``, ``registry_rows``,
        ``feature_groups``, ``invalidation_patterns``, ``audit_emitted``.

    Raises
    ------
    kailash_ml.errors.TenantRequiredError
        ``tenant_id`` missing / invalid / a forbidden sentinel.
    kailash_ml.errors.ErasureRefusedError
        The tenant has a feature group linked to a protected resource and
        ``force`` is ``False``.
    kailash_ml.errors.FeatureStoreError
        A delete leg failed — the erase is PARTIAL; surfaced rather than swallowed.
    """
    if df is None:
        raise TypeError(
            "erase_tenant(df=...) requires a live DataFlow instance "
            "(composition, not a FeatureStore kwarg — spec §11.6; "
            "rules/facade-manager-detection.md Rule 3)."
        )

    # 1. Validate the tenant — a destructive op MUST NOT run unscoped/cross-tenant.
    tenant = validate_tenant_id(tenant_id, operation="FeatureStore.erase_tenant")
    fingerprint = fingerprint_classified_value(tenant)

    started_at = time.monotonic()
    logger.info(
        "feature_store.erase_tenant.start",
        extra={
            "source": "dataflow",
            "mode": "real",
            "tenant_fingerprint": fingerprint,
            "force": force,
        },
    )

    try:
        registry = FeatureRegistry(df, default_tenant_id=tenant)
        # Ensure the registry @db.model is registered/migrated before we read it
        # (idempotent; a never-registered tenant yields an empty list, not error).
        registry._ensure_model()

        # 2. Alias-protection refusal hook (forward-compat; REUSE ErasureRefusedError).
        if not force:
            alias_check = getattr(df, "has_production_alias_for_tenant", None)
            if alias_check is not None:
                refused = await alias_check(tenant_id=tenant)
                if refused:
                    raise ErasureRefusedError(
                        reason=(
                            "erase_tenant refused: tenant has a feature group "
                            "linked to a 'production'-aliased resource. Clear the "
                            "alias first or pass force=True "
                            "(spec ml-feature-store.md §11.4 / §11.3)."
                        ),
                        tenant_fingerprint=fingerprint,
                    )

        # 3. Read the tenant's registry rows — the per-tenant feature-table index.
        try:
            registry_rows = await df.express.list(
                _REGISTRY_MODEL, {"tenant_id": tenant}, limit=1_000_000
            )
        except Exception as exc:  # noqa: BLE001 — re-raised typed; not swallowed
            raise FeatureStoreError(
                reason=(
                    f"erase_tenant: reading registry index failed: "
                    f"{type(exc).__name__}"
                ),
                tenant_fingerprint=fingerprint,
            ) from exc

        # Distinct schemas for this tenant (a name may carry multiple versions —
        # each version is its own materialized table-shape, all named schema.name,
        # so we delete per (name, version) to derive the right content-addressed id).
        schemas: list[FeatureSchema] = []
        for row in registry_rows:
            try:
                schemas.append(FeatureSchema.from_dict(json.loads(row["schema_json"])))
            except Exception as exc:  # noqa: BLE001 — re-raised typed; not swallowed
                raise FeatureStoreError(
                    reason=(
                        f"erase_tenant: rehydrating a registry schema failed: "
                        f"{type(exc).__name__}"
                    ),
                    tenant_fingerprint=fingerprint,
                ) from exc

        # 3b. Delete the tenant's materialized rows per registered feature table.
        feature_rows = 0
        invalidation_patterns: list[str] = []
        for schema in schemas:
            feature_rows += await _delete_tenant_feature_rows(
                df, schema=schema, tenant=tenant
            )
            # 5. Tenant-scoped cache wildcard for the online-store eviction sweep.
            invalidation_patterns.append(
                make_feature_group_wildcard(
                    tenant_id=tenant,
                    schema_name=schema.name,
                    version=schema.version,
                )
            )

        # 4. Delete the tenant's registry rows (after the materialized rows so a
        # mid-erase failure leaves the registry index intact for a retry).
        registry_count = await _delete_tenant_registry_rows(df, tenant=tenant)

        latency_ms = (time.monotonic() - started_at) * 1000.0
        # 6. State-transition audit log (observability Rule 4). tenant_id only —
        # no raw feature data / PII beyond the tenant (Rule 8).
        logger.info(
            "feature_store.erase_tenant.ok",
            extra={
                "source": "dataflow",
                "mode": "real",
                "tenant_fingerprint": fingerprint,
                "action": "erase",
                "resource_kind": "feature_tenant",
                "new_state": json.dumps(
                    {
                        "feature_rows": feature_rows,
                        "registry_rows": registry_count,
                        "feature_groups": len(schemas),
                    }
                ),
                "latency_ms": latency_ms,
            },
        )

        return EraseTenantResult(
            tenant_fingerprint=fingerprint,
            feature_rows=feature_rows,
            registry_rows=registry_count,
            feature_groups=len(schemas),
            invalidation_patterns=invalidation_patterns,
            audit_emitted=True,
        )
    except (ErasureRefusedError, FeatureStoreError):
        # Already typed + already logged-by-construction at the raise site or
        # below — surface unchanged (do NOT reclassify the refusal/partial-erase).
        latency_ms = (time.monotonic() - started_at) * 1000.0
        logger.warning(
            "feature_store.erase_tenant.error",
            extra={
                "source": "dataflow",
                "mode": "real",
                "tenant_fingerprint": fingerprint,
                "latency_ms": latency_ms,
            },
        )
        raise
    except Exception as exc:
        latency_ms = (time.monotonic() - started_at) * 1000.0
        logger.exception(
            "feature_store.erase_tenant.error",
            extra={
                "source": "dataflow",
                "mode": "real",
                "tenant_fingerprint": fingerprint,
                "latency_ms": latency_ms,
            },
        )
        raise FeatureStoreError(
            reason=f"erase_tenant failed: {type(exc).__name__}",
            tenant_fingerprint=fingerprint,
        ) from exc
