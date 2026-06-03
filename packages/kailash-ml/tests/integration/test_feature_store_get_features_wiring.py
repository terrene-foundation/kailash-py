# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 wiring — ``FeatureStore.get_features`` end-to-end (issue #1241).

Per ``rules/facade-manager-detection.md`` MUST Rule 2 + ``rules/orphan-detection.md``
MUST Rule 2, this exercises the canonical ``FeatureStore.get_features`` retrieval
surface against a REAL DataFlow instance (file-backed SQLite) and asserts the
externally-observable contract:

* happy path returns a ``polars.DataFrame`` carrying ``entity_id`` + every field
  column, populated with real rows written through ``db.express``.
* point-in-time correctness (spec §6.2 MUST-1): per entity, the latest row with
  ``timestamp <= point_in_time`` is returned — NOT a value materialised after T.
* ``entity_ids`` filter narrows the result.
* an empty table returns an empty DataFrame, not an error.

NO MOCKING — real DataFlow read path (``rules/testing.md`` Tier 2). File-backed
SQLite mirrors the precedent in
``packages/kailash-dataflow/tests/integration/test_dataflow_ml_feature_source_wiring.py``.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl
import pytest
from kailash_ml.features import FeatureField, FeatureSchema, FeatureStore

from dataflow import DataFlow

pytestmark = pytest.mark.integration


@pytest.fixture
def churn_db(tmp_path: Path):
    """Single-tenant DataFlow with a multi-row-per-entity feature table."""
    db_path = tmp_path / "feat_store.sqlite"
    df = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)

    @df.model
    class UserChurn:
        entity_id: str
        event_time: datetime
        login_count_7d: int

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
        name="UserChurn",
        version=1,
        fields=(FeatureField(name="login_count_7d", dtype="int64"),),
        entity_id_column="entity_id",
        timestamp_column="event_time",
    )


async def test_get_features_happy_path_returns_dataframe(churn_db: DataFlow):
    db = churn_db
    db.express_sync.create(
        "UserChurn",
        {"entity_id": "u1", "event_time": datetime(2026, 1, 1), "login_count_7d": 3},
    )
    db.express_sync.create(
        "UserChurn",
        {"entity_id": "u2", "event_time": datetime(2026, 1, 1), "login_count_7d": 7},
    )

    store = FeatureStore(db, default_tenant_id="_single")
    out = await store.get_features(_schema())

    assert isinstance(out, pl.DataFrame)
    assert "entity_id" in out.columns
    assert "login_count_7d" in out.columns
    assert set(out["entity_id"].to_list()) == {"u1", "u2"}


async def test_get_features_point_in_time_returns_as_of_value(churn_db: DataFlow):
    """The canonical point-in-time contract: latest row with event_time <= T."""
    db = churn_db
    # Two observations for the SAME entity at different times.
    db.express_sync.create(
        "UserChurn",
        {"entity_id": "u1", "event_time": datetime(2026, 1, 1), "login_count_7d": 1},
    )
    db.express_sync.create(
        "UserChurn",
        {"entity_id": "u1", "event_time": datetime(2026, 3, 1), "login_count_7d": 99},
    )

    store = FeatureStore(db, default_tenant_id="_single")
    # As-of 2026-02-01: must see the Jan value (1), NOT the Mar value (99).
    out = await store.get_features(_schema(), timestamp=datetime(2026, 2, 1))

    assert out.height == 1
    assert out["entity_id"].to_list() == ["u1"]
    assert out["login_count_7d"].to_list() == [1]


async def test_get_features_entity_ids_filter(churn_db: DataFlow):
    db = churn_db
    for eid, val in (("u1", 3), ("u2", 7), ("u3", 11)):
        db.express_sync.create(
            "UserChurn",
            {
                "entity_id": eid,
                "event_time": datetime(2026, 1, 1),
                "login_count_7d": val,
            },
        )

    store = FeatureStore(db, default_tenant_id="_single")
    out = await store.get_features(_schema(), entity_ids=["u1", "u3"])

    assert set(out["entity_id"].to_list()) == {"u1", "u3"}


async def test_get_features_empty_table_returns_empty_dataframe(churn_db: DataFlow):
    store = FeatureStore(churn_db, default_tenant_id="_single")
    out = await store.get_features(_schema())

    assert isinstance(out, pl.DataFrame)
    assert out.height == 0
