# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Integration: MLEngine.compare() propagates tenant_id end-to-end.

Tier 2 — per ``specs/ml-engines.md`` §4.2 MUST 3 every TrainingResult's
``tenant_id`` MUST echo ``engine.tenant_id``. ComparisonResult.tenant_id
carries the same value at the outer envelope.
"""
from __future__ import annotations

import pytest

import polars as pl

from kailash_ml import MLEngine


@pytest.fixture
def sample_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "x1": list(range(40)),
            "x2": [i * 2 for i in range(40)],
            "y": [i % 2 for i in range(40)],
        }
    )


@pytest.mark.integration
async def test_compare_tenant_propagation(sample_df: pl.DataFrame) -> None:
    """Multi-tenant engine.compare() echoes tenant_id on every result."""
    engine = MLEngine(tenant_id="acme")
    result = await engine.compare(
        data=sample_df,
        target="y",
        metric="accuracy",
        families=["sklearn"],
    )
    # ComparisonResult envelope carries the tenant
    assert result.tenant_id == "acme"
    # Every TrainingResult in the leaderboard independently satisfies
    # §4.2 MUST 3 — tenant_id echoes engine.tenant_id
    for entry in result.leaderboard:
        assert entry.tenant_id == "acme", (
            f"TrainingResult for family={entry.family} has tenant_id="
            f"{entry.tenant_id!r}, expected 'acme' (see "
            f"specs/ml-engines.md §4.2 MUST 3)"
        )


@pytest.mark.integration
async def test_compare_single_tenant_none_echoes_none(sample_df: pl.DataFrame) -> None:
    """Single-tenant engine (tenant_id=None) produces None tenant_id on result."""
    engine = MLEngine()
    result = await engine.compare(
        data=sample_df,
        target="y",
        metric="accuracy",
        families=["sklearn"],
    )
    assert result.tenant_id is None
    for entry in result.leaderboard:
        assert entry.tenant_id is None
