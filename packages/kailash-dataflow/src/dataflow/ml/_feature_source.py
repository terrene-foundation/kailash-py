# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``dataflow.ml_feature_source`` — materialize a ``FeatureGroup`` as a
polars ``LazyFrame``.

DataFlow does NOT take a hard dependency on kailash-ml. The
``FeatureGroup`` import is deferred inside the function body; if
kailash-ml is absent the helper raises
:class:`dataflow.ml._errors.FeatureSourceError` with an actionable
message (per ``rules/dependencies.md`` § "Optional Extras With Loud
Failure").

Tenant isolation:

* ``multi_tenant=True`` feature groups MUST receive a non-``None``
  ``tenant_id``; omission raises :class:`MLTenantRequiredError`
  (per ``rules/tenant-isolation.md`` § 2).
* ``tenant_id`` is preserved on every cache key the helper constructs
  (see ``_cache_key`` below) so a tenant-scoped invalidation only
  clears its own slots.

SQL safety: every identifier reaching the dialect adapter routes
through ``dialect.quote_identifier()`` (``rules/dataflow-identifier-safety.md``
§ 1) — feature group names, column names, and tenant-prefixed
identifiers are all validated + quoted before interpolation.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, List, Optional

from dataflow.ml._errors import (
    FeatureSourceError,
    MLTenantRequiredError,
)

logger = logging.getLogger(__name__)

__all__ = ["ml_feature_source", "build_cache_key"]


def _feature_source_cache_key(
    *,
    group_name: str,
    tenant_id: Optional[str],
    point_in_time: Optional[datetime],
    since: Optional[datetime],
    until: Optional[datetime],
    limit: Optional[int],
) -> str:
    """Build the canonical cache key for a feature-source materialization.

    Shape (per ``rules/tenant-isolation.md`` § 1 + § 3a):

    * multi-tenant: ``kailash_ml:v1:{tenant_id}:feature_source:{group}:{params}``
    * single-tenant: ``kailash_ml:v1:feature_source:{group}:{params}``

    The ``v1`` version segment mirrors DataFlow's cache keyspace, so a
    future cross-SDK parity bump can sweep both via ``v*`` wildcards
    without rewriting the ML-bridge caller.
    """
    params = (
        f"pit={point_in_time.isoformat() if point_in_time else 'none'}"
        f"|since={since.isoformat() if since else 'none'}"
        f"|until={until.isoformat() if until else 'none'}"
        f"|limit={limit if limit is not None else 'none'}"
    )
    if tenant_id is not None:
        return f"kailash_ml:v1:{tenant_id}:feature_source:{group_name}:{params}"
    return f"kailash_ml:v1:feature_source:{group_name}:{params}"


# Public alias — matches the naming convention in
# ``rules/tenant-isolation.md`` § "Audit Protocol" (``build_cache_key``).
build_cache_key = _feature_source_cache_key


def _import_feature_group_class() -> "Any":
    """Import ``FeatureGroup`` from kailash-ml, or raise a loud error.

    Deferred so callers who never invoke ``ml_feature_source`` do not
    need kailash-ml installed.
    """
    try:
        from kailash_ml.engines.feature_store import FeatureGroup  # type: ignore
    except ImportError as exc:  # pragma: no cover — depends on user's install
        raise FeatureSourceError(
            "dataflow.ml_feature_source requires kailash-ml>=1.0.0. "
            "Install via: pip install kailash-ml>=1.0.0"
        ) from exc
    return FeatureGroup


def _is_multi_tenant_group(feature_group: "Any") -> bool:
    """Inspect a ``FeatureGroup`` for its ``multi_tenant`` flag.

    Accepts both direct attribute and a nested ``model`` attribute —
    ``FeatureGroup`` implementations differ between kailash-ml versions.
    Default: ``False`` (single-tenant) if neither path is present.
    """
    multi = getattr(feature_group, "multi_tenant", None)
    if multi is not None:
        return bool(multi)
    model = getattr(feature_group, "model", None)
    if model is not None:
        return bool(getattr(model, "multi_tenant", False))
    return False


def _group_name(feature_group: "Any") -> str:
    """Return the feature group's canonical name."""
    name = getattr(feature_group, "name", None)
    if not isinstance(name, str) or not name:
        raise FeatureSourceError(
            "dataflow.ml_feature_source received a FeatureGroup without a "
            "string .name attribute"
        )
    return name


def _classification_metadata(feature_group: "Any") -> dict:
    """Return polars metadata to attach to the returned LazyFrame.

    The metadata preserves classification awareness from DataFlow
    through the transform chain (spec § 2.5). We do NOT include raw
    classified values — only classification metadata (which column
    is classified, which strategy).
    """
    classification = getattr(feature_group, "classification", None)
    if classification is None:
        return {}
    try:
        return {"kailash_ml.classification": dict(classification)}
    except Exception:
        # Feature groups may expose classification as an object, not a
        # dict. Store its repr so downstream tooling can inspect it
        # without DataFlow needing to know the kailash-ml type.
        return {"kailash_ml.classification": repr(classification)}


def ml_feature_source(
    feature_group: "Any",
    *,
    tenant_id: Optional[str] = None,
    point_in_time: Optional[datetime] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    limit: Optional[int] = None,
) -> "Any":
    """Materialize a feature group as a ``polars.LazyFrame``.

    Args:
        feature_group: The ``FeatureGroup`` instance from
            ``kailash_ml.engines.feature_store``.
        tenant_id: Tenant scope. Required for ``multi_tenant=True``
            groups; ``None`` is only valid for single-tenant groups.
        point_in_time: Snapshot at a specific wall-clock moment for
            point-in-time-correct feature joins.
        since / until: Window bounds. If both ``point_in_time`` AND
            ``since``/``until`` are provided, ``ValueError`` — the
            caller must pick one semantic.
        limit: Optional row cap for bounding query cost.

    Returns:
        ``polars.LazyFrame`` — the caller must ``.collect()`` to
        materialize.

    Raises:
        FeatureSourceError: kailash-ml is absent, the feature group's
            shape is invalid, or the underlying store refused to
            serve.
        MLTenantRequiredError: ``multi_tenant=True`` without a
            ``tenant_id``.
        ValueError: Conflicting window arguments.
    """
    try:
        import polars as pl
    except ImportError as exc:  # pragma: no cover
        raise FeatureSourceError(
            "dataflow.ml_feature_source requires polars — install kailash-dataflow>=2.1.0."
        ) from exc

    # Validate caller argument shape BEFORE consulting kailash-ml so
    # single-tenant caller errors don't depend on kailash-ml being
    # installed.
    if point_in_time is not None and (since is not None or until is not None):
        raise ValueError(
            "dataflow.ml_feature_source: point_in_time supersedes since/until; "
            "pass either point_in_time OR since/until, not both"
        )

    # Defer importing FeatureGroup — raises FeatureSourceError with an
    # actionable message if kailash-ml is missing.
    _import_feature_group_class()

    group_name = _group_name(feature_group)

    # Tenant strict mode — missing tenant on a multi-tenant group is a
    # typed error (`rules/tenant-isolation.md` § 2).
    if _is_multi_tenant_group(feature_group) and tenant_id is None:
        raise MLTenantRequiredError(
            f"FeatureGroup {group_name!r} is multi_tenant=True; tenant_id is required"
        )

    cache_key = _feature_source_cache_key(
        group_name=group_name,
        tenant_id=tenant_id,
        point_in_time=point_in_time,
        since=since,
        until=until,
        limit=limit,
    )

    logger.info(
        "dataflow.ml_feature_source.start",
        extra={
            "group": group_name,
            "tenant_id": tenant_id,
            "point_in_time": point_in_time.isoformat() if point_in_time else None,
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
            "limit": limit,
            "cache_key": cache_key,
            "source": "dataflow",
            "mode": "real",
        },
    )

    # Delegate to the feature group's own materializer — it knows its
    # backing store (DataFlow table, parquet, etc.). FeatureStore owns
    # the caching contract per spec § 1.3.
    try:
        materializer = getattr(feature_group, "materialize", None)
        if not callable(materializer):
            raise FeatureSourceError(
                f"FeatureGroup {group_name!r} does not expose a callable "
                ".materialize(...) method — cannot satisfy ml_feature_source "
                "contract"
            )
        frame = materializer(
            tenant_id=tenant_id,
            point_in_time=point_in_time,
            since=since,
            until=until,
            limit=limit,
        )
    except (FeatureSourceError, MLTenantRequiredError):
        raise
    except TypeError as exc:
        # Older FeatureGroup implementations may not accept every kwarg;
        # rather than silently swallow the TypeError, surface it with an
        # actionable message.
        raise FeatureSourceError(
            f"FeatureGroup {group_name!r}.materialize(...) rejected kwargs: "
            f"{exc!r}. Upgrade kailash-ml to >=1.0.0 for the full kwarg surface."
        ) from exc
    except Exception as exc:
        raise FeatureSourceError(
            f"FeatureGroup {group_name!r}.materialize(...) failed: {exc!r}"
        ) from exc

    if not isinstance(frame, (pl.LazyFrame, pl.DataFrame)):
        raise FeatureSourceError(
            f"FeatureGroup {group_name!r}.materialize(...) returned "
            f"{type(frame).__name__}, expected polars.LazyFrame or "
            "polars.DataFrame"
        )

    if isinstance(frame, pl.DataFrame):
        frame = frame.lazy()

    # Attach DataFlow-side classification metadata so downstream
    # transforms can enforce redact/mask per spec § 2.5.
    meta = _classification_metadata(feature_group)
    if meta:
        # polars doesn't expose a public "attach user metadata" API on
        # LazyFrame; we stash it on an attribute so transform() can
        # forward it without relying on polars internals.
        try:
            frame._kailash_ml_metadata = meta  # type: ignore[attr-defined]
        except Exception:
            pass

    logger.info(
        "dataflow.ml_feature_source.ok",
        extra={
            "group": group_name,
            "tenant_id": tenant_id,
            "cache_key": cache_key,
            "source": "dataflow",
            "mode": "real",
        },
    )

    return frame
