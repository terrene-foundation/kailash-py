# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression — issue #1241: canonical ``FeatureStore.get_features`` always raised.

Before #1241, ``get_features`` forwarded a declarative ``FeatureSchema`` to
``dataflow.ml_feature_source``, which duck-types on a FeatureGroup-shaped
``.materialize`` the schema does not expose — so EVERY call raised
``FeatureStoreError``. The fix wraps the schema in a read adapter
(``SchemaFeatureGroup``) that reads the backing DataFlow table. This test pins
the happy path (returns a populated ``polars.DataFrame``) and point-in-time
correctness so the bug cannot silently return.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl
import pytest
from kailash_ml.features import FeatureField, FeatureSchema, FeatureStore

from dataflow import DataFlow

pytestmark = [pytest.mark.regression, pytest.mark.integration]


@pytest.fixture
def db(tmp_path: Path):
    df = DataFlow(f"sqlite:///{tmp_path / 'issue_1241.sqlite'}", auto_migrate=True)

    @df.model
    class Churn:
        entity_id: str
        event_time: datetime
        score: int

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
        name="Churn",
        version=1,
        fields=(FeatureField(name="score", dtype="int64"),),
        entity_id_column="entity_id",
        timestamp_column="event_time",
    )


async def test_issue_1241_get_features_returns_populated_dataframe(db: DataFlow):
    db.express_sync.create(
        "Churn",
        {"entity_id": "e1", "event_time": datetime(2026, 1, 1), "score": 5},
    )
    store = FeatureStore(db, default_tenant_id="_single")

    out = await store.get_features(_schema())

    assert isinstance(out, pl.DataFrame), "get_features must return a DataFrame (#1241)"
    assert out.height == 1
    assert out["score"].to_list() == [5]


async def test_issue_1241_get_features_point_in_time_is_correct(db: DataFlow):
    db.express_sync.create(
        "Churn", {"entity_id": "e1", "event_time": datetime(2026, 1, 1), "score": 1}
    )
    db.express_sync.create(
        "Churn", {"entity_id": "e1", "event_time": datetime(2026, 3, 1), "score": 9}
    )
    store = FeatureStore(db, default_tenant_id="_single")

    out = await store.get_features(_schema(), timestamp=datetime(2026, 2, 1))

    assert out["score"].to_list() == [
        1
    ], "as-of must return latest row <= T, not after T"


async def test_issue_1241_empty_table_with_entity_ids_returns_empty(db: DataFlow):
    """MED-1 regression: an empty table + entity_ids filter must return an
    empty DataFrame, not raise. The adapter's empty return must carry the
    entity_id column so the store's `pl.col(entity_id).is_in(...)` filter
    resolves instead of raising ColumnNotFoundError → FeatureStoreError.
    """
    store = FeatureStore(db, default_tenant_id="_single")

    out = await store.get_features(_schema(), entity_ids=["e1", "e2"])

    assert isinstance(out, pl.DataFrame)
    assert out.height == 0
    assert "entity_id" in out.columns


class _FixedExpressSync:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def list(self, model, filter=None, limit=100, order_by=None):  # noqa: A002
        return list(self._rows)


class _Security:
    multi_tenant = False


class _Config:
    security = _Security()


class _DeterministicDataFlow:
    """Protocol-satisfying deterministic stand-in for the as-of dedup unit test
    (NOT a mock — `rules/testing.md` § "Protocol-Satisfying Deterministic
    Adapters"). Returns fixed rows so the polars dedup can be exercised against
    a NULL-timestamp row, a state a real DataFlow table cannot produce (it
    enforces NOT NULL on the column).
    """

    def __init__(self, rows: list[dict]) -> None:
        self.config = _Config()
        self.express_sync = _FixedExpressSync(rows)


def test_issue_1241_null_timestamp_does_not_shadow_real_as_of_row():
    """MED-2 regression (unit): a NULL timestamp_column row must never shadow a
    real timestamped row in the as-of dedup. A descending sort places NULLs
    first by default, where unique(keep="first") would pick them — the adapter's
    `nulls_last=True` prevents that. DataFlow tables cannot store a NULL in the
    timestamp column (NOT NULL constraint), so this is unit-tier via a
    deterministic adapter.
    """
    from kailash_ml.features._schema_feature_group import SchemaFeatureGroup

    rows = [
        {"entity_id": "e1", "event_time": datetime(2026, 1, 1), "score": 1},
        {"entity_id": "e1", "event_time": None, "score": 99},
    ]
    group = SchemaFeatureGroup(
        dataflow=_DeterministicDataFlow(rows),  # type: ignore[arg-type]
        schema=_schema(),
    )

    frame = group.materialize(point_in_time=datetime(2026, 2, 1)).collect()

    assert frame["entity_id"].to_list() == ["e1"]
    assert frame["score"].to_list() == [1], "null-ts row must not shadow the real row"
