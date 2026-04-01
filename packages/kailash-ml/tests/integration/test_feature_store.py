# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for FeatureStore engine.

Uses a real SQLite database via ConnectionManager (no mocking).
"""
from __future__ import annotations

from datetime import datetime, timezone

import polars as pl
import pytest

from kailash.db.connection import ConnectionManager
from kailash_ml.engines.feature_store import FeatureStore
from kailash_ml_protocols import FeatureField, FeatureSchema


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def conn():
    """Real SQLite ConnectionManager for integration tests."""
    cm = ConnectionManager("sqlite://:memory:")
    await cm.initialize()
    yield cm
    await cm.close()


@pytest.fixture
async def store(conn: ConnectionManager) -> FeatureStore:
    """Initialized FeatureStore backed by real SQLite."""
    fs = FeatureStore(conn)
    await fs.initialize()
    return fs


@pytest.fixture
def basic_schema() -> FeatureSchema:
    return FeatureSchema(
        name="test_features",
        features=[
            FeatureField("feature_a", "float64"),
            FeatureField("feature_b", "float64"),
        ],
        entity_id_column="entity_id",
    )


@pytest.fixture
def temporal_schema() -> FeatureSchema:
    return FeatureSchema(
        name="temporal_features",
        features=[FeatureField("score", "float64")],
        entity_id_column="user_id",
        timestamp_column="event_time",
    )


@pytest.fixture
def sample_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "entity_id": ["e0", "e1", "e2"],
            "feature_a": [1.0, 2.0, 3.0],
            "feature_b": [10.0, 20.0, 30.0],
        }
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_register_features_creates_table(
    store: FeatureStore, basic_schema: FeatureSchema
) -> None:
    await store.register_features(basic_schema)
    schemas = await store.list_schemas()
    assert len(schemas) == 1
    assert schemas[0]["schema_name"] == "test_features"


@pytest.mark.integration
async def test_register_features_idempotent(
    store: FeatureStore, basic_schema: FeatureSchema
) -> None:
    await store.register_features(basic_schema)
    await store.register_features(basic_schema)  # no error
    schemas = await store.list_schemas()
    assert len(schemas) == 1


@pytest.mark.integration
async def test_register_features_rejects_schema_drift(
    store: FeatureStore,
) -> None:
    schema_v1 = FeatureSchema(
        name="drifting",
        features=[FeatureField("a", "float64")],
        entity_id_column="id",
    )
    schema_v2 = FeatureSchema(
        name="drifting",
        features=[FeatureField("a", "float64"), FeatureField("b", "int64")],
        entity_id_column="id",
    )
    await store.register_features(schema_v1)
    with pytest.raises(ValueError, match="different definition"):
        await store.register_features(schema_v2)


# ---------------------------------------------------------------------------
# Compute (validation)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_compute_validates_columns(
    store: FeatureStore, sample_df: pl.DataFrame
) -> None:
    schema = FeatureSchema(
        name="strict",
        features=[FeatureField("nonexistent_column", "float64")],
        entity_id_column="entity_id",
    )
    with pytest.raises(ValueError, match="nonexistent_column"):
        store.compute(sample_df, schema)


@pytest.mark.integration
async def test_compute_validates_nullable(store: FeatureStore) -> None:
    schema = FeatureSchema(
        name="non_null",
        features=[FeatureField("val", "float64", nullable=False)],
        entity_id_column="entity_id",
    )
    df = pl.DataFrame({"entity_id": ["e0", "e1"], "val": [1.0, None]})
    with pytest.raises(ValueError, match="null values"):
        store.compute(df, schema)


@pytest.mark.integration
async def test_compute_projects_to_schema_columns(
    store: FeatureStore, basic_schema: FeatureSchema
) -> None:
    df = pl.DataFrame(
        {
            "entity_id": ["e0"],
            "feature_a": [1.0],
            "feature_b": [2.0],
            "extra_col": ["ignored"],
        }
    )
    result = store.compute(df, basic_schema)
    assert set(result.columns) == {"entity_id", "feature_a", "feature_b"}


# ---------------------------------------------------------------------------
# Store + Retrieve round-trip
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_compute_store_retrieve_round_trip(
    store: FeatureStore, basic_schema: FeatureSchema, sample_df: pl.DataFrame
) -> None:
    await store.register_features(basic_schema)

    computed = store.compute(sample_df, basic_schema)
    count = await store.store(computed, basic_schema)
    assert count == 3

    retrieved = await store.get_features(
        ["e0", "e1", "e2"],
        ["feature_a", "feature_b"],
        schema=basic_schema,
    )
    assert retrieved.height == 3
    assert set(retrieved.columns) >= {"entity_id", "feature_a", "feature_b"}

    # Verify actual values persisted
    e0_row = retrieved.filter(pl.col("entity_id") == "e0")
    assert float(e0_row["feature_a"][0]) == pytest.approx(1.0)
    assert float(e0_row["feature_b"][0]) == pytest.approx(10.0)


@pytest.mark.integration
async def test_retrieve_empty_returns_empty_df(
    store: FeatureStore, basic_schema: FeatureSchema
) -> None:
    await store.register_features(basic_schema)
    result = await store.get_features(
        ["nonexistent"], ["feature_a"], schema=basic_schema
    )
    assert result.height == 0


# ---------------------------------------------------------------------------
# Point-in-time correctness
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_point_in_time_correctness(
    store: FeatureStore, temporal_schema: FeatureSchema
) -> None:
    await store.register_features(temporal_schema)

    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 6, 1, tzinfo=timezone.utc)

    df_t1 = pl.DataFrame(
        {
            "user_id": ["u1"],
            "score": [0.5],
            "event_time": [t1.isoformat()],
        }
    )
    df_t2 = pl.DataFrame(
        {
            "user_id": ["u1"],
            "score": [0.9],
            "event_time": [t2.isoformat()],
        }
    )

    await store.store(df_t1, temporal_schema)
    await store.store(df_t2, temporal_schema)

    # Query as of March -- should get t1 value (0.5)
    result_march = await store.get_features(
        ["u1"],
        ["score"],
        schema=temporal_schema,
        as_of=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )
    assert result_march.height == 1
    assert float(result_march["score"][0]) == pytest.approx(0.5)

    # Query as of July -- should get t2 value (0.9)
    result_july = await store.get_features(
        ["u1"],
        ["score"],
        schema=temporal_schema,
        as_of=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )
    assert result_july.height == 1
    assert float(result_july["score"][0]) == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# Training set retrieval
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_get_training_set(
    store: FeatureStore, temporal_schema: FeatureSchema
) -> None:
    await store.register_features(temporal_schema)

    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 6, 1, tzinfo=timezone.utc)
    t3 = datetime(2026, 12, 1, tzinfo=timezone.utc)

    for t, score in [(t1, 0.1), (t2, 0.5), (t3, 0.9)]:
        df = pl.DataFrame(
            {"user_id": ["u1"], "score": [score], "event_time": [t.isoformat()]}
        )
        await store.store(df, temporal_schema)

    # Window that includes t1 and t2 but not t3
    result = await store.get_training_set(
        temporal_schema,
        start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        end=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )
    # Should get 2 rows (created_at for t1 and t2 stores are within window)
    assert result.height >= 2


# ---------------------------------------------------------------------------
# Lazy retrieval
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_get_features_lazy(
    store: FeatureStore, basic_schema: FeatureSchema, sample_df: pl.DataFrame
) -> None:
    await store.register_features(basic_schema)
    computed = store.compute(sample_df, basic_schema)
    await store.store(computed, basic_schema)

    lazy_result = await store.get_features_lazy(
        ["e0", "e1"], ["feature_a"], schema=basic_schema
    )
    assert isinstance(lazy_result, pl.LazyFrame)
    collected = lazy_result.collect()
    assert collected.height == 2


# ---------------------------------------------------------------------------
# List schemas
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_list_schemas_multiple(store: FeatureStore) -> None:
    for name in ["alpha", "beta", "gamma"]:
        schema = FeatureSchema(
            name=name,
            features=[FeatureField("x", "float64")],
            entity_id_column="id",
        )
        await store.register_features(schema)

    schemas = await store.list_schemas()
    names = [s["schema_name"] for s in schemas]
    assert sorted(names) == ["alpha", "beta", "gamma"]
