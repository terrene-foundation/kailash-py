# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Public ``FeatureGroup`` — the user-facing declarative authoring object.

A :class:`FeatureGroup` is the AUTHORING handle a user constructs to declare a
named set of features. It HAS-A frozen, content-addressed
:class:`~kailash_ml.features.schema.FeatureSchema` (it does NOT re-implement
field/dtype validation — ``schema.py`` owns that), and it satisfies the exact
duck-type ``dataflow.ml_feature_source`` consumes:

* ``.name`` — non-empty string (the group / backing-table name)
* ``.multi_tenant`` — bool (whether reads scope by ``tenant_id``)
* ``.classification`` — optional dict (propagated as polars metadata by the
  binding's ``_classification_metadata``)
* ``.materialize(*, tenant_id, point_in_time, since, until, limit)`` — the
  **5-kwarg** signature mandated by the shipped binding contract
  (``packages/kailash-dataflow/src/dataflow/ml/_feature_source.py:262-269``;
  reference impl ``_schema_feature_group.py:97-105``).

**Distinct from the internal adapter (load-bearing invariant).** The internal
:class:`~kailash_ml.features._schema_feature_group.SchemaFeatureGroup` is the
read-path bridge that ``FeatureStore.get_features`` wraps a bare schema in.
``FeatureGroup`` is the PUBLIC authoring object that the registry (Shard E)
persists and that users hold; it COMPOSES the internal adapter to read the base
table, then layers ``@feature``-authored derived columns on top via the shipped
``dataflow.transform`` binding. The two are duck-type-compatible but serve
different roles (``rules/orphan-detection.md`` — two classes for the same
concept is BLOCKED; these are two distinct concepts).

**Framework-first (``rules/framework-first.md``).** The base read routes through
the internal ``SchemaFeatureGroup`` (DataFlow Express only, zero raw SQL); each
derived column routes through ``dataflow.transform`` (the shipped polars-Expr
binding). No persistence, no DDL, no raw SQL is added here.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from kailash_ml.features.cache_keys import validate_tenant_id
from kailash_ml.features.decorators import FeatureDefinition
from kailash_ml.features.schema import FeatureSchema

if TYPE_CHECKING:  # avoid eager DataFlow import on type-only paths
    import polars as pl

    from dataflow.core.engine import DataFlow

__all__ = ["FeatureGroup", "lookup_feature_group"]

logger = logging.getLogger(__name__)


def lookup_feature_group(
    groups: "dict[str, FeatureGroup]",
    name: str,
) -> "FeatureGroup":
    """Resolve a :class:`FeatureGroup` by name from an authored collection.

    The raise-site for :class:`~kailash_ml.errors.FeatureGroupNotFoundError`
    (FM2 Wave-1 Shard A). The Shard-E ``FeatureRegistry`` is the durable,
    DataFlow-backed group store; this helper is the in-memory authoring-side
    resolution used by callers holding a dict of authored groups (and by the
    registry's read path once it lands). A missing name fails loudly with the
    typed error rather than a ``KeyError`` so ``except FeatureStoreError``
    handlers catch it (``specs/ml-feature-store.md §6.2 / §11.7``).

    Parameters
    ----------
    groups:
        Mapping of group name → :class:`FeatureGroup`.
    name:
        The group name to resolve.

    Returns
    -------
    The matching :class:`FeatureGroup`.

    Raises
    ------
    kailash_ml.errors.FeatureGroupNotFoundError
        If ``name`` is not present in ``groups``.
    """
    group = groups.get(name)
    if group is None:
        from kailash_ml.errors import FeatureGroupNotFoundError

        # Do NOT echo a hostile name verbatim — fingerprint per
        # ``rules/dataflow-identifier-safety.md`` error-message discipline.
        raise FeatureGroupNotFoundError(
            reason=(
                "no FeatureGroup registered for the requested name "
                f"(fingerprint={hash(name) & 0xFFFF:04x}); "
                f"{len(groups)} group(s) available"
            )
        )
    return group


class FeatureGroup:
    """Public declarative feature group — the user-facing authoring object.

    Wraps (HAS-A) a :class:`FeatureSchema` and satisfies the
    ``ml_feature_source`` duck-type so it drops into the shipped DataFlow
    binding unchanged.

    Parameters
    ----------
    schema:
        The frozen, content-addressed :class:`FeatureSchema` this group
        declares. Field/dtype validation is owned by the schema (composition,
        not re-implementation).
    dataflow:
        The live ``DataFlow`` instance backing reads. Required to
        :meth:`materialize`; may be ``None`` for a pure declarative handle
        (e.g. one being authored before a store is bound) — calling
        :meth:`materialize` on a ``None``-dataflow group raises a typed error.
    multi_tenant:
        Whether reads scope by ``tenant_id``. Surfaced as ``.multi_tenant`` for
        the binding's tenant-strict-mode gate.
    classification:
        Optional classification metadata dict, propagated to the binding's
        ``_classification_metadata`` (``rules/dataflow-classification.md`` —
        classification is a property carried on every read surface).
    features:
        Optional iterable of :class:`FeatureDefinition` (typically authored via
        the ``@feature`` decorator). Each is applied as a derived column at
        materialisation time via ``dataflow.transform``.
    """

    def __init__(
        self,
        schema: FeatureSchema,
        *,
        dataflow: "DataFlow | None" = None,
        multi_tenant: bool = False,
        classification: dict | None = None,
        features: "list[FeatureDefinition] | tuple[FeatureDefinition, ...] | None" = None,
    ) -> None:
        if not isinstance(schema, FeatureSchema):
            raise TypeError(
                f"FeatureGroup(schema=...) must be a FeatureSchema, got "
                f"{type(schema).__name__}"
            )
        self._schema = schema
        self._df = dataflow
        # Duck-type surface consumed by dataflow.ml_feature_source.
        self.name = schema.name
        self.multi_tenant = bool(multi_tenant)
        self.classification = classification or {}

        feats: tuple[FeatureDefinition, ...] = tuple(features or ())
        seen: set[str] = set()
        for f in feats:
            if not isinstance(f, FeatureDefinition):
                raise TypeError(
                    "FeatureGroup(features=...) entries must be FeatureDefinition "
                    "(author via the @feature decorator), got "
                    f"{type(f).__name__}"
                )
            if f.name in seen:
                raise ValueError(
                    "FeatureGroup has a duplicate derived-feature name "
                    f"(fingerprint={hash(f.name) & 0xFFFF:04x})"
                )
            seen.add(f.name)
        self._features = feats

    # ------------------------------------------------------------------
    # Authoring surface
    # ------------------------------------------------------------------

    @property
    def schema(self) -> FeatureSchema:
        """The wrapped :class:`FeatureSchema` (read-only)."""
        return self._schema

    @property
    def version(self) -> int:
        """Schema version (inherited from the wrapped schema)."""
        return self._schema.version

    @property
    def content_hash(self) -> str:
        """Schema content-hash (inherited — content-addressing preserved)."""
        return self._schema.content_hash

    @property
    def features(self) -> tuple[FeatureDefinition, ...]:
        """Ordered tuple of declared :class:`FeatureDefinition` derived columns."""
        return self._features

    def add_feature(self, definition: FeatureDefinition) -> "FeatureGroup":
        """Return a NEW :class:`FeatureGroup` with ``definition`` appended.

        The group is treated as an immutable authoring handle; refinement
        derives a fresh group (mirrors ``FeatureSchema.with_features``). The
        wrapped schema, ``dataflow``, ``multi_tenant``, and ``classification``
        are preserved.
        """
        if not isinstance(definition, FeatureDefinition):
            raise TypeError(
                "add_feature(...) expects a FeatureDefinition (author via the "
                f"@feature decorator), got {type(definition).__name__}"
            )
        return FeatureGroup(
            self._schema,
            dataflow=self._df,
            multi_tenant=self.multi_tenant,
            classification=self.classification,
            features=self._features + (definition,),
        )

    # ------------------------------------------------------------------
    # FeatureGroup contract (ml_feature_source duck-type)
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
        """Materialise the group as a ``polars.LazyFrame``.

        Reads the base feature columns from the backing DataFlow table (via the
        internal :class:`SchemaFeatureGroup` adapter — same point-in-time /
        tenant / window scoping the read path uses), then applies every declared
        ``@feature`` derived column on top through the shipped
        ``dataflow.transform`` binding.

        The **5-kwarg** signature is mandatory parity with the shipped
        ``ml_feature_source`` binding contract; the binding calls this method
        with exactly these keyword arguments
        (``dataflow/ml/_feature_source.py:253-259``).

        Raises
        ------
        kailash_ml.errors.FeatureStoreError
            If the group has no bound ``dataflow`` instance (a pure-declarative
            handle cannot read a backing store).
        """
        if self._df is None:
            # Typed, actionable failure — never a bare AttributeError
            # (``rules/zero-tolerance.md`` Rule 3a).
            from kailash_ml.errors import FeatureStoreError

            raise FeatureStoreError(
                reason=(
                    f"FeatureGroup {self.name!r}.materialize(...) requires a bound "
                    "DataFlow instance; construct via FeatureGroup(schema, "
                    "dataflow=...)"
                ),
                tenant_id=tenant_id,
            )

        # Validate tenant for a multi-tenant group BEFORE reading. The binding
        # also gates this, but failing here keeps the contract explicit when a
        # caller invokes materialize() directly (not via ml_feature_source).
        if self.multi_tenant:
            validate_tenant_id(
                tenant_id, operation=f"FeatureGroup[{self.name}].materialize"
            )

        # Base read — delegate to the internal adapter (DataFlow Express, no raw
        # SQL, owns the as-of dedup + tenant binding).
        from kailash_ml.features._schema_feature_group import SchemaFeatureGroup

        base_group = SchemaFeatureGroup(
            dataflow=self._df,
            schema=self._schema,
            multi_tenant=self.multi_tenant,
            classification=self.classification,
        )
        frame = base_group.materialize(
            tenant_id=tenant_id,
            point_in_time=point_in_time,
            since=since,
            until=until,
            limit=limit,
        )

        if not self._features:
            return frame

        # Apply each declared derived feature via the shipped dataflow.transform
        # binding (classification + lineage tagging preserved; no raw compute).
        transform = _import_transform()
        for definition in self._features:
            frame = transform(
                definition.expr(),
                frame,
                name=definition.name,
                tenant_id=tenant_id,
            )

        logger.debug(
            "feature_group.materialize.derived",
            extra={
                "group": self.name,
                "tenant_id": tenant_id,
                "derived_count": len(self._features),
            },
        )
        return frame


# ---------------------------------------------------------------------------
# Deferred DataFlow binding — loud failure when transform is not landed.
# ---------------------------------------------------------------------------


def _import_transform() -> Any:
    """Resolve ``dataflow.transform`` at call time (loud on absence).

    Mirrors ``store.py::_import_ml_feature_source`` — a missing binding MUST
    surface a descriptive :class:`ImportError`, never a silent degrade
    (``rules/dependencies.md`` § Optional Extras With Loud Failure).
    """
    try:
        from dataflow import transform  # type: ignore[attr-defined]

        return transform
    except (ImportError, AttributeError):
        pass
    try:
        from dataflow.ml import transform  # type: ignore[attr-defined]

        return transform
    except (ImportError, AttributeError) as exc:
        raise ImportError(
            "dataflow.transform is not available. kailash-ml FeatureGroup "
            "derived-feature materialisation requires DataFlow 2.11+'s polars "
            "transform binding — see specs/dataflow-ml-integration.md §3.2 for "
            "the canonical contract. Upgrade kailash-dataflow to a version that "
            "exports transform from `dataflow.ml`."
        ) from exc
