# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Integration: MLEngine.finalize(full_fit=True) re-trains through self.fit.

Tier 2 — per ``specs/ml-engines.md`` §2.2 the refitted TrainingResult
must come through the Lightning-spine pipeline (self.fit), preserving
the device/accelerator/precision contract. The FinalizeResult.full_fit
flag echoes the caller's intent.
"""
from __future__ import annotations

import pytest

import polars as pl

from kailash_ml import FinalizeResult, MLEngine, TrainingResult


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
async def test_finalize_full_fit_retrains_through_fit(
    sample_df: pl.DataFrame,
) -> None:
    """finalize(full_fit=True) returns a fresh TrainingResult from self.fit."""
    engine = MLEngine()
    # Build a candidate by running compare() first
    compare_result = await engine.compare(
        data=sample_df,
        target="y",
        metric="accuracy",
        families=["sklearn"],
    )
    candidate = compare_result.best
    assert isinstance(candidate, TrainingResult)

    # Finalize with full refit
    fresh = await engine.finalize(
        candidate,
        full_fit=True,
        data=sample_df,
        target="y",
    )
    assert isinstance(fresh, FinalizeResult)
    assert fresh.full_fit is True
    assert isinstance(fresh.training_result, TrainingResult)
    # The refit result carries the device contract
    assert fresh.training_result.device is not None
    assert fresh.training_result.accelerator != "auto"
    assert fresh.training_result.precision != "auto"
    # Original candidate preserved
    assert fresh.original_candidate is candidate


@pytest.mark.integration
async def test_finalize_full_fit_tenant_propagation(
    sample_df: pl.DataFrame,
) -> None:
    """finalize() echoes tenant_id on both envelope and inner result."""
    engine = MLEngine(tenant_id="beta")
    compare_result = await engine.compare(
        data=sample_df,
        target="y",
        metric="accuracy",
        families=["sklearn"],
    )
    candidate = compare_result.best
    # Pre-condition
    assert candidate.tenant_id == "beta"

    fresh = await engine.finalize(
        candidate,
        full_fit=True,
        data=sample_df,
        target="y",
    )
    assert fresh.tenant_id == "beta"
    assert fresh.training_result.tenant_id == "beta"
