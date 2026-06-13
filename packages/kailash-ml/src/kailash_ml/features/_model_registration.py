# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Shared on-demand backing-``@db.model`` registration for the feature store.

The materialiser registers a dynamic DataFlow ``@db.model`` (auto_migrate) for a
feature group's backing table in ITS OWN DataFlow instance on first write. A
DIFFERENT instance (a fresh ``FeatureStore`` over the same SQLite file, a
separate serving process) has NOT registered that model, so a read through
``ml_feature_source`` / ``SchemaFeatureGroup`` fails with
``FeatureSourceError: Node ...ListNode not found. Ensure model '...' is
registered`` — the limitation recorded in
``workspaces/fm2-feature-store-m2-py/journal/0004`` (disposition **(a)**:
re-register on demand when reading).

This module owns the ONE model-shape derivation (entity_id + timestamp +
declared fields + content-addressed ``id`` PK) so the WRITE path
(:mod:`~kailash_ml.features.materialiser`) and the READ self-heal
(:mod:`~kailash_ml.features._schema_feature_group`) register byte-identical
models. DataFlow ``auto_migrate`` is the DDL path — NO inline DDL, NO raw SQL
(``rules/schema-migration.md`` Rule 1, ``rules/framework-first.md``).

Tenant isolation is unchanged: registration is purely a per-instance binding of
the model class so the node exists; the tenant scoping continues to ride on
DataFlow's context-bound multi-tenancy at read/write time (the dynamic model
carries no ``tenant_id`` column by design — journal/0004 § "NO cross-tenant read
leak").
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # avoid eager DataFlow / FeatureSchema import on type-only paths
    from kailash_ml.features.schema import FeatureSchema

    from dataflow.core.engine import DataFlow

__all__ = ["DTYPE_TO_PYTYPE", "ensure_feature_model_registered"]

#: Polars dtype string -> Python annotation type for the dynamic ``@db.model``
#: field declaration. The backing table is created by DataFlow ``auto_migrate``
#: from these annotations; only the coarse Python type matters for DDL (DataFlow
#: maps to the dialect column type). Unknown dtypes fall back to ``str`` (safe,
#: never silently drops a column). SINGLE SOURCE shared by the write + read
#: paths so both register identical column shapes.
DTYPE_TO_PYTYPE: dict[str, type] = {
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


def ensure_feature_model_registered(
    dataflow: "DataFlow",
    schema: "FeatureSchema",
    *,
    extra_columns: dict[str, type] | None = None,
) -> bool:
    """Register the schema's backing ``@db.model`` in ``dataflow`` if absent.

    Idempotent + cross-instance-safe: consults the DataFlow registry of record
    (``dataflow._models``) — NOT a per-caller cache — so re-registration on a
    FRESH instance that has never seen the model succeeds, while a second call
    on an instance that ALREADY has it is a cheap no-op (DataFlow rejects a
    duplicate ``df.model(...)`` with "Model already registered").

    The model columns are: a content-addressed ``id`` (str PK) + the schema's
    ``entity_id_column`` + ``timestamp_column`` (when declared) + every declared
    field. ``extra_columns`` adds derived ``@feature`` columns the write path
    knows about (the read path does NOT, and does not need to — ``auto_migrate``
    never DROPs columns, so a read-side registration that omits derived columns
    binds the model class without disturbing the already-migrated wider table).

    Parameters
    ----------
    dataflow:
        The live ``DataFlow`` instance to register the model in.
    schema:
        The :class:`FeatureSchema` whose ``name`` is the backing model/table
        name and whose ``fields`` define the declared columns.
    extra_columns:
        Optional ``{name: pytype}`` for derived ``@feature`` columns (write
        path). Omit on the read path.

    Returns
    -------
    bool
        ``True`` if a registration was performed in this call, ``False`` if the
        model was already present in ``dataflow._models`` (no-op).
    """
    model_name = schema.name

    # A DataFlow-shaped read double (a Protocol-satisfying deterministic adapter
    # per rules/testing.md, or any object that serves reads directly without a
    # node registry) does NOT expose the registration API. There is no model to
    # register — its express_sync.list already returns rows — so the self-heal is
    # a no-op. Guard BOTH the registry-of-record AND the model() registrar.
    if not hasattr(dataflow, "model") or not hasattr(dataflow, "_ensure_connected"):
        return False

    # Already registered in THIS instance's registry of record → connect + done.
    if model_name in getattr(dataflow, "_models", {}):
        dataflow._ensure_connected()
        return False

    annotations: dict[str, type] = {"id": str, schema.entity_id_column: str}
    if schema.timestamp_column is not None:
        annotations[schema.timestamp_column] = datetime
    for fld in schema.fields:
        annotations[fld.name] = DTYPE_TO_PYTYPE.get(fld.dtype, str)
    if extra_columns:
        for name, pytype in extra_columns.items():
            annotations.setdefault(name, pytype)

    # Construct the model class dynamically so the backing table matches the
    # authored schema; df.model() registers it, auto_migrate creates the table
    # on first connect (no inline DDL, schema-migration Rule 1).
    model_cls: Any = type(model_name, (), {"__annotations__": annotations})
    dataflow.model(model_cls)
    dataflow._ensure_connected()
    return True
