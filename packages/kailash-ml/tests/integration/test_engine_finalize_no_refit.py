# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Integration: MLEngine.finalize(full_fit=False) wraps without retraining.

Tier 2 — when the caller explicitly opts out of refit, the returned
:class:`FinalizeResult.training_result` is identical to the candidate
and no new fit path is invoked. Useful for marking a candidate as
finalized without paying the retrain cost.
"""
from __future__ import annotations

import pytest

import polars as pl

from kailash_ml import FinalizeResult, MLEngine


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
async def test_finalize_no_refit_passes_through(sample_df: pl.DataFrame) -> None:
    """finalize(full_fit=False): training_result is the candidate."""
    engine = MLEngine()
    candidate = await engine.fit(data=sample_df, target="y", family="sklearn")

    wrapped = await engine.finalize(candidate, full_fit=False)

    assert isinstance(wrapped, FinalizeResult)
    assert wrapped.full_fit is False
    # No retraining → training_result IS candidate (same object, since
    # tenant_id already matches and dataclasses.replace is only called
    # when it doesn't)
    assert wrapped.training_result is candidate
    assert wrapped.original_candidate is candidate


@pytest.mark.integration
async def test_finalize_no_refit_tenant_echo(sample_df: pl.DataFrame) -> None:
    """finalize(full_fit=False) re-stamps tenant_id if it drifted."""
    engine = MLEngine(tenant_id="gamma")
    candidate = await engine.fit(data=sample_df, target="y", family="sklearn")
    # Candidate already has tenant_id="gamma" (propagated by fit);
    # the wrapped result carries it too.
    assert candidate.tenant_id == "gamma"

    wrapped = await engine.finalize(candidate, full_fit=False)
    assert wrapped.tenant_id == "gamma"
    assert wrapped.training_result.tenant_id == "gamma"
