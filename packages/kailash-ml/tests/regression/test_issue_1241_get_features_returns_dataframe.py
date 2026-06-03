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
