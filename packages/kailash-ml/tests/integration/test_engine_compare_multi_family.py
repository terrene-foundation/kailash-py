# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Integration: MLEngine.compare() runs a multi-family Lightning sweep.

Tier 2 — uses real polars DataFrame, real Trainable adapters, real
Lightning Trainer. No mocking. Per
``specs/ml-engines.md`` §2.1 MUST 7 every family in the leaderboard
goes through the Lightning-wrapped fit path, so every TrainingResult
in the leaderboard carries a concrete ``device`` / ``accelerator`` /
``precision`` triple.
"""
from __future__ import annotations

import pytest

import polars as pl

from kailash_ml import ComparisonResult, MLEngine, TrainingResult


@pytest.fixture
def sample_classification_df() -> pl.DataFrame:
    """A small well-behaved classification frame.

    80 rows keeps the Lightning Trainer warmup fast while giving each
    family enough signal to fit without degenerate metrics.
    """
    return pl.DataFrame(
        {
            "feat_a": [i for i in range(80)],
            "feat_b": [i * 2 for i in range(80)],
            "feat_c": [(i % 7) - 3 for i in range(80)],
            "y": [i % 2 for i in range(80)],
        }
    )


@pytest.mark.integration
async def test_compare_sklearn_family_ranks_best(
    sample_classification_df: pl.DataFrame,
) -> None:
    """Sklearn family runs end-to-end through compare() without setup()."""
    engine = MLEngine()
    result = await engine.compare(
        data=sample_classification_df,
        target="y",
        metric="accuracy",
        families=["sklearn"],
    )

    assert isinstance(result, ComparisonResult)
    assert len(result.leaderboard) == 1
    assert result.best is result.leaderboard[0]
    assert result.metric == "accuracy"
    assert result.elapsed_seconds >= 0.0
    # Every leaderboard entry is a fully-populated TrainingResult
    for entry in result.leaderboard:
        assert isinstance(entry, TrainingResult)
        assert entry.device_used != ""
        assert entry.accelerator != "auto"
        assert entry.precision != "auto"
        # §4.2 MUST 5: Phase 1 family adapters populate device
        assert entry.device is not None
        assert entry.device.family in (
            "sklearn",
            "xgboost",
            "lightgbm",
        )


@pytest.mark.integration
async def test_compare_multi_family_leaderboard_best_first(
    sample_classification_df: pl.DataFrame,
) -> None:
    """Multi-family sweep returns a leaderboard ordered best-first."""
    engine = MLEngine()
    # Explicitly pass the full optional-extras list. Missing backends
    # (xgboost / lightgbm when not installed) are gracefully skipped.
    result = await engine.compare(
        data=sample_classification_df,
        target="y",
        metric="accuracy",
        families=["sklearn", "xgboost", "lightgbm"],
    )

    assert isinstance(result, ComparisonResult)
    assert len(result.leaderboard) >= 1  # at minimum sklearn
    # Best-first order by the accuracy metric (higher-is-better)
    scores = [entry.metrics.get("accuracy", 0.0) for entry in result.leaderboard]
    assert scores == sorted(
        scores, reverse=True
    ), f"leaderboard not sorted best-first: {scores}"
    # best field equals leaderboard[0]
    assert result.best is result.leaderboard[0]
    # Every entry has the per-family device report
    for entry in result.leaderboard:
        assert entry.device is not None, f"family {entry.family} missing device"


@pytest.mark.integration
async def test_compare_default_family_set_from_task_type(
    sample_classification_df: pl.DataFrame,
) -> None:
    """When families=None, the default set matches the task_type default."""
    from types import SimpleNamespace

    engine = MLEngine()
    # Simulate a setup_result (sibling shard A owns the real setup()).
    # task_type="classification" → (sklearn, xgboost, lightgbm) default.
    engine._setup_result = SimpleNamespace(
        task_type="classification",
        primary_metric="accuracy",
        target="y",
        _data=sample_classification_df,
    )

    result = await engine.compare()

    assert isinstance(result, ComparisonResult)
    # At minimum sklearn runs; xgboost / lightgbm skip gracefully if absent
    assert len(result.leaderboard) >= 1
    families_in_board = {e.family for e in result.leaderboard}
    assert "sklearn" in families_in_board
