# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for AutoMLEngine."""
from __future__ import annotations

import polars as pl
import pytest
from kailash_ml.engines.automl_engine import (
    AutoMLConfig,
    AutoMLEngine,
    LLMBudgetExceededError,
    LLMCostTracker,
)
from kailash_ml.types import FeatureField, FeatureSchema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_schema(n_features: int = 3) -> FeatureSchema:
    features = [FeatureField(name=f"f{i}", dtype="float64") for i in range(n_features)]
    return FeatureSchema(name="test", features=features, entity_id_column="f0")


def _make_small_df(n_rows: int = 10) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "f0": list(range(n_rows)),
            "f1": [float(x) for x in range(n_rows)],
            "f2": [float(x * 2) for x in range(n_rows)],
            "target": [0, 1] * (n_rows // 2),
        }
    )


# ---------------------------------------------------------------------------
# AutoMLConfig
# ---------------------------------------------------------------------------


class TestAutoMLConfig:
    """Tests for AutoMLConfig defaults."""

    def test_defaults(self) -> None:
        cfg = AutoMLConfig()
        assert cfg.task_type == "classification"
        assert cfg.metric_to_optimize == "accuracy"
        assert cfg.direction == "maximize"
        assert cfg.candidate_families is None
        assert cfg.search_strategy == "random"
        assert cfg.search_n_trials == 30
        assert cfg.agent is False
        assert cfg.auto_approve is False
        assert cfg.max_llm_cost_usd == 1.0

    def test_regression_config(self) -> None:
        cfg = AutoMLConfig(
            task_type="regression", metric_to_optimize="rmse", direction="minimize"
        )
        assert cfg.task_type == "regression"
        assert cfg.direction == "minimize"


# ---------------------------------------------------------------------------
# LLMCostTracker (Guardrail 2)
# ---------------------------------------------------------------------------


class TestLLMCostTracker:
    """Tests for LLMCostTracker budget enforcement."""

    def test_initial_state(self) -> None:
        tracker = LLMCostTracker(max_budget_usd=5.0)
        assert tracker.total_spent == 0.0
        assert tracker.calls == []

    def test_record_accumulates_cost(self) -> None:
        tracker = LLMCostTracker(max_budget_usd=10.0)
        tracker.record("test-model", input_tokens=1000, output_tokens=0)
        assert tracker.total_spent > 0
        assert len(tracker.calls) == 1

    def test_budget_exceeded_raises(self) -> None:
        tracker = LLMCostTracker(max_budget_usd=0.001)
        with pytest.raises(LLMBudgetExceededError, match="exceeds budget"):
            tracker.record("model", input_tokens=100_000, output_tokens=100_000)

    def test_nan_budget_raises_on_construction(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            LLMCostTracker(max_budget_usd=float("nan"))

    def test_inf_budget_raises_on_construction(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            LLMCostTracker(max_budget_usd=float("inf"))

    def test_negative_budget_raises_on_construction(self) -> None:
        with pytest.raises(ValueError, match="finite non-negative"):
            LLMCostTracker(max_budget_usd=-1.0)

    def test_calls_property_returns_copy(self) -> None:
        tracker = LLMCostTracker(max_budget_usd=10.0)
        tracker.record("m", 100, 50)
        calls = tracker.calls
        calls.clear()  # mutate the copy
        assert len(tracker.calls) == 1  # original unchanged


# ---------------------------------------------------------------------------
# Baseline recommendation (no LLM, no pipeline)
# ---------------------------------------------------------------------------


class TestBaselineRecommendation:
    """Tests for _compute_baseline_recommendation (algorithmic, no LLM)."""

    def test_small_classification_prefers_logistic(self) -> None:
        engine = AutoMLEngine(pipeline=None, search=None)
        data = _make_small_df(100)
        schema = _make_schema(2)
        config = AutoMLConfig(task_type="classification")

        baseline = engine._compute_baseline_recommendation(data, schema, config)
        assert len(baseline) == 3
        # Small dataset + few features => LogisticRegression first
        assert "LogisticRegression" in baseline[0]

    def test_large_classification_prefers_gradient_boosting(self) -> None:
        engine = AutoMLEngine(pipeline=None, search=None)
        data = _make_small_df(600)
        schema = FeatureSchema(
            name="test",
            features=[FeatureField(name=f"f{i}", dtype="float64") for i in range(10)],
            entity_id_column="f0",
        )
        config = AutoMLConfig(task_type="classification")

        baseline = engine._compute_baseline_recommendation(data, schema, config)
        assert "GradientBoosting" in baseline[0]

    def test_small_regression_prefers_ridge(self) -> None:
        engine = AutoMLEngine(pipeline=None, search=None)
        data = _make_small_df(100)
        schema = _make_schema(2)
        config = AutoMLConfig(task_type="regression")

        baseline = engine._compute_baseline_recommendation(data, schema, config)
        assert "Ridge" in baseline[0]

    def test_large_regression_prefers_gradient_boosting(self) -> None:
        engine = AutoMLEngine(pipeline=None, search=None)
        data = _make_small_df(600)
        schema = FeatureSchema(
            name="test",
            features=[FeatureField(name=f"f{i}", dtype="float64") for i in range(10)],
            entity_id_column="f0",
        )
        config = AutoMLConfig(task_type="regression")

        baseline = engine._compute_baseline_recommendation(data, schema, config)
        assert "GradientBoosting" in baseline[0]


# ---------------------------------------------------------------------------
# Candidate family selection
# ---------------------------------------------------------------------------


class TestGetCandidates:
    """Tests for _get_candidates."""

    def test_classification_returns_all_families(self) -> None:
        engine = AutoMLEngine(pipeline=None, search=None)
        candidates = engine._get_candidates(AutoMLConfig(task_type="classification"))
        # sklearn baseline (3) + xgboost + lightgbm = 5
        assert len(candidates) == 5
        classes = [c[0] for c in candidates]
        assert any("RandomForest" in c for c in classes)
        assert any("xgboost" in c for c in classes)
        assert any("lightgbm" in c for c in classes)

    def test_regression_returns_all_families(self) -> None:
        engine = AutoMLEngine(pipeline=None, search=None)
        candidates = engine._get_candidates(AutoMLConfig(task_type="regression"))
        assert len(candidates) == 5
        classes = [c[0] for c in candidates]
        assert any("Ridge" in c for c in classes)
        assert any("xgboost" in c for c in classes)
        assert any("lightgbm" in c for c in classes)

    def test_unknown_task_type_raises(self) -> None:
        engine = AutoMLEngine(pipeline=None, search=None)
        with pytest.raises(ValueError, match="Unknown task type"):
            engine._get_candidates(AutoMLConfig(task_type="clustering"))


# ---------------------------------------------------------------------------
# Default search space
# ---------------------------------------------------------------------------


class TestDefaultSearchSpace:
    """Tests for _default_search_space."""

    def test_random_forest_search_space(self) -> None:
        engine = AutoMLEngine(pipeline=None, search=None)
        space = engine._default_search_space(
            "sklearn.ensemble.RandomForestClassifier", "sklearn"
        )
        param_names = {p.name for p in space.params}
        assert "n_estimators" in param_names
        assert "max_depth" in param_names

    def test_gradient_boosting_search_space_includes_learning_rate(self) -> None:
        engine = AutoMLEngine(pipeline=None, search=None)
        space = engine._default_search_space(
            "sklearn.ensemble.GradientBoostingClassifier", "sklearn"
        )
        param_names = {p.name for p in space.params}
        assert "learning_rate" in param_names

    def test_logistic_regression_search_space(self) -> None:
        engine = AutoMLEngine(pipeline=None, search=None)
        space = engine._default_search_space(
            "sklearn.linear_model.LogisticRegression", "sklearn"
        )
        param_names = {p.name for p in space.params}
        assert "C" in param_names

    def test_unknown_model_gets_fallback_space(self) -> None:
        engine = AutoMLEngine(pipeline=None, search=None)
        space = engine._default_search_space("sklearn.svm.SVC", "sklearn")
        # Fallback should still produce a valid SearchSpace
        assert len(space.params) >= 1
