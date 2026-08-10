# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 wiring — public ``FeatureGroup`` + ``@feature`` authoring (FM2 Shard A).

Per ``rules/facade-manager-detection.md`` MUST Rule 2 + ``rules/orphan-detection.md``
MUST Rule 2, this exercises the PUBLIC authoring surface end-to-end against a REAL
DataFlow instance (file-backed SQLite) and asserts the externally-observable
contract:

* a user authors a :class:`FeatureGroup` (HAS-A ``FeatureSchema``) carrying a
  ``@feature``-declared derived column;
* :func:`dataflow.ml_feature_source` consumes the group unchanged (duck-type
  conformance) and the ``@feature`` computation routes through the shipped
  ``dataflow.transform`` binding — read-back asserts the derived values;
* the 5-kwarg ``materialize(*, tenant_id, point_in_time, since, until, limit)``
  surface matches the shipped binding contract;
* multi-tenant scoping isolates tenant rows;
* a lookup of a missing group raises :class:`FeatureGroupNotFoundError`.

NO MOCKING — real DataFlow read path + real ``dataflow.transform``
(``rules/testing.md`` Tier 2). File-backed SQLite mirrors the precedent in
``test_feature_store_get_features_wiring.py``.
"""
from __future__ import annotations

import inspect
from datetime import datetime
from pathlib import Path

import polars as pl
import pytest
from kailash_ml.errors import FeatureGroupNotFoundError, FeatureStoreError
from kailash_ml.features import (
    FeatureField,
    FeatureGroup,
    FeatureSchema,
    feature,
    lookup_feature_group,
)
from kailash_ml.features.feature_group import FeatureGroup as _FG_module_class

from dataflow import DataFlow
from dataflow.ml import ml_feature_source

pytestmark = pytest.mark.integration


@pytest.fixture
def txn_db(tmp_path: Path):
    """Single-tenant DataFlow with a per-entity transaction-amount table."""
    db_path = tmp_path / "feat_authoring.sqlite"
    df = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)

    @df.model
    class UserTxn:
        entity_id: str
        event_time: datetime
        amount: float

    df._ensure_connected()
    try:
        yield df
    finally:
        try:
            df.close()
        except Exception:
            pass


def _schema() -> FeatureSchema:
    return FeatureSchema(
        name="UserTxn",
        version=1,
        fields=(FeatureField(name="amount", dtype="float64"),),
        entity_id_column="entity_id",
        timestamp_column="event_time",
    )


# A @feature-authored derived column: log1p of the base amount.
@feature(name="amount_log", dtype="float64")
def amount_log() -> pl.Expr:
    """Natural log (1 + amount) of the transaction amount."""
    return pl.col("amount").log1p()


def test_feature_group_is_distinct_from_internal_adapter():
    """Load-bearing invariant: public FeatureGroup is NOT SchemaFeatureGroup."""
    from kailash_ml.features._schema_feature_group import SchemaFeatureGroup

    assert FeatureGroup is _FG_module_class
    assert FeatureGroup is not SchemaFeatureGroup
    assert not issubclass(FeatureGroup, SchemaFeatureGroup)


def test_feature_group_materialize_5kwarg_signature():
    """The 5-kwarg surface is mandatory binding parity (keyword-only)."""
    sig = inspect.signature(FeatureGroup.materialize)
    params = {name: p for name, p in sig.parameters.items() if name != "self"}
    assert set(params) == {
        "tenant_id",
        "point_in_time",
        "since",
        "until",
        "limit",
    }
    assert all(
        p.kind is inspect.Parameter.KEYWORD_ONLY for p in params.values()
    ), "materialize kwargs MUST be keyword-only for ml_feature_source parity"


def test_author_feature_group_then_materialize_via_binding(txn_db: DataFlow):
    """Author → ml_feature_source → read-back assert the derived feature."""
    db = txn_db
    # u1 has TWO observations — no-timestamp materialize MUST return the latest.
    db.express_sync.create(
        "UserTxn",
        {"entity_id": "u1", "event_time": datetime(2026, 1, 1), "amount": 9.0},
    )
    db.express_sync.create(
        "UserTxn",
        {"entity_id": "u1", "event_time": datetime(2026, 2, 1), "amount": 99.0},
    )
    db.express_sync.create(
        "UserTxn",
        {"entity_id": "u2", "event_time": datetime(2026, 1, 1), "amount": 0.0},
    )

    group = FeatureGroup(
        _schema(),
        dataflow=db,
        features=[amount_log],
    )
    # Duck-type surface consumed by ml_feature_source.
    assert group.name == "UserTxn"
    assert group.multi_tenant is False
    assert group.classification == {}
    assert group.version == 1
    assert group.content_hash == _schema().content_hash  # content-addressing

    # The shipped binding consumes the public group UNCHANGED.
    lazy = ml_feature_source(group)
    out = lazy.collect()

    assert isinstance(out, pl.DataFrame)
    assert "entity_id" in out.columns
    assert "amount" in out.columns
    # The @feature-derived column produced via dataflow.transform.
    assert "amount_log" in out.columns
    assert out.height == 2  # latest row per entity

    by_entity = {r["entity_id"]: r for r in out.to_dicts()}
    # Read-back the BASE value (u1 latest = Feb = 99.0).
    assert by_entity["u1"]["amount"] == 99.0
    assert by_entity["u2"]["amount"] == 0.0
    # Read-back the DERIVED value: log1p(99) and log1p(0).
    import math

    assert by_entity["u1"]["amount_log"] == pytest.approx(math.log1p(99.0))
    assert by_entity["u2"]["amount_log"] == pytest.approx(math.log1p(0.0))


def test_feature_group_point_in_time_with_derived_column(txn_db: DataFlow):
    """5-kwarg point_in_time flows through to the base read; derived applied as-of."""
    db = txn_db
    db.express_sync.create(
        "UserTxn",
        {"entity_id": "u1", "event_time": datetime(2026, 1, 1), "amount": 1.0},
    )
    db.express_sync.create(
        "UserTxn",
        {"entity_id": "u1", "event_time": datetime(2026, 3, 1), "amount": 999.0},
    )

    group = FeatureGroup(_schema(), dataflow=db, features=[amount_log])
    # As-of 2026-02-01 → must see Jan (amount=1.0), NOT Mar (999.0).
    out = ml_feature_source(group, point_in_time=datetime(2026, 2, 1)).collect()

    assert out.height == 1
    assert out["amount"].to_list() == [1.0]
    import math

    assert out["amount_log"].to_list() == pytest.approx([math.log1p(1.0)])


def test_multi_tenant_feature_group_isolates_rows(tmp_path: Path):
    """Multi-tenant group scopes the read to the bound tenant context."""
    db_path = tmp_path / "feat_mt.sqlite"
    db = DataFlow(
        f"sqlite:///{db_path}",
        auto_migrate=True,
        multi_tenant=True,
    )

    @db.model
    class TenantTxn:
        entity_id: str
        event_time: datetime
        amount: float

    db._ensure_connected()
    db.tenant_context.register_tenant("tenant_a", "Tenant A")
    db.tenant_context.register_tenant("tenant_b", "Tenant B")
    try:
        with db.tenant_context.switch("tenant_a"):
            db.express_sync.create(
                "TenantTxn",
                {
                    "entity_id": "a1",
                    "event_time": datetime(2026, 1, 1),
                    "amount": 5.0,
                },
            )
        with db.tenant_context.switch("tenant_b"):
            db.express_sync.create(
                "TenantTxn",
                {
                    "entity_id": "b1",
                    "event_time": datetime(2026, 1, 1),
                    "amount": 50.0,
                },
            )

        schema = FeatureSchema(
            name="TenantTxn",
            version=1,
            fields=(FeatureField(name="amount", dtype="float64"),),
            entity_id_column="entity_id",
            timestamp_column="event_time",
        )
        group = FeatureGroup(
            schema, dataflow=db, multi_tenant=True, features=[amount_log]
        )
        assert group.multi_tenant is True

        out_a = ml_feature_source(group, tenant_id="tenant_a").collect()
        assert set(out_a["entity_id"].to_list()) == {"a1"}
        assert out_a["amount"].to_list() == [5.0]

        out_b = ml_feature_source(group, tenant_id="tenant_b").collect()
        assert set(out_b["entity_id"].to_list()) == {"b1"}
        assert out_b["amount"].to_list() == [50.0]
    finally:
        try:
            db.close()
        except Exception:
            pass


def test_lookup_missing_feature_group_raises_typed_error(txn_db: DataFlow):
    """Negative: resolving an unregistered group name raises the M2 typed error."""
    group = FeatureGroup(_schema(), dataflow=txn_db)
    authored = {group.name: group}

    # Present name resolves.
    assert lookup_feature_group(authored, "UserTxn") is group

    # Absent name raises FeatureGroupNotFoundError (a FeatureStoreError subclass).
    with pytest.raises(FeatureGroupNotFoundError):
        lookup_feature_group(authored, "DoesNotExist")
    with pytest.raises(FeatureStoreError):
        lookup_feature_group(authored, "DoesNotExist")


def test_pure_declarative_group_materialize_requires_dataflow():
    """A group with no bound DataFlow fails loudly (typed), never AttributeError."""
    group = FeatureGroup(_schema())  # no dataflow bound
    assert group.name == "UserTxn"
    with pytest.raises(FeatureStoreError):
        group.materialize(tenant_id=None)


def test_add_feature_returns_new_group_preserving_identity(txn_db: DataFlow):
    """add_feature derives a fresh immutable group; schema identity preserved."""
    base = FeatureGroup(_schema(), dataflow=txn_db)
    assert base.features == ()

    derived = base.add_feature(amount_log)
    assert derived is not base
    assert base.features == ()  # original unchanged
    assert [f.name for f in derived.features] == ["amount_log"]
    assert derived.content_hash == base.content_hash  # same wrapped schema
