# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 integration test for :meth:`MLEngine.setup` idempotency.

Per ``specs/ml-engines.md`` §2.1 MUST 6: calling ``setup()`` twice with
identical ``(df_fingerprint, target, ignore, feature_store_name)`` MUST
produce equal ``schema_hash`` AND equal ``split_seed`` values, and MUST
NOT create a duplicate FeatureSchema registration.
"""
from __future__ import annotations

import os
import tempfile

import polars as pl
import pytest

pytest.importorskip("polars")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_engine_setup_is_idempotent_on_repeated_calls() -> None:
    """Two setup() calls with the same inputs yield the same SetupResult."""
    from kailash_ml import MLEngine

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["KAILASH_ML_STORE_URL"] = f"sqlite:///{tmp}/ml.db"
        engine = MLEngine()
        df = pl.DataFrame(
            {
                "id": list(range(50)),
                "x1": [float(i) for i in range(50)],
                "x2": [float(i * 2) for i in range(50)],
                "y": [i % 2 for i in range(50)],
            }
        )
        r1 = await engine.setup(df, target="y")
        r2 = await engine.setup(df, target="y")

        # §2.1 MUST 6 — same hash, same split seed, equal sizes.
        assert r1.schema_hash == r2.schema_hash
        assert r1.split_seed == r2.split_seed
        assert r1.train_size == r2.train_size
        assert r1.test_size == r2.test_size

        # Same target + task + feature columns.
        assert r1.target == r2.target == "y"
        assert r1.task_type == r2.task_type == "classification"
        assert r1.feature_columns == r2.feature_columns

        # r2 is the cached result (idempotent hit returns the stored object).
        assert r2 is r1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_engine_setup_ignore_permutation_yields_same_hash() -> None:
    """Ignore-list ordering does NOT affect the schema hash."""
    from kailash_ml import MLEngine

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["KAILASH_ML_STORE_URL"] = f"sqlite:///{tmp}/ml.db"
        engine_a = MLEngine()
        engine_b = MLEngine()
        df = pl.DataFrame(
            {
                "id": list(range(30)),
                "extra": list(range(30)),
                "x1": [float(i) for i in range(30)],
                "y": [i % 2 for i in range(30)],
            }
        )
        r_a = await engine_a.setup(df, target="y", ignore=["extra", "id"])
        r_b = await engine_b.setup(df, target="y", ignore=["id", "extra"])
        assert r_a.schema_hash == r_b.schema_hash
        assert r_a.ignored_columns == r_b.ignored_columns == ("extra", "id")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_engine_setup_different_data_yields_different_hash() -> None:
    """Different row counts produce different schema_hash values."""
    from kailash_ml import MLEngine

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["KAILASH_ML_STORE_URL"] = f"sqlite:///{tmp}/ml.db"
        engine = MLEngine()
        df_small = pl.DataFrame({"x": list(range(10)), "y": [i % 2 for i in range(10)]})
        df_big = pl.DataFrame({"x": list(range(100)), "y": [i % 2 for i in range(100)]})
        r_small = await engine.setup(df_small, target="y")
        # reset the cached _setup_result so a second shape can be tested.
        engine._setup_result = None
        r_big = await engine.setup(df_big, target="y")
        assert r_small.schema_hash != r_big.schema_hash
