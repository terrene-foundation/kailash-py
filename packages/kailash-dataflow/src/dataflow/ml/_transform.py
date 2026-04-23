# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``dataflow.transform`` — apply a polars expression to a feature source.

The ``@feature`` decorator in kailash-ml wraps a function returning a
polars ``Expr``; at materialization time the decorator calls
``dataflow.transform(expr, source, name=..., tenant_id=...)`` to produce
the derived column while:

* propagating classification metadata (so a transform on a classified
  column produces a classified result — spec § 3.3);
* tagging the result with the transform name in polars metadata for
  downstream lineage capture;
* enforcing tenant scope on the cache key of any cached transform
  chain.

Non-polars inputs (pandas DataFrame, raw dict, numpy array) are
rejected at the boundary — see ``rules/framework-first.md`` § "Raw Is
Always Wrong" — to keep the dependency surface narrow and the
classification metadata path intact.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from dataflow.ml._errors import DataFlowTransformError

logger = logging.getLogger(__name__)

__all__ = ["transform"]


def _is_polars_expr(obj: "Any") -> bool:
    try:
        import polars as pl
    except ImportError:  # pragma: no cover
        return False
    return isinstance(obj, pl.Expr)


def _is_polars_frame(obj: "Any") -> bool:
    try:
        import polars as pl
    except ImportError:  # pragma: no cover
        return False
    return isinstance(obj, (pl.LazyFrame, pl.DataFrame))


def transform(
    expr: "Any",
    source: "Any",
    *,
    name: str,
    tenant_id: Optional[str] = None,
) -> "Any":
    """Apply a polars expression to a feature-source LazyFrame.

    Args:
        expr: A ``polars.Expr`` produced by a ``@feature``-decorated
            function or an equivalent caller.
        source: A ``polars.LazyFrame`` (typically from
            ``dataflow.ml_feature_source``) or ``polars.DataFrame``.
            Pandas / numpy inputs are rejected.
        name: Human-readable transform identifier used for lineage and
            logging. MUST be non-empty.
        tenant_id: Tenant scope for cache keys constructed downstream.
            May be ``None`` for single-tenant groups.

    Returns:
        ``polars.LazyFrame`` with the transform applied and the
        transform name stashed on ``_kailash_ml_metadata``.

    Raises:
        DataFlowTransformError: ``expr`` is not a ``polars.Expr``,
            ``source`` is not a polars frame, ``name`` is empty, or
            applying the expression failed.
    """
    if not isinstance(name, str) or not name:
        raise DataFlowTransformError(
            "dataflow.transform: name MUST be a non-empty string for " "lineage capture"
        )

    if not _is_polars_expr(expr):
        raise DataFlowTransformError(
            "dataflow.transform: expr MUST be a polars.Expr; got "
            f"{type(expr).__name__}. Pandas/numpy/SQL expressions are not "
            "supported — see specs/dataflow-ml-integration.md § 1.3."
        )

    if not _is_polars_frame(source):
        raise DataFlowTransformError(
            "dataflow.transform: source MUST be a polars.LazyFrame or "
            "polars.DataFrame; got "
            f"{type(source).__name__}. Use dataflow.ml_feature_source(...) to "
            "obtain a polars source from DataFlow."
        )

    import polars as pl

    # Normalize to LazyFrame so callers always get the lazy-chain
    # composability promised by spec § 3.4.
    if isinstance(source, pl.DataFrame):
        source = source.lazy()

    logger.info(
        "dataflow.transform.start",
        extra={
            "transform": name,
            "tenant_id": tenant_id,
            "source": "dataflow",
            "mode": "real",
        },
    )

    try:
        result = source.with_columns(expr.alias(name))
    except Exception as exc:
        raise DataFlowTransformError(
            f"dataflow.transform(name={name!r}) could not apply expression: " f"{exc!r}"
        ) from exc

    # Propagate classification metadata from source to result so
    # downstream transforms still see which columns are classified.
    source_meta = getattr(source, "_kailash_ml_metadata", None)
    transform_meta = {"kailash_ml.transform": name}
    if tenant_id is not None:
        transform_meta["kailash_ml.tenant_id"] = tenant_id
    if isinstance(source_meta, dict):
        merged = dict(source_meta)
        merged.update(transform_meta)
    else:
        merged = transform_meta
    try:
        result._kailash_ml_metadata = merged  # type: ignore[attr-defined]
    except Exception:
        pass

    logger.info(
        "dataflow.transform.ok",
        extra={
            "transform": name,
            "tenant_id": tenant_id,
            "source": "dataflow",
            "mode": "real",
        },
    )

    return result
